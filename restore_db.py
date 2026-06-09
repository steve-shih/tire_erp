import os
from bson import json_util
from backend.database import get_db

def restore():
    db = get_db()
    backup_dir = "database_backup"
    
    if not os.path.exists(backup_dir):
        print(f"Error: Backup directory '{backup_dir}' not found!")
        return
        
    print(f"Starting database restore from '{backup_dir}'...")
    
    for filename in os.listdir(backup_dir):
        if filename.endswith(".json"):
            coll_name = filename[:-5]
            file_path = os.path.join(backup_dir, filename)
            
            with open(file_path, "r", encoding="utf-8") as f:
                docs = json_util.loads(f.read())
                
            if docs:
                coll = db[coll_name]
                # Drop existing collection to prevent duplicates
                coll.drop()
                coll.insert_many(docs)
                print(f"Restored collection '{coll_name}' ({len(docs)} documents)")
            else:
                print(f"Collection '{coll_name}' is empty, skipped")
                
    print("Database restore completed successfully!")

if __name__ == "__main__":
    restore()
