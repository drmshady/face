import os


CORS_ORIGINS: list[str] = [
    origin.strip()
    for origin in os.getenv("CORS_ORIGINS", "https://localhost:5173").split(",")
    if origin.strip()
]

MAX_IMAGE_SIZE_MB: int = int(os.getenv("MAX_IMAGE_SIZE_MB", "10"))
MAX_IMAGE_SIZE_BYTES: int = MAX_IMAGE_SIZE_MB * 1024 * 1024

MAX_STL_SIZE_MB: int = int(os.getenv("MAX_STL_SIZE_MB", "100"))
MAX_STL_SIZE_BYTES: int = MAX_STL_SIZE_MB * 1024 * 1024

RATE_LIMIT_PER_MINUTE: int = int(os.getenv("RATE_LIMIT_PER_MINUTE", "120"))

SSL_CERTFILE: str | None = os.getenv("SSL_CERTFILE")
SSL_KEYFILE: str | None = os.getenv("SSL_KEYFILE")
