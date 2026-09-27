import logging
import re

from sqlalchemy import inspect, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import CompanyKnowledge
from app.utils.time_utils import utc_now


logger = logging.getLogger(__name__)

MAX_EMBEDDING_TEXT_CHARS = 8000


class EmbeddingServiceError(RuntimeError):
    def __init__(self, message: str, stage: str = "api_call", error_type: str = "EmbeddingServiceError"):
        super().__init__(message)
        self.stage = stage
        self.error_type = error_type
        self.safe_message = sanitize_error_message(message)


def clean_value(value):
    if value is None:
        return ""

    return str(value).strip()


def sanitize_error_message(message: str):
    text_value = " ".join(clean_value(message).split())

    if settings.GEMINI_API_KEY:
        text_value = text_value.replace(settings.GEMINI_API_KEY, "[redacted]")

    text_value = re.sub(r"AIza[0-9A-Za-z_-]{20,}", "[redacted]", text_value)
    text_value = re.sub(r"Bearer\s+[0-9A-Za-z._-]+", "Bearer [redacted]", text_value, flags=re.IGNORECASE)

    return text_value[:500] or "Embedding generation failed. Keyword search fallback is still available."


def _embedding_error(stage: str, exc: Exception | str):
    if isinstance(exc, EmbeddingServiceError):
        return {
            "stage": exc.stage,
            "error_type": exc.error_type,
            "error_message": exc.safe_message,
        }

    return {
        "stage": stage,
        "error_type": exc.__class__.__name__ if isinstance(exc, Exception) else "EmbeddingServiceError",
        "error_message": sanitize_error_message(str(exc)),
    }


def format_embedding_error(stage: str, exc: Exception | str):
    return _embedding_error(stage, exc)


def _entry_error_payload(entry: CompanyKnowledge, stage: str, exc: Exception | str):
    error = _embedding_error(stage, exc)

    return {
        "knowledge_id": entry.id,
        "title": clean_value(entry.title),
        **error,
    }


def _clean_embedding_text(text: str):
    return " ".join(clean_value(text).split())[:MAX_EMBEDDING_TEXT_CHARS]


def _build_entry_embedding_text(entry: CompanyKnowledge):
    return _clean_embedding_text(
        "\n".join(
            part
            for part in [
                clean_value(entry.title),
                clean_value(entry.category),
                clean_value(entry.tags),
                clean_value(entry.content),
            ]
            if clean_value(part)
        )
    )


def _extract_embedding_values(response):
    embeddings = getattr(response, "embeddings", None)

    if embeddings:
        first_embedding = embeddings[0]
        values = getattr(first_embedding, "values", None)
        if values:
            return [float(value) for value in values]

        if isinstance(first_embedding, dict):
            values = first_embedding.get("values")
            if values:
                return [float(value) for value in values]

    embedding = getattr(response, "embedding", None)

    if embedding:
        values = getattr(embedding, "values", None)
        if values:
            return [float(value) for value in values]

    if isinstance(response, dict):
        response_embeddings = response.get("embeddings") or []
        if response_embeddings:
            values = response_embeddings[0].get("values")
            if values:
                return [float(value) for value in values]

    raise EmbeddingServiceError(
        "Embedding response did not include embedding values.",
        stage="api_call",
        error_type="InvalidEmbeddingResponse",
    )


def _format_pgvector(values: list[float]):
    return "[" + ",".join(f"{float(value):.8f}" for value in values) + "]"


def embedding_storage_available(db: Session):
    bind = db.get_bind()

    if bind.dialect.name != "postgresql":
        return False

    try:
        inspector = inspect(bind)
        columns = {column["name"] for column in inspector.get_columns("company_knowledge")}
    except Exception:
        return False

    return "embedding" in columns


def semantic_rag_available(db: Session):
    return bool(settings.ENABLE_SEMANTIC_RAG and settings.GEMINI_API_KEY and embedding_storage_available(db))


def get_embedding(text: str) -> list[float]:
    embedding_text = _clean_embedding_text(text)

    if not embedding_text:
        raise EmbeddingServiceError("Embedding text is empty.", stage="api_call", error_type="EmptyEmbeddingText")

    if not settings.GEMINI_API_KEY:
        raise EmbeddingServiceError(
            "GEMINI_API_KEY is not configured.",
            stage="api_call",
            error_type="MissingAPIKey",
        )

    try:
        from google import genai

        client = genai.Client(api_key=settings.GEMINI_API_KEY)
        response = client.models.embed_content(
            model=settings.EMBEDDING_MODEL,
            contents=embedding_text,
        )
        values = _extract_embedding_values(response)
    except EmbeddingServiceError:
        raise
    except Exception as exc:
        raise EmbeddingServiceError(
            str(exc) or "Embedding generation failed. Keyword search fallback is still available.",
            stage="api_call",
            error_type=exc.__class__.__name__,
        ) from exc

    if len(values) != settings.EMBEDDING_DIMENSION:
        raise EmbeddingServiceError(
            f"Embedding dimension {len(values)} did not match configured dimension {settings.EMBEDDING_DIMENSION}.",
            stage="api_call",
            error_type="EmbeddingDimensionMismatch",
        )

    return values


def embed_query(text: str) -> list[float]:
    return get_embedding(text)


def _save_embedding_error(db: Session, entry: CompanyKnowledge, error_message: str):
    entry.embedding_model = settings.EMBEDDING_MODEL
    entry.embedding_updated_at = utc_now()
    entry.embedding_error = clean_value(error_message)[:1000]

    try:
        db.commit()
        db.refresh(entry)
    except SQLAlchemyError:
        db.rollback()


def embed_knowledge_entry_with_details(db: Session, knowledge_entry: CompanyKnowledge) -> dict:
    if not settings.ENABLE_SEMANTIC_RAG:
        return {
            "embedded": False,
            "error": _entry_error_payload(knowledge_entry, "precheck", "Semantic RAG is disabled."),
        }

    if not embedding_storage_available(db):
        return {
            "embedded": False,
            "error": _entry_error_payload(knowledge_entry, "db_save", "pgvector embedding storage is unavailable."),
        }

    entry_text = _build_entry_embedding_text(knowledge_entry)

    if not entry_text:
        return {
            "embedded": False,
            "error": _entry_error_payload(knowledge_entry, "api_call", "Embedding text is empty."),
        }

    try:
        embedding = get_embedding(entry_text)
    except Exception as exc:
        _save_embedding_error(db, knowledge_entry, sanitize_error_message(str(exc)))
        logger.warning("Embedding API call failed for knowledge entry %s. %s", knowledge_entry.id, exc)
        return {
            "embedded": False,
            "error": _entry_error_payload(knowledge_entry, "api_call", exc),
        }

    try:
        vector_value = _format_pgvector(embedding)
        now = utc_now()
        db.execute(
            text(
                "UPDATE company_knowledge "
                "SET embedding = CAST(:embedding AS vector), "
                "embedding_model = :embedding_model, "
                "embedding_updated_at = :embedding_updated_at, "
                "embedding_error = NULL "
                "WHERE id = :knowledge_id"
            ),
            {
                "embedding": vector_value,
                "embedding_model": settings.EMBEDDING_MODEL,
                "embedding_updated_at": now,
                "knowledge_id": knowledge_entry.id,
            },
        )
        db.commit()
        db.refresh(knowledge_entry)
        return {
            "embedded": True,
            "dimension": len(embedding),
        }
    except Exception as exc:
        db.rollback()
        _save_embedding_error(db, knowledge_entry, sanitize_error_message(str(exc)))
        logger.warning("Embedding DB save failed for knowledge entry %s. %s", knowledge_entry.id, exc)
        return {
            "embedded": False,
            "error": _entry_error_payload(knowledge_entry, "db_save", exc),
        }


def embed_knowledge_entry(db: Session, knowledge_entry: CompanyKnowledge) -> bool:
    return bool(embed_knowledge_entry_with_details(db, knowledge_entry).get("embedded"))


def _count_remaining_missing_embeddings(db: Session):
    if not embedding_storage_available(db):
        return (
            db.query(CompanyKnowledge)
            .filter(CompanyKnowledge.is_active.is_(True))
            .count()
        )

    return db.execute(
        text(
            "SELECT COUNT(*) FROM company_knowledge "
            "WHERE is_active = TRUE AND (embedding IS NULL OR embedding_error IS NOT NULL)"
        )
    ).scalar() or 0


def embed_missing_knowledge(db: Session, limit=20) -> dict:
    effective_limit = max(1, min(int(limit or 20), 100))

    if not settings.ENABLE_SEMANTIC_RAG or not settings.GEMINI_API_KEY or not embedding_storage_available(db):
        return {
            "processed": 0,
            "embedded": 0,
            "failed": 0,
            "remaining": _count_remaining_missing_embeddings(db),
            "semantic_available": False,
            "message": "Semantic search unavailable. Keyword fallback used.",
            "errors": [],
        }

    rows = db.execute(
        text(
            "SELECT id FROM company_knowledge "
            "WHERE is_active = TRUE AND (embedding IS NULL OR embedding_error IS NOT NULL) "
            "ORDER BY COALESCE(updated_at, created_at) DESC, id DESC "
            "LIMIT :limit"
        ),
        {"limit": effective_limit},
    ).all()

    processed = 0
    embedded = 0
    failed = 0
    errors = []

    for row in rows:
        entry = db.get(CompanyKnowledge, row.id)
        if not entry:
            continue

        processed += 1
        result = embed_knowledge_entry_with_details(db, entry)
        if result.get("embedded"):
            embedded += 1
        else:
            failed += 1
            error = result.get("error")
            if error:
                errors.append(error)

    return {
        "processed": processed,
        "embedded": embedded,
        "failed": failed,
        "remaining": _count_remaining_missing_embeddings(db),
        "semantic_available": True,
        "errors": errors,
    }


def get_embedding_status(db: Session) -> dict:
    total_active = (
        db.query(CompanyKnowledge)
        .filter(CompanyKnowledge.is_active.is_(True))
        .count()
    )
    embedding_errors = (
        db.query(CompanyKnowledge)
        .filter(
            CompanyKnowledge.is_active.is_(True),
            CompanyKnowledge.embedding_error.isnot(None),
        )
        .count()
    )

    if embedding_storage_available(db):
        with_embeddings = db.execute(
            text("SELECT COUNT(*) FROM company_knowledge WHERE is_active = TRUE AND embedding IS NOT NULL")
        ).scalar() or 0
    else:
        with_embeddings = 0

    missing_embeddings = max(total_active - with_embeddings, 0)
    semantic_available = semantic_rag_available(db)

    return {
        "total_active": total_active,
        "with_embeddings": with_embeddings,
        "missing_embeddings": missing_embeddings,
        "embedding_errors": embedding_errors,
        "semantic_rag_enabled": settings.ENABLE_SEMANTIC_RAG,
        "semantic_available": semantic_available,
        "embedding_model": settings.EMBEDDING_MODEL,
        "embedding_dimension": settings.EMBEDDING_DIMENSION,
    }
