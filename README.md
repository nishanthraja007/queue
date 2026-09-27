# Hospital Appointment Management System (HAMS) / Queue

Complete assignment submission for the Hospital Appointment Management System (HAMS), featuring a FastAPI backend, relational database schema, interactive frontend interface, technical documentation, and AI development report.

## 📁 Repository Structure

```
├── frontend/                 # Node.js Express & static HTML/JS/CSS web interface
│   ├── index.html            # Main UI Dashboard & Appointment Booking
│   ├── app.js                # Frontend application logic
│   ├── style.css             # Frontend styling
│   ├── server.js             # Express server
│   └── package.json          # Node dependencies
└── que/                      # Core HAMS backend, database schema, & project documentation
    ├── 01_Requirement_Analysis_and_Design.md # Requirements & Mermaid workflow diagrams
    ├── 02_Technical_Documentation.md         # Technical architecture & setup guide
    ├── 03_AI_Development_Report.md           # AI implementation report & test evidence
    ├── appointments_router.py                # Router for appointment scheduling
    ├── main.py                               # Application entrypoint
    ├── schema.sql                            # Database schema DDL
    ├── database/                             # Database scripts & DDL
    └── backend/                              # FastAPI Backend application
        ├── main.py                           # FastAPI main application
        ├── auth.py                           # Authentication & JWT handler
        ├── database.py                       # DB engine & session configuration
        ├── models.py                         # SQLAlchemy models
        ├── schemas.py                        # Pydantic schemas
        ├── sms_service.py                    # SMS notification service
        ├── sms_queue_monitor.py              # Background queue monitor
        ├── routers/                          # API endpoint routes
        └── requirements.txt                  # Python dependencies
```

## 🚀 Quick Start

### 1. Backend Setup (FastAPI)

```bash
cd que/backend
python -m venv venv
# On Windows PowerShell:
.\venv\Scripts\Activate.ps1
# On Linux/macOS:
# source venv/bin/activate

pip install -r requirements.txt
uvicorn main:app --reload
```

FastAPI server runs at `http://127.0.0.1:8000`. Interactive Swagger UI available at `http://127.0.0.1:8000/docs`.

### 2. Frontend Setup (Node.js)

```bash
cd frontend
npm install
npm start
```

Frontend UI runs at `http://localhost:3000`.

## 📖 Key Documentation

1. `que/01_Requirement_Analysis_and_Design.md` — Requirement analysis, user stories, acceptance criteria, sequence & ER diagrams.
2. `que/database/schema.sql` — Relational schema DDL including double-booking prevention constraints.
3. `que/02_Technical_Documentation.md` — Comprehensive architecture and setup documentation.
4. `que/03_AI_Development_Report.md` — AI development breakdown, concurrency race condition solutions, and verification logs.
