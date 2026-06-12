from fastapi import APIRouter, Depends, HTTPException
from typing import Optional
from backend.database import get_db
from backend.auth import (
    get_password_hash, verify_password, create_access_token, get_current_user,
    ACCESS_TOKEN_EXPIRE_MINUTES
)
from backend.domain.auth.models import (
    LoginRequest, Token, UserCreate, UserResponse, PasswordUpdate, SettingsUpdate
)
from datetime import timedelta, datetime, timezone
import uuid

router = APIRouter(prefix="/api", tags=["Auth"])

def _now():
    return datetime.now(timezone.utc)

def _audit_create(username: str) -> dict:
    return {"created_by": username, "created_at": _now(), "is_deleted": False,
            "updated_by": None, "updated_at": None, "deleted_by": None, "deleted_at": None}

def _audit_update(username: str) -> dict:
    return {"updated_by": username, "updated_at": _now()}

def _audit_delete(username: str) -> dict:
    return {"is_deleted": True, "deleted_by": username, "deleted_at": _now()}

def log_action(db, username: str, action: str, entity: str, description: str):
    db["system_logs"].insert_one({
        "username": username,
        "action": action,
        "entity": entity,
        "description": description,
        "timestamp": _now()
    })

@router.post("/setup-admin", status_code=201)
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

@router.post("/login", response_model=Token)
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

@router.get("/me")
def read_users_me(current_user: dict = Depends(get_current_user)):
    return {"username": current_user["username"], "role": current_user["role"], "is_active": current_user["is_active"]}

@router.get("/logs")
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

@router.get("/users")
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

@router.post("/users", response_model=UserResponse)
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

@router.put("/users/{username}/password")
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

@router.delete("/users/{username}")
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

@router.get("/settings/permissions")
def get_permissions(current_user: dict = Depends(get_current_user)):
    db = get_db()
    doc = db["settings"].find_one({"_id": "permissions"})
    if not doc:
        return {"staff_visible_menus": []}
    return {"staff_visible_menus": doc.get("staff_visible_menus", [])}

@router.put("/settings/permissions")
def update_permissions(payload: SettingsUpdate, current_user: dict = Depends(get_current_user)):
    if current_user["role"] != "owner":
        raise HTTPException(status_code=403, detail="Forbidden")
    db = get_db()
    db["settings"].update_one(
        {"_id": "permissions"},
        {"$set": {"staff_visible_menus": payload.staff_visible_menus}},
        upsert=True
    )
    log_action(db, current_user["username"], "UPDATE", "permissions", f"Updated staff menus to {payload.staff_visible_menus}")
    return {"message": "Permissions updated"}
