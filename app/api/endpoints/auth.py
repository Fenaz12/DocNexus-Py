# app/api/endpoints/auth.py
from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordRequestForm
from jose import jwt
from datetime import datetime, timedelta, timezone
from pydantic import BaseModel, EmailStr

# Import services
from app.services.user_service import create_user, get_user_by_email, verify_password, get_user_by_id
# Import centralized config and dependencies
from app.core.config import settings
from app.api.endpoints.dependencies import get_current_user_id, oauth2_scheme

router = APIRouter()

# --- Models can stay here or move to schemas/ ---
class Token(BaseModel):
    access_token: str
    token_type: str
    user: dict

class UserCreate(BaseModel):
    email: EmailStr
    password: str

class UserResponse(BaseModel):
    id: str
    email: str
    username: str

# --- Helper function using Settings ---
def create_access_token(data: dict, expires_delta: timedelta = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode.update({"exp": expire})
    # Use settings here
    encoded_jwt = jwt.encode(to_encode, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)
    return encoded_jwt

@router.post("/register", response_model=UserResponse)
async def register(user_data: UserCreate, request: Request):
    """Register a new user"""
    pool = request.app.state.pool
    
    if len(user_data.password) < 6:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must be at least 6 characters"
        )
    
    try:
        user = await create_user(pool, user_data.email, user_data.password)
        return user
    except ValueError as e:
        # Handle "User already exists" nicely
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        print(f"Registration error: {e}")
        raise HTTPException(status_code=500, detail="Registration failed")

@router.post("/login", response_model=Token)
async def login(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends()
):
    pool = request.app.state.pool
    
    user = await get_user_by_email(pool, form_data.username)
    
    # Combined check for security (prevents timing attacks/user enumeration)
    if not user or not await verify_password(form_data.password, user["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    if not user.get("is_active", True):
        raise HTTPException(status_code=400, detail="Inactive user")
    
    access_token = create_access_token(
        data={"sub": user["id"]}
    )
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": {
            "id": user["id"],
            "email": user["email"],
            "username": user["username"]
        }
    }

# --- Improved /me endpoint ---
@router.get("/me", response_model=UserResponse)
async def get_current_user(
    request: Request,
    # Reuse the logic from dependencies.py!
    user_id: str = Depends(get_current_user_id) 
):
    """Get current authenticated user"""
    pool = request.app.state.pool
    
    user = await get_user_by_id(pool, user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found"
        )
    
    return user 