import json
from bson import json_util
from backend.database import get_db
import os

def backup():
    db = get_db()
    backup_dir = "database_backup"
    os.makedirs(backup_dir, exist_ok=True)
    
    # List of collections to backup
    collections = db.list_collection_names()
    print(f"Starting database backup to '{backup_dir}'...")
    
    for coll_name in collections:
        if coll_name.startswith("system."):
            continue
        coll = db[coll_name]
        cursor = coll.find({})
        docs = list(cursor)
        
        file_path = os.path.join(backup_dir, f"{coll_name}.json")
        with open(file_path, "w", encoding="utf-8") as f:
            # Use bson.json_util to preserve MongoDB types (like ObjectIds and Datetimes)
            f.write(json_util.dumps(docs, indent=2))
        print(f"Backed up collection '{coll_name}' ({len(docs)} documents) -> {file_path}")
        
    print("Database backup completed successfully!")

if __name__ == "__main__":
    backup()
