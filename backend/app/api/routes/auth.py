"""
api/routes/auth.py — Authentication endpoints.

POST /api/auth/register  → 201 UserResponse
POST /api/auth/login     → 200 TokenResponse
GET  /api/auth/me        → 200 UserResponse (requires Bearer)

Security notes:
  - Wrong email and wrong password return the SAME 401 message (no enumeration).
  - password_hash never appears in any response (UserResponse excludes it).
  - Passwords are never logged.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.core.security import create_access_token, hash_password, verify_password
from app.models.user import User
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse, UserResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])

_WRONG_CREDS = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Invalid email or password.",
    headers={"WWW-Authenticate": "Bearer"},
)


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register(body: RegisterRequest, db: Session = Depends(get_db)) -> UserResponse:
    """Create a new user. Emails are stored lowercase."""
    email = body.email.lower()

    existing = db.query(User).filter(User.email == email).first()
    if existing:
        raise HTTPException(status_code=409, detail="Email already registered.")

    user = User(
        name=body.name,
        email=email,
        password_hash=hash_password(body.password),
        role="user",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    logger.info("New user registered: id=%s", user.id)
    return UserResponse.model_validate(user)


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    """Authenticate and return a JWT access token."""
    email = body.email.lower()
    user = db.query(User).filter(User.email == email).first()

    # Same 401 for both "unknown email" and "wrong password" to prevent enumeration.
    if user is None or not verify_password(body.password, user.password_hash):
        raise _WRONG_CREDS

    token = create_access_token(str(user.id))
    logger.info("User logged in: id=%s", user.id)
    return TokenResponse(access_token=token)


@router.get("/me", response_model=UserResponse)
def me(current_user: User = Depends(get_current_user)) -> UserResponse:
    """Return the authenticated user's profile."""
    return UserResponse.model_validate(current_user)
