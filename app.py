from collections import defaultdict
import cloudinary
import cloudinary.uploader
from cloudinary.utils import cloudinary_url
from flask import Flask, Response, render_template, redirect, url_for, request, jsonify, flash, session
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
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



load_dotenv()

app = Flask(__name__)
app.config["SECRET_KEY"] = "memorybox"

app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = 'aryanmanchan@gmail.com'
app.config['MAIL_PASSWORD'] = 'wrkg emyi gumg putl'  # Use App Password for Gmail

mail = Mail(app)

login_manager = LoginManager(app)
login_manager.init_app(app)
bcrypt = Bcrypt(app)

cloudinary.config( 
    cloud_name = os.environ.get("CLOUDINARY_NAME"),
    api_key = os.environ.get("CLOUDINARY_API_KEY"), 
    api_secret = os.environ.get("CLOUDINARY_SECRET"), # Click 'View API Keys' above to copy your API secret
    secure=True
)


uri = os.getenv("MONGO_URI")
client = MongoClient(uri, server_api=ServerApi("1"))
db = client["MemoryBox"]


class Admin(UserMixin):
    def __init__(self, admin_dict):
        self.id = str(admin_dict["_id"])
        self.email = admin_dict["email"]

@login_manager.user_loader
def load_user(user_id):
    admins = db["Admins"]
    admin = admins.find_one({"_id": ObjectId(user_id)})
    if admin:
        return Admin(admin)
    return None

def is_valid_objectid(oid):
    try:
        ObjectId(oid)
        return True
    except (InvalidId, TypeError):
        return False


@app.route("/")
def home():
    # Fetch latest 3 events from the Photos (or Events) collection
    latest_events = list(
        db.Events.find().sort("_id", -1)
    )

    return render_template("index.html", latest_events=latest_events)


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("username")
        password = request.form.get("password")

        admin = db.Admins.find_one({"email": email})
        if admin and bc.checkpw(password.encode("utf-8"), admin["password"]):
            user = Admin(admin)
            login_user(user)
            return redirect(url_for("admin"))
        else:
            return redirect(url_for("login"))

    return render_template("login.html")


@app.route("/events")
def events():
    events = list(db["Events"].find())
    return render_template("events.html", events=events)


@app.route("/events/<event_id>")
def event(event_id):
    event_doc = db["Events"].find_one({"_id": ObjectId(event_id)})
    photos_data = list(db["Photos"].find({"event": event_id}))
    year = event_doc["year"] if event_doc else ""
    event_name = event_doc["event_name"] if event_doc else ""

    combined_photos = []
    for p in photos_data:
        combined_photos.append({
            "_id": p["_id"],
            "photo": get_watermarked_url(p["photo"]),  # 🔹 Watermarked URL
            "event": p["event"],
            "photo_name": p["photo_name"],
            "year": event_doc["year"] if event_doc else None
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

    # ✅ Filter only valid ObjectIds
    object_ids = [ObjectId(pid) for pid in cart_ids if is_valid_objectid(pid)]

    cart_products = list(db.Photos.find({"_id": {"$in": object_ids}}))

    total_price = 0

    for i in cart_products:
        # ✅ Fetch event document for each photo
        event_doc = db.Events.find_one({"_id": ObjectId(i["event"])})
        if event_doc:
            i["event"] = event_doc.get("event_name", "Unknown Event")

        # ✅ Add watermark to photo
        i["photo"] = get_watermarked_url(i["photo"])

        # ✅ Add to total price (convert price to float/int safely)
        try:
            total_price += float(i.get("price", 0))
        except ValueError:
            pass  # Ignore if price is invalid

    print(cart_products)

    return render_template(
        "cart.html",
        cart_products=cart_products,
        total_price=total_price,  # ✅ Pass total price to template
        isEmpty=len(cart_products) == 0,
        cart_items=len(cart_products)
    )


@app.route("/billing", methods=["GET", "POST"])
def billing():
    cart_ids = session.get("cart", [])

    # ✅ Filter only valid ObjectIds
    object_ids = [ObjectId(pid) for pid in cart_ids if is_valid_objectid(pid)]

    cart_products = list(db.Photos.find({"_id": {"$in": object_ids}}))

    total_price = 0

    for i in cart_products:
        # ✅ Fetch event document for each photo
        event_doc = db.Events.find_one({"_id": ObjectId(i["event"])})
        if event_doc:
            i["event"] = event_doc.get("event_name", "Unknown Event")
            i["year"] = event_doc.get("year")

        # ✅ Add watermark to photo
        i["photo"] = get_watermarked_url(i["photo"])

        # ✅ Add to total price (convert price to float/int safely)
        try:
            total_price += float(i.get("price", 0))
        except ValueError:
            pass  # Ignore if price is invalid

    return render_template("billing.html", cart_products=cart_products, total_price=total_price)


@app.route("/admin")
@login_required
def admin():
    events = len(list(db["Events"].find()))
    photos = len(list(db["Photos"].find()))
    orders = len(list(db["Orders"].find()))
    pending = len(list(db["Orders"].find({"confirmed": False})))
    return render_template("admin.html", events=events, photos=photos, orders=orders, pending=pending)


@app.route("/admin-events")
@login_required
def admin_events():
    events = list(db["Events"].find())
    return render_template("admin-events.html", events=events)


@app.route("/orders")
@login_required
def orders():
    orders_cursor = db.Orders.find({"confirmed": False})
    orders = []

    for order in orders_cursor:
        cart_ids = order.get("cart", [])
        product_objects = []
        total_price = 0  # Initialize total price for each order

        if cart_ids:
            object_ids = [ObjectId(pid) for pid in cart_ids if is_valid_objectid(pid)]
            product_cursor = db.Photos.find({"_id": {"$in": object_ids}})
            product_objects = list(product_cursor)

            # Calculate total price
            for product in product_objects:
                price = product.get("price", 0)
                try:
                    price = float(price)
                except (ValueError, TypeError):
                    price = 0
                total_price += price

        order["products"] = product_objects
        order["total_price"] = total_price  # Add total price to order
        orders.append(order)

    return render_template("orders.html", orders=orders)


@app.route("/<event>/photos")
@login_required
def photos(event):
    event_doc = db["Events"].find_one({"_id": ObjectId(event)})
    photos_data = list(db["Photos"].find({"event": event}))
    year = event_doc["year"] if event_doc else ""
    event_name = event_doc["event_name"]

    combined_photos = []
    for p in photos_data:
        combined_photos.append({
            "photo": p["photo"],  # ObjectId of the image
            "event": p["event"],  # event name
            "photo_name": p["photo_name"],
            "year": event_doc["year"] if event_doc else None
        })


    return render_template(
        "photos.html",
        name=event_name,
        photos=combined_photos,
        year=year
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

    event = {
        "event_name": event_name,
        "day": day,
        "month": month,
        "year": year,
        "photo": image_url
    }

    db["Events"].insert_one(event)
    return redirect(url_for("admin_events"))


@app.route("/image/<file_id>")
def get_image(file_id):
    event = db["Events"].find_one({"_id": ObjectId(file_id)})
    if not event or not event.get("photo"):
        return "No image found", 404

    return Response(event["photo"], mimetype=event.get("photo_mime", "image/png"))


@app.route("/remove_event/<event_id>", methods=["GET", "POST"])
@login_required
def remove_event(event_id):
    removeEvent(event_id)

    return redirect(url_for("admin_events"))


@app.route("/<event>/photos/add_photo", methods=["GET", "POST"])
@login_required
def add_photo(event):
    photo_name = request.form.get("photo_name")
    price = request.form.get("price")
    photo = request.files.get("photo")
    upload_result = cloudinary.uploader.upload(photo)
    image_url = upload_result['secure_url']
    

    event_doc = {
        "photo_name": photo_name,
        "event": event,
        "price": price,
        "photo": image_url,
    }

    db["Photos"].insert_one(event_doc)
    return redirect(url_for("photos", event=event))


@app.route("/events/<event>/photo/<photo>")
def photo(event, photo):
    event_doc = db["Events"].find_one({"_id": ObjectId(event)})
    photos_data = list(db["Photos"].find({"_id": ObjectId(photo)}))
    year = event_doc["year"] if event_doc else ""
    event_name = event_doc["event_name"] if event_doc else ""

    combined_photos = []
    for p in photos_data:
        combined_photos.append({
            "pid": p["_id"],
            "photo": get_watermarked_url(p["photo"]),  # 🔹 Watermarked URL
            "event": p["event"],
            "photo_name": p["photo_name"],
            "year": event_doc["year"] if event_doc else None,
            "price": p["price"]
        })


    return render_template("photo.html", year=year, photos=combined_photos, event_name=event_name)


@app.route("/add_to_cart")
def add_to_cart():
    pid = request.args.get("pid")
    print(pid)
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

    details = {
        "name": name,
        "email": email,
        "phone": phone,
        "cart": cart,
        "confirmed": False
    }

    db["Orders"].insert_one(details)

    return redirect(url_for('home'))

@app.route("/reject_order")
@login_required
def reject_order():
    oid = request.args.get("oid")
    db.Orders.delete_one({"_id": ObjectId(oid)})

    return redirect(url_for('orders'))


@app.route("/accept_order")
@login_required
def accept_order():
    oid = request.args.get("oid")

    order = db.Orders.find_one({"_id": ObjectId(oid)})

    db.Orders.update_one({"_id": ObjectId(oid)},
                {"$set": {"confirmed": True}})
    
    cart_ids = order.get("cart", [])
    product_objects = []
    if cart_ids:
        object_ids = [ObjectId(pid) for pid in cart_ids if is_valid_objectid(pid)]
        product_cursor = db.Photos.find({"_id": {"$in": object_ids}})
        product_objects = list(product_cursor)

    # ✅ Create ZIP file in memory
    zip_buffer = BytesIO()
    with zipfile.ZipFile(zip_buffer, "w") as zip_file:
        for idx, product in enumerate(product_objects):
            image_url = product.get("photo")
            if not image_url:
                continue
            try:
                response = requests.get(image_url)
                if response.status_code == 200:
                    # Save with a readable name
                    zip_file.writestr(f"{product.get('title', f'image_{idx+1}')}.jpg", response.content)
            except:
                pass

    zip_buffer.seek(0)

    # ✅ Build Email Body
    email_html = render_template_string("""
        <html>
        <body>
            <h2>Hello {{ name }},</h2>
            <p>Your order <strong>#{{ oid }}</strong> has been confirmed! 🎉</p>
            <p>We have attached your purchased photos as a downloadable ZIP file.</p>
            <p>Thank you for shopping with Memory Box ❤️</p>
        </body>
        </html>
    """, name=order.get("name", "Customer"), oid=oid)

    # ✅ Send Email with ZIP attachment
    customer_email = order.get("email")
    if customer_email:
        msg = Message(
            subject="🎉 Your Memory Box Order Has Been Confirmed!",
            sender=app.config['MAIL_USERNAME'],
            recipients=[customer_email]
        )
        msg.html = email_html
        msg.attach(f"MemoryBox_Order_{oid}.zip", "application/zip", zip_buffer.read())
        mail.send(msg)


    return redirect(url_for('orders'))

@app.route("/logout")
def logout():
    logout_user()
    return redirect(url_for("home"))

if __name__ == "__main__":
    with app.app_context():
        app.run(port=5000, debug=True)