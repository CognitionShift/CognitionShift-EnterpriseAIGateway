"""File processing service — parsing, chunking, and embedding."""

import os
import hashlib
import uuid
from pathlib import Path
from dataclasses import dataclass
import structlog

logger = structlog.get_logger()

UPLOAD_DIR = os.environ.get("UPLOAD_DIR", "/app/uploads")
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB

ALLOWED_TYPES = {
    "text/plain": ".txt",
    "text/csv": ".csv",
    "text/markdown": ".md",
    "application/pdf": ".pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
    "application/json": ".json",
}


@dataclass
class ProcessedFile:
    text: str
    chunks: list[str]
    metadata: dict


def compute_sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def save_file(data: bytes, org_id: uuid.UUID, file_id: uuid.UUID, ext: str) -> str:
    """Save file to local storage. Returns storage path."""
    dir_path = Path(UPLOAD_DIR) / str(org_id)
    dir_path.mkdir(parents=True, exist_ok=True)
    file_path = dir_path / f"{file_id}{ext}"
    file_path.write_bytes(data)
    return str(file_path)


def extract_text(data: bytes, mime_type: str, filename: str) -> str:
    """Extract text content from various file types."""
    if mime_type in ("text/plain", "text/csv", "text/markdown"):
        return data.decode("utf-8", errors="replace")

    if mime_type == "application/json":
        return data.decode("utf-8", errors="replace")

    if mime_type == "application/pdf":
        return _extract_pdf(data)

    if mime_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
        return _extract_docx(data)

    return data.decode("utf-8", errors="replace")


def _extract_pdf(data: bytes) -> str:
    """Extract text from PDF. Falls back gracefully if libraries missing."""
    try:
        import io
        # Try pypdf first (lightweight)
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(data))
        text_parts = []
        for page in reader.pages:
            text = page.extract_text()
            if text:
                text_parts.append(text)
        return "\n\n".join(text_parts)
    except ImportError:
        logger.warning("pypdf_not_installed")
        return "[PDF parsing requires pypdf — install with: pip install pypdf]"
    except Exception as e:
        logger.error("pdf_extraction_failed", error=str(e))
        return f"[PDF extraction failed: {str(e)}]"


def _extract_docx(data: bytes) -> str:
    """Extract text from DOCX."""
    try:
        import io
        from docx import Document
        doc = Document(io.BytesIO(data))
        return "\n\n".join(p.text for p in doc.paragraphs if p.text.strip())
    except ImportError:
        logger.warning("python-docx_not_installed")
        return "[DOCX parsing requires python-docx — install with: pip install python-docx]"
    except Exception as e:
        logger.error("docx_extraction_failed", error=str(e))
        return f"[DOCX extraction failed: {str(e)}]"


def chunk_text(text: str, chunk_size: int = 1000, overlap: int = 200) -> list[str]:
    """
    Split text into overlapping chunks.
    Uses paragraph boundaries when possible, falls back to character splitting.
    """
    if not text.strip():
        return []

    # Split on paragraphs first
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]

    chunks = []
    current_chunk = ""

    for para in paragraphs:
        # If adding this paragraph exceeds chunk_size, save current and start new
        if len(current_chunk) + len(para) + 2 > chunk_size and current_chunk:
            chunks.append(current_chunk.strip())
            # Overlap: keep the tail of the current chunk
            if overlap > 0 and len(current_chunk) > overlap:
                current_chunk = current_chunk[-overlap:] + "\n\n" + para
            else:
                current_chunk = para
        else:
            current_chunk = (current_chunk + "\n\n" + para).strip()

    if current_chunk.strip():
        chunks.append(current_chunk.strip())

    # Handle case where a single paragraph is longer than chunk_size
    final_chunks = []
    for chunk in chunks:
        if len(chunk) > chunk_size * 1.5:
            # Force split on sentences or characters
            words = chunk.split()
            sub_chunk = ""
            for word in words:
                if len(sub_chunk) + len(word) + 1 > chunk_size and sub_chunk:
                    final_chunks.append(sub_chunk.strip())
                    sub_chunk = word
                else:
                    sub_chunk = (sub_chunk + " " + word).strip()
            if sub_chunk.strip():
                final_chunks.append(sub_chunk.strip())
        else:
            final_chunks.append(chunk)

    return final_chunks


def process_file(data: bytes, mime_type: str, filename: str) -> ProcessedFile:
    """Full file processing pipeline: extract → chunk → return."""
    text = extract_text(data, mime_type, filename)
    chunks = chunk_text(text)

    return ProcessedFile(
        text=text,
        chunks=chunks,
        metadata={
            "filename": filename,
            "mime_type": mime_type,
            "size_bytes": len(data),
            "text_length": len(text),
            "chunk_count": len(chunks),
        },
    )
