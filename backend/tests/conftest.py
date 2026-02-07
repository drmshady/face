import pytest
from httpx import ASGITransport, AsyncClient

from backend.src.main import app


@pytest.fixture(autouse=True)
def _reset_state():
    """Reset singleton state between tests."""
    from backend.src.services.session_store import store

    store._sessions.clear()
    store._token_to_session_id.clear()
    store._session_id_to_token.clear()
    store._created_at.clear()

    # Set very high rate limit for tests
    import backend.src.config as config
    original = config.RATE_LIMIT_PER_MINUTE
    config.RATE_LIMIT_PER_MINUTE = 10000
    yield
    config.RATE_LIMIT_PER_MINUTE = original


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="https://test") as ac:
        yield ac
