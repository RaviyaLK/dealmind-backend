# DealMind Backend

**AI-Powered Deal Intelligence Platform — Backend API**

Built with FastAPI + LangGraph + ChromaDB for the **Agentic AI Hackathon 2026** by ESSHVA's Hallucination Squad.
Developed as a solution to be used in ESSHVA only. 

---

## Quick Start

### Prerequisites

- Python 3.10+
- PostgreSQL (or SQLite for dev)
- Google Cloud project with OAuth credentials (for Gmail integration)
- OpenRouter API key (free tier with DeepSeek R1)

### Installation

```bash
cd dealmind-backend
pip install -r requirements.txt
```

### Environment Setup

Create a `.env` file in the project root:

```env
# Database
DATABASE_URL=sqlite:///./dealmind.db

# LLM (OpenRouter — free tier)
OPENROUTER_API_KEY=your_openrouter_api_key
LLM_MODEL=deepseek/deepseek-r1-0528:free

# JWT Authentication
JWT_SECRET_KEY=your-secret-key
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=480

# Google OAuth (Gmail + Calendar)
GOOGLE_CLIENT_ID=your_google_client_id
GOOGLE_CLIENT_SECRET=your_google_client_secret
GOOGLE_REDIRECT_URI=http://localhost:8000/api/integrations/google/callback
GOOGLE_FRONTEND_REDIRECT=http://localhost:5173/settings

# Embedding Model
EMBEDDING_MODEL=all-MiniLM-L6-v2

# Server
HOST=0.0.0.0
PORT=8000
DEBUG=true
CORS_ORIGINS=["http://localhost:5173","http://localhost:3000"]
```

### Run the Server

```bash
uvicorn app.main:app --reload --port 8000
```

The API will be available at `http://localhost:8000`. Interactive docs at `http://localhost:8000/docs`.

---

## Architecture

```
app/
├── main.py                  # FastAPI app init, router registration, startup
├── config.py                # Settings & environment variables (Pydantic)
├── database.py              # SQLAlchemy engine, session factory, init_db()
├── logging_config.py        # Logging setup
│
├── models/                  # SQLAlchemy ORM models (12 tables)
│   ├── user.py              # User accounts
│   ├── deal.py              # Deals, DealRequirements, DealAnalysis
│   ├── document.py          # Documents, DocumentChunks
│   ├── employee.py          # Employee roster
│   ├── assignment.py        # Deal-Employee assignments
│   ├── alert.py             # Alerts, RecoveryActions
│   ├── proposal.py          # Generated proposals
│   └── integration.py       # OAuth tokens
│
├── schemas/                 # Pydantic request/response schemas
│   ├── user.py, deal.py, document.py, employee.py
│   ├── assignment.py, alert.py, proposal.py, agent.py
│
├── routers/                 # API endpoint handlers (42+ endpoints)
│   ├── auth.py              # Register, login, profile
│   ├── deals.py             # Deal CRUD + requirements + analysis
│   ├── documents.py         # Upload, process, extract text
│   ├── employees.py         # Team roster + Excel bulk upload
│   ├── assignments.py       # Team assignment + auto-assign
│   ├── proposals.py         # Proposals + DOCX export (3 templates)
│   ├── agents.py            # Agent flow trigger + status polling
│   ├── alerts.py            # Alert management + recovery actions
│   ├── rag.py               # RAG search endpoints
│   ├── integrations.py      # Google OAuth + Gmail/Calendar
│   └── websocket.py         # WebSocket connection handlers
│
├── agents/                  # LangGraph AI agent flows
│   ├── state.py             # TypedDict state classes (3 flows)
│   ├── qualification.py     # 5-step: ingest → extract → analyze → match → decide
│   ├── proposal.py          # 3-step: retrieve → generate → comply
│   ├── monitoring.py        # 4-step: sentiment → health → alert → recovery
│   └── orchestrator.py      # Flow runner, task tracking, company profile loader
│
├── data/
│   └── esshva_company_profile.json  # Structured company capabilities
│
├── services/
│   ├── auth.py              # JWT tokens, password hashing
│   ├── llm.py               # OpenRouter LLM client (DeepSeek R1)
│   └── graph_api.py         # Gmail/Calendar API client
│
├── rag/                     # RAG pipeline
│   ├── vectorstore.py       # ChromaDB wrapper
│   ├── embeddings.py        # Sentence-transformers (all-MiniLM-L6-v2)
│   └── retriever.py         # Document chunker + retriever
│
├── ingestion/               # Document processors
│   ├── pdf.py               # PDF extraction (PyMuPDF)
│   ├── docx_extractor.py    # DOCX extraction (python-docx)
│   └── excel.py             # Excel parsing (openpyxl)
│
└── websocket/
    └── manager.py           # WebSocket connection manager
```

---

## AI Agent Flows

DealMind uses **LangGraph** to orchestrate three autonomous AI workflows, each powered by **DeepSeek R1** via OpenRouter.

### 1. Qualification Flow (5 steps)

```
INGEST → EXTRACT → ANALYZE → MATCH → DECIDE
```

Analyzes uploaded RFP/documents, extracts requirements, performs gap analysis against company's real company profile and employee skills, matches team members, and produces a GO/NO-GO recommendation with confidence score.

### 2. Proposal Flow (3 steps)

```
RETRIEVE → GENERATE → COMPLY
```

Searches the RAG knowledge base for relevant context, generates a full proposal using company's company profile + assigned team data + requirement analysis, then scores compliance against original requirements.

### 3. Monitoring Flow (4 steps)

```
SENTIMENT → HEALTH → ALERT → RECOVERY
```

Fetches emails from Gmail, analyzes sentiment, calculates deal health score, detects risks, and generates recovery emails with action items.

---

## Key API Endpoints

| Group | Method | Endpoint | Description |
|-------|--------|----------|-------------|
| Auth | POST | `/api/auth/register` | Register user |
| Auth | POST | `/api/auth/login` | Login (returns JWT) |
| Deals | GET/POST | `/api/deals/` | List/Create deals |
| Documents | POST | `/api/documents/upload` | Upload & process document |
| Agents | POST | `/api/agents/run` | Start agent flow |
| Agents | GET | `/api/agents/status/{task_id}` | Poll task progress |
| Proposals | GET | `/api/proposals/{id}/export/docx` | Export branded DOCX |
| Gmail | GET | `/api/integrations/google/auth` | Start Gmail OAuth |
| Gmail | POST | `/api/integrations/google/send-email` | Send recovery email |
| WebSocket | WS | `/ws/agent/{task_id}` | Real-time progress |

Full API docs available at `/docs` (Swagger UI) when running.

---

## Company Intelligence

The backend loads `app/data/esshva_company_profile.json` at startup — a structured profile containing ESSHVA's services, technologies, industries, products, awards, certifications, and global reach. This data is injected into both the qualification agent (for grounded gap analysis) and the proposal agent (for factual, company-specific proposals).

---

## Document Export

Three branded DOCX templates for proposal export:

| Template | Style | Colors |
|----------|-------|--------|
| **Modern** | Bold, contemporary | Purple + Cyan |
| **Classic** | Traditional, formal | Navy + Gold |
| **Minimal** | Ultra-clean | Black + Cyan |

Each includes cover page, project overview, full proposal content, and closing page with ESSHVA branding.

---

## File Storage

| Directory | Content |
|-----------|---------|
| `uploads/documents/` | Uploaded RFPs, proposals, transcripts |
| `uploads/employees/` | Employee roster Excel files |
| `uploads/proposals/` | Proposal attachments |
| `chroma_data/` | ChromaDB vector store |
| `exports/` | Generated DOCX files |

---

## Tech Stack

| Technology | Purpose |
|-----------|---------|
| FastAPI | Async REST API framework |
| SQLAlchemy 2.0 | ORM (SQLite/PostgreSQL) |
| LangGraph | Agent workflow orchestration |
| LangChain | LLM integration layer |
| ChromaDB | Vector database for RAG |
| sentence-transformers | Document embeddings (all-MiniLM-L6-v2) |
| OpenRouter + DeepSeek R1 | LLM reasoning engine |
| python-docx | Branded DOCX proposal export |
| PyMuPDF | PDF text extraction |
| python-jose + Passlib | JWT auth + bcrypt hashing |
| Google APIs | Gmail + Calendar integration |

---

*Built by Hallucination Squad (ESSHVA) for the Agentic AI Hackathon 2026*
