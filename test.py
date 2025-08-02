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

removeEvent("688da50258543b1f63276db9")