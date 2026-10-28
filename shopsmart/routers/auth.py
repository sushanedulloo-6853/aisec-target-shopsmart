from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from shopsmart.auth import Principal, create_access_token, enforce_login_rate_limit, get_current_user, verify_password
from shopsmart.db import get_db
from shopsmart.models import User

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    merchant_id: int | None


@router.post("/login", response_model=TokenResponse, dependencies=[Depends(enforce_login_rate_limit)])
def login(req: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    user = db.scalar(select(User).where(User.email == req.email.lower().strip()))
    if user is None or not verify_password(req.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")
    return TokenResponse(access_token=create_access_token(user), role=user.role, merchant_id=user.merchant_id)


@router.get("/me")
def me(principal: Principal = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    user = db.get(User, principal.user_id)
    return {
        "id": user.id,
        "email": user.email,
        "full_name": user.full_name,
        "role": user.role,
        "merchant_id": user.merchant_id,
        "loyalty_tier": user.loyalty_tier,
    }
