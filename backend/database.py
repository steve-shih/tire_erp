import os
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv()

# Fetch connection URI from environment, default to local MongoDB
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")

client = MongoClient(MONGO_URI)
db = client["tire_erp"]

def get_db():
    return db
