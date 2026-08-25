# MPLADS AI — Unified Monitoring & Anomaly Detection Platform

A full-stack intelligence and auditing dashboard for the **Member of Parliament Local Area Development Scheme (MPLADS)**. Integrates machine learning (Isolation Forest) with heuristic audit rules to track fund utilization, detect expenditure discrepancies, and monitor physical project execution across India.

---

## 🏛 Project Architecture

```
mplads-ai/
├── backend/                  # High-performance FastAPI Backend & ML Engine
│   ├── database.py           # Optimized SQLite engine with WAL mode & PRAGMAs
│   ├── models.py             # SQLAlchemy models with indexes on high-traffic columns
│   ├── schemas.py            # Pydantic schemas for data validation
│   ├── main.py               # FastAPI application with CORS, aggregations & AI routes
│   ├── mplads.db             # SQLite database containing 83,000+ project records
│   ├── requirements.txt      # Python dependencies
│   └── ml/
│       ├── predictor.py      # ML Isolation Forest inference + heuristic scoring
│       ├── anomaly_model.pkl # Trained ML model & feature definitions
│       └── train_anomaly_model.py # Model training script
│
├── frontend/                 # React + Vite Client Dashboard
│   ├── src/
│   │   ├── services/api.js   # Unified API client connected to backend
│   │   ├── pages/
│   │   │   ├── Overview.jsx    # Executive dashboard with AI narrative findings
│   │   │   ├── Projects.jsx    # Live project explorer with search & filters
│   │   │   ├── RiskCenter.jsx  # AI anomaly detection & severity categorizations
│   │   │   └── Reports.jsx     # Exportable audit reports (CSV, JSON, PDF)
│   │   ├── components/       # TopBar & Sidebar navigation
│   │   └── App.jsx
│   ├── package.json          # Node dependencies
│   ├── vite.config.js        # Vite config with dev API proxy
│   └── .env                  # Environment configuration (VITE_API_URL)
│
├── start_app.py              # Single launcher for FastAPI backend
├── start_all.bat             # 1-click full-stack launcher for Windows
└── README.md                 # Project documentation
```

---

## 🚀 Quick Start Guide

### 1. Prerequisites
- **Python 3.10+**
- **Node.js 18+** & **npm**

### 2. Backend Setup
```bash
cd backend
pip install -r requirements.txt
python -m uvicorn main:app --host 127.0.0.1 --port 8000 --reload
```
- Backend API runs on: `http://127.0.0.1:8000`
- Swagger Interactive Documentation: `http://127.0.0.1:8000/docs`

### 3. Frontend Setup
```bash
cd frontend
npm install
npm run dev
```
- Frontend web app runs on: `http://localhost:5173`

---

## ⚡ Key Optimizations & Linkages

1. **CORS & Seamless Linking**:
   - Configured FastAPI `CORSMiddleware` with unrestricted development access.
   - Added Vite dev server reverse proxy (`/api` -> `http://127.0.0.1:8000`).
   - Centralized all frontend requests into `src/services/api.js`.

2. **Fixed Critical Backend Bugs**:
   - Resolved missing `HTTPException` imports preventing runtime crashes.
   - Eliminated redundant route definitions across `/dashboard/*`.
   - Added missing `/filters/states` and `/filters/districts` endpoints.

3. **High-Performance Aggregations (Eliminated N+1 Queries)**:
   - State-level breakdowns (`/dashboard/states`) use SQL conditional sums (`CASE WHEN`) in a single query instead of iterative loops.
   - In-memory time-to-live (TTL) caching for heavy statistics and financial metrics.
   - Enabled SQLite **WAL mode**, `synchronous=NORMAL`, and memory temp stores.

4. **AI & ML Anomaly Detection**:
   - Pre-computed `RiskScore` table joining seamlessly with `Project` for sub-10ms query times.
   - Combined Isolation Forest statistical scoring with 7 rule-based compliance checks.
   - Live AI Narrative Insights integrated directly into the Executive Overview.

5. **Server-Side Pagination & Search**:
   - Fast keyword search on project names and categories.
   - Paginated responses to protect client browsers from loading 83,000 records at once.

