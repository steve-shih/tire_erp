from fastapi import FastAPI, Depends, HTTPException, status, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from datetime import datetime, timezone
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
    LoginRequest, Token, UserCreate, UserResponse, PasswordUpdate,
    CustomerCreate, VendorCreate, ProductCreate, StockAdjustment,
    SalesOrderCreate, PurchaseOrderCreate, QuoteCreate,
    AnnouncementBase,
    ReceivableCreate, PayableCreate, PaymentCreate, NoteCreate,
    SettingsUpdate, EmployeeCreate, PayrollRecordCreate
)
from fastapi.responses import Response
from backend.excel_engine import (
    create_sales_order_excel, create_envelope_excel, create_address_label_excel,
    create_purchase_order_excel, create_quote_excel
)
from datetime import timedelta
import uuid

app = FastAPI(title="Tire ERP API", version="3.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def _now():
    return datetime.now(timezone.utc)

def _audit_create(username: str) -> dict:
    return {"created_by": username, "created_at": _now(), "is_deleted": False,
            "updated_by": None, "updated_at": None, "deleted_by": None, "deleted_at": None}

def _audit_update(username: str) -> dict:
    return {"updated_by": username, "updated_at": _now()}

def _audit_delete(username: str) -> dict:
    return {"is_deleted": True, "deleted_by": username, "deleted_at": _now()}

def _gen_id(prefix: str) -> str:
    return f"{prefix}-{_now().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6]}"

def log_action(db, username: str, action: str, entity: str, description: str):
    db["system_logs"].insert_one({
        "username": username,
        "action": action,
        "entity": entity,
        "description": description,
        "timestamp": _now()
    })


# ==================== Setup / Seed ====================
@app.post("/api/setup-admin", status_code=201)
def setup_admin():
    db = get_db()
    default_users = [
        {"username": "owner1", "password": "owner123", "role": "owner"},
        {"username": "owner2", "password": "owner123", "role": "owner"},
        {"username": "staff1", "password": "staff123", "role": "staff"},
        {"username": "staff2", "password": "staff123", "role": "staff"},
        {"username": "branch_taichung", "password": "taichung123", "role": "staff"},
        {"username": "branch_miaoli", "password": "miaoli123", "role": "staff"},
        {"username": "branch_hsinchu", "password": "hsinchu123", "role": "staff"}
    ]
    created = []
    for u in default_users:
        if db["users"].count_documents({"username": u["username"]}) == 0:
            db["users"].insert_one({
                "username": u["username"],
                "hashed_password": get_password_hash(u["password"]),
                "role": u["role"], "is_active": True,
                **_audit_create("system_setup")
            })
            created.append(u["username"])
    if db["announcements"].count_documents({}) == 0:
        db["announcements"].insert_one({
            "content": "歡迎光臨！本公司提供各式輪胎零售批發、定位保養、翻修胎加工，品質保證，服務至上！",
            "updated_by": "system_setup", "updated_at": _now()
        })
    if db["settings"].count_documents({"_id": "permissions"}) == 0:
        db["settings"].insert_one({
            "_id": "permissions",
            "staff_visible_menus": ["sales-section", "quotes-section", "inventory-section", "purchases-section", "customers-section", "vendors-section", "payroll-section"]
        })
    return {"message": "Setup finished", "users_created": created}


# ==================== Auth ====================
@app.post("/api/login", response_model=Token)
def login(request: LoginRequest):
    db = get_db()
    user = db["users"].find_one({"username": request.username, "is_deleted": False})
    if not user or not verify_password(request.password, user["hashed_password"]):
        raise HTTPException(status_code=401, detail="Incorrect username or password")
    token = create_access_token(
        data={"sub": user["username"], "role": user["role"]},
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    return {"access_token": token, "token_type": "bearer"}

@app.get("/api/me")
def read_users_me(current_user: dict = Depends(get_current_user)):
    return {"username": current_user["username"], "role": current_user["role"], "is_active": current_user["is_active"]}

@app.get("/api/logs")
def get_logs(username: Optional[str] = None, page: int = 1, limit: int = 30, current_user: dict = Depends(get_current_user)):
    if current_user["role"] != "owner":
        raise HTTPException(status_code=403, detail="Only owners can view logs")
    db = get_db()
    query = {}
    if username:
        query["username"] = username
    total = db["system_logs"].count_documents(query)
    skip = (page - 1) * limit
    logs = list(db["system_logs"].find(query).sort("timestamp", -1).skip(skip).limit(limit))
    for l in logs:
        l["_id"] = str(l["_id"])
    return {
        "data": logs,
        "total": total,
        "page": page,
        "limit": limit
    }

# ============================================================
# User Management (Phase 7)
# ============================================================
@app.get("/api/users")
def list_users(page: int = 1, limit: int = 30, current_user: dict = Depends(get_current_user)):
    if current_user["role"] != "owner":
        raise HTTPException(status_code=403, detail="Forbidden")
    db = get_db()
    total = db["users"].count_documents({"is_deleted": {"$ne": True}})
    skip = (page - 1) * limit
    users = list(db["users"].find({"is_deleted": {"$ne": True}}).skip(skip).limit(limit))
    for u in users:
        u["_id"] = str(u["_id"])
    return {
        "data": users,
        "total": total,
        "page": page,
        "limit": limit
    }

@app.post("/api/users", response_model=UserResponse)
def create_user(user: UserCreate, current_user: dict = Depends(get_current_user)):
    if current_user["role"] != "owner":
        raise HTTPException(status_code=403, detail="Forbidden")
    db = get_db()
    if db["users"].count_documents({"username": user.username}) > 0:
        raise HTTPException(status_code=400, detail="Username already exists")
    
    new_user = user.model_dump()
    new_user["hashed_password"] = get_password_hash(new_user.pop("password"))
    new_user.update(_audit_create(current_user["username"]))
    db["users"].insert_one(new_user)
    log_action(db, current_user["username"], "CREATE", "user", f"Created user {user.username}")
    return new_user

@app.put("/api/users/{username}/password")
def update_user_password(username: str, payload: PasswordUpdate, current_user: dict = Depends(get_current_user)):
    if current_user["role"] != "owner":
        raise HTTPException(status_code=403, detail="Forbidden")
    db = get_db()
    if not db["users"].find_one({"username": username, "is_deleted": {"$ne": True}}):
        raise HTTPException(status_code=404, detail="User not found")
        
    hashed = get_password_hash(payload.password)
    db["users"].update_one(
        {"username": username}, 
        {"$set": {"hashed_password": hashed, **_audit_update(current_user["username"])}}
    )
    log_action(db, current_user["username"], "UPDATE", "user", f"Changed password for {username}")
    return {"message": "Password updated"}

@app.delete("/api/users/{username}")
def delete_user(username: str, current_user: dict = Depends(get_current_user)):
    if current_user["role"] != "owner":
        raise HTTPException(status_code=403, detail="Forbidden")
    if username == current_user["username"]:
        raise HTTPException(status_code=400, detail="Cannot delete yourself")
    db = get_db()
    if not db["users"].find_one({"username": username, "is_deleted": {"$ne": True}}):
        raise HTTPException(status_code=404, detail="User not found")
        
    db["users"].update_one(
        {"username": username}, 
        {"$set": _audit_delete(current_user["username"])}
    )
    log_action(db, current_user["username"], "DELETE", "user", f"Deleted user {username}")
    return {"message": "User deleted"}


# ==================== Customers CRUD ====================
@app.post("/api/customers", status_code=201)
def create_customer(customer: CustomerCreate, current_user: dict = Depends(get_current_user)):
    db = get_db()
    if db["customers"].find_one({"customer_id": customer.customer_id, "is_deleted": False}):
        raise HTTPException(status_code=400, detail="Customer ID already exists.")
    doc = customer.model_dump()
    doc.update(_audit_create(current_user["username"]))
    db["customers"].insert_one(doc)
    return {"message": "Customer created", "customer_id": customer.customer_id}

@app.get("/api/customers")
def list_customers(search: Optional[str] = None, page: int = 1, limit: int = 30, current_user: dict = Depends(get_current_user)):
    db = get_db()
    q = {"is_deleted": False}
    if search:
        q["$or"] = [{"customer_id": {"$regex": search, "$options": "i"}},
                     {"name": {"$regex": search, "$options": "i"}},
                     {"phone": {"$regex": search, "$options": "i"}}]
    total = db["customers"].count_documents(q)
    skip = (page - 1) * limit
    result = list(db["customers"].find(q).skip(skip).limit(limit))
    for c in result: c["_id"] = str(c["_id"])
    return {
        "data": result,
        "total": total,
        "page": page,
        "limit": limit
    }

@app.get("/api/customers/{customer_id}")
def get_customer(customer_id: str, current_user: dict = Depends(get_current_user)):
    db = get_db()
    c = db["customers"].find_one({"customer_id": customer_id, "is_deleted": False})
    if not c: raise HTTPException(status_code=404, detail="Customer not found")
    c["_id"] = str(c["_id"])
    return c

@app.put("/api/customers/{customer_id}")
def update_customer(customer_id: str, customer: CustomerCreate, current_user: dict = Depends(get_current_user)):
    db = get_db()
    if not db["customers"].find_one({"customer_id": customer_id, "is_deleted": False}):
        raise HTTPException(status_code=404, detail="Customer not found")
    data = customer.model_dump()
    data.update(_audit_update(current_user["username"]))
    db["customers"].update_one({"customer_id": customer_id, "is_deleted": False}, {"$set": data})
    return {"message": "Customer updated"}

@app.delete("/api/customers/{customer_id}")
def delete_customer(customer_id: str, current_user: dict = Depends(get_current_user)):
    db = get_db()
    if not db["customers"].find_one({"customer_id": customer_id, "is_deleted": False}):
        raise HTTPException(status_code=404, detail="Customer not found")
    db["customers"].update_one({"customer_id": customer_id}, {"$set": _audit_delete(current_user["username"])})
    return {"message": "Customer deleted"}


# ==================== Vendors CRUD ====================
@app.post("/api/vendors", status_code=201)
def create_vendor(vendor: VendorCreate, current_user: dict = Depends(get_current_user)):
    db = get_db()
    if db["vendors"].find_one({"vendor_id": vendor.vendor_id, "is_deleted": False}):
        raise HTTPException(status_code=400, detail="Vendor ID already exists.")
    doc = vendor.model_dump()
    doc.update(_audit_create(current_user["username"]))
    db["vendors"].insert_one(doc)
    return {"message": "Vendor created", "vendor_id": vendor.vendor_id}

@app.get("/api/vendors")
def list_vendors(search: Optional[str] = None, page: int = 1, limit: int = 30, current_user: dict = Depends(get_current_user)):
    db = get_db()
    q = {"is_deleted": False}
    if search:
        q["$or"] = [{"vendor_id": {"$regex": search, "$options": "i"}},
                     {"name": {"$regex": search, "$options": "i"}},
                     {"phone": {"$regex": search, "$options": "i"}}]
    total = db["vendors"].count_documents(q)
    skip = (page - 1) * limit
    result = list(db["vendors"].find(q).skip(skip).limit(limit))
    for v in result: v["_id"] = str(v["_id"])
    return {
        "data": result,
        "total": total,
        "page": page,
        "limit": limit
    }

@app.get("/api/vendors/{vendor_id}")
def get_vendor(vendor_id: str, current_user: dict = Depends(get_current_user)):
    db = get_db()
    v = db["vendors"].find_one({"vendor_id": vendor_id, "is_deleted": False})
    if not v: raise HTTPException(status_code=404, detail="Vendor not found")
    v["_id"] = str(v["_id"])
    return v

@app.put("/api/vendors/{vendor_id}")
def update_vendor(vendor_id: str, vendor: VendorCreate, current_user: dict = Depends(get_current_user)):
    db = get_db()
    if not db["vendors"].find_one({"vendor_id": vendor_id, "is_deleted": False}):
        raise HTTPException(status_code=404, detail="Vendor not found")
    data = vendor.model_dump()
    data.update(_audit_update(current_user["username"]))
    db["vendors"].update_one({"vendor_id": vendor_id, "is_deleted": False}, {"$set": data})
    return {"message": "Vendor updated"}

@app.delete("/api/vendors/{vendor_id}")
def delete_vendor(vendor_id: str, current_user: dict = Depends(get_current_user)):
    db = get_db()
    if not db["vendors"].find_one({"vendor_id": vendor_id, "is_deleted": False}):
        raise HTTPException(status_code=404, detail="Vendor not found")
    db["vendors"].update_one({"vendor_id": vendor_id}, {"$set": _audit_delete(current_user["username"])})
    return {"message": "Vendor deleted"}


# ==================== Products CRUD ====================
@app.post("/api/products", status_code=201)
def create_product(product: ProductCreate, current_user: dict = Depends(get_current_user)):
    db = get_db()
    if db["products"].find_one({"product_code": product.product_code, "is_deleted": False}):
        raise HTTPException(status_code=400, detail="Product code already exists.")
    doc = product.model_dump()
    doc.update(_audit_create(current_user["username"]))
    db["products"].insert_one(doc)
    return {"message": "Product created", "product_code": product.product_code}

@app.get("/api/products")
def list_products(category: Optional[str] = None, search: Optional[str] = None, page: int = 1, limit: int = 50, current_user: dict = Depends(get_current_user)):
    db = get_db()
    q = {"is_deleted": False}
    if category: q["category"] = category
    if search:
        q["$or"] = [
            {"product_code": {"$regex": search, "$options": "i"}},
            {"brand": {"$regex": search, "$options": "i"}},
            {"specification": {"$regex": search, "$options": "i"}}
        ]
    total = db["products"].count_documents(q)
    skip = (page - 1) * limit
    result = list(db["products"].find(q).skip(skip).limit(limit))
    for p in result: p["_id"] = str(p["_id"])
    return {
        "data": result,
        "total": total,
        "page": page,
        "limit": limit
    }

@app.put("/api/products/{product_code}")
def update_product(product_code: str, product: ProductCreate, current_user: dict = Depends(get_current_user)):
    db = get_db()
    if not db["products"].find_one({"product_code": product_code, "is_deleted": False}):
        raise HTTPException(status_code=404, detail="Product not found")
    data = product.model_dump()
    data.update(_audit_update(current_user["username"]))
    db["products"].update_one({"product_code": product_code, "is_deleted": False}, {"$set": data})
    return {"message": "Product updated"}

@app.delete("/api/products/{product_code}")
def delete_product(product_code: str, current_user: dict = Depends(get_current_user)):
    db = get_db()
    if not db["products"].find_one({"product_code": product_code, "is_deleted": False}):
        raise HTTPException(status_code=404, detail="Product not found")
    db["products"].update_one({"product_code": product_code}, {"$set": _audit_delete(current_user["username"])})
    return {"message": "Product deleted"}


@app.post("/api/products/{product_code}/adjust_stock")
def adjust_stock(product_code: str, adjustment_data: StockAdjustment, current_user: dict = Depends(get_current_user)):
    db = get_db()
    product = db["products"].find_one({"product_code": product_code, "is_deleted": False})
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    
    new_qty = product.get("stock_qty", 0) + adjustment_data.adjustment
    db["products"].update_one(
        {"product_code": product_code, "is_deleted": False},
        {"$set": {"stock_qty": new_qty, **_audit_update(current_user["username"])}}
    )
    
    log_action(db, current_user["username"], "ADJUST_STOCK", "product", 
               f"Adjusted stock for {product_code} by {adjustment_data.adjustment}. Reason: {adjustment_data.reason}. New qty: {new_qty}")
    
    return {"message": "Stock adjusted successfully", "new_qty": new_qty}


# ==================== Sales Orders CRUD ====================
@app.post("/api/sales", status_code=201)
def create_sales_order(order: SalesOrderCreate, current_user: dict = Depends(get_current_user)):
    db = get_db()
    if db["sales_orders"].find_one({"order_id": order.order_id, "is_deleted": False}):
        raise HTTPException(status_code=400, detail="Sales Order ID already exists.")
    doc = order.model_dump()
    doc.update(_audit_create(current_user["username"]))
    db["sales_orders"].insert_one(doc)
    # Deduct stock
    for item in order.items:
        db["products"].update_one(
            {"product_code": item.product_code, "is_deleted": False},
            {"$inc": {"stock_qty": -item.qty}})
    # Auto-create receivable if payment is credit-based
    if order.payment_status in ("應收貨款", "receivable"):
        recv_doc = {
            "receivable_id": _gen_id("RCV"),
            "order_id": order.order_id,
            "date": order.date,
            "customer_id": order.customer_id,
            "customer_name": order.customer_name,
            "plate_number": order.plate_number,
            "amount": order.grand_total,
            "paid_amount": 0.0,
            "balance": order.grand_total,
            "status": "unpaid",
            "due_date": None,
            **_audit_create(current_user["username"])
        }
        db["receivables"].insert_one(recv_doc)
    log_action(db, current_user["username"], "CREATE", "sales_order", f"Created order {order.order_id}")
    return {"message": "Sales Order created", "order_id": order.order_id}

@app.get("/api/sales")
def list_sales_orders(department: Optional[str] = None, category: Optional[str] = None,
                      start_date: Optional[str] = None, end_date: Optional[str] = None,
                      page: int = 1, limit: int = 30, current_user: dict = Depends(get_current_user)):
    db = get_db()
    q = {"is_deleted": False}
    if department: q["department"] = department
    if category: q["category"] = category
    if start_date or end_date:
        q["date"] = {}
        if start_date: q["date"]["$gte"] = datetime.fromisoformat(start_date)
        if end_date: q["date"]["$lte"] = datetime.fromisoformat(end_date)
    total = db["sales_orders"].count_documents(q)
    skip = (page - 1) * limit
    orders = list(db["sales_orders"].find(q).sort("date", -1).skip(skip).limit(limit))
    for o in orders: o["_id"] = str(o["_id"])
    return {
        "data": orders,
        "total": total,
        "page": page,
        "limit": limit
    }

@app.get("/api/sales/{order_id}")
def get_sales_order(order_id: str, current_user: dict = Depends(get_current_user)):
    db = get_db()
    o = db["sales_orders"].find_one({"order_id": order_id, "is_deleted": False})
    if not o: raise HTTPException(status_code=404, detail="Sales Order not found")
    o["_id"] = str(o["_id"])
    if o.get("customer_id"):
        cust = db["customers"].find_one({"customer_id": o["customer_id"], "is_deleted": False})
        if cust:
            cust["_id"] = str(cust["_id"])
            o["customer_detail"] = cust
    return o

@app.delete("/api/sales/{order_id}")
def delete_sales_order(order_id: str, current_user: dict = Depends(get_current_user)):
    db = get_db()
    existing = db["sales_orders"].find_one({"order_id": order_id, "is_deleted": False})
    if not existing: raise HTTPException(status_code=404, detail="Sales Order not found")
    for item in existing["items"]:
        db["products"].update_one(
            {"product_code": item["product_code"], "is_deleted": False},
            {"$inc": {"stock_qty": item["qty"]}})
    db["sales_orders"].update_one({"order_id": order_id}, {"$set": _audit_delete(current_user["username"])})
    # Also soft-delete related receivable
    db["receivables"].update_many({"order_id": order_id, "is_deleted": False}, {"$set": _audit_delete(current_user["username"])})
    log_action(db, current_user["username"], "DELETE", "sales_order", f"Deleted order {order_id}")
    return {"message": "Sales Order deleted"}


# ==================== Purchase Orders CRUD ====================
@app.post("/api/purchases", status_code=201)
def create_purchase_order(purchase: PurchaseOrderCreate, current_user: dict = Depends(get_current_user)):
    db = get_db()
    if db["purchase_orders"].find_one({"purchase_id": purchase.purchase_id, "is_deleted": False}):
        raise HTTPException(status_code=400, detail="Purchase Order ID already exists.")
    doc = purchase.model_dump()
    doc.update(_audit_create(current_user["username"]))
    db["purchase_orders"].insert_one(doc)
    for item in purchase.items:
        db["products"].update_one(
            {"product_code": item.product_code, "is_deleted": False},
            {"$inc": {"stock_qty": item.qty}})
    # Auto-create payable if credit-based
    if purchase.payment_status in ("應付帳款", "payable"):
        pay_doc = {
            "payable_id": _gen_id("PAY"),
            "purchase_id": purchase.purchase_id,
            "date": purchase.date,
            "vendor_id": purchase.vendor_id,
            "vendor_name": purchase.vendor_name,
            "invoice_number": purchase.invoice_number,
            "amount": purchase.grand_total,
            "paid_amount": 0.0,
            "balance": purchase.grand_total,
            "status": "unpaid",
            "due_date": None,
            **_audit_create(current_user["username"])
        }
        db["payables"].insert_one(pay_doc)
    log_action(db, current_user["username"], "CREATE", "purchase_order", f"Created order {purchase.purchase_id}")
    return {"message": "Purchase Order created", "purchase_id": purchase.purchase_id}

@app.get("/api/purchases")
def list_purchase_orders(page: int = 1, limit: int = 30, current_user: dict = Depends(get_current_user)):
    db = get_db()
    total = db["purchase_orders"].count_documents({"is_deleted": False})
    skip = (page - 1) * limit
    purchases = list(db["purchase_orders"].find({"is_deleted": False}).sort("date", -1).skip(skip).limit(limit))
    for p in purchases: p["_id"] = str(p["_id"])
    return {
        "data": purchases,
        "total": total,
        "page": page,
        "limit": limit
    }

@app.get("/api/purchases/{purchase_id}")
def get_purchase_order(purchase_id: str, current_user: dict = Depends(get_current_user)):
    db = get_db()
    p = db["purchase_orders"].find_one({"purchase_id": purchase_id, "is_deleted": False})
    if not p: raise HTTPException(status_code=404, detail="Purchase Order not found")
    p["_id"] = str(p["_id"])
    if p.get("vendor_id"):
        v = db["vendors"].find_one({"vendor_id": p["vendor_id"], "is_deleted": False})
        if v:
            v["_id"] = str(v["_id"])
            p["vendor_detail"] = v
    return p

@app.delete("/api/purchases/{purchase_id}")
def delete_purchase_order(purchase_id: str, current_user: dict = Depends(get_current_user)):
    db = get_db()
    existing = db["purchase_orders"].find_one({"purchase_id": purchase_id, "is_deleted": False})
    if not existing: raise HTTPException(status_code=404, detail="Purchase Order not found")
    for item in existing["items"]:
        db["products"].update_one(
            {"product_code": item["product_code"], "is_deleted": False},
            {"$inc": {"stock_qty": -item["qty"]}})
    db["purchase_orders"].update_one({"purchase_id": purchase_id}, {"$set": _audit_delete(current_user["username"])})
    db["payables"].update_many({"purchase_id": purchase_id, "is_deleted": False}, {"$set": _audit_delete(current_user["username"])})
    log_action(db, current_user["username"], "DELETE", "purchase_order", f"Deleted order {purchase_id}")
    return {"message": "Purchase Order deleted"}


# ==================== Quotes CRUD ====================
@app.post("/api/quotes", status_code=201)
def create_quote(quote: QuoteCreate, current_user: dict = Depends(get_current_user)):
    db = get_db()
    if db["quotes"].find_one({"quote_id": quote.quote_id, "is_deleted": False}):
        raise HTTPException(status_code=400, detail="Quote ID already exists.")
    doc = quote.model_dump()
    doc.update(_audit_create(current_user["username"]))
    db["quotes"].insert_one(doc)
    log_action(db, current_user["username"], "CREATE", "quote", f"Created quote {quote.quote_id}")
    return {"message": "Quote created", "quote_id": quote.quote_id}

@app.get("/api/quotes")
def list_quotes(quote_type: Optional[str] = None, category: Optional[str] = None,
                page: int = 1, limit: int = 30, current_user: dict = Depends(get_current_user)):
    db = get_db()
    q = {"is_deleted": False}
    if quote_type: q["quote_type"] = quote_type
    if category: q["category"] = category
    total = db["quotes"].count_documents(q)
    skip = (page - 1) * limit
    quotes = list(db["quotes"].find(q).sort("date", -1).skip(skip).limit(limit))
    for qt in quotes: qt["_id"] = str(qt["_id"])
    return {
        "data": quotes,
        "total": total,
        "page": page,
        "limit": limit
    }

@app.get("/api/quotes/{quote_id}")
def get_quote(quote_id: str, current_user: dict = Depends(get_current_user)):
    db = get_db()
    qt = db["quotes"].find_one({"quote_id": quote_id, "is_deleted": False})
    if not qt: raise HTTPException(status_code=404, detail="Quote not found")
    qt["_id"] = str(qt["_id"])
    return qt

@app.put("/api/quotes/{quote_id}")
def update_quote(quote_id: str, quote: QuoteCreate, current_user: dict = Depends(get_current_user)):
    db = get_db()
    if not db["quotes"].find_one({"quote_id": quote_id, "is_deleted": False}):
        raise HTTPException(status_code=404, detail="Quote not found")
    data = quote.model_dump()
    data.update(_audit_update(current_user["username"]))
    db["quotes"].update_one({"quote_id": quote_id, "is_deleted": False}, {"$set": data})
    log_action(db, current_user["username"], "UPDATE", "quote", f"Updated quote {quote_id}")
    return {"message": "Quote updated"}

@app.delete("/api/quotes/{quote_id}")
def delete_quote(quote_id: str, current_user: dict = Depends(get_current_user)):
    db = get_db()
    if not db["quotes"].find_one({"quote_id": quote_id, "is_deleted": False}):
        raise HTTPException(status_code=404, detail="Quote not found")
    db["quotes"].update_one({"quote_id": quote_id}, {"$set": _audit_delete(current_user["username"])})
    log_action(db, current_user["username"], "DELETE", "quote", f"Deleted quote {quote_id}")
    return {"message": "Quote deleted"}

@app.post("/api/quotes/{quote_id}/convert")
def convert_quote(quote_id: str, conversion_data: dict, current_user: dict = Depends(get_current_user)):
    db = get_db()
    quote = db["quotes"].find_one({"quote_id": quote_id, "is_deleted": False})
    if not quote: raise HTTPException(status_code=404, detail="Quote not found")

    if quote["quote_type"] == "customer":
        order_id = conversion_data.get("order_id")
        if db["sales_orders"].find_one({"order_id": order_id, "is_deleted": False}):
            raise HTTPException(status_code=400, detail="Sales Order ID already exists.")
        department = "truck" if "大車" in quote["category"] else "sedan"
        sales_order = {
            "order_id": order_id,
            "department": department,
            "category": conversion_data.get("category", "轎車店內"),
            "date": _now(),
            "customer_id": quote["party_id"],
            "customer_name": quote.get("party_name"),
            "customer_phone": quote.get("phone"),
            "customer_uniform_number": quote.get("uniform_number"),
            "customer_address": quote.get("address"),
            "plate_number": quote.get("plate_number"),
            "items": quote["items"],
            "total_amount": quote["total_amount"],
            "tax_amount": quote["tax_amount"],
            "grand_total": quote["grand_total"],
            "payment_status": conversion_data.get("payment_status", "收現"),
            "invoice_number": conversion_data.get("invoice_number"),
            "note": f"由報價單 {quote_id} 轉換",
            **_audit_create(current_user["username"])
        }
        db["sales_orders"].insert_one(sales_order)
        for item in quote["items"]:
            db["products"].update_one(
                {"product_code": item["product_code"], "is_deleted": False},
                {"$inc": {"stock_qty": -item["qty"]}})
        # Auto-create receivable if credit
        ps = conversion_data.get("payment_status", "收現")
        if ps in ("應收貨款", "receivable"):
            db["receivables"].insert_one({
                "receivable_id": _gen_id("RCV"), "order_id": order_id, "date": _now(),
                "customer_id": quote["party_id"], "customer_name": quote.get("party_name"),
                "plate_number": quote.get("plate_number"),
                "amount": quote["grand_total"], "paid_amount": 0.0, "balance": quote["grand_total"],
                "status": "unpaid", "due_date": None,
                **_audit_create(current_user["username"])
            })
        db["quotes"].update_one({"quote_id": quote_id}, {"$set": {"is_converted": True, "note": f"(已轉出貨單 {order_id}) " + (quote.get("note") or "")}})
        log_action(db, current_user["username"], "CONVERT", "quote", f"Converted quote {quote_id} to order {order_id}")
        return {"message": "Quote converted to Sales Order", "order_id": order_id}

    elif quote["quote_type"] == "vendor":
        purchase_id = conversion_data.get("purchase_id")
        if db["purchase_orders"].find_one({"purchase_id": purchase_id, "is_deleted": False}):
            raise HTTPException(status_code=400, detail="Purchase Order ID already exists.")
        purchase_order = {
            "purchase_id": purchase_id, "date": _now(),
            "vendor_id": quote["party_id"], "vendor_name": quote.get("party_name"),
            "vendor_phone": quote.get("phone"), "vendor_uniform_number": quote.get("uniform_number"),
            "vendor_address": quote.get("address"),
            "items": quote["items"],
            "total_amount": quote["total_amount"], "tax_amount": quote["tax_amount"],
            "grand_total": quote["grand_total"],
            "payment_status": conversion_data.get("payment_status", "應付帳款"),
            "invoice_number": conversion_data.get("invoice_number"),
            "note": f"由報價單 {quote_id} 轉換",
            **_audit_create(current_user["username"])
        }
        db["purchase_orders"].insert_one(purchase_order)
        for item in quote["items"]:
            db["products"].update_one(
                {"product_code": item["product_code"], "is_deleted": False},
                {"$inc": {"stock_qty": item["qty"]}})
        ps = conversion_data.get("payment_status", "應付帳款")
        if ps in ("應付帳款", "payable"):
            db["payables"].insert_one({
                "payable_id": _gen_id("PAY"), "purchase_id": purchase_id, "date": _now(),
                "vendor_id": quote["party_id"], "vendor_name": quote.get("party_name"),
                "invoice_number": conversion_data.get("invoice_number"),
                "amount": quote["grand_total"], "paid_amount": 0.0, "balance": quote["grand_total"],
                "status": "unpaid", "due_date": None,
                **_audit_create(current_user["username"])
            })
        db["quotes"].update_one({"quote_id": quote_id}, {"$set": {"is_converted": True, "note": f"(已轉進貨單 {purchase_id}) " + (quote.get("note") or "")}})
        log_action(db, current_user["username"], "CONVERT", "quote", f"Converted quote {quote_id} to purchase {purchase_id}")
        return {"message": "Quote converted to Purchase Order", "purchase_id": purchase_id}


# ==================== Announcements ====================
@app.get("/api/announcements")
def get_announcements():
    db = get_db()
    a = db["announcements"].find_one({})
    return {"content": a["content"] if a else ""}

@app.put("/api/announcements")
def update_announcements(data: AnnouncementBase, current_user: dict = Depends(get_current_user)):
    db = get_db()
    db["announcements"].update_one({}, {"$set": {"content": data.content, "updated_by": current_user["username"], "updated_at": _now()}}, upsert=True)
    return {"message": "Announcement updated"}


# ==================== Settings ====================
@app.get("/api/settings/permissions")
def get_permissions(current_user: dict = Depends(get_current_user)):
    db = get_db()
    p = db["settings"].find_one({"_id": "permissions"})
    return {"staff_visible_menus": p.get("staff_visible_menus", []) if p else []}

@app.put("/api/settings/permissions")
def update_permissions(data: SettingsUpdate, current_user: dict = Depends(get_current_user)):
    if current_user["role"] != "owner":
        raise HTTPException(status_code=403, detail="Only owners can modify permissions")
    db = get_db()
    db["settings"].update_one({"_id": "permissions"}, {"$set": {"staff_visible_menus": data.staff_visible_menus}}, upsert=True)
    return {"message": "Permissions updated"}


# ============================================================
# 財務模組 API Endpoints
# ============================================================

# ==================== Receivables (應收帳款) ====================
@app.get("/api/receivables")
def list_receivables(customer_id: Optional[str] = None, status: Optional[str] = None,
                     page: int = 1, limit: int = 30, current_user: dict = Depends(get_current_user)):
    db = get_db()
    q = {"is_deleted": False}
    if customer_id: q["customer_id"] = customer_id
    if status: q["status"] = status
    total = db["receivables"].count_documents(q)
    skip = (page - 1) * limit
    result = list(db["receivables"].find(q).sort("date", -1).skip(skip).limit(limit))
    for r in result: r["_id"] = str(r["_id"])
    return {
        "data": result,
        "total": total,
        "page": page,
        "limit": limit
    }

@app.get("/api/receivables/summary")
def receivables_summary(page: int = 1, limit: int = 30, current_user: dict = Depends(get_current_user)):
    """Summarize receivables by customer with aging analysis."""
    db = get_db()
    
    # Calculate total unique customers with unpaid balance
    total_pipeline = [
        {"$match": {"is_deleted": False, "status": {"$ne": "paid"}}},
        {"$group": {"_id": "$customer_id"}},
        {"$count": "total"}
    ]
    total_res = list(db["receivables"].aggregate(total_pipeline))
    total = total_res[0]["total"] if total_res else 0
    
    skip = (page - 1) * limit
    pipeline = [
        {"$match": {"is_deleted": False, "status": {"$ne": "paid"}}},
        {"$group": {
            "_id": "$customer_id",
            "customer_name": {"$first": "$customer_name"},
            "total_amount": {"$sum": "$amount"},
            "total_paid": {"$sum": "$paid_amount"},
            "total_balance": {"$sum": "$balance"},
            "count": {"$sum": 1}
        }},
        {"$sort": {"total_balance": -1}},
        {"$skip": skip},
        {"$limit": limit}
    ]
    result = list(db["receivables"].aggregate(pipeline))
    return {
        "data": result,
        "total": total,
        "page": page,
        "limit": limit
    }


# ==================== Payables (應付帳款) ====================
@app.get("/api/payables")
def list_payables(vendor_id: Optional[str] = None, status: Optional[str] = None,
                  page: int = 1, limit: int = 30, current_user: dict = Depends(get_current_user)):
    db = get_db()
    q = {"is_deleted": False}
    if vendor_id: q["vendor_id"] = vendor_id
    if status: q["status"] = status
    total = db["payables"].count_documents(q)
    skip = (page - 1) * limit
    result = list(db["payables"].find(q).sort("date", -1).skip(skip).limit(limit))
    for r in result: r["_id"] = str(r["_id"])
    return {
        "data": result,
        "total": total,
        "page": page,
        "limit": limit
    }

@app.get("/api/payables/summary")
def payables_summary(page: int = 1, limit: int = 30, current_user: dict = Depends(get_current_user)):
    db = get_db()
    
    total_pipeline = [
        {"$match": {"is_deleted": False, "status": {"$ne": "paid"}}},
        {"$group": {"_id": "$vendor_id"}},
        {"$count": "total"}
    ]
    total_res = list(db["payables"].aggregate(total_pipeline))
    total = total_res[0]["total"] if total_res else 0
    
    skip = (page - 1) * limit
    pipeline = [
        {"$match": {"is_deleted": False, "status": {"$ne": "paid"}}},
        {"$group": {
            "_id": "$vendor_id",
            "vendor_name": {"$first": "$vendor_name"},
            "total_payable": {"$sum": "$amount"},
            "total_paid": {"$sum": "$paid_amount"},
            "balance": {"$sum": "$balance"},
            "count": {"$sum": 1}
        }},
        {"$sort": {"balance": -1}},
        {"$skip": skip},
        {"$limit": limit}
    ]
    result = list(db["payables"].aggregate(pipeline))
    return {
        "data": result,
        "total": total,
        "page": page,
        "limit": limit
    }


# ==================== Payments (收付款沖帳) ====================
@app.post("/api/payments", status_code=201)
def create_payment(payment: PaymentCreate, current_user: dict = Depends(get_current_user)):
    db = get_db()
    doc = payment.model_dump()
    doc.update(_audit_create(current_user["username"]))
    db["payments"].insert_one(doc)

    # Update the related receivable or payable
    if payment.payment_type == "receivable":
        recv = db["receivables"].find_one({"receivable_id": payment.ref_id, "is_deleted": False})
        if recv:
            new_paid = recv["paid_amount"] + payment.amount
            new_balance = recv["amount"] - new_paid
            new_status = "paid" if new_balance <= 0 else "partial"
            db["receivables"].update_one(
                {"receivable_id": payment.ref_id},
                {"$set": {"paid_amount": new_paid, "balance": max(0, new_balance), "status": new_status,
                          **_audit_update(current_user["username"])}})
            if new_status == "paid" and recv.get("order_id"):
                db["sales_orders"].update_one(
                    {"order_id": recv["order_id"]},
                    {"$set": {"payment_status": "已結清", **_audit_update(current_user["username"])}}
                )
    elif payment.payment_type == "payable":
        pay = db["payables"].find_one({"payable_id": payment.ref_id, "is_deleted": False})
        if pay:
            new_paid = pay["paid_amount"] + payment.amount
            new_balance = pay["amount"] - new_paid
            new_status = "paid" if new_balance <= 0 else "partial"
            db["payables"].update_one(
                {"payable_id": payment.ref_id},
                {"$set": {"paid_amount": new_paid, "balance": max(0, new_balance), "status": new_status,
                          **_audit_update(current_user["username"])}})
            if new_status == "paid" and pay.get("purchase_id"):
                db["purchase_orders"].update_one(
                    {"purchase_id": pay["purchase_id"]},
                    {"$set": {"payment_status": "已結清", **_audit_update(current_user["username"])}}
                )

    log_action(db, current_user["username"], "CREATE", "payment", f"Created payment {payment.payment_id}")
    return {"message": "Payment recorded", "payment_id": payment.payment_id}

@app.get("/api/payments")
def list_payments(payment_type: Optional[str] = None, page: int = 1, limit: int = 30, current_user: dict = Depends(get_current_user)):
    db = get_db()
    q = {"is_deleted": False}
    if payment_type: q["payment_type"] = payment_type
    total = db["payments"].count_documents(q)
    skip = (page - 1) * limit
    result = list(db["payments"].find(q).sort("date", -1).skip(skip).limit(limit))
    for r in result: r["_id"] = str(r["_id"])
    return {
        "data": result,
        "total": total,
        "page": page,
        "limit": limit
    }


# ==================== Notes/Checks (票據管理) ====================
@app.post("/api/notes", status_code=201)
def create_note(note: NoteCreate, current_user: dict = Depends(get_current_user)):
    db = get_db()
    doc = note.model_dump()
    doc.update(_audit_create(current_user["username"]))
    db["notes"].insert_one(doc)
    log_action(db, current_user["username"], "CREATE", "note", f"Created note {note.note_id}")
    return {"message": "Note created", "note_id": note.note_id}

@app.get("/api/notes")
def list_notes(note_type: Optional[str] = None, status: Optional[str] = None,
               page: int = 1, limit: int = 30, current_user: dict = Depends(get_current_user)):
    db = get_db()
    q = {"is_deleted": False}
    if note_type: q["note_type"] = note_type
    if status: q["status"] = status
    total = db["notes"].count_documents(q)
    skip = (page - 1) * limit
    result = list(db["notes"].find(q).sort("due_date", 1).skip(skip).limit(limit))
    for r in result: r["_id"] = str(r["_id"])
    return {
        "data": result,
        "total": total,
        "page": page,
        "limit": limit
    }

@app.put("/api/notes/{note_id}")
def update_note(note_id: str, note: NoteCreate, current_user: dict = Depends(get_current_user)):
    db = get_db()
    if not db["notes"].find_one({"note_id": note_id, "is_deleted": False}):
        raise HTTPException(status_code=404, detail="Note not found")
    data = note.model_dump()
    data.update(_audit_update(current_user["username"]))
    db["notes"].update_one({"note_id": note_id, "is_deleted": False}, {"$set": data})
    log_action(db, current_user["username"], "UPDATE", "note", f"Updated note {note_id}")
    return {"message": "Note updated"}

@app.put("/api/notes/{note_id}/clear")
def clear_note(note_id: str, current_user: dict = Depends(get_current_user)):
    """Mark a note as cleared (兌現)."""
    db = get_db()
    note = db["notes"].find_one({"note_id": note_id, "is_deleted": False})
    if not note: raise HTTPException(status_code=404, detail="Note not found")
    db["notes"].update_one({"note_id": note_id}, {"$set": {
        "status": "cleared", "cleared_date": _now(), **_audit_update(current_user["username"])
    }})
    log_action(db, current_user["username"], "CLEAR", "note", f"Cleared note {note_id}")
    return {"message": "Note marked as cleared"}

@app.delete("/api/notes/{note_id}")
def delete_note(note_id: str, current_user: dict = Depends(get_current_user)):
    db = get_db()
    if not db["notes"].find_one({"note_id": note_id, "is_deleted": False}):
        raise HTTPException(status_code=404, detail="Note not found")
    db["notes"].update_one({"note_id": note_id}, {"$set": _audit_delete(current_user["username"])})
    log_action(db, current_user["username"], "DELETE", "note", f"Deleted note {note_id}")
    return {"message": "Note deleted"}


# ============================================================
# 人事薪資模組 (Payroll)
# ============================================================

@app.post("/api/employees", status_code=201)
def create_employee(emp: EmployeeCreate, current_user: dict = Depends(get_current_user)):
    db = get_db()
    if db["employees"].find_one({"employee_id": emp.employee_id, "is_deleted": False}):
        raise HTTPException(status_code=400, detail="Employee ID already exists.")
    doc = emp.model_dump()
    doc.update(_audit_create(current_user["username"]))
    doc["is_deleted"] = False
    
    db["employees"].insert_one(doc)
    log_action(db, current_user["username"], "CREATE", "employee", f"Created employee {emp.employee_id}")
    return {"message": "Employee created"}

@app.get("/api/employees")
def list_employees(page: int = 1, limit: int = 30, current_user: dict = Depends(get_current_user)):
    db = get_db()
    total = db["employees"].count_documents({"is_deleted": False})
    skip = (page - 1) * limit
    result = list(db["employees"].find({"is_deleted": False}).skip(skip).limit(limit))
    for r in result: r["_id"] = str(r["_id"])
    return {
        "data": result,
        "total": total,
        "page": page,
        "limit": limit
    }

@app.put("/api/employees/{emp_id}")
def update_employee(emp_id: str, emp: EmployeeCreate, current_user: dict = Depends(get_current_user)):
    db = get_db()
    if not db["employees"].find_one({"employee_id": emp_id, "is_deleted": False}):
        raise HTTPException(status_code=404, detail="Employee not found")
    data = emp.model_dump()
    data.update(_audit_update(current_user["username"]))
    db["employees"].update_one({"employee_id": emp_id, "is_deleted": False}, {"$set": data})
    log_action(db, current_user["username"], "UPDATE", "employee", f"Updated employee {emp_id}")
    return {"message": "Employee updated"}

@app.delete("/api/employees/{emp_id}")
def delete_employee(emp_id: str, current_user: dict = Depends(get_current_user)):
    db = get_db()
    if not db["employees"].find_one({"employee_id": emp_id, "is_deleted": False}):
        raise HTTPException(status_code=404, detail="Employee not found")
    db["employees"].update_one({"employee_id": emp_id}, {"$set": _audit_delete(current_user["username"])})
    log_action(db, current_user["username"], "DELETE", "employee", f"Deleted employee {emp_id}")
    return {"message": "Employee deleted"}

@app.post("/api/payroll", status_code=201)
def create_payroll(record: PayrollRecordCreate, current_user: dict = Depends(get_current_user)):
    db = get_db()
    if db["payroll"].find_one({"payroll_id": record.payroll_id, "is_deleted": False}):
        raise HTTPException(status_code=400, detail="Payroll ID already exists.")
    doc = record.model_dump()
    doc.update(_audit_create(current_user["username"]))
    db["payroll"].insert_one(doc)
    log_action(db, current_user["username"], "CREATE", "payroll", f"Created payroll {record.payroll_id}")
    return {"message": "Payroll record created"}

@app.get("/api/payroll")
def list_payroll(year: Optional[int] = None, month: Optional[int] = None, page: int = 1, limit: int = 30, current_user: dict = Depends(get_current_user)):
    db = get_db()
    q = {"is_deleted": False}
    if year: q["year"] = year
    if month: q["month"] = month
    total = db["payroll"].count_documents(q)
    skip = (page - 1) * limit
    result = list(db["payroll"].find(q).sort([("year", -1), ("month", -1)]).skip(skip).limit(limit))
    for r in result: r["_id"] = str(r["_id"])
    return {
        "data": result,
        "total": total,
        "page": page,
        "limit": limit
    }

@app.put("/api/payroll/{payroll_id}/pay")
def pay_payroll(payroll_id: str, current_user: dict = Depends(get_current_user)):
    db = get_db()
    if not db["payroll"].find_one({"payroll_id": payroll_id, "is_deleted": False}):
        raise HTTPException(status_code=404, detail="Payroll not found")
    db["payroll"].update_one({"payroll_id": payroll_id}, {"$set": {"status": "paid", **_audit_update(current_user["username"])}})
    return {"message": "Payroll marked as paid"}

@app.delete("/api/payroll/{payroll_id}")
def delete_payroll(payroll_id: str, current_user: dict = Depends(get_current_user)):
    db = get_db()
    if not db["payroll"].find_one({"payroll_id": payroll_id, "is_deleted": False}):
        raise HTTPException(status_code=404, detail="Payroll not found")
    db["payroll"].update_one({"payroll_id": payroll_id}, {"$set": _audit_delete(current_user["username"])})
    return {"message": "Payroll deleted"}


# ============================================================
# Excel Print Engine API
# ============================================================

@app.get("/api/print/sales/{order_id}")
def print_sales_order(order_id: str, current_user: dict = Depends(get_current_user)):
    db = get_db()
    order = db["sales_orders"].find_one({"order_id": order_id, "is_deleted": False})
    if not order: raise HTTPException(status_code=404, detail="Sales Order not found")
    
    excel_bytes = create_sales_order_excel(order)
    return Response(
        content=excel_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename=SalesOrder_{order_id}.xlsx"}
    )

@app.get("/api/print/purchases/{order_id}")
def print_purchase_order(order_id: str, current_user: dict = Depends(get_current_user)):
    db = get_db()
    order = db["purchase_orders"].find_one({"purchase_id": order_id, "is_deleted": False})
    if not order: raise HTTPException(status_code=404, detail="Purchase Order not found")
    
    excel_bytes = create_purchase_order_excel(order)
    return Response(
        content=excel_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename=PurchaseOrder_{order_id}.xlsx"}
    )

@app.get("/api/print/quotes/{quote_id}")
def print_quote(quote_id: str, current_user: dict = Depends(get_current_user)):
    db = get_db()
    order = db["quotes"].find_one({"quote_id": quote_id, "is_deleted": False})
    if not order: raise HTTPException(status_code=404, detail="Quote not found")
    
    excel_bytes = create_quote_excel(order)
    return Response(
        content=excel_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename=Quote_{quote_id}.xlsx"}
    )

@app.post("/api/print/envelopes")
def print_envelopes(party_ids: List[str], is_return: bool = False, current_user: dict = Depends(get_current_user)):
    db = get_db()
    # Find parties in both customers and vendors
    parties = list(db["customers"].find({"customer_id": {"$in": party_ids}}))
    parties += list(db["vendors"].find({"vendor_id": {"$in": party_ids}}))
    
    if not parties:
        raise HTTPException(status_code=404, detail="No parties found")
    
    # We just print the first one for the envelope demo (since envelope usually is 1 page per file or multi-sheet)
    # For simplicity, returning the first selected party's envelope
    excel_bytes = create_envelope_excel(parties[0], is_return=is_return)
    return Response(
        content=excel_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename=Envelope.xlsx"}
    )

@app.post("/api/print/labels")
def print_address_labels(party_ids: List[str], current_user: dict = Depends(get_current_user)):
    db = get_db()
    parties = list(db["customers"].find({"customer_id": {"$in": party_ids}}))
    parties += list(db["vendors"].find({"vendor_id": {"$in": party_ids}}))
    
    excel_bytes = create_address_label_excel(parties)
    return Response(
        content=excel_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename=AddressLabels.xlsx"}
    )

# ==================== Reports ====================
@app.get("/api/reports/profit-loss")
def profit_loss_report(year: Optional[int] = None, month: Optional[int] = None,
                       current_user: dict = Depends(get_current_user)):
    """Virtual P&L report: Revenue (sales) - Cost (purchases) = Gross Profit."""
    db = get_db()

    # Build date filter
    date_match = {"is_deleted": False}
    if year:
        start = datetime(year, 1, 1, tzinfo=timezone.utc)
        end = datetime(year + 1, 1, 1, tzinfo=timezone.utc)
        if month:
            start = datetime(year, month, 1, tzinfo=timezone.utc)
            end_month = month + 1 if month < 12 else 1
            end_year = year if month < 12 else year + 1
            end = datetime(end_year, end_month, 1, tzinfo=timezone.utc)
        date_match["date"] = {"$gte": start, "$lt": end}

    # Revenue from sales
    sales_pipeline = [
        {"$match": date_match},
        {"$group": {
            "_id": None,
            "total_revenue": {"$sum": "$grand_total"},
            "order_count": {"$sum": 1}
        }}
    ]
    sales_result = list(db["sales_orders"].aggregate(sales_pipeline))
    revenue = sales_result[0]["total_revenue"] if sales_result else 0
    order_count = sales_result[0]["order_count"] if sales_result else 0

    # Cost from purchases
    purchase_pipeline = [
        {"$match": date_match},
        {"$group": {
            "_id": None,
            "total_cost": {"$sum": "$grand_total"},
            "purchase_count": {"$sum": 1}
        }}
    ]
    purchase_result = list(db["purchase_orders"].aggregate(purchase_pipeline))
    cost = purchase_result[0]["total_cost"] if purchase_result else 0
    purchase_count = purchase_result[0]["purchase_count"] if purchase_result else 0

    gross_profit = revenue - cost
    margin = (gross_profit / revenue * 100) if revenue > 0 else 0

    # Monthly breakdown
    monthly_pipeline = [
        {"$match": date_match},
        {"$group": {
            "_id": {"$month": "$date"},
            "revenue": {"$sum": "$grand_total"},
            "count": {"$sum": 1}
        }},
        {"$sort": {"_id": 1}}
    ]
    monthly_revenue = list(db["sales_orders"].aggregate(monthly_pipeline))
    monthly_cost_pipeline = [
        {"$match": date_match},
        {"$group": {
            "_id": {"$month": "$date"},
            "cost": {"$sum": "$grand_total"},
            "count": {"$sum": 1}
        }},
        {"$sort": {"_id": 1}}
    ]
    monthly_cost = list(db["purchase_orders"].aggregate(monthly_cost_pipeline))

    return {
        "year": year, "month": month,
        "total_revenue": revenue,
        "total_cost": cost,
        "gross_profit": gross_profit,
        "margin_percent": round(margin, 2),
        "order_count": order_count,
        "purchase_count": purchase_count,
        "monthly_revenue": monthly_revenue,
        "monthly_cost": monthly_cost
    }


@app.get("/api/reports/customer-abc")
def customer_abc_report(year: Optional[int] = None, current_user: dict = Depends(get_current_user)):
    """Rank customers by total sales amount into A/B/C categories."""
    db = get_db()
    match = {"is_deleted": False}
    if year:
        match["date"] = {"$gte": datetime(year, 1, 1, tzinfo=timezone.utc),
                         "$lt": datetime(year + 1, 1, 1, tzinfo=timezone.utc)}
    pipeline = [
        {"$match": match},
        {"$group": {
            "_id": "$customer_id",
            "customer_name": {"$first": "$customer_name"},
            "total_amount": {"$sum": "$grand_total"},
            "order_count": {"$sum": 1}
        }},
        {"$sort": {"total_amount": -1}}
    ]
    customers = list(db["sales_orders"].aggregate(pipeline))
    # Assign ABC rating (top 20% = A, next 30% = B, rest = C)
    total = len(customers)
    for i, c in enumerate(customers):
        if i < total * 0.2:
            c["rating"] = "A"
        elif i < total * 0.5:
            c["rating"] = "B"
        else:
            c["rating"] = "C"
    return customers


@app.get("/api/reports/vendor-abc")
def vendor_abc_report(year: Optional[int] = None, current_user: dict = Depends(get_current_user)):
    """Rank vendors by total purchase amount into A/B/C categories."""
    db = get_db()
    match = {"is_deleted": False}
    if year:
        match["date"] = {"$gte": datetime(year, 1, 1, tzinfo=timezone.utc),
                         "$lt": datetime(year + 1, 1, 1, tzinfo=timezone.utc)}
    pipeline = [
        {"$match": match},
        {"$group": {
            "_id": "$vendor_id",
            "vendor_name": {"$first": "$vendor_name"},
            "total_amount": {"$sum": "$grand_total"},
            "purchase_count": {"$sum": 1}
        }},
        {"$sort": {"total_amount": -1}}
    ]
    vendors = list(db["purchase_orders"].aggregate(pipeline))
    total = len(vendors)
    for i, v in enumerate(vendors):
        if i < total * 0.2:
            v["rating"] = "A"
        elif i < total * 0.5:
            v["rating"] = "B"
        else:
            v["rating"] = "C"
    return vendors

import os
from fastapi.responses import FileResponse

frontend_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../frontend"))

@app.get("/")
def serve_index():
    return FileResponse(os.path.join(frontend_path, "index.html"))

app.mount("/", StaticFiles(directory=frontend_path, html=True), name="frontend")
