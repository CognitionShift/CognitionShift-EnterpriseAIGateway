"""Tests for context portability bundle builder and validator."""

import os
import sqlite3
import tempfile
import uuid
from datetime import datetime, timezone

import pytest

from app.services.context_portability import (
    BUNDLE_DDL,
    BUNDLE_SCHEMA_VERSION,
    BundleValidator,
    REQUIRED_TABLES,
)


@pytest.fixture
def tmp_dir():
    with tempfile.TemporaryDirectory() as d:
        yield d


def _create_valid_bundle(path: str) -> None:
    """Create a minimal valid .csgw bundle."""
    conn = sqlite3.connect(path)
    conn.executescript(BUNDLE_DDL)
    meta_rows = [
        ("schema_version", BUNDLE_SCHEMA_VERSION),
        ("exported_at", datetime.now(timezone.utc).isoformat()),
        ("gateway_version", "0.1.0"),
        ("user_id", str(uuid.uuid4())),
        ("org_id", str(uuid.uuid4())),
    ]
    conn.executemany("INSERT INTO _meta (key, value) VALUES (?, ?)", meta_rows)
    conn.commit()
    conn.close()


def _create_bundle_with_data(path: str) -> dict:
    """Create a bundle with sample conversations and messages."""
    conn = sqlite3.connect(path)
    conn.executescript(BUNDLE_DDL)

    user_id = str(uuid.uuid4())
    org_id = str(uuid.uuid4())
    conv_id = str(uuid.uuid4())
    msg1_id = str(uuid.uuid4())
    msg2_id = str(uuid.uuid4())
    file_id = str(uuid.uuid4())
    chunk_id = str(uuid.uuid4())
    kb_id = str(uuid.uuid4())

    meta_rows = [
        ("schema_version", BUNDLE_SCHEMA_VERSION),
        ("exported_at", datetime.now(timezone.utc).isoformat()),
        ("gateway_version", "0.1.0"),
        ("user_id", user_id),
        ("org_id", org_id),
        ("user_email", "test@example.com"),
    ]
    conn.executemany("INSERT INTO _meta (key, value) VALUES (?, ?)", meta_rows)

    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT INTO conversations VALUES (?, ?, ?, ?, ?, ?, ?)",
        (conv_id, "Test Conversation", "claude-sonnet-4-20250514", None, now, now, 2),
    )
    conn.execute(
        "INSERT INTO messages VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (msg1_id, conv_id, 1, "user", "Hello there", None, 5, None, now),
    )
    conn.execute(
        "INSERT INTO messages VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (msg2_id, conv_id, 2, "assistant", "Hi! How can I help?", "claude-sonnet-4-20250514", None, 12, now),
    )
    conn.execute(
        "INSERT INTO files VALUES (?, ?, ?, ?, ?, ?, ?)",
        (file_id, "readme.md", "text/markdown", 1024, "abc123", 1, now),
    )
    conn.execute(
        "INSERT INTO file_chunks VALUES (?, ?, ?, ?, ?)",
        (chunk_id, file_id, 0, "# README\nThis is a test file.", 10),
    )
    conn.execute(
        "INSERT INTO knowledge_bases VALUES (?, ?, ?, ?)",
        (kb_id, "Test KB", "A test knowledge base", "text-embedding-3-small"),
    )
    conn.execute(
        "INSERT INTO embedding_config VALUES (?, ?, ?)",
        ("text-embedding-3-small", 1536, "openai"),
    )

    conn.commit()
    conn.close()

    return {
        "user_id": user_id,
        "org_id": org_id,
        "conv_id": conv_id,
        "msg_ids": [msg1_id, msg2_id],
        "file_id": file_id,
        "chunk_id": chunk_id,
        "kb_id": kb_id,
    }


class TestBundleValidator:
    def test_valid_bundle(self, tmp_dir):
        path = os.path.join(tmp_dir, "valid.csgw")
        _create_valid_bundle(path)
        validator = BundleValidator(path)
        assert validator.validate() is True
        assert validator.errors == []

    def test_missing_file(self, tmp_dir):
        validator = BundleValidator(os.path.join(tmp_dir, "nonexistent.csgw"))
        assert validator.validate() is False
        assert len(validator.errors) == 1
        assert "not found" in validator.errors[0]

    def test_not_sqlite(self, tmp_dir):
        path = os.path.join(tmp_dir, "bad.csgw")
        with open(path, "w") as f:
            f.write("this is not a sqlite database")
        validator = BundleValidator(path)
        assert validator.validate() is False

    def test_missing_tables(self, tmp_dir):
        path = os.path.join(tmp_dir, "incomplete.csgw")
        conn = sqlite3.connect(path)
        conn.execute("CREATE TABLE _meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        conn.execute("INSERT INTO _meta VALUES ('schema_version', '1')")
        conn.commit()
        conn.close()

        validator = BundleValidator(path)
        assert validator.validate() is False
        assert any("Missing required tables" in e for e in validator.errors)

    def test_wrong_schema_version(self, tmp_dir):
        path = os.path.join(tmp_dir, "wrong_version.csgw")
        conn = sqlite3.connect(path)
        conn.executescript(BUNDLE_DDL)
        conn.execute("INSERT INTO _meta VALUES ('schema_version', '99')")
        conn.execute("INSERT INTO _meta VALUES ('exported_at', '2026-01-01')")
        conn.execute("INSERT INTO _meta VALUES ('gateway_version', '0.1.0')")
        conn.execute("INSERT INTO _meta VALUES ('user_id', 'abc')")
        conn.execute("INSERT INTO _meta VALUES ('org_id', 'def')")
        conn.commit()
        conn.close()

        validator = BundleValidator(path)
        assert validator.validate() is False
        assert any("Unsupported schema version" in e for e in validator.errors)

    def test_missing_meta_keys(self, tmp_dir):
        path = os.path.join(tmp_dir, "missing_meta.csgw")
        conn = sqlite3.connect(path)
        conn.executescript(BUNDLE_DDL)
        conn.execute("INSERT INTO _meta VALUES ('schema_version', '1')")
        # Missing exported_at, gateway_version, user_id, org_id
        conn.commit()
        conn.close()

        validator = BundleValidator(path)
        assert validator.validate() is False
        assert any("Missing required _meta keys" in e for e in validator.errors)


class TestBundleStats:
    def test_get_stats_empty(self, tmp_dir):
        path = os.path.join(tmp_dir, "empty.csgw")
        _create_valid_bundle(path)
        validator = BundleValidator(path)
        stats = validator.get_stats()
        assert stats["conversations"] == 0
        assert stats["messages"] == 0

    def test_get_stats_with_data(self, tmp_dir):
        path = os.path.join(tmp_dir, "data.csgw")
        _create_bundle_with_data(path)
        validator = BundleValidator(path)
        stats = validator.get_stats()
        assert stats["conversations"] == 1
        assert stats["messages"] == 2
        assert stats["files"] == 1
        assert stats["file_chunks"] == 1
        assert stats["knowledge_bases"] == 1


class TestBundleSchema:
    def test_ddl_creates_all_tables(self, tmp_dir):
        path = os.path.join(tmp_dir, "schema.csgw")
        conn = sqlite3.connect(path)
        conn.executescript(BUNDLE_DDL)
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {row[0] for row in cursor.fetchall()}
        conn.close()

        assert REQUIRED_TABLES.issubset(tables)

    def test_message_conversation_fk(self, tmp_dir):
        """Messages reference conversations via conversation_id."""
        path = os.path.join(tmp_dir, "fk.csgw")
        conn = sqlite3.connect(path)
        conn.execute("PRAGMA foreign_keys = ON")
        conn.executescript(BUNDLE_DDL)

        conv_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            "INSERT INTO conversations VALUES (?, ?, ?, ?, ?, ?, ?)",
            (conv_id, "Test", None, None, now, now, 0),
        )

        # This should succeed (valid FK)
        msg_id = str(uuid.uuid4())
        conn.execute(
            "INSERT INTO messages VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (msg_id, conv_id, 1, "user", "test", None, None, None, now),
        )
        conn.commit()

        # Verify the message was inserted
        cursor = conn.execute("SELECT COUNT(*) FROM messages")
        assert cursor.fetchone()[0] == 1
        conn.close()

    def test_bundle_indices_exist(self, tmp_dir):
        """Check that expected indices are created."""
        path = os.path.join(tmp_dir, "idx.csgw")
        conn = sqlite3.connect(path)
        conn.executescript(BUNDLE_DDL)
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='index'")
        indices = {row[0] for row in cursor.fetchall()}
        conn.close()

        assert "idx_messages_conversation" in indices
        assert "idx_file_chunks_file" in indices
        assert "idx_embeddings_source" in indices


class TestBundleDataIntegrity:
    def test_round_trip_data(self, tmp_dir):
        """Write data to a bundle, read it back, verify integrity."""
        path = os.path.join(tmp_dir, "roundtrip.csgw")
        ids = _create_bundle_with_data(path)

        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row

        # Verify conversation
        row = conn.execute("SELECT * FROM conversations WHERE id = ?", (ids["conv_id"],)).fetchone()
        assert row["title"] == "Test Conversation"
        assert row["model_id"] == "claude-sonnet-4-20250514"
        assert row["message_count"] == 2

        # Verify messages
        msgs = conn.execute(
            "SELECT * FROM messages WHERE conversation_id = ? ORDER BY sequence",
            (ids["conv_id"],),
        ).fetchall()
        assert len(msgs) == 2
        assert msgs[0]["role"] == "user"
        assert msgs[0]["content"] == "Hello there"
        assert msgs[1]["role"] == "assistant"
        assert msgs[1]["content"] == "Hi! How can I help?"

        # Verify file
        f = conn.execute("SELECT * FROM files WHERE id = ?", (ids["file_id"],)).fetchone()
        assert f["name"] == "readme.md"
        assert f["mime_type"] == "text/markdown"

        # Verify chunk
        c = conn.execute("SELECT * FROM file_chunks WHERE id = ?", (ids["chunk_id"],)).fetchone()
        assert c["content"] == "# README\nThis is a test file."

        # Verify KB
        kb = conn.execute("SELECT * FROM knowledge_bases WHERE id = ?", (ids["kb_id"],)).fetchone()
        assert kb["name"] == "Test KB"
        assert kb["embedding_model"] == "text-embedding-3-small"

        # Verify embedding config
        ec = conn.execute("SELECT * FROM embedding_config WHERE model_name = 'text-embedding-3-small'").fetchone()
        assert ec["dimensions"] == 1536
        assert ec["provider"] == "openai"

        conn.close()

    def test_meta_values(self, tmp_dir):
        """Verify _meta table content."""
        path = os.path.join(tmp_dir, "meta.csgw")
        ids = _create_bundle_with_data(path)

        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row

        meta = {}
        for row in conn.execute("SELECT * FROM _meta").fetchall():
            meta[row["key"]] = row["value"]

        assert meta["schema_version"] == BUNDLE_SCHEMA_VERSION
        assert meta["gateway_version"] == "0.1.0"
        assert meta["user_id"] == ids["user_id"]
        assert meta["org_id"] == ids["org_id"]
        assert meta["user_email"] == "test@example.com"
        assert "exported_at" in meta

        conn.close()
