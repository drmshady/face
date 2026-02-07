"""Secure in-memory session store per T009.

Sessions are keyed by cryptographically random tokens (not session_id).
Tokens are delivered via HTTP-only cookies. Sessions auto-expire after 1 hour.
"""

import secrets
import time

from backend.src.models.session import FaceAnalysisSession

_SESSION_TTL_SECONDS = 3600  # 1 hour


class SessionStore:
    def __init__(self) -> None:
        self._sessions: dict[str, FaceAnalysisSession] = {}
        self._token_to_session_id: dict[str, str] = {}
        self._session_id_to_token: dict[str, str] = {}
        self._created_at: dict[str, float] = {}

    def create_session(self) -> tuple[FaceAnalysisSession, str]:
        """Create a new session. Returns (session, token)."""
        session = FaceAnalysisSession()
        token = secrets.token_urlsafe(32)

        self._sessions[session.session_id] = session
        self._token_to_session_id[token] = session.session_id
        self._session_id_to_token[session.session_id] = token
        self._created_at[token] = time.monotonic()

        return session, token

    def get_session_by_token(self, token: str) -> FaceAnalysisSession | None:
        """Get session by token. Returns None if expired or invalid."""
        session_id = self._token_to_session_id.get(token)
        if session_id is None:
            return None

        created = self._created_at.get(token, 0)
        if time.monotonic() - created > _SESSION_TTL_SECONDS:
            self._remove(token, session_id)
            return None

        return self._sessions.get(session_id)

    def get_session_by_id(
        self, session_id: str, token: str
    ) -> FaceAnalysisSession | None:
        """Get session by ID, but only if the token owns it."""
        owner_id = self._token_to_session_id.get(token)
        if owner_id is None:
            return None
        if owner_id != session_id:
            return None
        return self.get_session_by_token(token)

    def update_session(
        self, token: str, session: FaceAnalysisSession
    ) -> bool:
        """Update session data. Returns False if token invalid."""
        session_id = self._token_to_session_id.get(token)
        if session_id is None:
            return False
        self._sessions[session_id] = session
        return True

    def _remove(self, token: str, session_id: str) -> None:
        self._sessions.pop(session_id, None)
        self._token_to_session_id.pop(token, None)
        self._session_id_to_token.pop(session_id, None)
        self._created_at.pop(token, None)


# Singleton instance
store = SessionStore()
