import re
from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.orm import Session, joinedload

from app.core.config import settings
from app.db.models import CompanyKnowledge
from app.services.embedding_service import (
    embed_query,
    embedding_storage_available,
    semantic_rag_available,
)

MAX_KNOWLEDGE_CONTEXT_CHARS = 2400
MAX_KNOWLEDGE_ENTRY_CHARS = 520
OLDEST_DATETIME = datetime.min.replace(tzinfo=timezone.utc)
MAX_MATCH_REASONS = 3
STOPWORD_TOKENS = {
    "a",
    "an",
    "and",
    "are",
    "can",
    "for",
    "how",
    "is",
    "it",
    "me",
    "of",
    "on",
    "or",
    "our",
    "the",
    "to",
    "us",
    "we",
    "will",
    "you",
}

QUERY_EXPANSION_RULES = [
    {
        "label": "pricing",
        "patterns": ["cost", "costs", "how much", "price", "pricing", "budget", "quote"],
        "token_sets": [{"cost"}, {"price"}, {"pricing"}, {"budget"}, {"quote"}],
        "terms": ["pricing", "price", "budget", "quote"],
    },
    {
        "label": "demo",
        "patterns": ["walkthrough", "walk through", "show us", "show me", "quick look"],
        "token_sets": [{"walkthrough"}, {"demo"}, {"overview"}],
        "terms": ["demo", "product demo", "overview"],
    },
    {
        "label": "pilot",
        "patterns": ["start small", "small first", "start with one", "start first", "mvp pilot"],
        "token_sets": [{"start", "small"}, {"small", "first"}, {"pilot"}, {"mvp"}],
        "terms": ["pilot", "MVP pilot", "one department", "limited modules", "3 to 5 modules"],
    },
    {
        "label": "analytics",
        "patterns": ["track progress", "employee progress", "progress tracking", "managers track"],
        "token_sets": [
            {"track", "progress"},
            {"manager", "progress"},
            {"managers", "progress"},
            {"employee", "progress"},
            {"employees", "progress"},
        ],
        "terms": ["analytics", "completion", "quiz scores", "engagement", "HR dashboard"],
    },
    {
        "label": "value",
        "patterns": ["useful", "usefulness", "worth it", "relevant"],
        "token_sets": [{"useful"}, {"usefulness"}, {"value"}, {"benefit"}, {"relevance"}],
        "terms": ["value", "benefit", "relevance", "training needs"],
    },
]


def _clean(value):
    if value is None:
        return ""

    return str(value).strip()


def _normalize(value):
    return _clean(value).lower()


def _tokens(value):
    return {
        token
        for token in re.findall(r"[a-z0-9]+", _normalize(value))
        if len(token) >= 2 and token not in STOPWORD_TOKENS
    }


def _unique_values(values):
    unique = []
    seen = set()

    for value in values:
        cleaned = _clean(value)
        key = _normalize(cleaned)

        if cleaned and key not in seen:
            unique.append(cleaned)
            seen.add(key)

    return unique


def expand_search_query(query: str):
    query_text = _clean(query)
    normalized_query = _normalize(query_text)
    query_tokens = _tokens(query_text)
    expansion_terms = []
    matched_labels = []

    for rule in QUERY_EXPANSION_RULES:
        pattern_match = any(pattern in normalized_query for pattern in rule["patterns"])
        token_match = any(
            all(token in query_tokens for token in token_set)
            for token_set in rule.get("token_sets", [])
        )

        if pattern_match or token_match:
            expansion_terms.extend(rule["terms"])
            matched_labels.append(rule["label"])

    expansion_terms = _unique_values(expansion_terms)
    matched_labels = _unique_values(matched_labels)
    expanded_query = " ".join(_unique_values([query_text, *expansion_terms]))
    semantic_query = query_text

    if expansion_terms:
        semantic_query = f"{query_text}\nRelated terms: {', '.join(expansion_terms)}"

    return {
        "original_query": query_text,
        "expanded_query": expanded_query,
        "semantic_query": semantic_query,
        "terms": expansion_terms,
        "matched_labels": matched_labels,
    }


def _add_reason(reasons: list[str], reason: str):
    if reason and reason not in reasons and len(reasons) < MAX_MATCH_REASONS:
        reasons.append(reason)


def _field_match_score(
    field_name: str,
    field_value: str,
    phrase: str,
    weights: dict[str, int],
    reasons: list[str],
):
    if not phrase or phrase not in field_value:
        return 0

    score = weights.get(field_name, 0)

    if score:
        _add_reason(reasons, f"matched {field_name}")

    return score


def _entry_keyword_match(
    entry: CompanyKnowledge,
    query: str,
    query_tokens: set[str],
    expansion_terms: list[str] | None = None,
):
    if not query_tokens:
        return 0, []

    normalized_query = _normalize(query)
    title = _normalize(entry.title)
    category = _normalize(entry.category)
    tags = _normalize(entry.tags)
    content = _normalize(entry.content)
    score = 0
    reasons = []

    if normalized_query and normalized_query in title:
        score += 14
        _add_reason(reasons, "matched title")
    if normalized_query and normalized_query in tags:
        score += 9
        _add_reason(reasons, "matched tags")
    if normalized_query and normalized_query in category:
        score += 8
        _add_reason(reasons, "matched category")
    if normalized_query and normalized_query in content:
        score += 4
        _add_reason(reasons, "matched content")

    phrase_weights = {
        "title": 7,
        "tags": 6,
        "category": 6,
        "content": 3,
    }

    for phrase in [_normalize(term) for term in expansion_terms or [] if _normalize(term)]:
        score += _field_match_score("title", title, phrase, phrase_weights, reasons)
        score += _field_match_score("tags", tags, phrase, phrase_weights, reasons)
        score += _field_match_score("category", category, phrase, phrase_weights, reasons)
        score += _field_match_score("content", content, phrase, phrase_weights, reasons)

    for token in query_tokens:
        if token in title:
            score += 6
            _add_reason(reasons, "matched title")
        if token in tags:
            score += 4
            _add_reason(reasons, "matched tags")
        if token in category:
            score += 4
            _add_reason(reasons, "matched category")
        if token in content:
            score += 1
            _add_reason(reasons, "matched content")

    return score, reasons


def _entry_score(entry: CompanyKnowledge, query: str, query_tokens: set[str]):
    return _entry_keyword_match(entry, query, query_tokens)[0]


def _format_keyword_reason(reasons: list[str], expansion):
    labels = expansion.get("matched_labels") or []
    reason_text = "; ".join(reasons[:MAX_MATCH_REASONS])

    if labels:
        expansion_text = f"expanded {', '.join(labels)} terms"
        return f"{reason_text}; {expansion_text}" if reason_text else expansion_text

    return reason_text or "keyword match"


def _semantic_match_reason(similarity_score: float, expansion):
    labels = expansion.get("matched_labels") or []
    base = f"semantic similarity {similarity_score:.2f}"

    if labels:
        return f"{base}; expanded {', '.join(labels)} terms"

    return base


def _combine_match_reasons(*reasons):
    parts = []

    for reason in reasons:
        for part in str(reason or "").split(";"):
            cleaned = part.strip()

            if cleaned and cleaned not in parts:
                parts.append(cleaned)

    return "; ".join(parts[:MAX_MATCH_REASONS])


def _is_strong_keyword_match(entry: CompanyKnowledge):
    keyword_score = getattr(entry, "keyword_score", None) or 0
    match_reason = _normalize(getattr(entry, "match_reason", ""))

    return keyword_score >= 12 or "matched category" in match_reason or "matched tags" in match_reason


def _entry_timestamp(entry: CompanyKnowledge):
    value = entry.updated_at or entry.created_at or OLDEST_DATETIME

    if value.tzinfo:
        return value.astimezone(timezone.utc).timestamp()

    return value.replace(tzinfo=timezone.utc).timestamp()


def _attach_retrieval_metadata(
    entry: CompanyKnowledge,
    retrieval_method: str,
    similarity_score: float | None = None,
    keyword_score: int | None = None,
    match_reason: str | None = None,
):
    entry.retrieval_method = retrieval_method
    entry.similarity_score = similarity_score
    entry.keyword_score = keyword_score
    entry.match_reason = match_reason

    return entry


def _vector_literal(values: list[float]):
    return "[" + ",".join(f"{float(value):.8f}" for value in values) + "]"


def search_keyword_knowledge(db: Session, query, limit: int = 5):
    query_text = _clean(query)
    expansion = expand_search_query(query_text)
    query_tokens = _tokens(expansion["expanded_query"])
    effective_limit = max(1, min(int(limit or 5), 10))

    entries = (
        db.query(CompanyKnowledge)
        .options(joinedload(CompanyKnowledge.document))
        .filter(CompanyKnowledge.is_active.is_(True))
        .order_by(CompanyKnowledge.updated_at.desc(), CompanyKnowledge.created_at.desc())
        .all()
    )

    scored_entries = []

    for entry in entries:
        score, reasons = _entry_keyword_match(
            entry,
            query_text,
            query_tokens,
            expansion_terms=expansion["terms"],
        )

        if score > 0:
            scored_entries.append((score, reasons, entry))

    results = []

    for score, reasons, entry in sorted(
            scored_entries,
            key=lambda item: (item[0], _entry_timestamp(item[2])),
            reverse=True,
    )[:effective_limit]:
        results.append(
            _attach_retrieval_metadata(
                entry,
                "keyword",
                keyword_score=score,
                match_reason=_format_keyword_reason(reasons, expansion),
            )
        )

    return results


def search_semantic_knowledge(db: Session, query, limit: int = 5, min_score: float | None = None):
    query_text = _clean(query)
    effective_limit = max(1, min(int(limit or settings.SEMANTIC_RAG_TOP_K or 5), 10))
    effective_min_score = settings.SEMANTIC_RAG_MIN_SCORE if min_score is None else float(min_score)
    expansion = expand_search_query(query_text)

    if not query_text or not semantic_rag_available(db):
        return []

    query_embedding = embed_query(expansion["semantic_query"])
    vector_value = _vector_literal(query_embedding)
    candidate_limit = max(effective_limit, min(effective_limit * 3, 25))
    rows = db.execute(
        text(
            "SELECT id, 1 - (embedding <=> CAST(:query_embedding AS vector)) AS similarity_score "
            "FROM company_knowledge "
            "WHERE is_active = TRUE AND embedding IS NOT NULL "
            "ORDER BY embedding <=> CAST(:query_embedding AS vector) "
            "LIMIT :limit"
        ),
        {
            "query_embedding": vector_value,
            "limit": candidate_limit,
        },
    ).all()

    if not rows:
        return []

    row_by_id = {}

    for row in rows:
        similarity_score = float(row.similarity_score or 0)

        if similarity_score >= effective_min_score and len(row_by_id) < effective_limit:
            row_by_id[int(row.id)] = similarity_score

    if not row_by_id:
        return []

    entries = (
        db.query(CompanyKnowledge)
        .options(joinedload(CompanyKnowledge.document))
        .filter(CompanyKnowledge.id.in_(row_by_id.keys()))
        .all()
    )
    entry_by_id = {entry.id: entry for entry in entries}
    results = []

    for entry_id in row_by_id:
        entry = entry_by_id.get(entry_id)

        if entry:
            results.append(
                _attach_retrieval_metadata(
                    entry,
                    "semantic",
                    similarity_score=round(row_by_id[entry_id], 4),
                    match_reason=_semantic_match_reason(row_by_id[entry_id], expansion),
                )
            )

    return results


def search_hybrid_knowledge(db: Session, query, limit: int = 5):
    effective_limit = max(1, min(int(limit or 5), 10))
    keyword_results = search_keyword_knowledge(db, query, limit=max(effective_limit * 2, 10))
    keyword_metadata_by_id = {
        entry.id: {
            "keyword_score": getattr(entry, "keyword_score", None),
            "match_reason": getattr(entry, "match_reason", None),
            "is_strong": _is_strong_keyword_match(entry),
        }
        for entry in keyword_results
    }
    semantic_results = []
    semantic_available = semantic_rag_available(db)
    semantic_error = None

    if semantic_available:
        try:
            semantic_results = search_semantic_knowledge(
                db,
                query,
                limit=max(effective_limit, settings.SEMANTIC_RAG_TOP_K),
            )
        except Exception as exc:
            semantic_results = []
            semantic_available = False
            semantic_error = str(exc)

    strong_keyword_results = [
        entry
        for entry in keyword_results
        if keyword_metadata_by_id.get(entry.id, {}).get("is_strong")
    ]
    semantic_slots = effective_limit

    if semantic_results and strong_keyword_results:
        semantic_slots = max(1, effective_limit - min(len(strong_keyword_results), 2))

    merged_results = []
    seen_ids = set()

    for entry in semantic_results[:semantic_slots]:
        keyword_metadata = keyword_metadata_by_id.get(entry.id)

        if keyword_metadata:
            entry.keyword_score = keyword_metadata.get("keyword_score")
            entry.retrieval_method = "hybrid"
            entry.match_reason = _combine_match_reasons(
                getattr(entry, "match_reason", None),
                keyword_metadata.get("match_reason"),
            )

        merged_results.append(entry)
        seen_ids.add(entry.id)

    for entry in strong_keyword_results:
        if entry.id in seen_ids:
            continue

        metadata = keyword_metadata_by_id.get(entry.id, {})
        entry.keyword_score = metadata.get("keyword_score")
        entry.match_reason = metadata.get("match_reason")
        entry.similarity_score = None
        entry.retrieval_method = "keyword"
        merged_results.append(entry)
        seen_ids.add(entry.id)

        if len(merged_results) >= effective_limit:
            break

    for entry in semantic_results[semantic_slots:]:
        if entry.id in seen_ids:
            continue

        keyword_metadata = keyword_metadata_by_id.get(entry.id)

        if keyword_metadata:
            entry.keyword_score = keyword_metadata.get("keyword_score")
            entry.retrieval_method = "hybrid"
            entry.match_reason = _combine_match_reasons(
                getattr(entry, "match_reason", None),
                keyword_metadata.get("match_reason"),
            )

        merged_results.append(entry)
        seen_ids.add(entry.id)

        if len(merged_results) >= effective_limit:
            break

    for entry in keyword_results:
        if entry.id in seen_ids:
            continue

        metadata = keyword_metadata_by_id.get(entry.id, {})
        entry.keyword_score = metadata.get("keyword_score")
        entry.match_reason = metadata.get("match_reason")
        entry.similarity_score = None
        entry.retrieval_method = "keyword"
        merged_results.append(entry)
        seen_ids.add(entry.id)

        if len(merged_results) >= effective_limit:
            break

    results = merged_results[:effective_limit]
    retrieval_method = "hybrid" if semantic_results and keyword_results else "semantic" if semantic_results else "keyword"
    message = None

    if semantic_error:
        message = "Semantic search unavailable, keyword fallback used."
    elif not semantic_available:
        message = "Semantic search unavailable, keyword fallback used."
    elif not semantic_results and keyword_results:
        message = "No semantic matches above threshold. Keyword fallback used."

    return {
        "results": results,
        "semantic_available": semantic_available,
        "semantic_error": semantic_error,
        "retrieval_method": retrieval_method,
        "message": message,
    }


def search_knowledge(db: Session, query, limit: int = 5, mode: str = "hybrid"):
    normalized_mode = _normalize(mode) or "hybrid"
    effective_limit = max(1, min(int(limit or 5), 10))

    if normalized_mode == "keyword":
        return {
            "results": search_keyword_knowledge(db, query, limit=effective_limit),
            "semantic_available": semantic_rag_available(db),
            "retrieval_method": "keyword",
            "message": None,
        }

    if normalized_mode == "semantic":
        semantic_available = semantic_rag_available(db)
        semantic_error = None

        try:
            semantic_results = search_semantic_knowledge(db, query, limit=effective_limit)
        except Exception as exc:
            semantic_results = []
            semantic_available = False
            semantic_error = str(exc)

        if semantic_results:
            return {
                "results": semantic_results,
                "semantic_available": semantic_available,
                "retrieval_method": "semantic",
                "message": None,
            }

        return {
            "results": search_keyword_knowledge(db, query, limit=effective_limit),
            "semantic_available": semantic_available,
            "semantic_error": semantic_error,
            "retrieval_method": "keyword",
            "message": (
                "Semantic search unavailable, keyword fallback used."
                if not semantic_available
                else "No semantic matches above threshold. Keyword fallback used."
            ),
        }

    return search_hybrid_knowledge(db, query, limit=effective_limit)


def search_relevant_knowledge(db: Session, query, limit: int = 5):
    if settings.ENABLE_SEMANTIC_RAG:
        return search_hybrid_knowledge(db, query, limit=limit)["results"]

    return search_keyword_knowledge(db, query, limit=limit)


def _document_source_label(entry: CompanyKnowledge):
    document = getattr(entry, "document", None)
    document_name = _clean(getattr(document, "original_filename", ""))
    chunk_index = entry.chunk_index

    if document_name and chunk_index:
        return f"Document: {document_name} | Chunk {chunk_index}"

    if document_name:
        return f"Document: {document_name}"

    if chunk_index:
        return f"Document | Chunk {chunk_index}"

    return "Document"


def _source_label(entry: CompanyKnowledge):
    if _normalize(entry.source_type) == "document":
        return _document_source_label(entry)

    return "Manual"


def build_knowledge_context(entries):
    context_parts = []
    total_chars = 0

    for entry in entries:
        title = _clean(entry.title)
        category = _clean(entry.category) or "Other"
        content = " ".join(_clean(entry.content).split())

        if not title or not content:
            continue

        if len(content) > MAX_KNOWLEDGE_ENTRY_CHARS:
            content = f"{content[:MAX_KNOWLEDGE_ENTRY_CHARS].rstrip()}..."

        block = f"[{category} | {_source_label(entry)}] {title}:\n{content}"
        remaining_chars = MAX_KNOWLEDGE_CONTEXT_CHARS - total_chars

        if remaining_chars <= 0:
            break

        if len(block) > remaining_chars:
            block = f"{block[:remaining_chars].rstrip()}..."

        context_parts.append(block)
        total_chars += len(block)

    return "\n\n".join(context_parts)
