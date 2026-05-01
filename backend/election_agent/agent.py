"""
ElectionGuide AI — Agent Definition
Configures the ADK root agent with Gemini model, tools, and system prompt.
"""

import os
import sys

# Ensure the parent directory is in the path for config imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from google.adk.agents import Agent
from .prompts import SYSTEM_PROMPT
from .tools import (
    get_election_timeline,
    get_voter_registration_guide,
    get_nomination_process,
    get_polling_day_guide,
    get_counting_process,
    check_eligibility,
)

# ─── Model Configuration ─────────────────────────────────────────────────────
# Uses the model name from env; the google-genai client authenticates via:
#   - GOOGLE_GENAI_USE_VERTEXAI=1  → Vertex AI Express Mode (AQ. key)
#   - GOOGLE_GENAI_USE_VERTEXAI=0  → Gemini Developer API (AIza key)
MODEL_ID = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

# ─── Root Agent ──────────────────────────────────────────────────────────────
root_agent = Agent(
    model=MODEL_ID,
    name="election_guide",
    description=(
        "An expert, non-partisan AI assistant that educates users about the "
        "Indian election process — voter registration, timelines, nomination, "
        "polling, counting, and eligibility. Uses specialized tools for accurate data."
    ),
    instruction=SYSTEM_PROMPT,
    tools=[
        get_election_timeline,
        get_voter_registration_guide,
        get_nomination_process,
        get_polling_day_guide,
        get_counting_process,
        check_eligibility,
    ],
)
