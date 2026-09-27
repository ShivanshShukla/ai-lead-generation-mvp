import os
from dotenv import load_dotenv

load_dotenv()


def get_frontend_origins():
    configured_origins = os.getenv("FRONTEND_URLS", "")
    fallback_origin = os.getenv("FRONTEND_URL", "http://localhost:5173")

    origins = [
        fallback_origin,
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]

    if configured_origins:
        origins.extend(configured_origins.split(","))

    return list(dict.fromkeys(origin.strip().rstrip("/") for origin in origins if origin.strip()))


def get_int_env(name, default):
    try:
        return int(os.getenv(name, str(default)) or default)
    except ValueError:
        return default


def get_float_env(name, default):
    try:
        return float(os.getenv(name, str(default)) or default)
    except ValueError:
        return default


def get_bool_env(name, default):
    value = os.getenv(name)

    if value is None:
        return default

    return value.strip().lower() in {"1", "true", "yes", "on"}


def get_embedding_model_env():
    configured_model = os.getenv("EMBEDDING_MODEL", "gemini-embedding-001").strip() or "gemini-embedding-001"

    if configured_model in {"text-embedding-004", "models/text-embedding-004"}:
        return "gemini-embedding-001"

    return configured_model


def get_embedding_dimension_env(model):
    configured_dimension = get_int_env("EMBEDDING_DIMENSION", 3072)

    if model in {
        "gemini-embedding-001",
        "models/gemini-embedding-001",
        "gemini-embedding-2",
        "models/gemini-embedding-2",
        "gemini-embedding-2-preview",
        "models/gemini-embedding-2-preview",
    }:
        return 3072

    return configured_dimension


class Settings:
    APP_NAME: str = os.getenv("APP_NAME", "AI Lead Generation MVP")
    APP_ENV: str = os.getenv("APP_ENV", "development")
    FRONTEND_URL: str = os.getenv("FRONTEND_URL", "http://localhost:5173")
    FRONTEND_URLS: list[str] = get_frontend_origins()
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./leadgen.db")
    DB_POOL_SIZE: int = get_int_env("DB_POOL_SIZE", 5)
    DB_MAX_OVERFLOW: int = get_int_env("DB_MAX_OVERFLOW", 2)
    DB_POOL_TIMEOUT: int = get_int_env("DB_POOL_TIMEOUT", 30)
    DB_POOL_RECYCLE: int = get_int_env("DB_POOL_RECYCLE", 1800)
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    EMBEDDING_MODEL: str = get_embedding_model_env()
    EMBEDDING_DIMENSION: int = get_embedding_dimension_env(EMBEDDING_MODEL)
    ENABLE_SEMANTIC_RAG: bool = get_bool_env("ENABLE_SEMANTIC_RAG", True)
    SEMANTIC_RAG_TOP_K: int = get_int_env("SEMANTIC_RAG_TOP_K", 5)
    SEMANTIC_RAG_MIN_SCORE: float = get_float_env("SEMANTIC_RAG_MIN_SCORE", 0.50)
    GMAIL_CLIENT_ID: str = os.getenv("GMAIL_CLIENT_ID", "")
    GMAIL_CLIENT_SECRET: str = os.getenv("GMAIL_CLIENT_SECRET", "")
    GMAIL_REDIRECT_URI: str = os.getenv("GMAIL_REDIRECT_URI", "")
    GMAIL_SENDER_EMAIL: str = os.getenv("GMAIL_SENDER_EMAIL", "")
    GMAIL_DAILY_LIMIT: int = get_int_env("GMAIL_DAILY_LIMIT", 20)
    HUNTER_API_KEY: str = os.getenv("HUNTER_API_KEY", "")
    HUNTER_REQUEST_TIMEOUT: float = get_float_env("HUNTER_REQUEST_TIMEOUT", 8.0)
    HUNTER_BULK_MAX_LEADS: int = get_int_env("HUNTER_BULK_MAX_LEADS", 10)
    HUNTER_BULK_MAX_SECONDS: float = get_float_env("HUNTER_BULK_MAX_SECONDS", 45.0)
    HUNTER_BULK_DELAY_SECONDS: float = get_float_env("HUNTER_BULK_DELAY_SECONDS", 0.25)
    APOLLO_API_KEY: str = os.getenv("APOLLO_API_KEY", "")
    VAPI_ENABLED: bool = get_bool_env("VAPI_ENABLED", False)
    VAPI_API_KEY: str = os.getenv("VAPI_API_KEY", "")
    VAPI_ASSISTANT_ID: str = os.getenv("VAPI_ASSISTANT_ID", "")
    VAPI_PHONE_NUMBER_ID: str = os.getenv("VAPI_PHONE_NUMBER_ID", "")
    VAPI_WEBHOOK_SECRET: str = os.getenv("VAPI_WEBHOOK_SECRET", "")
    VAPI_DEFAULT_TEST_PHONE: str = os.getenv("VAPI_DEFAULT_TEST_PHONE", "")
    VAPI_BASE_URL: str = os.getenv("VAPI_BASE_URL", "https://api.vapi.ai").rstrip("/")
    BACKEND_HOST: str = os.getenv("BACKEND_HOST", "127.0.0.1")
    BACKEND_PORT: int = get_int_env("BACKEND_PORT", 8000)

settings = Settings()
