"""
ElectionGuide AI — Firestore Session Service
Persistent session storage using Google Cloud Firestore.
Replaces InMemorySessionService for production Cloud Run deployments.
"""

import logging
from datetime import datetime, timezone
from typing import Any

import firebase_admin
from firebase_admin import credentials, firestore
from google.cloud.firestore_v1 import AsyncClient

logger = logging.getLogger("electionguide")

# ── Firebase Admin SDK Initialization ───────────────────────────────────────

_firebase_app = None


def init_firebase(project_id: str, service_account_path: str = "") -> None:
    """Initialize the Firebase Admin SDK (idempotent)."""
    global _firebase_app
    if _firebase_app is not None:
        return

    try:
        if service_account_path:
            cred = credentials.Certificate(service_account_path)
            _firebase_app = firebase_admin.initialize_app(cred, {"projectId": project_id})
        else:
            # Use Application Default Credentials (Cloud Run provides these automatically)
            _firebase_app = firebase_admin.initialize_app(options={"projectId": project_id})
        logger.info("Firebase Admin SDK initialized for project: %s", project_id)
    except ValueError:
        # Already initialized
        _firebase_app = firebase_admin.get_app()
        logger.info("Firebase Admin SDK already initialized")


def get_firestore_client() -> Any:
    """Get the Firestore client from the initialized Firebase app."""
    return firestore.client()


# ── Firestore Session Service ───────────────────────────────────────────────

class FirestoreSessionService:
    """
    Persists chat sessions to Firestore.

    Collection structure:
        sessions/{session_id}
            - user_id: str
            - created_at: datetime
            - updated_at: datetime
            - messages: list[dict]  (role, content, timestamp)
    """

    COLLECTION = "sessions"

    def __init__(self):
        self._db = None

    @property
    def db(self):
        if self._db is None:
            self._db = get_firestore_client()
        return self._db

    def get_session(self, session_id: str) -> dict | None:
        """Retrieve a session from Firestore."""
        doc = self.db.collection(self.COLLECTION).document(session_id).get()
        if doc.exists:
            return doc.to_dict()
        return None

    def create_session(self, session_id: str, user_id: str = "user_web") -> dict:
        """Create a new session document in Firestore."""
        session_data = {
            "user_id": user_id,
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
            "messages": [],
            "message_count": 0,
        }
        self.db.collection(self.COLLECTION).document(session_id).set(session_data)
        logger.info("Created Firestore session: %s", session_id)
        return session_data

    def save_message(self, session_id: str, role: str, content: str, tools_used: list[str] | None = None) -> None:
        """Append a message to the session's message history."""
        doc_ref = self.db.collection(self.COLLECTION).document(session_id)
        doc = doc_ref.get()

        message = {
            "role": role,
            "content": content[:5000],  # Truncate to prevent oversized documents
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        if tools_used:
            message["tools_used"] = tools_used

        if doc.exists:
            data = doc.to_dict()
            messages = data.get("messages", [])
            messages.append(message)
            # Keep only last 50 messages per session to control costs
            if len(messages) > 50:
                messages = messages[-50:]
            doc_ref.update({
                "messages": messages,
                "message_count": len(messages),
                "updated_at": datetime.now(timezone.utc),
            })
        else:
            # Auto-create session if it doesn't exist
            self.create_session(session_id)
            doc_ref.update({
                "messages": [message],
                "message_count": 1,
            })

    def get_session_count(self) -> int:
        """Return the total number of sessions (for analytics)."""
        try:
            docs = self.db.collection(self.COLLECTION).count().get()
            return docs[0][0].value if docs else 0
        except Exception:
            return 0

    def delete_session(self, session_id: str) -> None:
        """Delete a session from Firestore."""
        self.db.collection(self.COLLECTION).document(session_id).delete()
        logger.info("Deleted Firestore session: %s", session_id)
