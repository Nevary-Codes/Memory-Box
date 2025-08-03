from pymongo import MongoClient
from pymongo.server_api import ServerApi
import bcrypt
import os
from dotenv import load_dotenv

load_dotenv()

uri = os.getenv("MONGO_URI")
client = MongoClient(uri, server_api=ServerApi('1'))
db = client["MemoryBox"]
customers = db["Admins"]

def addAdmin(email, password):

    user = {
        "email": email,
        "password": bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
    }

    result = customers.insert_one(user)
    user["_id"] = result.inserted_id
    return user


addAdmin("aryanmanchanda@hotmail.com", "123456")