-- =====================================================================
-- Hospital Appointment Management System (HAMS)
-- Relational Database Schema (PostgreSQL dialect; SQLite-compatible
-- with minor type adjustments — see backend/database.py which auto-
-- generates this same structure via SQLAlchemy for the demo app)
-- =====================================================================

-- ---------------------------------------------------------------------
-- 1. USERS  (base identity table shared by Patient / Doctor / Admin)
-- ---------------------------------------------------------------------
CREATE TABLE users (
    user_id         SERIAL PRIMARY KEY,
    full_name       VARCHAR(120)  NOT NULL,
    email           VARCHAR(150)  NOT NULL UNIQUE,
    phone           VARCHAR(20)   NOT NULL,
    password_hash   VARCHAR(255)  NOT NULL,
    role            VARCHAR(10)   NOT NULL CHECK (role IN ('PATIENT','DOCTOR','ADMIN')),
    is_active       BOOLEAN       NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- ---------------------------------------------------------------------
-- 2. DEPARTMENTS  (specialties, e.g. Cardiology, Dermatology)
-- ---------------------------------------------------------------------
CREATE TABLE departments (
    department_id   SERIAL PRIMARY KEY,
    name            VARCHAR(100)  NOT NULL UNIQUE,
    description     VARCHAR(500)
);

-- ---------------------------------------------------------------------
-- 3. PATIENTS  (extends users)
-- ---------------------------------------------------------------------
CREATE TABLE patients (
    patient_id      INTEGER PRIMARY KEY REFERENCES users(user_id) ON DELETE CASCADE,
    date_of_birth   DATE,
    gender          VARCHAR(10) CHECK (gender IN ('MALE','FEMALE','OTHER')),
    address         VARCHAR(255),
    blood_group     VARCHAR(5)
);

-- ---------------------------------------------------------------------
-- 4. DOCTORS  (extends users)
-- ---------------------------------------------------------------------
CREATE TABLE doctors (
    doctor_id           INTEGER PRIMARY KEY REFERENCES users(user_id) ON DELETE CASCADE,
    department_id       INTEGER NOT NULL REFERENCES departments(department_id),
    specialization      VARCHAR(120) NOT NULL,
    qualification        VARCHAR(150),
    experience_years    INTEGER DEFAULT 0,
    consultation_fee    NUMERIC(10,2) DEFAULT 0.00
);

-- ---------------------------------------------------------------------
-- 5. DOCTOR_AVAILABILITY  (recurring weekly working hours + slot size)
-- ---------------------------------------------------------------------
CREATE TABLE doctor_availability (
    availability_id     SERIAL PRIMARY KEY,
    doctor_id           INTEGER NOT NULL REFERENCES doctors(doctor_id) ON DELETE CASCADE,
    day_of_week         SMALLINT NOT NULL CHECK (day_of_week BETWEEN 0 AND 6), -- 0=Mon ... 6=Sun
    start_time          TIME NOT NULL,
    end_time            TIME NOT NULL,
    slot_duration_mins  SMALLINT NOT NULL DEFAULT 15 CHECK (slot_duration_mins > 0),
    is_active           BOOLEAN NOT NULL DEFAULT TRUE,
    CONSTRAINT chk_time_order CHECK (end_time > start_time),
    -- prevents a doctor from having two overlapping availability windows
    -- on the same day (application layer also validates this)
    UNIQUE (doctor_id, day_of_week, start_time, end_time)
);

-- ---------------------------------------------------------------------
-- 6. APPOINTMENTS  (the core booking table)
-- ---------------------------------------------------------------------
CREATE TABLE appointments (
    appointment_id      SERIAL PRIMARY KEY,
    patient_id           INTEGER NOT NULL REFERENCES patients(patient_id),
    doctor_id            INTEGER NOT NULL REFERENCES doctors(doctor_id),
    appointment_date     DATE NOT NULL,
    slot_start_time       TIME NOT NULL,
    slot_end_time         TIME NOT NULL,
    status                VARCHAR(15) NOT NULL DEFAULT 'BOOKED'
                          CHECK (status IN ('BOOKED','CANCELLED','COMPLETED','IN_PROGRESS','NO_SHOW')),
    reason                VARCHAR(255),
    created_at            TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at            TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    -- =================================================================
    -- DOUBLE-BOOKING PREVENTION (the critical business constraint)
    -- A given doctor cannot have two ACTIVE (non-cancelled) appointments
    -- for the exact same date + start time. Combined with the app-level
    -- transactional check in appointments.py, this gives us both an
    -- optimistic in-app guard AND a hard DB-level guarantee, so even
    -- concurrent requests from two patients cannot both succeed.
    -- =================================================================
    CONSTRAINT uq_doctor_slot UNIQUE (doctor_id, appointment_date, slot_start_time)
);

CREATE INDEX idx_appt_patient   ON appointments(patient_id);
CREATE INDEX idx_appt_doctor_date ON appointments(doctor_id, appointment_date);

-- ---------------------------------------------------------------------
-- Note on the UNIQUE constraint + cancellations:
-- Because CANCELLED rows keep their (doctor_id, date, start_time) tuple,
-- a naive UNIQUE constraint would block re-booking a cancelled slot.
-- Production systems handle this with a partial/filtered unique index:
--   CREATE UNIQUE INDEX uq_doctor_slot_active ON appointments
--     (doctor_id, appointment_date, slot_start_time)
--     WHERE status IN ('BOOKED','IN_PROGRESS','COMPLETED');
-- (Postgres/SQLite support partial indexes; MySQL does not, so MySQL
-- deployments must enforce this rule purely in the application
-- transaction — see AI_DEVELOPMENT_REPORT for the discussion.)
-- ---------------------------------------------------------------------
CREATE UNIQUE INDEX uq_doctor_slot_active ON appointments
    (doctor_id, appointment_date, slot_start_time)
    WHERE status IN ('BOOKED','IN_PROGRESS','COMPLETED');
