"""
models.py
---------
SQLAlchemy ORM models mirroring database/schema.sql.
"""
import enum
from datetime import datetime

from sqlalchemy import (
    Column, Integer, String, Boolean, Date, Time, DateTime, ForeignKey,
    Numeric, SmallInteger, UniqueConstraint, Enum
)
from sqlalchemy.orm import relationship

from database import Base


class RoleEnum(str, enum.Enum):
    PATIENT = "PATIENT"
    DOCTOR = "DOCTOR"
    ADMIN = "ADMIN"


class AppointmentStatus(str, enum.Enum):
    BOOKED = "BOOKED"
    WAITING = "WAITING"
    CANCELLED = "CANCELLED"
    COMPLETED = "COMPLETED"
    IN_PROGRESS = "IN_PROGRESS"
    NO_SHOW = "NO_SHOW"


class User(Base):
    __tablename__ = "users"

    user_id = Column(Integer, primary_key=True, index=True)
    full_name = Column(String(120), nullable=False)
    email = Column(String(150), unique=True, nullable=False, index=True)
    phone = Column(String(20), nullable=False)
    password_hash = Column(String(255), nullable=False)
    role = Column(Enum(RoleEnum), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    patient_profile = relationship("Patient", back_populates="user", uselist=False, cascade="all,delete")
    doctor_profile = relationship("Doctor", back_populates="user", uselist=False, cascade="all,delete")


class Department(Base):
    __tablename__ = "departments"

    department_id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, nullable=False)
    description = Column(String(500))

    doctors = relationship("Doctor", back_populates="department")


class Patient(Base):
    __tablename__ = "patients"

    patient_id = Column(Integer, ForeignKey("users.user_id", ondelete="CASCADE"), primary_key=True)
    date_of_birth = Column(Date, nullable=True)
    gender = Column(String(10), nullable=True)
    address = Column(String(255), nullable=True)
    blood_group = Column(String(5), nullable=True)

    user = relationship("User", back_populates="patient_profile")
    appointments = relationship("Appointment", back_populates="patient")


class Doctor(Base):
    __tablename__ = "doctors"

    doctor_id = Column(Integer, ForeignKey("users.user_id", ondelete="CASCADE"), primary_key=True)
    department_id = Column(Integer, ForeignKey("departments.department_id"), nullable=False)
    specialization = Column(String(120), nullable=False)
    qualification = Column(String(150), nullable=True)
    experience_years = Column(Integer, default=0)
    consultation_fee = Column(Numeric(10, 2), default=0)

    user = relationship("User", back_populates="doctor_profile")
    department = relationship("Department", back_populates="doctors")
    availability = relationship("DoctorAvailability", back_populates="doctor", cascade="all,delete")
    appointments = relationship("Appointment", back_populates="doctor")


class DoctorAvailability(Base):
    __tablename__ = "doctor_availability"
    __table_args__ = (
        UniqueConstraint("doctor_id", "day_of_week", "start_time", "end_time", name="uq_availability_window"),
    )

    availability_id = Column(Integer, primary_key=True, index=True)
    doctor_id = Column(Integer, ForeignKey("doctors.doctor_id", ondelete="CASCADE"), nullable=False)
    day_of_week = Column(SmallInteger, nullable=False)  # 0=Mon ... 6=Sun
    start_time = Column(Time, nullable=False)
    end_time = Column(Time, nullable=False)
    slot_duration_mins = Column(SmallInteger, nullable=False, default=15)
    is_active = Column(Boolean, default=True)

    doctor = relationship("Doctor", back_populates="availability")


class Appointment(Base):
    __tablename__ = "appointments"
    __table_args__ = (
        # DB-level guarantee against double booking for the SAME doctor
        # + date + start time. See AI_DEVELOPMENT_REPORT for the note on
        # partial-index handling of cancelled rows in production DBs.
        UniqueConstraint("doctor_id", "appointment_date", "slot_start_time", name="uq_doctor_slot"),
    )

    appointment_id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(Integer, ForeignKey("patients.patient_id"), nullable=False)
    doctor_id = Column(Integer, ForeignKey("doctors.doctor_id"), nullable=False)
    appointment_date = Column(Date, nullable=False)
    slot_start_time = Column(Time, nullable=False)
    slot_end_time = Column(Time, nullable=False)
    status = Column(Enum(AppointmentStatus), default=AppointmentStatus.BOOKED, nullable=False)
    reason = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    patient = relationship("Patient", back_populates="appointments")
    doctor = relationship("Doctor", back_populates="appointments")

    @property
    def doctor_name(self):
        return self.doctor.user.full_name if self.doctor and self.doctor.user else None

    @property
    def department_name(self):
        return self.doctor.department.name if self.doctor and self.doctor.department else None

    @property
    def patient_name(self):
        return self.patient.user.full_name if self.patient and self.patient.user else None


    @property
    def patient_phone(self):
        return self.patient.user.phone if self.patient and self.patient.user else None


class SmsNotification(Base):
    """
    Tracks which appointments have already triggered an SMS queue-position notification.
    Prevents duplicate alerts across server restarts and repeated poll cycles.
    """
    __tablename__ = "sms_notifications"

    id = Column(Integer, primary_key=True, index=True)
    appointment_id = Column(
        Integer,
        ForeignKey("appointments.appointment_id", ondelete="CASCADE"),
        nullable=False,
        unique=True,   # one notification per appointment
        index=True,
    )
    queue_position_at_notification = Column(Integer, nullable=False)
    sent_at = Column(DateTime, default=datetime.utcnow, nullable=False)
