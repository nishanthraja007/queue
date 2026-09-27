"""
routers/auth_router.py
-----------------------
(a) PATIENT LOGIN / AUTHENTICATION
Handles patient self-registration and login for ALL roles (Patient,
Doctor, Admin share one users table but doctors/admins are provisioned
by an administrator rather than self-registering).
"""
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

import models
import schemas
from database import get_db
from auth import hash_password, verify_password, create_access_token, get_current_user

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/register", response_model=schemas.UserOut, status_code=status.HTTP_201_CREATED)
def register_patient(payload: schemas.PatientRegister, db: Session = Depends(get_db)):
    """Public self-registration endpoint for patients."""
    existing = db.query(models.User).filter(models.User.email == payload.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="An account with this email already exists.")

    user = models.User(
        full_name=payload.full_name,
        email=payload.email,
        phone=payload.phone,
        password_hash=hash_password(payload.password),
        role=models.RoleEnum.PATIENT,
    )
    db.add(user)
    db.flush()  # get user.user_id before commit

    patient = models.Patient(
        patient_id=user.user_id,
        date_of_birth=payload.date_of_birth,
        gender=payload.gender,
        address=payload.address,
    )
    db.add(patient)
    db.commit()
    db.refresh(user)
    return user


@router.post("/login", response_model=schemas.Token)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    """
    OAuth2-compatible login. `form_data.username` is the user's email.
    Works identically for Patient / Doctor / Admin accounts -- the JWT
    payload embeds the role so downstream endpoints can authorize
    correctly (see auth.require_role()).
    """
    user = db.query(models.User).filter(models.User.email == form_data.username).first()

    # Constant-shape error to avoid leaking whether the email exists.
    if not user or not verify_password(form_data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        raise HTTPException(status_code=403, detail="This account has been deactivated.")

    token = create_access_token(data={"sub": str(user.user_id), "role": user.role.value})
    return schemas.Token(
        access_token=token,
        token_type="bearer",
        role=user.role.value,
        user_id=user.user_id,
        full_name=user.full_name,
    )


@router.get("/me", response_model=schemas.UserOut)
def get_me(current_user: models.User = Depends(get_current_user)):
    """Returns the authenticated user's profile."""
    return current_user

