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
from test import addEvent, removeEvent
from bson.errors import InvalidId
import os
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.config["SECRET_KEY"] = "memorybox"

cloudinary.config( 
    cloud_name = os.environ.get("CLOUDINARY_NAME"),
    api_key = os.environ.get("CLOUDINARY_API_KEY"), 
    api_secret = os.environ.get("CLOUDINARY_SECRET"), # Click 'View API Keys' above to copy your API secret
    secure=True
)


uri = os.getenv("MONGO_URI")
client = MongoClient(uri, server_api=ServerApi("1"))
db = client["MemoryBox"]


@app.route("/")
def home():
    return render_template("index.html")


@app.route("/events")
def events():
    return render_template("events.html")


@app.route("/event")
def event():
    return render_template("event.html")


@app.route("/cart")
def cart():
    return render_template("cart.html")


@app.route("/billing")
def billing():
    return render_template("billing.html")


@app.route("/admin")
def admin():
    events = len(list(db["Events"].find()))
    photos = len(list(db["Photos"].find()))
    return render_template("admin.html", events=events, photos=photos)


@app.route("/admin-events")
def admin_events():
    events = list(db["Events"].find())
    return render_template("admin-events.html", events=events)


@app.route("/orders")
def orders():
    return render_template("orders.html")


@app.route("/<event>/photos")
def photos(event):
    event_doc = db["Events"].find_one({"event_name": event})
    photos_data = list(db["Photos"].find({"event": event}))
    year = event_doc["year"] if event_doc else None

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
        name=event,
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
def admin_event():
    return render_template("admin-event.html")


@app.route("/<event>/photos/admin-photo", methods=["GET", "POST"])
def admin_photo(event):

    return render_template("admin-photo.html", event=event)


@app.route("/add_event", methods=["GET", "POST"])
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
def remove_event(event_id):
    removeEvent(event_id)

    return redirect(url_for("admin_events"))


@app.route("/<event>/photos/add_photo", methods=["GET", "POST"])
def add_photo(event):
    photo_name = request.form.get("photo_name")
    price = request.form.get("price")
    photo = request.files.get("photo")

    upload_result = cloudinary.uploader.upload(photo)
    image_url = upload_result['secure_url']

    event = {
        "photo_name": photo_name,
        "event": event,
        "price": price,
        "photo": image_url,
    }

    db["Photos"].insert_one(event)
    return redirect(url_for("photos", event=event["event"]))





if __name__ == "__main__":
    with app.app_context():
        app.run(port=5000, debug=True)