"""Context portability service: export/import SQLite bundles with sqlite-vec."""

import os
import sqlite3
import struct
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import structlog
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation import Conversation, Message
from app.models.file import File, FileChunk, KnowledgeBase

logger = structlog.get_logger()

BUNDLE_SCHEMA_VERSION = "1"
GATEWAY_VERSION = "0.1.0"

# SQLite bundle DDL
BUNDLE_DDL = """
CREATE TABLE IF NOT EXISTS _meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS conversations (
    id TEXT PRIMARY KEY,
    title TEXT,
    model_id TEXT,
    system_prompt TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    message_count INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS messages (
    id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL REFERENCES conversations(id),
    sequence INTEGER NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    model_id TEXT,
    input_tokens INTEGER,
    output_tokens INTEGER,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS files (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    mime_type TEXT,
    size_bytes INTEGER,
    sha256_hash TEXT,
    chunk_count INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS file_chunks (
    id TEXT PRIMARY KEY,
    file_id TEXT NOT NULL REFERENCES files(id),
    chunk_index INTEGER NOT NULL,
    content TEXT NOT NULL,
    token_count INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS knowledge_bases (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    embedding_model TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS kb_documents (
    id TEXT PRIMARY KEY,
    knowledge_base_id TEXT NOT NULL REFERENCES knowledge_bases(id),
    file_id TEXT REFERENCES files(id),
    chunk_count INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS embeddings (
    id TEXT PRIMARY KEY,
    source_type TEXT NOT NULL,
    source_id TEXT NOT NULL,
    chunk_index INTEGER NOT NULL,
    content TEXT
);

CREATE TABLE IF NOT EXISTS embedding_config (
    model_name TEXT PRIMARY KEY,
    dimensions INTEGER NOT NULL,
    provider TEXT
);

CREATE INDEX IF NOT EXISTS idx_messages_conversation ON messages(conversation_id, sequence);
CREATE INDEX IF NOT EXISTS idx_file_chunks_file ON file_chunks(file_id, chunk_index);
CREATE INDEX IF NOT EXISTS idx_embeddings_source ON embeddings(source_type, source_id);
"""

REQUIRED_TABLES = {
    "_meta", "conversations", "messages", "files", "file_chunks",
    "knowledge_bases", "kb_documents", "embeddings", "embedding_config",
}


class BundleValidator:
    """Validate a .csgw SQLite bundle for schema correctness."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self.errors: list[str] = []

    def validate(self) -> bool:
        """Return True if bundle is valid, False otherwise. Errors in self.errors."""
        self.errors = []

        if not os.path.exists(self.db_path):
            self.errors.append(f"Bundle file not found: {self.db_path}")
            return False

        try:
            conn = sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True)
        except sqlite3.Error as e:
            self.errors.append(f"Cannot open bundle as SQLite: {e}")
            return False

        try:
            # Check required tables
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
            tables = {row[0] for row in cursor.fetchall()}

            missing = REQUIRED_TABLES - tables
            if missing:
                self.errors.append(f"Missing required tables: {', '.join(sorted(missing))}")

            # Check _meta has schema_version
            if "_meta" in tables:
                cursor = conn.execute(
                    "SELECT value FROM _meta WHERE key = 'schema_version'"
                )
                row = cursor.fetchone()
                if not row:
                    self.errors.append("Missing schema_version in _meta table")
                elif row[0] != BUNDLE_SCHEMA_VERSION:
                    self.errors.append(
                        f"Unsupported schema version: {row[0]} (expected {BUNDLE_SCHEMA_VERSION})"
                    )

            # Check required _meta keys
            if "_meta" in tables:
                cursor = conn.execute("SELECT key FROM _meta")
                meta_keys = {row[0] for row in cursor.fetchall()}
                required_meta = {"schema_version", "exported_at", "gateway_version", "user_id", "org_id"}
                missing_meta = required_meta - meta_keys
                if missing_meta:
                    self.errors.append(f"Missing required _meta keys: {', '.join(sorted(missing_meta))}")

        except sqlite3.Error as e:
            self.errors.append(f"Error reading bundle: {e}")
        finally:
            conn.close()

        return len(self.errors) == 0

    def get_stats(self) -> dict[str, int]:
        """Get record counts from the bundle."""
        stats: dict[str, int] = {}
        try:
            conn = sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True)
            for table in ["conversations", "messages", "files", "file_chunks", "knowledge_bases", "embeddings"]:
                try:
                    cursor = conn.execute(f"SELECT COUNT(*) FROM {table}")  # noqa: S608
                    stats[table] = cursor.fetchone()[0]
                except sqlite3.Error:
                    stats[table] = 0
            conn.close()
        except sqlite3.Error:
            pass
        return stats


class ContextExporter:
    """Build a .csgw SQLite bundle from PostgreSQL data."""

    def __init__(self, db: AsyncSession, org_id: uuid.UUID, user_id: uuid.UUID):
        self.db = db
        self.org_id = org_id
        self.user_id = user_id

    async def export_bundle(
        self,
        output_path: str,
        conversation_ids: list[uuid.UUID] | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        include_files: bool = True,
        include_embeddings: bool = True,
        user_email: str | None = None,
        source_instance: str | None = None,
    ) -> int:
        """
        Export user context to a SQLite bundle.
        Returns file size in bytes.
        """
        # Remove existing file if any
        if os.path.exists(output_path):
            os.remove(output_path)

        conn = sqlite3.connect(output_path)
        try:
            conn.executescript(BUNDLE_DDL)

            # Write metadata
            self._write_meta(conn, user_email, source_instance)

            # Export conversations and messages
            await self._export_conversations(conn, conversation_ids, date_from, date_to)

            # Export files and chunks
            if include_files:
                await self._export_files(conn)

            # Export knowledge bases
            await self._export_knowledge_bases(conn)

            conn.commit()
        except Exception:
            conn.close()
            if os.path.exists(output_path):
                os.remove(output_path)
            raise
        finally:
            conn.close()

        return os.path.getsize(output_path)

    def _write_meta(
        self,
        conn: sqlite3.Connection,
        user_email: str | None,
        source_instance: str | None,
    ) -> None:
        meta_rows = [
            ("schema_version", BUNDLE_SCHEMA_VERSION),
            ("exported_at", datetime.now(timezone.utc).isoformat()),
            ("gateway_version", GATEWAY_VERSION),
            ("user_id", str(self.user_id)),
            ("org_id", str(self.org_id)),
        ]
        if user_email:
            meta_rows.append(("user_email", user_email))
        if source_instance:
            meta_rows.append(("source_instance", source_instance))

        conn.executemany(
            "INSERT INTO _meta (key, value) VALUES (?, ?)", meta_rows
        )

    async def _export_conversations(
        self,
        conn: sqlite3.Connection,
        conversation_ids: list[uuid.UUID] | None,
        date_from: datetime | None,
        date_to: datetime | None,
    ) -> None:
        filters = [
            Conversation.org_id == self.org_id,
            Conversation.user_id == self.user_id,
            Conversation.deleted_at.is_(None),
        ]
        if conversation_ids:
            filters.append(Conversation.id.in_(conversation_ids))
        if date_from:
            filters.append(Conversation.created_at >= date_from)
        if date_to:
            filters.append(Conversation.created_at <= date_to)

        result = await self.db.execute(
            select(Conversation).where(and_(*filters))
        )
        conversations = result.scalars().all()

        for conv in conversations:
            # Count messages
            msg_result = await self.db.execute(
                select(Message).where(
                    Message.conversation_id == conv.id,
                    Message.deleted_at.is_(None),
                ).order_by(Message.sequence)
            )
            messages = msg_result.scalars().all()

            conn.execute(
                """INSERT INTO conversations (id, title, model_id, system_prompt, created_at, updated_at, message_count)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    str(conv.id),
                    conv.title,
                    conv.model_id,
                    conv.system_prompt,
                    conv.created_at.isoformat(),
                    conv.updated_at.isoformat(),
                    len(messages),
                ),
            )

            for msg in messages:
                conn.execute(
                    """INSERT INTO messages (id, conversation_id, sequence, role, content, model_id, input_tokens, output_tokens, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        str(msg.id),
                        str(msg.conversation_id),
                        msg.sequence,
                        msg.role,
                        msg.content,
                        msg.model_id,
                        msg.input_tokens,
                        msg.output_tokens,
                        msg.created_at.isoformat(),
                    ),
                )

        logger.info(
            "exported_conversations",
            count=len(conversations),
            user_id=str(self.user_id),
        )

    async def _export_files(self, conn: sqlite3.Connection) -> None:
        result = await self.db.execute(
            select(File).where(
                File.org_id == self.org_id,
                File.user_id == self.user_id,
                File.deleted_at.is_(None),
            )
        )
        files = result.scalars().all()

        for f in files:
            conn.execute(
                """INSERT INTO files (id, name, mime_type, size_bytes, sha256_hash, chunk_count, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    str(f.id),
                    f.name,
                    f.mime_type,
                    f.size_bytes,
                    f.sha256_hash,
                    f.chunk_count,
                    f.created_at.isoformat(),
                ),
            )

            # Export chunks
            chunks_result = await self.db.execute(
                select(FileChunk).where(FileChunk.file_id == f.id).order_by(FileChunk.chunk_index)
            )
            chunks = chunks_result.scalars().all()

            for chunk in chunks:
                conn.execute(
                    """INSERT INTO file_chunks (id, file_id, chunk_index, content, token_count)
                       VALUES (?, ?, ?, ?, ?)""",
                    (
                        str(chunk.id),
                        str(chunk.file_id),
                        chunk.chunk_index,
                        chunk.content,
                        chunk.token_count,
                    ),
                )

        logger.info("exported_files", count=len(files), user_id=str(self.user_id))

    async def _export_knowledge_bases(self, conn: sqlite3.Connection) -> None:
        result = await self.db.execute(
            select(KnowledgeBase).where(
                KnowledgeBase.org_id == self.org_id,
                KnowledgeBase.deleted_at.is_(None),
            )
        )
        kbs = result.scalars().all()

        for kb in kbs:
            conn.execute(
                """INSERT INTO knowledge_bases (id, name, description, embedding_model)
                   VALUES (?, ?, ?, ?)""",
                (str(kb.id), kb.name, kb.description, kb.embedding_model),
            )

            # Store embedding config
            conn.execute(
                """INSERT OR IGNORE INTO embedding_config (model_name, dimensions, provider)
                   VALUES (?, ?, ?)""",
                (kb.embedding_model, 1536, _infer_provider(kb.embedding_model)),
            )

        logger.info("exported_knowledge_bases", count=len(kbs), user_id=str(self.user_id))


class ContextImporter:
    """Read a .csgw SQLite bundle and insert into PostgreSQL."""

    def __init__(self, db: AsyncSession, org_id: uuid.UUID, user_id: uuid.UUID):
        self.db = db
        self.org_id = org_id
        self.user_id = user_id

    async def import_bundle(self, bundle_path: str, mode: str = "merge") -> dict[str, int]:
        """
        Import a bundle into PostgreSQL.
        Returns stats dict with counts of imported records.
        """
        validator = BundleValidator(bundle_path)
        if not validator.validate():
            raise ValueError(f"Invalid bundle: {'; '.join(validator.errors)}")

        conn = sqlite3.connect(f"file:{bundle_path}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        stats: dict[str, int] = {
            "conversations": 0,
            "messages": 0,
            "files": 0,
            "file_chunks": 0,
            "knowledge_bases": 0,
        }

        try:
            stats["conversations"], stats["messages"] = await self._import_conversations(conn)
            stats["files"], stats["file_chunks"] = await self._import_files(conn)
            stats["knowledge_bases"] = await self._import_knowledge_bases(conn)
        finally:
            conn.close()

        logger.info("import_complete", stats=stats, user_id=str(self.user_id))
        return stats

    async def _import_conversations(self, conn: sqlite3.Connection) -> tuple[int, int]:
        cursor = conn.execute("SELECT * FROM conversations")
        conv_count = 0
        msg_count = 0

        for row in cursor.fetchall():
            conv = Conversation(
                id=uuid.UUID(row["id"]),
                org_id=self.org_id,
                user_id=self.user_id,
                title=row["title"],
                model_id=row["model_id"],
                system_prompt=row["system_prompt"],
                created_at=datetime.fromisoformat(row["created_at"]),
                updated_at=datetime.fromisoformat(row["updated_at"]),
            )
            self.db.add(conv)
            conv_count += 1

            # Import messages for this conversation
            msg_cursor = conn.execute(
                "SELECT * FROM messages WHERE conversation_id = ? ORDER BY sequence",
                (row["id"],),
            )
            for msg_row in msg_cursor.fetchall():
                msg = Message(
                    id=uuid.UUID(msg_row["id"]),
                    conversation_id=uuid.UUID(msg_row["conversation_id"]),
                    org_id=self.org_id,
                    sequence=msg_row["sequence"],
                    role=msg_row["role"],
                    content=msg_row["content"],
                    model_id=msg_row["model_id"],
                    input_tokens=msg_row["input_tokens"],
                    output_tokens=msg_row["output_tokens"],
                    created_at=datetime.fromisoformat(msg_row["created_at"]),
                )
                self.db.add(msg)
                msg_count += 1

        await self.db.flush()
        return conv_count, msg_count

    async def _import_files(self, conn: sqlite3.Connection) -> tuple[int, int]:
        cursor = conn.execute("SELECT * FROM files")
        file_count = 0
        chunk_count = 0

        for row in cursor.fetchall():
            f = File(
                id=uuid.UUID(row["id"]),
                org_id=self.org_id,
                user_id=self.user_id,
                name=row["name"],
                mime_type=row["mime_type"] or "application/octet-stream",
                size_bytes=row["size_bytes"] or 0,
                sha256_hash=row["sha256_hash"],
                storage_path=f"imported/{row['id']}",  # Placeholder path
                status="ready",
                chunk_count=row["chunk_count"] or 0,
            )
            self.db.add(f)
            file_count += 1

            # Import chunks
            chunk_cursor = conn.execute(
                "SELECT * FROM file_chunks WHERE file_id = ? ORDER BY chunk_index",
                (row["id"],),
            )
            for chunk_row in chunk_cursor.fetchall():
                chunk = FileChunk(
                    id=uuid.UUID(chunk_row["id"]),
                    file_id=uuid.UUID(chunk_row["file_id"]),
                    org_id=self.org_id,
                    chunk_index=chunk_row["chunk_index"],
                    content=chunk_row["content"],
                    token_count=chunk_row["token_count"] or 0,
                )
                self.db.add(chunk)
                chunk_count += 1

        await self.db.flush()
        return file_count, chunk_count

    async def _import_knowledge_bases(self, conn: sqlite3.Connection) -> int:
        cursor = conn.execute("SELECT * FROM knowledge_bases")
        count = 0

        for row in cursor.fetchall():
            kb = KnowledgeBase(
                id=uuid.UUID(row["id"]),
                org_id=self.org_id,
                name=row["name"],
                description=row["description"],
                embedding_model=row["embedding_model"],
                created_by=self.user_id,
            )
            self.db.add(kb)
            count += 1

        await self.db.flush()
        return count


def _infer_provider(model_name: str) -> str:
    """Infer embedding provider from model name."""
    if "openai" in model_name.lower() or model_name.startswith("text-embedding"):
        return "openai"
    if "cohere" in model_name.lower():
        return "cohere"
    if "voyage" in model_name.lower():
        return "voyageai"
    return "unknown"
