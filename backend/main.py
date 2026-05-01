"""
ElectionGuide AI — FastAPI Server
Main entry point serving the API endpoints and static frontend.
Integrates Google Cloud services: Gemini, Firestore, Cloud Logging, Cloud Run.
"""

import os
import sys
import uuid
import time
import json
import asyncio
import logging
from datetime import datetime, timezone
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field
from starlette.middleware.base import BaseHTTPMiddleware

# ── Path setup ──────────────────────────────────────────────────────────────
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv(os.path.join(ROOT_DIR, ".env"))

# Set the API key for google-genai before importing ADK.
os.environ.setdefault("GOOGLE_API_KEY", os.getenv("GEMINI_API_KEY", ""))

from config import get_settings
from election_agent.agent import root_agent
from election_agent.prompts import DEMO_QUERIES, TOPIC_CARDS
from election_agent.tools import (
    get_election_timeline,
    get_voter_registration_guide,
    get_nomination_process,
    get_polling_day_guide,
    get_counting_process,
    check_eligibility,
)

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception
from cache import response_cache
from firestore_sessions import FirestoreSessionService, init_firebase

# ── Google Cloud Logging ────────────────────────────────────────────────────
# Uses structured logging on Cloud Run, falls back to standard logging locally.
try:
    import google.cloud.logging as cloud_logging
    cloud_client = cloud_logging.Client()
    cloud_client.setup_logging(log_level=logging.INFO)
    logging.info("Google Cloud Logging initialized")
except Exception:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
    logging.info("Using standard logging (Cloud Logging not available)")

logger = logging.getLogger("electionguide")

# ── Session & Runner ────────────────────────────────────────────────────────
# ADK uses InMemorySessionService for its internal agent loop.
# We ALSO use FirestoreSessionService for persistent chat history & analytics.
session_service = InMemorySessionService()
runner = Runner(
    agent=root_agent,
    app_name="election_guide_ai",
    session_service=session_service,
)

# Firestore session service for persistent storage (initialized in lifespan)
firestore_sessions: FirestoreSessionService | None = None

# ── Rate Limiting: Semaphore + Sliding Window ──────────────────────────────
_gemini_semaphore = asyncio.Semaphore(3)     # Max 3 concurrent Gemini calls
_request_timestamps: list[float] = []
_RPM_LIMIT = 12                              # Stay under free-tier ~15 RPM


# ── Security Headers Middleware ─────────────────────────────────────────────
class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add security headers to all responses."""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        return response


# ── Lifespan ────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    global firestore_sessions
    settings = get_settings()
    logger.info("ElectionGuide AI starting on port %s", settings.port)
    logger.info("Model: %s", settings.gemini_model)

    # ── Initialize Firebase / Firestore ─────────────────────────────────
    if settings.firebase_project_id:
        try:
            sa_path = ""
            if settings.firebase_service_account_path:
                # Resolve relative to project root
                candidate = os.path.join(ROOT_DIR, settings.firebase_service_account_path)
                if os.path.exists(candidate):
                    sa_path = candidate
                elif os.path.exists(settings.firebase_service_account_path):
                    sa_path = settings.firebase_service_account_path
            init_firebase(settings.firebase_project_id, sa_path)
            firestore_sessions = FirestoreSessionService()
            logger.info("Firestore session persistence ENABLED")
        except Exception as e:
            logger.warning("Firestore init failed, falling back to in-memory: %s", e)
            firestore_sessions = None
    else:
        logger.info("No FIREBASE_PROJECT_ID set — using in-memory sessions only")

    # ── Pre-seed cache to save quota ────────────────────────────────────
    logger.info("Pre-seeding cache with static responses...")

    timeline_data = get_election_timeline()
    registration_data = get_voter_registration_guide()
    nomination_data = get_nomination_process()
    polling_data = get_polling_day_guide()
    counting_data = get_counting_process()
    eligibility_19 = check_eligibility(19, "indian", "voting")
    eligibility_17 = check_eligibility(17, "indian", "voting")

    preseed_data = [
        # Topic Cards
        ("Walk me through the complete election timeline step by step.", "get_election_timeline", timeline_data),
        ("How do I register to vote in India?", "get_voter_registration_guide", registration_data),
        ("Explain the nomination process for Indian elections", "get_nomination_process", nomination_data),
        ("What happens on polling day in India?", "get_polling_day_guide", polling_data),
        ("How are votes counted in Indian elections?", "get_counting_process", counting_data),
        ("Am I eligible to vote? I am 19 years old, an Indian citizen", "check_eligibility", eligibility_19),

        # Demo Queries
        ("What are the key stages in the Indian election timeline?", "get_election_timeline", timeline_data),
        ("Check eligibility: I am 17 years old, Indian citizen", "check_eligibility", eligibility_17),
    ]

    for query, tool_name, tool_result in preseed_data:
        response_cache.set(query, {
            "response": f"Here is the requested information:\n\n```json\n{json.dumps(tool_result, indent=2)}\n```\n\nIs there anything else you'd like to know?",
            "tools_used": [tool_name],
            "tool_used": tool_name,
        })

    logger.info("Cache pre-seeded with %d entries", len(preseed_data))
    yield
    logger.info("ElectionGuide AI shutting down")


# ── App ─────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="ElectionGuide AI",
    description="Interactive election process education assistant powered by Google ADK + Gemini",
    version="1.0.0",
    lifespan=lifespan,
)

settings = get_settings()

# Security headers
app.add_middleware(SecurityHeadersMiddleware)

# CORS — specific origins only (no wildcard)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list + [
        "https://electionguide-ai-239331599550.us-central1.run.app",
        "https://electionguide-ai-7c996.web.app",
        "https://electionguide-ai-7c996.firebaseapp.com",
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "Authorization"],
)

# ── Request / Response Models ───────────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000, description="User message")
    session_id: str = Field(default="", description="Session ID for conversation continuity")


class ChatResponse(BaseModel):
    response: str
    session_id: str
    tools_used: list[str] = []


# ── Helper: Run agent (Layer 1 — Core) ─────────────────────────────────────

async def run_agent(user_message: str, session_id: str) -> tuple[str, list[str]]:
    """Send a message to the ADK agent and collect the response."""
    user_id = "user_web"

    # Ensure session exists — create if not found
    try:
        session = await session_service.get_session(
            app_name="election_guide_ai", user_id=user_id, session_id=session_id
        )
        if session is None:
            await session_service.create_session(
                app_name="election_guide_ai", user_id=user_id, session_id=session_id
            )
    except Exception:
        try:
            await session_service.create_session(
                app_name="election_guide_ai", user_id=user_id, session_id=session_id
            )
        except Exception:
            pass  # Session may already exist from a race condition

    content = types.Content(role="user", parts=[types.Part(text=user_message)])

    response_parts: list[str] = []
    tools_used: list[str] = []

    async for event in runner.run_async(
        user_id=user_id, session_id=session_id, new_message=content
    ):
        if event.is_final_response():
            if event.content and event.content.parts:
                for part in event.content.parts:
                    if part.text:
                        response_parts.append(part.text)
        # Track tool usage
        if hasattr(event, 'function_calls') and event.function_calls:
            for fc in event.function_calls:
                if hasattr(fc, 'name'):
                    tools_used.append(fc.name)

    full_response = "\n".join(response_parts) if response_parts else "I'm sorry, I couldn't generate a response. Please try again."
    return full_response, tools_used


# ── Layer 2: Retry with Exponential Backoff ─────────────────────────────────

def _is_retryable(exc: BaseException) -> bool:
    """Check if an exception is a retryable Gemini API error (429/503)."""
    err_str = str(exc).lower()
    # Don't retry daily quota exhaustion — only burst limits
    if "perdayperproject" in err_str or "per_day" in err_str:
        return False
    return any(code in err_str for code in ["429", "resource_exhausted", "503", "unavailable", "overloaded"])


@retry(
    retry=retry_if_exception(_is_retryable),
    wait=wait_exponential(multiplier=1, min=2, max=30),
    stop=stop_after_attempt(4),
    reraise=True,
    before_sleep=lambda retry_state: logger.warning(
        "Gemini API rate limited — retrying in %.1fs (attempt %d/4)",
        retry_state.next_action.sleep, retry_state.attempt_number
    ),
)
async def run_agent_with_retry(user_message: str, session_id: str) -> tuple[str, list[str]]:
    """Wrap run_agent with exponential backoff retry for 429/503 errors."""
    return await run_agent(user_message, session_id)


# ── Layer 3: Throttle (Semaphore + Sliding Window + Daily Quota) ────────────

_daily_request_count = 0
_daily_reset_date = datetime.now(timezone.utc).date()


async def throttled_run_agent(user_message: str, session_id: str) -> tuple[str, list[str]]:
    """Rate-limited agent call: enforces concurrency + RPM limits + Daily Quotas."""
    global _daily_request_count, _daily_reset_date

    now_date = datetime.now(timezone.utc).date()
    if now_date != _daily_reset_date:
        _daily_request_count = 0
        _daily_reset_date = now_date

    if _daily_request_count >= 18:
        # Prevent completely burning out the quota, return a fallback.
        logger.warning("Daily request quota safeguard reached. Rejecting request.")
        raise Exception("429 RESOURCE_EXHAUSTED: Daily quota reached.")

    # Sliding window — wait if approaching RPM limit
    now = time.time()
    _request_timestamps[:] = [t for t in _request_timestamps if now - t < 60]

    if len(_request_timestamps) >= _RPM_LIMIT:
        wait_time = 60 - (now - _request_timestamps[0])
        if wait_time > 0:
            logger.warning("RPM throttle — waiting %.1fs before next request", wait_time)
            await asyncio.sleep(wait_time)

    # Concurrency gate — max 3 simultaneous calls
    async with _gemini_semaphore:
        _request_timestamps.append(time.time())
        _daily_request_count += 1
        try:
            return await run_agent_with_retry(user_message, session_id)
        except Exception as e:
            err_str = str(e).lower()
            if "perdayperproject" in err_str or "per_day" in err_str:
                _daily_request_count = 20  # Mark as exhausted
            raise


# ── API Endpoints ───────────────────────────────────────────────────────────

@app.get("/api/health")
async def health_check() -> dict[str, Any]:
    """Health check endpoint for Cloud Run."""
    return {
        "status": "healthy",
        "service": "ElectionGuide AI",
        "model": settings.gemini_model,
        "firebase_connected": firestore_sessions is not None,
        "google_services": [
            "Gemini 2.5 Flash (ADK)",
            "Cloud Run",
            "Cloud Logging",
            "Firebase Firestore",
            "Firebase Hosting",
            "Firebase Analytics",
        ],
    }


@app.get("/api/sessions/stats")
async def session_stats() -> dict[str, Any]:
    """Return Firestore session analytics."""
    if firestore_sessions:
        return {
            "total_sessions": firestore_sessions.get_session_count(),
            "storage": "firestore",
            "project": settings.firebase_project_id,
        }
    return {"total_sessions": 0, "storage": "in-memory"}


@app.post("/api/chat", response_model=None)
async def chat(request: ChatRequest):
    """Send a message to the election guide agent."""
    session_id = request.session_id or str(uuid.uuid4())

    # Layer 3: Check cache first
    cached = response_cache.get(request.message)
    if cached:
        logger.info("Returning cached response for: %s", request.message[:50])
        # Persist to Firestore even for cached responses
        if firestore_sessions:
            try:
                firestore_sessions.save_message(session_id, "user", request.message)
                firestore_sessions.save_message(session_id, "assistant", cached.get("response", ""), cached.get("tools_used", []))
            except Exception as e:
                logger.warning("Firestore save failed (cached): %s", e)
        return {**cached, "session_id": session_id, "cached": True}

    try:
        response_text, tools_used = await throttled_run_agent(request.message, session_id)
        tool_used = tools_used[0] if tools_used else None
        result = {
            "response": response_text,
            "session_id": session_id,
            "tools_used": tools_used,
            "tool_used": tool_used,
        }
        # Cache the response
        response_cache.set(request.message, {"response": response_text, "tools_used": tools_used, "tool_used": tool_used})

        # Persist conversation to Firestore
        if firestore_sessions:
            try:
                firestore_sessions.save_message(session_id, "user", request.message)
                firestore_sessions.save_message(session_id, "assistant", response_text, tools_used)
            except Exception as e:
                logger.warning("Firestore save failed: %s", e)

        return result
    except Exception as e:
        err_str = str(e)
        logger.error("Chat error: %s", err_str)
        # Detect rate limit errors and return 429 status
        if any(code in err_str.lower() for code in ["429", "resource_exhausted"]):
            return JSONResponse(
                status_code=429,
                content={"error": "The AI is processing many requests. Please wait a moment and try again.", "retry_after": 10}
            )
        return JSONResponse(status_code=500, content={"error": f"Agent error: {err_str}"})


class DemoRequest(BaseModel):
    question: str = Field(..., min_length=1, description="Demo question")
    step: int = Field(default=0, description="Demo step index")


# Persistent demo session
_demo_session_id: str = ""


@app.post("/api/demo", response_model=None)
async def run_demo(request: DemoRequest):
    """Run a single demo step — the frontend sends questions one at a time."""
    global _demo_session_id

    # Create a new session for step 0
    if request.step == 0:
        _demo_session_id = f"demo_{uuid.uuid4().hex[:8]}"

    session_id = _demo_session_id or f"demo_{uuid.uuid4().hex[:8]}"

    # Check cache first for demo just like chat!
    cached = response_cache.get(request.question)
    if cached:
        logger.info("Returning cached response for demo question: %s", request.question[:50])
        return {
            "response": cached.get("response"),
            "tool_used": cached.get("tool_used"),
            "tools_used": cached.get("tools_used", []),
            "step": request.step,
        }

    try:
        response_text, tools_used = await throttled_run_agent(request.question, session_id)
        tool_used = tools_used[0] if tools_used else None

        # Cache the response
        response_cache.set(request.question, {"response": response_text, "tools_used": tools_used, "tool_used": tool_used})

        return {
            "response": response_text,
            "tool_used": tool_used,
            "tools_used": tools_used,
            "step": request.step,
        }
    except Exception as e:
        err_str = str(e)
        logger.error("Demo error at step %d: %s", request.step, err_str)
        if any(code in err_str.lower() for code in ["429", "resource_exhausted"]):
            return JSONResponse(
                status_code=429,
                content={"error": "Rate limited — please wait a moment.", "retry_after": 10}
            )
        return JSONResponse(status_code=500, content={"error": err_str})


@app.get("/api/topics")
async def get_topics() -> dict[str, Any]:
    """Return the list of quick-access topic cards."""
    return {"topics": TOPIC_CARDS}


@app.get("/api/cache-stats")
async def cache_stats() -> dict[str, Any]:
    """Return cache performance metrics."""
    return response_cache.stats


# ── Static Frontend Serving ─────────────────────────────────────────────────
FRONTEND_DIR = os.path.join(ROOT_DIR, "frontend")

if os.path.isdir(FRONTEND_DIR):
    if os.path.isdir(os.path.join(FRONTEND_DIR, "assets")):
        app.mount("/assets", StaticFiles(directory=os.path.join(FRONTEND_DIR, "assets")), name="assets")
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")

    @app.get("/")
    async def serve_frontend() -> FileResponse:
        return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))
else:
    @app.get("/")
    async def root() -> dict[str, str]:
        return {"message": "ElectionGuide AI API is running. Frontend not found.", "docs": "/docs"}


# ── Run ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
