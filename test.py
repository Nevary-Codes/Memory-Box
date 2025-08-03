import os
from bson import ObjectId
from pymongo import MongoClient
from pymongo.server_api import ServerApi


from dotenv import load_dotenv

load_dotenv()

client = MongoClient(os.getenv("MONGO_URI"), server_api=ServerApi("1"))
db = client["MemoryBox"]

try:
    client.server_info()  # Forces a call to the server
    print("✅ Connected to MongoDB!")
except Exception as e:
    print("❌ Connection failed:", e)

def addEvent(event):
    
    events = db["Events"]
    _id = events.insert_one(event)
    return _id

def removeEvent(event_id):
    events = db["Events"]
    events.delete_one({"_id": ObjectId(event_id)})



from cloudinary.utils import cloudinary_url

def get_watermarked_url(image_url):
    from urllib.parse import quote
    watermark_text = "MemoryBox"
    encoded_text = quote(watermark_text)

    transformation = (
        "l_text:Arial_80_bold:" + encoded_text +  # Bigger & Bold font
        ",co_rgb:FFFFFF,"  # White color
        "g_center,"        # Center position
        "o_50"             # 50% opacity (more visible than 30)
    )

    return image_url.replace("/upload/", f"/upload/{transformation}/")