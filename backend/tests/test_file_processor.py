"""Tests for file processing service."""

from app.services.file_processor import chunk_text, extract_text, process_file, compute_sha256


def test_chunk_text_basic():
    text = "Hello world. " * 100
    chunks = chunk_text(text, chunk_size=200, overlap=50)
    assert len(chunks) > 1
    # Each chunk should be <= ~200 chars (with some tolerance)
    for chunk in chunks:
        assert len(chunk) < 400


def test_chunk_text_short():
    text = "Short text."
    chunks = chunk_text(text, chunk_size=1000)
    assert len(chunks) == 1
    assert chunks[0] == "Short text."


def test_chunk_text_empty():
    chunks = chunk_text("")
    assert len(chunks) == 0


def test_chunk_text_paragraphs():
    text = "Paragraph one about AI.\n\nParagraph two about governance.\n\nParagraph three about safety."
    chunks = chunk_text(text, chunk_size=50, overlap=10)
    assert len(chunks) >= 2


def test_extract_text_plain():
    data = b"Hello, this is plain text content."
    text = extract_text(data, "text/plain", "test.txt")
    assert "Hello" in text


def test_extract_text_csv():
    data = b"name,value\nAlice,100\nBob,200"
    text = extract_text(data, "text/csv", "data.csv")
    assert "Alice" in text


def test_process_file():
    data = b"This is a test document with some content about enterprise AI. " * 20
    result = process_file(data, "text/plain", "test.txt")
    assert result.text
    assert result.chunks
    assert result.metadata["filename"] == "test.txt"
    assert result.metadata["chunk_count"] > 0


def test_compute_sha256():
    data = b"test data"
    hash1 = compute_sha256(data)
    hash2 = compute_sha256(data)
    assert hash1 == hash2
    assert len(hash1) == 64
