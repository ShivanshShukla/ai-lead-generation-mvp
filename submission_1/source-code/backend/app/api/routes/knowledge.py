import os
import tempfile
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy import or_
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, joinedload

from app.core.config import settings
from app.db.database import get_db
from app.db.models import CompanyKnowledge, KnowledgeDocument
from app.schemas.knowledge_schema import (
    KNOWLEDGE_CATEGORIES,
    CompanyKnowledgeCreate,
    CompanyKnowledgeUpdate,
)
from app.services.document_service import (
    DocumentExtractionError,
    chunk_text,
    extract_text_from_file,
)
from app.services.embedding_service import (
    embed_knowledge_entry,
    embed_missing_knowledge,
    format_embedding_error,
    get_embedding,
    get_embedding_status,
)
from app.services.knowledge_service import search_knowledge
from app.utils.time_utils import utc_now

router = APIRouter(
    prefix="/knowledge",
    tags=["Knowledge"]
)

MAX_KNOWLEDGE_SEARCH_LIMIT = 10
MAX_UPLOAD_BYTES = 5 * 1024 * 1024
ALLOWED_DOCUMENT_EXTENSIONS = {".txt", ".md", ".pdf", ".docx"}


def clean_text(value):
    if value is None:
        return ""

    return str(value).strip()


def validate_category(category: str):
    category = clean_text(category)

    if category not in KNOWLEDGE_CATEGORIES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid knowledge category. Allowed categories: {', '.join(sorted(KNOWLEDGE_CATEGORIES))}"
        )

    return category


def get_content_preview(value, max_length=260):
    text = clean_text(value)

    if len(text) <= max_length:
        return text

    return f"{text[:max_length].rstrip()}..."


def serialize_knowledge(entry: CompanyKnowledge):
    document = getattr(entry, "document", None)
    similarity_score = getattr(entry, "similarity_score", None)
    keyword_score = getattr(entry, "keyword_score", None)

    return {
        "id": entry.id,
        "title": entry.title,
        "category": entry.category,
        "content": entry.content,
        "content_preview": get_content_preview(entry.content),
        "tags": entry.tags,
        "source_type": entry.source_type or "manual",
        "document_id": entry.document_id,
        "document_filename": document.original_filename if document else None,
        "chunk_index": entry.chunk_index,
        "retrieval_method": getattr(entry, "retrieval_method", None),
        "similarity_score": round(float(similarity_score), 4) if similarity_score is not None else None,
        "keyword_score": int(keyword_score) if keyword_score is not None else None,
        "match_reason": getattr(entry, "match_reason", None),
        "is_active": entry.is_active,
        "created_at": entry.created_at,
        "updated_at": entry.updated_at,
    }


def serialize_document(document: KnowledgeDocument, include_chunks=False):
    chunks = list(getattr(document, "knowledge_entries", []) or [])
    active_chunks = [chunk for chunk in chunks if chunk.is_active]
    data = {
        "id": document.id,
        "filename": document.filename,
        "original_filename": document.original_filename,
        "file_type": document.file_type,
        "category": document.category,
        "tags": document.tags,
        "status": document.status,
        "error_message": document.error_message,
        "total_chunks": document.total_chunks,
        "active_chunks": len(active_chunks),
        "uploaded_at": document.uploaded_at,
        "updated_at": document.updated_at,
    }

    if include_chunks:
        data["chunks"] = [serialize_knowledge(chunk) for chunk in chunks]

    return data


def get_knowledge_or_404(knowledge_id: int, db: Session):
    entry = db.query(CompanyKnowledge).filter(CompanyKnowledge.id == knowledge_id).first()

    if not entry:
        raise HTTPException(
            status_code=404,
            detail=f"Knowledge entry with id {knowledge_id} was not found"
        )

    return entry


def commit_knowledge_change(db: Session, entry: CompanyKnowledge, error_message: str):
    try:
        db.commit()
        db.refresh(entry)
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=error_message) from exc


def commit_document_change(db: Session, document: KnowledgeDocument, error_message: str):
    try:
        db.commit()
        db.refresh(document)
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=error_message) from exc


def get_document_or_404(document_id: int, db: Session):
    document = (
        db.query(KnowledgeDocument)
        .options(joinedload(KnowledgeDocument.knowledge_entries))
        .filter(KnowledgeDocument.id == document_id)
        .first()
    )

    if not document:
        raise HTTPException(
            status_code=404,
            detail=f"Knowledge document with id {document_id} was not found"
        )

    return document


def mark_document_failed(db: Session, document: KnowledgeDocument, error_message: str):
    document.status = "failed"
    document.error_message = error_message
    document.updated_at = utc_now()
    commit_document_change(db, document, "Document status could not be updated.")


def safe_original_filename(filename: str | None):
    cleaned_filename = Path(filename or "knowledge_document").name.strip()
    return cleaned_filename or "knowledge_document"


def get_upload_file_type(filename: str):
    extension = Path(filename).suffix.lower()

    if extension not in ALLOWED_DOCUMENT_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail="Unsupported file type. Please upload PDF, DOCX, TXT, or MD."
        )

    return extension, extension.lstrip(".")


def save_temp_upload(contents: bytes, extension: str):
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=extension)

    try:
        temp_file.write(contents)
        temp_file.flush()
        return temp_file.name
    finally:
        temp_file.close()


def create_document_chunks(
    db: Session,
    document: KnowledgeDocument,
    chunks: list[str],
    category: str,
    tags: str | None,
):
    created_entries = []

    for index, chunk in enumerate(chunks, start=1):
        entry = CompanyKnowledge(
            title=f"{document.original_filename} - Chunk {index}",
            category=category,
            content=chunk,
            tags=tags,
            is_active=True,
            source_type="document",
            document_id=document.id,
            chunk_index=index,
        )
        created_entries.append(entry)
        db.add(entry)

    document.status = "processed"
    document.error_message = None
    document.total_chunks = len(chunks)
    document.updated_at = utc_now()

    try:
        db.commit()
        db.refresh(document)
        for entry in created_entries:
            db.refresh(entry)
    except SQLAlchemyError as exc:
        db.rollback()
        mark_document_failed(db, document, "Knowledge chunks could not be saved.")
        raise HTTPException(status_code=500, detail="Knowledge chunks could not be saved.") from exc

    for entry in created_entries:
        embed_knowledge_entry(db, entry)


@router.get("/")
def get_knowledge_entries(
    category: str | None = None,
    active_only: bool = Query(True),
    search: str | None = None,
    db: Session = Depends(get_db),
):
    query = db.query(CompanyKnowledge).options(joinedload(CompanyKnowledge.document))

    if active_only:
        query = query.filter(CompanyKnowledge.is_active.is_(True))

    if category:
        query = query.filter(CompanyKnowledge.category == validate_category(category))

    search_text = clean_text(search)

    if search_text:
        like_value = f"%{search_text}%"
        query = query.filter(
            or_(
                CompanyKnowledge.title.ilike(like_value),
                CompanyKnowledge.category.ilike(like_value),
                CompanyKnowledge.tags.ilike(like_value),
                CompanyKnowledge.content.ilike(like_value),
            )
        )

    entries = (
        query
        .order_by(CompanyKnowledge.is_active.desc(), CompanyKnowledge.updated_at.desc(), CompanyKnowledge.created_at.desc())
        .all()
    )

    return {
        "status": "success",
        "data": [serialize_knowledge(entry) for entry in entries],
        "categories": sorted(KNOWLEDGE_CATEGORIES),
    }


@router.post("/")
def create_knowledge_entry(
    knowledge: CompanyKnowledgeCreate,
    db: Session = Depends(get_db),
):
    title = clean_text(knowledge.title)
    content = clean_text(knowledge.content)
    category = validate_category(knowledge.category)
    tags = clean_text(knowledge.tags) or None

    if not title or not content:
        raise HTTPException(status_code=400, detail="Title and content are required.")

    entry = CompanyKnowledge(
        title=title,
        category=category,
        content=content,
        tags=tags,
        is_active=knowledge.is_active,
        source_type="manual",
    )
    db.add(entry)
    commit_knowledge_change(db, entry, "Knowledge entry could not be saved.")
    embed_knowledge_entry(db, entry)

    return {
        "status": "success",
        "message": "Knowledge entry created successfully",
        "data": serialize_knowledge(entry),
    }


@router.get("/search/relevant")
def get_relevant_knowledge(
    q: str = Query(..., min_length=1),
    limit: int = Query(5, ge=1),
    mode: str = Query("hybrid"),
    db: Session = Depends(get_db),
):
    normalized_mode = clean_text(mode).lower() or "hybrid"

    if normalized_mode not in {"hybrid", "semantic", "keyword"}:
        raise HTTPException(status_code=400, detail="Search mode must be hybrid, semantic, or keyword.")

    search_result = search_knowledge(
        db,
        q,
        limit=min(limit, MAX_KNOWLEDGE_SEARCH_LIMIT),
        mode=normalized_mode,
    )
    entries = search_result["results"]

    return {
        "status": "success",
        "query": q,
        "mode": normalized_mode,
        "retrieval_method": search_result.get("retrieval_method"),
        "semantic_available": search_result.get("semantic_available", False),
        "message": search_result.get("message"),
        "data": [serialize_knowledge(entry) for entry in entries],
    }


@router.get("/embeddings/status")
def get_knowledge_embedding_status(db: Session = Depends(get_db)):
    return {
        "status": "success",
        **get_embedding_status(db),
    }


@router.post("/embeddings/backfill")
def backfill_knowledge_embeddings(
    limit: int = Query(20, ge=1),
    db: Session = Depends(get_db),
):
    result = embed_missing_knowledge(db, limit=limit)

    return {
        "status": "success",
        **result,
    }


@router.post("/embeddings/test")
def test_knowledge_embedding():
    try:
        embedding = get_embedding("pricing depends on employees and modules")
    except Exception as exc:
        return {
            "status": "error",
            "model": settings.EMBEDDING_MODEL,
            **format_embedding_error("api_call", exc),
        }

    return {
        "status": "success",
        "model": settings.EMBEDDING_MODEL,
        "dimension": len(embedding),
        "sample_values": [float(value) for value in embedding[:3]],
    }


@router.post("/upload")
async def upload_knowledge_document(
    file: UploadFile = File(...),
    category: str | None = Form(None),
    tags: str | None = Form(None),
    db: Session = Depends(get_db),
):
    original_filename = safe_original_filename(file.filename)
    extension, file_type = get_upload_file_type(original_filename)
    upload_category = validate_category(category or "Other")
    upload_tags = clean_text(tags) or None
    contents = await file.read(MAX_UPLOAD_BYTES + 1)

    if len(contents) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File is too large. Max size is 5 MB.")

    if not contents:
        raise HTTPException(status_code=400, detail="Document uploaded but no readable text was found.")

    document = KnowledgeDocument(
        filename=f"{uuid4().hex}{extension}",
        original_filename=original_filename,
        file_type=file_type,
        category=upload_category,
        tags=upload_tags,
        status="processing",
        total_chunks=0,
        uploaded_at=utc_now(),
    )
    db.add(document)
    commit_document_change(db, document, "Document metadata could not be saved.")

    temp_file_path = None

    try:
        temp_file_path = save_temp_upload(contents, extension)
        extracted_text = extract_text_from_file(temp_file_path, file_type)
        chunks = chunk_text(extracted_text)

        if not extracted_text:
            raise DocumentExtractionError("Document uploaded but no readable text was found.")

        if not chunks:
            raise DocumentExtractionError("Document uploaded but no readable text was found.")

        create_document_chunks(db, document, chunks, upload_category, upload_tags)
    except DocumentExtractionError as exc:
        error_message = str(exc) or "Could not extract text from this document."
        mark_document_failed(db, document, error_message)
        raise HTTPException(status_code=422, detail=error_message) from exc
    finally:
        if temp_file_path and os.path.exists(temp_file_path):
            os.unlink(temp_file_path)

    return {
        "status": "success",
        "message": "Document uploaded and processed successfully",
        "data": {
            "document_id": document.id,
            "filename": document.original_filename,
            "file_type": document.file_type,
            "total_chunks": document.total_chunks,
            "category": document.category,
        },
    }


@router.get("/documents")
def get_knowledge_documents(db: Session = Depends(get_db)):
    documents = (
        db.query(KnowledgeDocument)
        .options(joinedload(KnowledgeDocument.knowledge_entries))
        .order_by(KnowledgeDocument.uploaded_at.desc(), KnowledgeDocument.id.desc())
        .all()
    )

    return {
        "status": "success",
        "data": [serialize_document(document) for document in documents],
    }


@router.get("/documents/{document_id}")
def get_knowledge_document(document_id: int, db: Session = Depends(get_db)):
    document = get_document_or_404(document_id, db)

    return {
        "status": "success",
        "data": serialize_document(document, include_chunks=True),
    }


@router.delete("/documents/{document_id}")
def deactivate_knowledge_document(document_id: int, db: Session = Depends(get_db)):
    document = get_document_or_404(document_id, db)
    now = utc_now()

    for chunk in document.knowledge_entries:
        chunk.is_active = False
        chunk.updated_at = now

    document.updated_at = now
    commit_document_change(db, document, "Document knowledge could not be deactivated.")

    return {
        "status": "success",
        "message": "Document knowledge deactivated successfully",
        "data": serialize_document(document, include_chunks=True),
    }


@router.post("/documents/{document_id}/reactivate")
def reactivate_knowledge_document(document_id: int, db: Session = Depends(get_db)):
    document = get_document_or_404(document_id, db)
    now = utc_now()

    for chunk in document.knowledge_entries:
        chunk.is_active = True
        chunk.updated_at = now

    document.updated_at = now
    commit_document_change(db, document, "Document knowledge could not be reactivated.")

    return {
        "status": "success",
        "message": "Document knowledge reactivated successfully",
        "data": serialize_document(document, include_chunks=True),
    }


@router.get("/{knowledge_id}")
def get_knowledge_entry(knowledge_id: int, db: Session = Depends(get_db)):
    entry = get_knowledge_or_404(knowledge_id, db)

    return {
        "status": "success",
        "data": serialize_knowledge(entry),
    }


@router.patch("/{knowledge_id}")
def update_knowledge_entry(
    knowledge_id: int,
    knowledge_update: CompanyKnowledgeUpdate,
    db: Session = Depends(get_db),
):
    entry = get_knowledge_or_404(knowledge_id, db)
    update_data = knowledge_update.model_dump(exclude_unset=True)

    if "title" in update_data:
        title = clean_text(update_data["title"])
        if not title:
            raise HTTPException(status_code=400, detail="Title is required.")
        entry.title = title

    if "category" in update_data:
        entry.category = validate_category(update_data["category"])

    if "content" in update_data:
        content = clean_text(update_data["content"])
        if not content:
            raise HTTPException(status_code=400, detail="Content is required.")
        entry.content = content

    if "tags" in update_data:
        entry.tags = clean_text(update_data["tags"]) or None

    if "is_active" in update_data:
        entry.is_active = bool(update_data["is_active"])

    entry.updated_at = utc_now()
    commit_knowledge_change(db, entry, "Knowledge entry could not be updated.")

    if any(field in update_data for field in {"title", "category", "content", "tags"}):
        embed_knowledge_entry(db, entry)

    return {
        "status": "success",
        "message": "Knowledge entry updated successfully",
        "data": serialize_knowledge(entry),
    }


@router.delete("/{knowledge_id}")
def delete_knowledge_entry(knowledge_id: int, db: Session = Depends(get_db)):
    entry = get_knowledge_or_404(knowledge_id, db)
    entry.is_active = False
    entry.updated_at = utc_now()
    commit_knowledge_change(db, entry, "Knowledge entry could not be deactivated.")

    return {
        "status": "success",
        "message": "Knowledge entry deactivated successfully",
        "data": serialize_knowledge(entry),
    }
