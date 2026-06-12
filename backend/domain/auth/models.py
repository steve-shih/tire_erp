from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime, timezone

class AuditModel(BaseModel):
    created_by: str = "system"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_by: Optional[str] = None
    updated_at: Optional[datetime] = None
    is_deleted: bool = False
    deleted_by: Optional[str] = None
    deleted_at: Optional[datetime] = None

class UserBase(BaseModel):
    username: str
    role: str = "staff"  # owner, manager, staff
    is_active: bool = True

class UserCreate(UserBase):
    password: str

class UserInDB(UserBase, AuditModel):
    hashed_password: str

class UserResponse(UserBase):
    username: str
    role: str
    is_active: bool

class LoginRequest(BaseModel):
    username: str
    password: str

class PasswordUpdate(BaseModel):
    password: str

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    username: Optional[str] = None

class SettingsUpdate(BaseModel):
    staff_visible_menus: List[str]

class SystemLog(BaseModel):
    log_id: str
    timestamp: datetime
    username: str
    action: str
    target: str
    details: str
