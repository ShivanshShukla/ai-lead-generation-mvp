import re
from pathlib import Path

MAX_DOCUMENT_CHUNKS = 50


class DocumentExtractionError(RuntimeError):
    pass


def sanitize_text(text):
    if text is None:
        return ""

    cleaned_text = str(text).replace("\x00", "")
    cleaned_text = cleaned_text.replace("\r\n", "\n").replace("\r", "\n")
    cleaned_text = re.sub(r"[ \t\f\v]+", " ", cleaned_text)
    cleaned_text = re.sub(r" *\n *", "\n", cleaned_text)
    cleaned_text = re.sub(r"\n{3,}", "\n\n", cleaned_text)

    return cleaned_text.strip()


def _extract_plain_text(file_path):
    path = Path(file_path)

    for encoding in ("utf-8", "utf-8-sig", "latin-1"):
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue

    raise DocumentExtractionError("Could not extract text from this document.")


def _extract_pdf_text(file_path):
    try:
        from pypdf import PdfReader

        reader = PdfReader(file_path)
        page_text = []

        for page in reader.pages:
            text = page.extract_text() or ""
            if text.strip():
                page_text.append(text)

        return "\n\n".join(page_text)
    except Exception as exc:
        raise DocumentExtractionError("Could not extract text from this document.") from exc


def _extract_docx_text(file_path):
    try:
        from docx import Document

        document = Document(file_path)
        paragraphs = [
            paragraph.text
            for paragraph in document.paragraphs
            if paragraph.text and paragraph.text.strip()
        ]

        return "\n\n".join(paragraphs)
    except Exception as exc:
        raise DocumentExtractionError("Could not extract text from this document.") from exc


def extract_text_from_file(file_path, file_type) -> str:
    normalized_file_type = str(file_type or "").lower().lstrip(".")

    if normalized_file_type in {"txt", "md"}:
        raw_text = _extract_plain_text(file_path)
    elif normalized_file_type == "pdf":
        raw_text = _extract_pdf_text(file_path)
    elif normalized_file_type == "docx":
        raw_text = _extract_docx_text(file_path)
    else:
        raise DocumentExtractionError("Unsupported file type. Please upload PDF, DOCX, TXT, or MD.")

    return sanitize_text(raw_text)


def _split_long_text(text, max_chars):
    chunks = []
    start = 0
    text_length = len(text)

    while start < text_length and len(chunks) < MAX_DOCUMENT_CHUNKS:
        end = min(start + max_chars, text_length)

        if end < text_length:
            split_at = max(
                text.rfind(". ", start, end),
                text.rfind("! ", start, end),
                text.rfind("? ", start, end),
                text.rfind(" ", start, end),
            )

            if split_at > start + max_chars // 2:
                end = split_at + 1

        chunk = sanitize_text(text[start:end])
        if chunk:
            chunks.append(chunk)

        start = end

    return chunks


def _overlap_tail(text, overlap):
    if not overlap:
        return ""

    tail = sanitize_text(text)[-overlap:]
    first_space = tail.find(" ")

    if first_space > 0:
        tail = tail[first_space + 1:]

    return sanitize_text(tail)


def chunk_text(text, max_chars=2500, overlap=250) -> list[str]:
    clean_text = sanitize_text(text)

    if not clean_text:
        return []

    safe_max_chars = max(500, int(max_chars or 2500))
    safe_overlap = max(0, min(int(overlap or 0), safe_max_chars // 3))
    body_max_chars = safe_max_chars - safe_overlap if safe_overlap else safe_max_chars
    paragraphs = [
        paragraph.strip()
        for paragraph in re.split(r"\n{2,}", clean_text)
        if paragraph and paragraph.strip()
    ]
    base_chunks = []
    current_chunk = ""

    for paragraph in paragraphs:
        if len(base_chunks) >= MAX_DOCUMENT_CHUNKS:
            break

        if len(paragraph) > body_max_chars:
            if current_chunk:
                base_chunks.append(sanitize_text(current_chunk))
                current_chunk = ""

            for chunk in _split_long_text(paragraph, body_max_chars):
                if len(base_chunks) >= MAX_DOCUMENT_CHUNKS:
                    break
                base_chunks.append(chunk)

            continue

        candidate = f"{current_chunk}\n\n{paragraph}" if current_chunk else paragraph

        if len(candidate) <= body_max_chars:
            current_chunk = candidate
            continue

        if current_chunk:
            base_chunks.append(sanitize_text(current_chunk))

        current_chunk = paragraph

    if current_chunk and len(base_chunks) < MAX_DOCUMENT_CHUNKS:
        base_chunks.append(sanitize_text(current_chunk))

    chunks = []

    for index, chunk in enumerate(base_chunks[:MAX_DOCUMENT_CHUNKS]):
        prefix = _overlap_tail(base_chunks[index - 1], safe_overlap) if index > 0 else ""
        combined_chunk = f"{prefix}\n\n{chunk}" if prefix else chunk
        combined_chunk = sanitize_text(combined_chunk)

        if combined_chunk:
            chunks.append(combined_chunk[:safe_max_chars].strip())

    return chunks[:MAX_DOCUMENT_CHUNKS]
