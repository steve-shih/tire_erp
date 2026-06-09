import os
import pandas as pd
from datetime import datetime
from pymongo import MongoClient
from backend.auth import get_password_hash

# Connection URI
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
client = MongoClient(MONGO_URI)
db = client["tire_erp"]

def clean_value(val):
    if pd.isnull(val):
        return None
    val_str = str(val).strip()
    if val_str in ["0", "0.0", "False", "None", "(空白)"]:
        return None
    return val_str

def migrate_users():
    print("Migrating default users...")
    # Seed default users if they don't exist
    if db["users"].count_documents({}) == 0:
        default_users = [
            {"username": "admin", "password": "admin123", "role": "owner"},
            {"username": "manager", "password": "manager123", "role": "manager"},
            {"username": "staff", "password": "staff123", "role": "staff"}
        ]
        for u in default_users:
            db["users"].insert_one({
                "username": u["username"],
                "hashed_password": get_password_hash(u["password"]),
                "role": u["role"],
                "is_active": True,
                "created_by": "system_migration",
                "created_at": datetime.utcnow(),
                "is_deleted": False
            })
        print(f"Seeded {len(default_users)} default users.")
    else:
        print("Users already exist, skipping seeding.")

def migrate_customers(file_path, department):
    print(f"Migrating customers from {file_path} ({department})...")
    try:
        # Load without headers to identify rows manually
        df = pd.read_excel(file_path, sheet_name="客戶", header=None)
        
        # Row 4 is the header row
        headers = df.iloc[4].tolist()
        
        # Find columns indexes
        id_idx = 6  # 客戶編號
        name_idx = 9  # 客戶(公司)名稱
        uni_idx = 13  # 統一編號
        phone_idx = 16  # 連絡電話 1
        car_idx = 17  # 大車編號
        addr_idx = 28  # 戶籍(公司)地址 (輸入縣市全址)
        cat_idx = 8  # 簡稱(姓名) or category (A/B/C)
        
        count = 0
        # Data rows start from row 5
        for idx in range(5, len(df)):
            row = df.iloc[idx]
            cust_id = clean_value(row[id_idx])
            name = clean_value(row[name_idx])
            
            if not cust_id or not name:
                continue
                
            # Clean up names containing '>'
            if "＞" in name:
                name = name.split("＞")[0].strip()
            if ">" in name:
                name = name.split(">")[0].strip()
                
            # Construct vehicles list
            vehicles = []
            car_id = clean_value(row[car_idx])
            if car_id and car_id != "0":
                vehicles.append({"plate_number": car_id, "vehicle_type": "大車"})
                
            # Check if customer already exists in DB
            existing = db["customers"].find_one({"customer_id": cust_id, "is_deleted": False})
            if existing:
                # Append vehicle if new
                existing_plates = [v["plate_number"] for v in existing.get("vehicles", [])]
                if car_id and car_id not in existing_plates:
                    db["customers"].update_one(
                        {"_id": existing["_id"]},
                        {"$push": {"vehicles": {"plate_number": car_id, "vehicle_type": "大車"}}}
                    )
                continue
                
            cust_doc = {
                "customer_id": cust_id,
                "name": name,
                "uniform_number": clean_value(row[uni_idx]) if clean_value(row[uni_idx]) != "未稅" else None,
                "phone": clean_value(row[phone_idx]),
                "address": clean_value(row[addr_idx]),
                "category": "B",  # Default category
                "vehicles": vehicles,
                "department": department,
                "created_by": "system_migration",
                "created_at": datetime.utcnow(),
                "is_deleted": False
            }
            db["customers"].insert_one(cust_doc)
            count += 1
            
        print(f"Migrated {count} new customers.")
    except Exception as e:
        print(f"Error migrating customers: {e}")

def migrate_vendors(file_path):
    print(f"Migrating vendors from {file_path}...")
    try:
        df = pd.read_excel(file_path, sheet_name="廠商", header=None)
        
        id_idx = 1
        name_idx = 4
        uni_idx = 5
        phone_idx = 9
        addr_idx = 14
        
        count = 0
        for idx in range(5, len(df)):
            row = df.iloc[idx]
            vendor_id = clean_value(row[id_idx])
            name = clean_value(row[name_idx])
            
            if not vendor_id or not name:
                continue
                
            if "＞" in name:
                name = name.split("＞")[0].strip()
                
            existing = db["vendors"].find_one({"vendor_id": str(vendor_id), "is_deleted": False})
            if existing:
                continue
                
            vendor_doc = {
                "vendor_id": str(vendor_id),
                "name": name,
                "uniform_number": clean_value(row[uni_idx]) if clean_value(row[uni_idx]) != "未稅" else None,
                "phone": clean_value(row[phone_idx]),
                "address": clean_value(row[addr_idx]),
                "created_by": "system_migration",
                "created_at": datetime.utcnow(),
                "is_deleted": False
            }
            db["vendors"].insert_one(vendor_doc)
            count += 1
            
        print(f"Migrated {count} vendors.")
    except Exception as e:
        print(f"Error migrating vendors: {e}")

def migrate_products(file_path, default_category):
    print(f"Migrating products from {file_path}...")
    try:
        df = pd.read_excel(file_path, sheet_name="庫存表", header=None)
        
        # Slice the products table (columns 17 to 29) starting from row 7 (index 7)
        prod_df = df.iloc[7:, 17:30].copy()
        
        # Row 0 of sliced df (index 7) contains the column headers
        # Rename columns for easy ffill
        prod_df.columns = [
            "vendor_id", "vendor_name", "prod_type", "size_cat", 
            "spec", "pattern", "product_code", "inbound_total", 
            "col25", "col26", "col27", "outbound_total", "stock"
        ]
        
        # Data rows start from row 8 of original df (index 1 of sliced df)
        prod_df = prod_df.iloc[1:]
        
        # Forward fill the vendor ID and vendor Name
        prod_df["vendor_id"] = prod_df["vendor_id"].ffill()
        prod_df["vendor_name"] = prod_df["vendor_name"].ffill()
        prod_df["prod_type"] = prod_df["prod_type"].ffill()
        
        count = 0
        for _, row in prod_df.iterrows():
            prod_code = clean_value(row["product_code"])
            if not prod_code or prod_code == "產品編輯":
                continue
                
            # Check if product already exists
            existing = db["products"].find_one({"product_code": prod_code, "is_deleted": False})
            if existing:
                continue
                
            brand = "未知"
            # Try to guess brand from product_code
            for b in ["米其林", "普利司通", "馬牌", "倍耐力", "正新", "建大", "橫濱"]:
                if b in prod_code:
                    brand = b
                    break
                    
            spec = clean_value(row["spec"]) or "標準"
            pattern = clean_value(row["pattern"]) or "標準"
            prod_type = clean_value(row["prod_type"]) or "輪胎"
            
            try:
                stock_qty = int(row["stock"]) if pd.notnull(row["stock"]) else 0
            except:
                stock_qty = 0
                
            prod_doc = {
                "product_code": prod_code,
                "brand": brand,
                "spec": spec,
                "pattern": pattern,
                "category": default_category if "輪胎" in prod_type else prod_type,
                "stock_qty": stock_qty,
                "cost": 0.0,
                "price": 0.0,
                "created_by": "system_migration",
                "created_at": datetime.utcnow(),
                "is_deleted": False
            }
            db["products"].insert_one(prod_doc)
            count += 1
            
        print(f"Migrated {count} products.")
    except Exception as e:
        print(f"Error migrating products: {e}")

def main():
    print("Starting Data Migration...")
    
    # 1. Setup default users
    migrate_users()
    
    # Paths to the raw Excel files
    sedan_dir = "/Users/steve_shih/Desktop/tire_erp/2020應收貨款管理系統-轎車部"
    truck_dir = "/Users/steve_shih/Desktop/tire_erp/2020應收貨款管理系統-卡車部"
    
    sedan_acct = os.path.join(sedan_dir, "會計帳務系統.xlsm")
    truck_acct = os.path.join(truck_dir, "會計帳務系統1.xlsm")
    
    # 2. Migrate Sedan
    if os.path.exists(sedan_acct):
        migrate_customers(sedan_acct, "sedan")
        migrate_vendors(sedan_acct)
        migrate_products(sedan_acct, "轎車胎")
    else:
        print(f"Sedan Accounting system not found at {sedan_acct}")
        
    # 3. Migrate Truck
    if os.path.exists(truck_acct):
        migrate_customers(truck_acct, "truck")
        migrate_products(truck_acct, "卡車胎")
    else:
        print(f"Truck Accounting system not found at {truck_acct}")
        
    print("Data Migration finished successfully!")

if __name__ == "__main__":
    main()
