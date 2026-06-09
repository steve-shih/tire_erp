import os
from pymongo import MongoClient

# Fetch connection URI from environment, default to local MongoDB
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")

client = MongoClient(MONGO_URI)
db = client["tire_erp"]

def get_db():
    return db
