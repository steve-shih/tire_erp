from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime
from typing import List, Optional
from backend.database import get_db
from backend.auth import (
    get_password_hash,
    verify_password,
    create_access_token,
    get_current_user,
    ACCESS_TOKEN_EXPIRE_MINUTES
)
from backend.models import (
    LoginRequest,
    Token,
    UserCreate,
    CustomerCreate,
    CustomerInDB,
    ProductCreate,
    ProductInDB,
    SalesOrderCreate,
    SalesOrderInDB
)
from datetime import timedelta

app = FastAPI(title="Tire ERP API", version="1.0.0")

# Enable CORS for frontend integration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Bootstrapping / Seeding Admin User ---
@app.post("/api/setup-admin", status_code=status.HTTP_201_CREATED)
def setup_admin():
    db = get_db()
    # Check if any user exists
    if db["users"].count_documents({}) > 0:
        raise HTTPException(
            status_code=400,
            detail="System already has users. Admin setup is disabled."
        )
    
    # Create default owner, manager, staff
    default_users = [
        {"username": "admin", "password": "admin123", "role": "owner"},
        {"username": "manager", "password": "manager123", "role": "manager"},
        {"username": "staff", "password": "staff123", "role": "staff"}
    ]
    
    created = []
    for u in default_users:
        hashed = get_password_hash(u["password"])
        db_user = {
            "username": u["username"],
            "hashed_password": hashed,
            "role": u["role"],
            "is_active": True,
            "created_by": "system_setup",
            "created_at": datetime.utcnow(),
            "is_deleted": False
        }
        db["users"].insert_one(db_user)
        created.append(u["username"])
        
    return {"message": "Default users initialized successfully", "users": created}


# --- Authentication Route ---
@app.post("/api/login", response_model=Token)
def login(request: LoginRequest):
    db = get_db()
    user = db["users"].find_one({"username": request.username, "is_deleted": False})
    if not user or not verify_password(request.password, user["hashed_password"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user["username"], "role": user["role"]},
        expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}


# --- User Info Endpoint ---
@app.get("/api/me")
def read_users_me(current_user: dict = Depends(get_current_user)):
    return {
        "username": current_user["username"],
        "role": current_user["role"],
        "is_active": current_user["is_active"]
    }


# --- Customers API (CRUD + Soft Delete + Audit) ---
@app.post("/api/customers", status_code=status.HTTP_201_CREATED)
def create_customer(customer: CustomerCreate, current_user: dict = Depends(get_current_user)):
    db = get_db()
    # Check if customer_id exists
    existing = db["customers"].find_one({"customer_id": customer.customer_id, "is_deleted": False})
    if existing:
        raise HTTPException(status_code=400, detail="Customer ID already exists.")
        
    db_customer = customer.dict()
    db_customer.update({
        "created_by": current_user["username"],
        "created_at": datetime.utcnow(),
        "is_deleted": False,
        "updated_by": None,
        "updated_at": None,
        "deleted_by": None,
        "deleted_at": None
    })
    
    db["customers"].insert_one(db_customer)
    return {"message": "Customer created successfully", "customer_id": customer.customer_id}

@app.get("/api/customers")
def list_customers(current_user: dict = Depends(get_current_user)):
    db = get_db()
    # Filter out soft deleted records
    customers = list(db["customers"].find({"is_deleted": False}))
    for c in customers:
        c["_id"] = str(c["_id"])
    return customers

@app.put("/api/customers/{customer_id}")
def update_customer(customer_id: str, customer: CustomerCreate, current_user: dict = Depends(get_current_user)):
    db = get_db()
    existing = db["customers"].find_one({"customer_id": customer_id, "is_deleted": False})
    if not existing:
        raise HTTPException(status_code=404, detail="Customer not found")
        
    update_data = customer.dict()
    update_data.update({
        "updated_by": current_user["username"],
        "updated_at": datetime.utcnow()
    })
    
    # Preserve original creation fields
    db["customers"].update_one(
        {"customer_id": customer_id, "is_deleted": False},
        {"$set": update_data}
    )
    return {"message": "Customer updated successfully"}

@app.delete("/api/customers/{customer_id}")
def delete_customer(customer_id: str, current_user: dict = Depends(get_current_user)):
    db = get_db()
    existing = db["customers"].find_one({"customer_id": customer_id, "is_deleted": False})
    if not existing:
        raise HTTPException(status_code=404, detail="Customer not found")
        
    # Perform Soft Delete (虛刪除) & Audit deletion
    db["customers"].update_one(
        {"customer_id": customer_id},
        {
            "$set": {
                "is_deleted": True,
                "deleted_by": current_user["username"],
                "deleted_at": datetime.utcnow()
            }
        }
    )
    return {"message": "Customer soft-deleted successfully"}


# --- Products API (CRUD + Soft Delete + Audit) ---
@app.post("/api/products", status_code=status.HTTP_201_CREATED)
def create_product(product: ProductCreate, current_user: dict = Depends(get_current_user)):
    db = get_db()
    existing = db["products"].find_one({"product_code": product.product_code, "is_deleted": False})
    if existing:
        raise HTTPException(status_code=400, detail="Product code already exists.")
        
    db_product = product.dict()
    db_product.update({
        "created_by": current_user["username"],
        "created_at": datetime.utcnow(),
        "is_deleted": False,
        "updated_by": None,
        "updated_at": None,
        "deleted_by": None,
        "deleted_at": None
    })
    
    db["products"].insert_one(db_product)
    return {"message": "Product created successfully", "product_code": product.product_code}

@app.get("/api/products")
def list_products(current_user: dict = Depends(get_current_user)):
    db = get_db()
    products = list(db["products"].find({"is_deleted": False}))
    for p in products:
        p["_id"] = str(p["_id"])
    return products

@app.put("/api/products/{product_code}")
def update_product(product_code: str, product: ProductCreate, current_user: dict = Depends(get_current_user)):
    db = get_db()
    existing = db["products"].find_one({"product_code": product_code, "is_deleted": False})
    if not existing:
        raise HTTPException(status_code=404, detail="Product not found")
        
    update_data = product.dict()
    update_data.update({
        "updated_by": current_user["username"],
        "updated_at": datetime.utcnow()
    })
    
    db["products"].update_one(
        {"product_code": product_code, "is_deleted": False},
        {"$set": update_data}
    )
    return {"message": "Product updated successfully"}

@app.delete("/api/products/{product_code}")
def delete_product(product_code: str, current_user: dict = Depends(get_current_user)):
    db = get_db()
    existing = db["products"].find_one({"product_code": product_code, "is_deleted": False})
    if not existing:
        raise HTTPException(status_code=404, detail="Product not found")
        
    db["products"].update_one(
        {"product_code": product_code},
        {
            "$set": {
                "is_deleted": True,
                "deleted_by": current_user["username"],
                "deleted_at": datetime.utcnow()
            }
        }
    )
    return {"message": "Product soft-deleted successfully"}


# --- Sales Orders API (CRUD + Soft Delete + Audit) ---
@app.post("/api/sales", status_code=status.HTTP_201_CREATED)
def create_sales_order(order: SalesOrderCreate, current_user: dict = Depends(get_current_user)):
    db = get_db()
    existing = db["sales_orders"].find_one({"order_id": order.order_id, "is_deleted": False})
    if existing:
        raise HTTPException(status_code=400, detail="Sales Order ID already exists.")
        
    db_order = order.dict()
    db_order.update({
        "created_by": current_user["username"],
        "created_at": datetime.utcnow(),
        "is_deleted": False,
        "updated_by": None,
        "updated_at": None,
        "deleted_by": None,
        "deleted_at": None
    })
    
    db["sales_orders"].insert_one(db_order)
    
    # Adjust stock quantities of products
    for item in order.items:
        db["products"].update_one(
            {"product_code": item.product_code, "is_deleted": False},
            {"$inc": {"stock_qty": -item.qty}}
        )
        
    return {"message": "Sales Order created successfully", "order_id": order.order_id}

@app.get("/api/sales")
def list_sales_orders(department: Optional[str] = None, current_user: dict = Depends(get_current_user)):
    db = get_db()
    query = {"is_deleted": False}
    if department:
        query["department"] = department
        
    orders = list(db["sales_orders"].find(query))
    for o in orders:
        o["_id"] = str(o["_id"])
    return orders

@app.delete("/api/sales/{order_id}")
def delete_sales_order(order_id: str, current_user: dict = Depends(get_current_user)):
    db = get_db()
    existing = db["sales_orders"].find_one({"order_id": order_id, "is_deleted": False})
    if not existing:
        raise HTTPException(status_code=404, detail="Sales Order not found")
        
    # Revert stock quantity changes
    for item in existing["items"]:
        db["products"].update_one(
            {"product_code": item["product_code"], "is_deleted": False},
            {"$inc": {"stock_qty": item["qty"]}}
        )
        
    db["sales_orders"].update_one(
        {"order_id": order_id},
        {
            "$set": {
                "is_deleted": True,
                "deleted_by": current_user["username"],
                "deleted_at": datetime.utcnow()
            }
        }
    )
    return {"message": "Sales Order soft-deleted successfully"}
