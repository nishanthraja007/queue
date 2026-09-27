# 3. Technical Documentation
## Hospital Appointment Management System (HAMS)

---

## 3.1 Project Overview

The **Hospital Appointment Management System (HAMS)** is a web-based platform that digitizes the end-to-end consultation-booking journey for a multi-specialty hospital, replacing manual phone/reception-counter scheduling.

**Core capabilities delivered in this MVP:**
- **Patients** register, log in, search doctors by department/specialty, view real-time available slots, book/cancel appointments, and review their appointment history.
- **Doctors** define recurring weekly availability (days, hours, slot length), view their daily consultation queue, and update each appointment's status (Completed / In-Progress / No-Show).
- **Administrators** onboard doctors, manage departments/specialties, and pull an operational summary report (volume, status breakdown, utilization counts).

**Non-functional priorities addressed:**
- **Data integrity:** the appointment table is protected by a database-level uniqueness constraint, so double-booking is *structurally impossible*, not just discouraged by application logic.
- **Security:** passwords are hashed with bcrypt (never stored/transmitted in plaintext); all protected endpoints require a signed JWT and enforce role-based access control.
- **Accuracy of availability data:** available slots are computed **dynamically** at request time from (doctor's recurring availability − existing active bookings), so the numbers shown to a patient are always current — there's no separately-maintained "slots" table that could drift out of sync.

---

## 3.2 Technology Stack

| Layer | Technology | Rationale |
|---|---|---|
| **Backend Framework** | Python 3.12 + **FastAPI** | Async-ready, automatic OpenAPI/Swagger docs (`/docs`), first-class Pydantic validation — ideal for rapid, well-typed API development and easy grading/demoing. |
| **ORM / Data Layer** | **SQLAlchemy 2.0** | Portable across SQLite (dev/demo) and PostgreSQL/MySQL (production) with zero code changes beyond the connection string. |
| **Database** | **SQLite** (bundled, zero-config demo) — swappable to **PostgreSQL** in production | SQLite lets graders run the project instantly; Postgres is the recommended production target for its robust partial-index and concurrency support. |
| **Authentication** | **JWT** (`python-jose`) + **bcrypt** password hashing (`passlib`) | Stateless auth suits a REST API; bcrypt is the industry-standard adaptive hash for credential storage. |
| **API Validation** | **Pydantic v2** | Declarative request/response schemas with automatic 422 validation errors. |
| **Frontend (recommended)** | React (or any SPA framework) consuming the REST API | Not included in this MVP scope per the assignment's backend-focus, but the API is fully CORS-enabled and ready for any frontend. |
| **API Testing / Docs** | **Swagger UI** (auto-generated at `/docs`), `curl` | Lets graders exercise every endpoint interactively without writing a frontend. |
| **Dev Tools** | `uvicorn` (ASGI server), `pip`, `venv` | Standard, lightweight Python web-serving toolchain. |

---

## 3.3 Step-by-Step Installation & Setup Guide

### 3.3.1 Prerequisites

| Requirement | Minimum Version | Check with |
|---|---|---|
| Python | 3.10+ (built/tested on 3.12) | `python3 --version` |
| pip | Latest | `pip --version` |
| (Optional, production) PostgreSQL | 13+ | `psql --version` |

### 3.3.2 Project Structure

```
hams/
├── backend/
│   ├── main.py                    # FastAPI app entrypoint + seed data
│   ├── database.py                # DB engine/session config
│   ├── models.py                  # SQLAlchemy ORM models
│   ├── schemas.py                 # Pydantic request/response schemas
│   ├── auth.py                    # JWT + password hashing + RBAC
│   ├── requirements.txt
│   └── routers/
│       ├── auth_router.py         # Registration + Login
│       ├── doctors_router.py      # Search, filter, dynamic slot calc
│       ├── appointments_router.py # Booking, cancel, history, queue
│       └── admin_router.py        # Department/doctor management, reports
├── database/
│   └── schema.sql                 # Raw SQL DDL (Postgres dialect)
├── 01_Requirement_Analysis_and_Design.md
├── 02_Technical_Documentation.md   (this file)
├── 03_AI_Development_Report.md
└── README.md
```

### 3.3.3 Environment Setup

```bash
# 1. Clone / unzip the project, then move into the backend folder
cd hams/backend

# 2. Create and activate a virtual environment
python3 -m venv venv
source venv/bin/activate        # On Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt
```

> **Note on bcrypt version:** `requirements.txt` pins `bcrypt==4.0.1` alongside `passlib==1.7.4`. Newer bcrypt (5.x) removed an internal attribute that older passlib versions read on startup, causing a crash. This pin is confirmed working in this project.

### 3.3.4 Database Setup / Migration

**Option A — Zero-config demo (default, SQLite):**
No action needed. On first run, `main.py` automatically:
1. Creates all tables (`Base.metadata.create_all`) — equivalent to running `database/schema.sql`.
2. Seeds two departments, one demo doctor, and one demo admin account so the API is immediately testable.

**Option B — Production setup (PostgreSQL):**
```bash
# Create the database
createdb hams

# Point the app at it
export DATABASE_URL="postgresql://<user>:<password>@localhost:5432/hams"

# Apply the schema directly (or let SQLAlchemy create_all handle it on first run)
psql -d hams -f ../database/schema.sql
```

### 3.3.5 Run the Application

```bash
uvicorn main:app --reload
```

The API is now live at: **`http://127.0.0.1:8000`**
Interactive Swagger docs (try every endpoint from the browser): **`http://127.0.0.1:8000/docs`**

### 3.3.6 Demo Credentials (auto-seeded)

| Role | Email | Password |
|---|---|---|
| Admin | `admin@hams.local` | `Admin@123` |
| Doctor (Dr. Asha Rao, Cardiology) | `asha.rao@hams.local` | `Doctor@123` |

Patients self-register via `POST /auth/register`.

### 3.3.7 Quick Smoke Test (curl)

```bash
# Register a patient
curl -X POST http://127.0.0.1:8000/auth/register \
  -H "Content-Type: application/json" \
  -d '{"full_name":"John Doe","email":"john@test.com","phone":"9876543210","password":"Pass@123"}'

# Log in (OAuth2 password flow -- note: form-encoded, not JSON)
curl -X POST http://127.0.0.1:8000/auth/login \
  -d "username=john@test.com&password=Pass@123"

# Search doctors in Cardiology (department_id=1)
curl "http://127.0.0.1:8000/doctors?department_id=1"

# View Dr. Asha Rao's (doctor_id=2) slots for a given date
curl "http://127.0.0.1:8000/doctors/2/slots?date=2026-08-24"

# Book a slot (replace <TOKEN> with the access_token from login)
curl -X POST http://127.0.0.1:8000/appointments \
  -H "Authorization: Bearer <TOKEN>" -H "Content-Type: application/json" \
  -d '{"doctor_id":2,"appointment_date":"2026-08-24","slot_start_time":"09:00:00","reason":"Checkup"}'
```

All of the above have been executed and verified against the running application during development (see AI Development Report §4.3 for the full concurrency test transcript).
