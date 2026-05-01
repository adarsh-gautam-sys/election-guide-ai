# ElectionGuide AI 🗳️

> **PromptWars 2026 — Election Process Education**
> An interactive AI assistant that helps users understand the Indian election process, powered by **Google ADK + Gemini 2.5 Flash**.

[![Built with Google ADK](https://img.shields.io/badge/Google-ADK-blue?logo=google)](https://google.github.io/adk-docs/)
[![Gemini 2.5 Flash](https://img.shields.io/badge/Model-Gemini%202.5%20Flash-purple)](https://ai.google.dev/)
[![Cloud Run](https://img.shields.io/badge/Deploy-Cloud%20Run-green?logo=google-cloud)](https://cloud.google.com/run)
[![Firebase](https://img.shields.io/badge/Session-Firebase-orange?logo=firebase)](https://firebase.google.com/)

**🌐 Live Demo**: [https://electionguide-ai-239331599550.us-central1.run.app](https://electionguide-ai-239331599550.us-central1.run.app)

---

## 🌟 Overview

**Chosen Vertical**: Election Process Education

ElectionGuide AI is a civic education platform designed to demystify India's election process for first-time voters, students, and curious citizens. Using the **Google Agent Development Kit (ADK)** framework, it orchestrates a Gemini 2.5 Flash-powered agent with **6 specialized tools** that provide structured, factual, and non-partisan information sourced from the Election Commission of India (ECI).

### How the Solution Works

1. **User asks a question** via the chat interface or clicks a topic card.
2. **FastAPI backend** receives the request and checks the in-memory cache (24-hour TTL).
3. If not cached, the **ADK Runner** sends the query to the **Gemini 2.5 Flash** model.
4. Gemini analyzes intent and **calls the appropriate FunctionTool(s)** to retrieve structured data.
5. The model **synthesizes a markdown response** using the tool output + system prompt constraints.
6. The response is **cached**, returned to the frontend, and rendered with markdown formatting.

### Key Features
- **Interactive Q&A** — Ask anything about elections, voter registration, nomination, polling, or counting
- **6 Custom AI Tools** — Each tool maps to a core election domain (Timeline, Registration, Nomination, Polling, Counting, Eligibility)
- **Live Demo Mode** — Watch the agent answer pre-scripted questions, showcasing tool selection in real-time
- **Cache-First Architecture** — Pre-seeded cache on startup eliminates redundant API calls for common queries
- **Premium UI** — Dark glassmorphism theme with Indian tricolor accents, built using Google Stitch MCP
- **Rate Limiting** — 3-layer defense: concurrency semaphore + sliding window RPM + daily quota tracking
- **Session Persistence** — InMemorySessionService (with optional Firebase Firestore upgrade)
- **Cloud Run Ready** — Containerized with Docker, non-root user, security headers

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────┐
│                     User (Browser)                      │
│         Stitch-Designed SPA (HTML/CSS/JS + Tailwind)    │
└────────────────────────┬────────────────────────────────┘
                         │ REST API (JSON)
                         ▼
┌─────────────────────────────────────────────────────────┐
│              FastAPI Server (main.py)                    │
│  ┌───────────────────────────────────────────────────┐  │
│  │  Security Headers · CORS · Rate Limiting · Cache  │  │
│  │  ┌─────────────────────────────────────────────┐  │  │
│  │  │         Google ADK Runner                   │  │  │
│  │  │  ┌─────────────────────────────────────┐    │  │  │
│  │  │  │     root_agent (Gemini 2.5 Flash)   │    │  │  │
│  │  │  │  ┌───────────────────────────────┐  │    │  │  │
│  │  │  │  │ System Prompt (Civic Expert)  │  │    │  │  │
│  │  │  │  │ 6 FunctionTools (see below)   │  │    │  │  │
│  │  │  │  └───────────────────────────────┘  │    │  │  │
│  │  │  └─────────────────────────────────────┘    │  │  │
│  │  └─────────────────────────────────────────────┘  │  │
│  │         InMemorySessionService / Firebase         │  │
│  └───────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
```

---

## 📂 Project Structure

```
PromptWars2/
├── backend/
│   ├── main.py                 # FastAPI server + ADK Runner + Security Middleware
│   ├── config.py               # Pydantic settings (env vars)
│   ├── cache.py                # In-memory TTL cache (24h, SHA-256 keys)
│   ├── requirements.txt        # Pinned Python dependencies
│   └── election_agent/
│       ├── __init__.py          # Package init (exports root_agent)
│       ├── agent.py             # ADK Agent definition
│       ├── tools.py             # 6 custom FunctionTools
│       └── prompts.py           # System prompt + demo queries
├── frontend/
│   ├── index.html              # SPA (Stitch MCP + Tailwind, ARIA-compliant)
│   └── app.js                  # Chat logic, demo flow, topic cards
├── tests/
│   ├── conftest.py             # Shared test configuration
│   ├── test_tools.py           # Unit tests for 6 FunctionTools
│   ├── test_cache.py           # Unit tests for cache operations
│   ├── test_config.py          # Unit tests for settings/config
│   └── test_api.py             # Integration tests for API endpoints
├── docs/
│   ├── architecture.md         # System architecture decisions
│   ├── prompt_evolution.md     # Prompt engineering iterations
│   └── tool_usage.md           # Tool descriptions & selection logic
├── .env.example                # Environment template
├── .gitignore                  # Git exclusions
├── .dockerignore               # Docker build exclusions
├── .gcloudignore               # Cloud Run upload exclusions
├── Dockerfile                  # Production container (non-root user)
└── README.md                   # This file
```

---

## 🚀 Quick Start

### Prerequisites
- Python 3.12+
- Google Gemini API key ([Get one free](https://aistudio.google.com/apikey))

### Setup
```bash
# Clone the repo
git clone https://github.com/adarsh-gautam-sys/PromptWars2.git
cd PromptWars2

# Create virtual environment
python -m venv .venv
.venv\Scripts\activate   # Windows
# source .venv/bin/activate  # Linux/Mac

# Install dependencies
pip install -r backend/requirements.txt

# Configure environment
cp .env.example .env
# Edit .env and add your GEMINI_API_KEY

# Run locally
python backend/main.py
```

Visit **http://localhost:8000** to use the application.

---

## 🤖 AI Agent Design

### Approach & Logic
The agent follows a **tool-first architecture**: every election-domain question triggers a FunctionTool call before the LLM generates a response. This ensures:
- **Factual accuracy** — tools return curated, ECI-sourced data (no hallucination)
- **Deterministic outputs** — same question always retrieves the same structured data
- **Auditability** — tool usage is tracked and displayed in the UI

### Model Selection
- **Gemini 2.5 Flash** — Chosen for speed, cost-efficiency, and strong instruction-following
- Ideal for real-time chat with sub-2-second response times

### Prompt Engineering
The system prompt (v4, iteratively refined) instructs the agent to:
1. Act as a **non-partisan civic educator** focused on India's election process
2. Always **call the appropriate tool** before answering domain questions
3. Present information with **structured formatting** (headers, bullet points, tables)
4. Never express political opinions or partisan views
5. Cite the **Election Commission of India (ECI)** as the authoritative source

See [docs/prompt_evolution.md](docs/prompt_evolution.md) for the full iteration history.

### Custom Tools (6 FunctionTools)
| Tool | Domain | Key Data |
|------|--------|----------|
| `get_election_timeline` | Election calendar | 9-stage timeline, MCC, notifications |
| `get_voter_registration_guide` | Voter enrollment | Forms 6/7/8, NVSP portal, requirements |
| `get_nomination_process` | Candidate filing | Eligibility, deposits, affidavit scrutiny |
| `get_polling_day_guide` | Election day | EVM/VVPAT, voter rights, procedures |
| `get_counting_process` | Results | Counting rounds, NOTA, postal ballots |
| `check_eligibility` | Eligibility check | Age, citizenship, NRI rules |

---

## 🔒 Security

- **API keys** stored in environment variables, never committed to git
- **Input validation** via Pydantic models (max 2000 chars, min 1 char)
- **CORS** configured for specific origins only (no wildcard)
- **Security headers** on all responses (X-Content-Type-Options, X-Frame-Options, X-XSS-Protection, Referrer-Policy, Permissions-Policy)
- **Rate limiting** — 3-layer: concurrency semaphore + sliding-window RPM + daily quota tracking
- **Non-root Docker user** — container runs as `appuser`, not root
- **No secrets in image** — `.env` excluded via `.dockerignore`; env vars injected by Cloud Run
- **.gitignore** excludes `.env`, Firebase service account JSON, and build artifacts

---

## 📊 Google Services Integration

ElectionGuide AI is built from the ground up to showcase the power and scalability of the **Google Cloud Ecosystem**.

| Service | Category | Technical Implementation |
|---------|----------|--------------------------|
| **Gemini 2.5 Flash** | **AI & ML** | Core LLM reasoning engine. Chosen for its high-speed performance and state-of-the-art tool-use (function calling) capabilities. |
| **Google GenAI ADK** | **Development** | The **Agent Development Kit** orchestrates the conversation flow, manages tool execution, and ensures consistent structured outputs. |
| **Google Cloud Run** | **Compute** | Fully serverless hosting. The app is containerized via Docker and deployed to Cloud Run for automatic scaling, integrated security, and zero-downtime updates. |
| **Google Firestore** | **Database** | Used for high-speed session persistence. Firestore stores conversation logs and analytical data securely with sub-millisecond latency. |
| **Google Cloud Logging** | **Operations** | Integrated via `google-cloud-logging` to provide structured production monitoring, error tracking, and performance auditing. |
| **Firebase Hosting** | **Delivery** | (Optional Layer) Configured for global edge-delivery of static assets and secure routing via Firebase rewrites. |
| **Google Stitch MCP** | **Design** | Utilized to generate the "Civic Prism" design system, ensuring a high-fidelity, Material-compliant, and accessible user interface. |

---

## 🧪 Testing

```bash
# Run all unit and integration tests
python -m pytest tests/ -v

# Run specific test suites
python -m pytest tests/test_tools.py -v     # Tool output validation
python -m pytest tests/test_cache.py -v     # Cache operations
python -m pytest tests/test_config.py -v    # Configuration
python -m pytest tests/test_api.py -v       # API endpoints + security headers
```

### Test Coverage
| Suite | Tests | Coverage |
|-------|-------|----------|
| `test_tools.py` | 17 | All 6 tools, edge cases, parameter variations |
| `test_cache.py` | 12 | Set/get, TTL, eviction, normalization, stats |
| `test_config.py` | 10 | Defaults, CORS parsing, overrides |
| `test_api.py` | 14 | Endpoints, validation, security headers |
| **Total** | **53** | |

---

## ♿ Accessibility

- **ARIA landmarks**: `<main>`, `<header>`, `<nav>`, `<footer>`
- **ARIA labels**: All interactive elements (buttons, inputs, topic cards)
- **ARIA dialog**: Demo modal with `role="dialog"`, `aria-modal`, `aria-labelledby`
- **Keyboard navigation**: Topic cards respond to Enter/Space keys, focus rings on all interactive elements
- **Skip-to-content link**: Hidden link for screen reader users
- **Semantic HTML**: Proper heading hierarchy (h1 → h2 → h3)
- **Screen reader support**: `aria-hidden="true"` on decorative icons, `sr-only` labels

---

## 🚢 Deployment (Cloud Run)

```bash
# Deploy to Cloud Run
gcloud run deploy electionguide-ai \
  --source . \
  --region us-central1 \
  --allow-unauthenticated \
  --project electionguide-ai-7c996 \
  --set-env-vars GEMINI_API_KEY=your_key,GEMINI_MODEL=gemini-2.5-flash
```

---

## 📋 Assumptions

1. **Data Currency**: Election rules and procedures are based on ECI guidelines as of 2024-2025. The tool data is static and does not auto-update from external sources.
2. **Scope**: The assistant covers Indian elections only (Lok Sabha, State Assembly, Local Body). It does not cover international election processes.
3. **Accuracy vs. Real-time**: The agent provides educational information, not real-time election results or live polling data.
4. **Session Scope**: Each browser session is independent. Conversation history is stored in-memory and does not persist across server restarts.
5. **API Tier**: The application is designed to work within free-tier Gemini API limits (pre-seeded caching minimizes live API calls).
6. **Non-partisan**: The assistant never endorses parties or candidates. All responses are factual and sourced from ECI.

---

## 📝 License

Built for **PromptWars 2026** hackathon. Educational use only.

---

<p align="center">Made with ❤️ for Indian democracy 🇮🇳</p>
