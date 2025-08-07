from collections import defaultdict
import cloudinary
import cloudinary.uploader
from cloudinary.utils import cloudinary_url
from flask import Flask, Response, json, render_template, redirect, url_for, request, jsonify, flash, session
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import check_password_hash
from flask_bcrypt import Bcrypt
import bcrypt as bc
from bson import ObjectId
from pymongo import MongoClient
from pymongo.server_api import ServerApi
import random
from test import addEvent, get_watermarked_url, removeEvent
from bson.errors import InvalidId
import os
from dotenv import load_dotenv
from flask_mail import Mail, Message
import os
import requests
import zipfile
from io import BytesIO
from flask import render_template_string, send_file

def extract_public_id(url):
    """
    Extract the public_id from a Cloudinary URL.
    Assumes URL structure like:
    https://res.cloudinary.com/<cloud_name>/image/upload/v<version>/<public_id>.<ext>
    """
    try:
        parts = url.split("/")
        filename = parts[-1]  # <public_id>.<ext>
        public_id = filename.rsplit(".", 1)[0]  # Remove file extension
        return "/".join(parts[parts.index("upload") + 1:-1]) + "/" + public_id if "/" in url else public_id
    except Exception as e:
        print(f"Failed to extract public_id from URL: {url}, error: {e}")
        return None


load_dotenv()

app = Flask(__name__)
app.config["SECRET_KEY"] = "memorybox"

app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = 'aryanmanchan@gmail.com'
app.config['MAIL_PASSWORD'] = 'wrkg emyi gumg putl'  

mail = Mail(app)

login_manager = LoginManager(app)
login_manager.init_app(app)
bcrypt = Bcrypt(app)

cloudinary.config( 
    cloud_name = os.environ.get("CLOUDINARY_NAME"),
    api_key = os.environ.get("CLOUDINARY_API_KEY"), 
    api_secret = os.environ.get("CLOUDINARY_SECRET"), 
    secure=True
)

app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv("DATABASE_URL")
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)


class Admin(UserMixin, db.Model):
    __tablename__ = 'admins'
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.LargeBinary(60), nullable=False)

class Events(db.Model):
    __tablename__ = "events"
    id = db.Column(db.Integer, primary_key=True)
    event_name = db.Column(db.String(255), nullable=False)
    day = db.Column(db.Integer, nullable=False)
    month = db.Column(db.String(100), nullable=False)
    year = db.Column(db.Integer, nullable=False)
    photo = db.Column(db.String(500), nullable=False)
    photos = db.relationship("Photos", backref="event", cascade="all, delete", passive_deletes=True)

class Orders(db.Model):
    __tablename__ = "orders"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    email = db.Column(db.String(150), nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    cart = db.Column(db.JSON)
    confirmed = db.Column(db.Boolean, default=False, nullable=False)

class Photos(db.Model):
    __tablename__ = "photos"
    id = db.Column(db.Integer, primary_key=True)
    photo_name = db.Column(db.String(255), nullable=False)
    event_id = db.Column(db.Integer, db.ForeignKey("events.id", ondelete="CASCADE"), nullable=False)
    price = db.Column(db.Integer, nullable=False)
    photo = db.Column(db.String(500), nullable=False)

@login_manager.user_loader
def load_user(user_id):
    admin = Admin.query.get(user_id)
    if admin:
        return admin

def is_valid_objectid(oid):
    try:
        ObjectId(oid)
        return True
    except (InvalidId, TypeError):
        return False


@app.route("/")
def home():
    
    latest_events = Events.query.order_by(Events.id.desc()).limit(5).all()

    return render_template("index.html", latest_events=latest_events)


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("username")
        password = request.form.get("password")

        admin = Admin.query.filter_by(email=email).first()
        if admin and bc.checkpw(password.encode("utf-8"), admin.password):
            login_user(admin)
            return redirect(url_for("admin"))
        else:
            flash("Invalid credentials")
            return redirect(url_for("login"))

    return render_template("login.html")


@app.route("/events")
def events():
    events = list(Events.query.all())
    return render_template("events.html", events=events)


@app.route("/events/<event_id>")
def event(event_id):
    event_doc = Events.query.get(event_id)
    photos_data = Photos.query.filter_by(event_id=event_id).all()
    year = event_doc.year if event_doc else ""
    event_name = event_doc.event_name if event_doc else ""

    combined_photos = []
    for p in photos_data:
        combined_photos.append({
            "_id": p.id,
            "photo": get_watermarked_url(p.photo),
            "event": p.event,
            "photo_name": p.photo_name,
            "year": event_doc.year if event_doc else None
        })

    return render_template(
        "event.html",
        name=event_id,
        photos=combined_photos,
        year=year,
        event_name=event_name
    )
    


@app.route("/cart")
def cart():
    cart_ids = session.get("cart", [])
    object_ids = [pid for pid in cart_ids]

    cart_products = Photos.query.filter(Photos.id.in_(object_ids)).all()

    total_price = 0

    for i in cart_products:
        # Attach event name
        event_doc = Events.query.get(i.event_id)
        i.event_name = event_doc.event_name if event_doc else "Unknown Event"

        # Watermark photo URL
        i.photo = get_watermarked_url(i.photo)

        try:
            total_price += float(i.price)
        except ValueError:
            pass

    return render_template(
        "cart.html",
        cart_products=cart_products,
        total_price=total_price,
        isEmpty=len(cart_products) == 0,
        cart_items=len(cart_products)
    )


@app.route("/billing", methods=["GET", "POST"])
def billing():
    cart_ids = session.get("cart", [])
    object_ids = [pid for pid in cart_ids]

    cart_products = Photos.query.filter(Photos.id.in_(object_ids)).all()

    total_price = 0

    for i in cart_products:
        
        event_doc = Events.query.get(i.event_id)
        if event_doc:
            i.event_name = event_doc.event_name
            i.year = event_doc.year

        
        i.photo = get_watermarked_url(i.photo)

        
        try:
            total_price += float(i.price)
        except ValueError:
            pass  

    return render_template("billing.html", cart_products=cart_products, total_price=total_price)


@app.route("/admin")
@login_required
def admin():
    events = len(list(Events.query.all()))
    photos = len(list(Photos.query.all()))
    orders = len(list(Orders.query.all()))
    pending = len(list(Orders.query.filter_by(confirmed=False)))
    return render_template("admin.html", events=events, photos=photos, orders=orders, pending=pending)


@app.route("/admin-events")
@login_required
def admin_events():
    events = list(Events.query.all())
    return render_template("admin-events.html", events=events)


@app.route("/orders")
@login_required
def orders():
    orders_query = Orders.query.filter_by(confirmed=False).all()
    orders = []

    for order in orders_query:
        cart_ids = order.cart if order.cart else []  # assuming cart is a list of photo IDs
        product_objects = []
        total_price = 0

        if cart_ids:
            product_objects = Photos.query.filter(Photos.id.in_(cart_ids)).all()
            for product in product_objects:
                try:
                    total_price += float(product.price)
                except (ValueError, TypeError):
                    total_price += 0

        orders.append({
            "id": order.id,
            "products": product_objects,
            "total_price": total_price,
            "name": order.name
        })


    return render_template("orders.html", orders=orders)


@app.route("/<event>/photos")
@login_required
def photos(event):
    event_doc = Events.query.get(event)
    photos_data = list(Photos.query.filter_by(event_id=event).all())
    year = event_doc.year if event_doc else ""
    event_name = event_doc.event_name


    combined_photos = []
    for p in photos_data:
        combined_photos.append({
            "photo": p.photo,  
            "event": p.event_id,  
            "photo_name": p.photo_name,
            "year": event_doc.year if event_doc else None
        })


    return render_template(
        "photos.html",
        name=event_name,
        photos=combined_photos,
        year=year,
        event=event
    )


@app.route("/contact-us")
def contact():
    return render_template("contact.html")


@app.route("/about-us")
def about():
    return render_template("about.html")


@app.route("/admin-event", methods=["GET", "POST"])
@login_required
def admin_event():
    return render_template("admin-event.html")


@app.route("/<event>/photos/admin-photo", methods=["GET", "POST"])
@login_required
def admin_photo(event):
    return render_template("admin-photo.html", event=event)


@app.route("/add_event", methods=["GET", "POST"])
@login_required
def add_event():
    event_name = request.form.get("event_name")
    day = request.form.get("day")
    month = request.form.get("month")
    year = request.form.get("year")
    photo = request.files.get("photo")

    upload_result = cloudinary.uploader.upload(photo)
    image_url = upload_result['secure_url']

    event = Events(event_name=event_name, day=day, month=month, year=year, photo=image_url)
    db.session.add(event)
    db.session.commit()

    return redirect(url_for("admin_events"))


@app.route("/image/<file_id>")
def get_image(file_id):
    event = db["Events"].find_one({"_id": ObjectId(file_id)})
    if not event or not event.get("photo"):
        return "No image found", 404

    return Response(event["photo"], mimetype=event.get("photo_mime", "image/png"))



@app.route("/remove_event/<int:event_id>", methods=["GET", "POST"])
@login_required
def remove_event(event_id):
    event = Events.query.get(event_id)
    if not event:
        flash("Event not found.", "error")
        return redirect(url_for("admin_events"))

    # Delete associated photos (Cloudinary + DB)
    photos = Photos.query.filter_by(event_id=event_id).all()

    for photo in photos:
        public_id = extract_public_id(photo.photo)
        if public_id:
            try:
                cloudinary.uploader.destroy(public_id)
            except Exception as e:
                print(f"Error deleting {public_id} from Cloudinary:", e)

        db.session.delete(photo)

    db.session.delete(event)  # now safe to delete the event
    db.session.commit()

    flash("Event and photos deleted.", "success")
    return redirect(url_for("admin_events"))


@app.route("/<event>/photos/add_photo", methods=["GET", "POST"])
@login_required
def add_photo(event):
    photo_name = request.form.get("photo_name")
    price = request.form.get("price")
    photos = request.files.getlist("photo")

    for photo in photos:
        if photo:
            upload_result = cloudinary.uploader.upload(photo)
            image_url = upload_result['secure_url']

            photos = Photos(photo_name=photo_name, event_id=event, price=price, photo=image_url)
            db.session.add(photos)
            db.session.commit()


    return redirect(url_for("photos", event=event))


@app.route("/events/<event>/photo/<photo>")
def photo(event, photo):
    event_doc = Events.query.get(event)
    photos_data = Photos.query.get(photo)
    year = event_doc.year if event_doc else ""
    event_name = event_doc.event_name

    p = photos_data
    combined_photos = []
    
    combined_photos.append({
            "pid": p.id,
            "photo": get_watermarked_url(p.photo),  
            "event": p.event,
            "photo_name": p.photo_name,
            "year": event_doc.year if event_doc else None,
            "price": p.price
        })
        
    

    return render_template("photo.html", year=year, photos=combined_photos, event_name=event_name)


@app.route("/add_to_cart")
def add_to_cart():
    pid = request.args.get("pid")
    if not pid:
        return redirect(url_for("home"))

    if "cart" not in session:
            session["cart"] = []

    if pid not in session["cart"]:
        session["cart"].append(pid)
        session.modified = True

    return redirect(url_for('cart'))

@app.route("/remove_from_cart")
def remove_from_cart():
    pid = request.args.get("pid")
    if not pid:
        return redirect(url_for("checkout"))

    else:
        if "cart" in session and pid in session["cart"]:
            session["cart"].remove(pid)
            session.modified = True

    return redirect(url_for("cart"))
    

@app.route("/add_order", methods=["GET", "POST"])
def add_order():
    name = request.form.get("name")
    email = request.form.get("email")
    phone = request.form.get("phone")
    cart = session.get("cart")

    order = Orders(name=name, email=email, phone=phone, cart=cart, confirmed=False)

    # details = {
    #     "name": name,
    #     "email": email,
    #     "phone": phone,
    #     "cart": cart,
    #     "confirmed": False
    # }


    db.session.add(order)
    db.session.commit()

    oid = order.id

    session["cart"] = []
    session.modified = True  


    return redirect(url_for("confirmed", oid=str(oid)))

@app.route("/reject_order")
@login_required
def reject_order():
    oid = request.args.get("oid")
    order = Orders.query.get(oid)
    if order:
        db.session.delete(order)
        db.session.commit()

    return redirect(url_for('orders'))


@app.route("/accept_order")
@login_required
def accept_order():
    oid = request.args.get("oid")
    
    order = Orders.query.get(oid)
    if not order:
        flash("Order not found.")
        return redirect(url_for("orders"))

    # Mark order as confirmed
    order.confirmed = True
    db.session.commit()

    # Fetch cart product IDs (assuming JSON-encoded list)
    cart_ids = order.cart or []
    product_objects = []
    if cart_ids:
        product_objects = Photos.query.filter(Photos.id.in_(cart_ids)).all()

    # Create ZIP of photos
    # zip_buffer = BytesIO()
    # with zipfile.ZipFile(zip_buffer, "w") as zip_file:
    #     for idx, product in enumerate(product_objects):
    #         image_url = product.photo
    #         if not image_url:
    #             continue
    #         try:
    #             response = requests.get(image_url)
    #             if response.status_code == 200:
    #                 title = product.title or f'image_{idx+1}'
    #                 zip_file.writestr(f"{title}.jpg", response.content)
    #                 print(title)
    #         except:
    #             pass

    # zip_buffer.seek(0)
    # Create ZIP of photos
    zip_buffer = BytesIO()
    with zipfile.ZipFile(zip_buffer, "w") as zip_file:
        for idx, product in enumerate(product_objects):
            image_url = product.photo
            if not image_url:
                continue
            try:
                response = requests.get(image_url)
                if response.status_code == 200:
                    # Ensure safe file name
                    title = (product.photo_name or f"photo_{product.id}").replace("/", "_").replace("\\", "_")
                    zip_file.writestr(f"{title}.jpg", response.content)
                    print(f"✅ Added {title}.jpg to ZIP")
                else:
                    print(f"❌ Failed to fetch {image_url}: Status {response.status_code}")
            except Exception as e:
                print(f"⚠️ Error downloading {image_url}: {e}")

    zip_buffer.seek(0)

    # Prepare email
    email_html = render_template_string("""
        <html>
        <body>
            <h2>Hello {{ name }},</h2>
            <p>Your order <strong>#{{ oid }}</strong> has been accepted!</p>
            <p>We have attached your purchased photos as a downloadable ZIP file.</p>
            <p>Thank you for shopping with Memory Box ❤️</p>
        </body>
        </html>
    """, name=order.name or "Customer", oid=oid)

    if order.email:
        msg = Message(
            subject="🎉 Your Memory Box Order Has Been Confirmed!",
            sender=app.config['MAIL_USERNAME'],
            recipients=[order.email]
        )
        msg.html = email_html
        msg.attach(f"MemoryBox_Order_{oid}.zip", "application/zip", zip_buffer.read())
        mail.send(msg)

    return redirect(url_for('orders'))

@app.route("/logout")
def logout():
    logout_user()
    return redirect(url_for("home"))

@app.route("/confirmed")
def confirmed():
    oid = request.args.get("oid")

    return render_template("confirmed.html", oid=oid)

@app.route("/summary")
@login_required
def summary():
    oid = request.args.get("oid")

    # Fetch order using SQLAlchemy
    order = Orders.query.get(oid)
    if not order:
        flash("Order not found.")
        return redirect(url_for("orders"))

    # Decode cart (stored as JSON string in SQL DB)
    try:
        cart_ids = order.cart if order.cart else []
    except json.JSONDecodeError:
        cart_ids = []

    product_objects = []
    if cart_ids:
        product_objects = Photos.query.filter(Photos.id.in_(cart_ids)).all()

    return render_template("summary.html", order=order, products=product_objects)

@app.route("/add_admin")
def add_admin():
    username = "aryanmanchanda@hotmail.com"
    password = "123456"
    hashed_password = bc.hashpw(password.encode(), bc.gensalt())
    admin = Admin(email=username, password=hashed_password)
    db.session.add(admin)
    db.session.commit()

    return redirect(url_for('home'))


if __name__ == "__main__":
    with app.app_context():
        db.create_all()
        app.run(debug=True)