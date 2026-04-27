"""
ElectionGuide AI — FastAPI Server
Main entry point serving the API endpoints and static frontend.
"""

import os
import sys
import uuid
import time
import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

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

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception
from cache import response_cache

# ── Logging ─────────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger("electionguide")

# ── Session & Runner ────────────────────────────────────────────────────────
session_service = InMemorySessionService()
runner = Runner(
    agent=root_agent,
    app_name="election_guide_ai",
    session_service=session_service,
)

# ── Rate Limiting: Semaphore + Sliding Window ──────────────────────────────
_gemini_semaphore = asyncio.Semaphore(3)     # Max 3 concurrent Gemini calls
_request_timestamps: list[float] = []
_RPM_LIMIT = 12                              # Stay under free-tier ~15 RPM


# ── Lifespan ────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    logger.info("🗳️  ElectionGuide AI starting on port %s", settings.port)
    logger.info("📡  Model: %s", settings.gemini_model)
    yield
    logger.info("👋  ElectionGuide AI shutting down")


# ── App ─────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="ElectionGuide AI",
    description="Interactive election process education assistant powered by Google ADK + Gemini",
    version="1.0.0",
    lifespan=lifespan,
)

settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list + ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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

    response_parts = []
    tools_used = []

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


# ── Layer 3: Throttle (Semaphore + Sliding Window) ──────────────────────────

async def throttled_run_agent(user_message: str, session_id: str) -> tuple[str, list[str]]:
    """Rate-limited agent call: enforces concurrency + RPM limits."""
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
        return await run_agent_with_retry(user_message, session_id)


# ── API Endpoints ───────────────────────────────────────────────────────────

@app.get("/api/health")
async def health_check():
    """Health check endpoint for Cloud Run."""
    return {"status": "healthy", "service": "ElectionGuide AI", "model": settings.gemini_model}


@app.post("/api/chat")
async def chat(request: ChatRequest):
    """Send a message to the election guide agent."""
    session_id = request.session_id or str(uuid.uuid4())

    # Layer 3: Check cache first
    cached = response_cache.get(request.message)
    if cached:
        logger.info("Returning cached response for: %s", request.message[:50])
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


@app.post("/api/demo")
async def run_demo(request: DemoRequest):
    """Run a single demo step — the frontend sends questions one at a time."""
    global _demo_session_id

    # Create a new session for step 0
    if request.step == 0:
        _demo_session_id = f"demo_{uuid.uuid4().hex[:8]}"

    session_id = _demo_session_id or f"demo_{uuid.uuid4().hex[:8]}"

    try:
        response_text, tools_used = await throttled_run_agent(request.question, session_id)
        tool_used = tools_used[0] if tools_used else None
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
async def get_topics():
    """Return the list of quick-access topic cards."""
    return {"topics": TOPIC_CARDS}


@app.get("/api/cache-stats")
async def cache_stats():
    """Return cache performance metrics."""
    return response_cache.stats


# ── Static Frontend Serving ─────────────────────────────────────────────────
FRONTEND_DIR = os.path.join(ROOT_DIR, "frontend")

if os.path.isdir(FRONTEND_DIR):
    app.mount("/assets", StaticFiles(directory=os.path.join(FRONTEND_DIR, "assets")), name="assets") if os.path.isdir(os.path.join(FRONTEND_DIR, "assets")) else None
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")

    @app.get("/")
    async def serve_frontend():
        return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))
else:
    @app.get("/")
    async def root():
        return {"message": "ElectionGuide AI API is running. Frontend not found.", "docs": "/docs"}


# ── Run ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host=settings.host, port=settings.port, reload=True)
