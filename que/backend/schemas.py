"""
schemas.py
----------
Pydantic models used for request validation and response serialization.
"""
from datetime import date, time, datetime
from typing import Optional, List
from pydantic import BaseModel, EmailStr, Field


# ---------- Auth / Users ----------
class PatientRegister(BaseModel):
    full_name: str = Field(..., min_length=2, max_length=120)
    email: str
    phone: str = Field(..., min_length=7, max_length=20)
    password: str = Field(..., min_length=6)
    date_of_birth: Optional[date] = None
    gender: Optional[str] = None
    address: Optional[str] = None


class UserOut(BaseModel):
    user_id: int
    full_name: str
    email: str
    role: str

    class Config:
        from_attributes = True


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: Optional[str] = None
    user_id: Optional[int] = None
    full_name: Optional[str] = None


# ---------- Departments / Doctors ----------
class DepartmentOut(BaseModel):
    department_id: int
    name: str
    description: Optional[str] = None

    class Config:
        from_attributes = True


class DoctorOut(BaseModel):
    doctor_id: int
    full_name: str
    department: str
    specialization: str
    qualification: Optional[str] = None
    experience_years: int
    consultation_fee: float

    class Config:
        from_attributes = True


class SlotOut(BaseModel):
    start_time: time
    end_time: time
    is_available: bool


# ---------- Appointments ----------
class AppointmentCreate(BaseModel):
    doctor_id: int
    appointment_date: date
    slot_start_time: time
    reason: Optional[str] = None


class AppointmentOut(BaseModel):
    appointment_id: int
    doctor_id: int
    patient_id: int
    appointment_date: date
    slot_start_time: time
    slot_end_time: time
    status: str
    reason: Optional[str] = None
    created_at: datetime
    doctor_name: Optional[str] = None
    department_name: Optional[str] = None
    patient_name: Optional[str] = None
    patient_phone: Optional[str] = None

    class Config:
        from_attributes = True


class AppointmentStatusUpdate(BaseModel):
    status: str  # COMPLETED | IN_PROGRESS | NO_SHOW
