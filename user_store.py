from __future__ import annotations

import json
import re
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from werkzeug.security import check_password_hash, generate_password_hash

EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
WORD_RE = re.compile(r"[A-Za-z0-9]+(?:['’\-][A-Za-z0-9]+)*")
TAG_RE = re.compile(r"[^a-zA-Z0-9_\- ]+")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def normalize_email(email: str) -> str:
    return str(email or "").strip().lower()


def clean_title(title: str, lyrics: str = "") -> str:
    title = str(title or "").strip()
    if not title:
        for line in str(lyrics or "").splitlines():
            line = line.strip()
            if line and not line.startswith("//"):
                title = line[:64]
                break
    if not title:
        title = "Untitled rap"
    title = re.sub(r"\s+", " ", title).strip()
    return title[:120]


def normalize_tags(tags: Any) -> List[str]:
    if tags is None:
        return []
    if isinstance(tags, str):
        raw = re.split(r"[,#\n]+", tags)
    elif isinstance(tags, (list, tuple, set)):
        raw = list(tags)
    else:
        raw = []
    cleaned: List[str] = []
    seen = set()
    for item in raw:
        tag = TAG_RE.sub("", str(item or "").strip().lower())
        tag = re.sub(r"\s+", "-", tag).strip("-_ ")
        if not tag or tag in seen:
            continue
        seen.add(tag)
        cleaned.append(tag[:40])
        if len(cleaned) >= 12:
            break
    return cleaned


def _json_load(value: Any, fallback: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value or "")
    except Exception:
        return fallback


def _json_dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def public_user(row: sqlite3.Row | Dict[str, Any] | None) -> Optional[Dict[str, Any]]:
    if row is None:
        return None
    data = dict(row)
    return {
        "id": data.get("id"),
        "email": data.get("email"),
        "display_name": data.get("display_name") or data.get("email"),
        "created_at": data.get("created_at"),
        "updated_at": data.get("updated_at"),
    }


def _basic_stats(lyrics: str) -> Dict[str, Any]:
    words = WORD_RE.findall(lyrics or "")
    lines = [line for line in str(lyrics or "").splitlines() if line.strip()]
    chars = len(lyrics or "")
    return {
        "word_count": len(words),
        "line_count": len(lines),
        "char_count": chars,
    }


def rap_summary(row: sqlite3.Row | Dict[str, Any]) -> Dict[str, Any]:
    data = dict(row)
    lyrics = data.get("lyrics") or ""
    stats = _basic_stats(lyrics)
    tags_source = _json_load(data.get("tags_json"), data.get("tags", []))
    tags = normalize_tags(tags_source if tags_source is not None else data.get("tags", []))
    metadata = _json_load(data.get("metadata_json"), data.get("metadata", {}))
    last_snapshot = _json_load(data.get("last_snapshot_json"), data.get("last_snapshot", {}))
    preview = " ".join(lyrics.strip().split())[:220]
    return {
        "id": data.get("id"),
        "title": data.get("title") or "Untitled rap",
        "coach_mode": data.get("coach_mode") or "match",
        "created_at": data.get("created_at"),
        "updated_at": data.get("updated_at"),
        "word_count": stats["word_count"],
        "line_count": stats["line_count"],
        "char_count": stats["char_count"],
        "preview": preview,
        "tags": tags,
        "notes": data.get("notes") or "",
        "pinned": bool(data.get("pinned") or 0),
        "archived": bool(data.get("archived") or 0),
        "version_count": int(data.get("version_count") or 0),
        "last_score": data.get("last_score"),
        "last_snapshot_at": data.get("last_snapshot_at"),
        "last_snapshot_summary": last_snapshot.get("summary") if isinstance(last_snapshot, dict) else None,
        "metadata": metadata if isinstance(metadata, dict) else {},
    }


def rap_detail(row: sqlite3.Row | Dict[str, Any]) -> Dict[str, Any]:
    data = dict(row)
    detail = rap_summary(data)
    detail.update({
        "lyrics": data.get("lyrics") or "",
        "metadata": _json_load(data.get("metadata_json"), {}),
        "last_snapshot": _json_load(data.get("last_snapshot_json"), {}),
    })
    return detail


def version_detail(row: sqlite3.Row | Dict[str, Any]) -> Dict[str, Any]:
    data = dict(row)
    lyrics = data.get("lyrics") or ""
    stats = _basic_stats(lyrics)
    metadata = _json_load(data.get("metadata_json"), {})
    return {
        "id": data.get("id"),
        "rap_id": data.get("rap_id"),
        "version_number": int(data.get("version_number") or 0),
        "title": data.get("title") or "Untitled rap",
        "lyrics": lyrics,
        "coach_mode": data.get("coach_mode") or "match",
        "metadata": metadata if isinstance(metadata, dict) else {},
        "change_note": data.get("change_note") or "",
        "created_at": data.get("created_at"),
        "word_count": stats["word_count"],
        "line_count": stats["line_count"],
        "char_count": stats["char_count"],
        "preview": " ".join(lyrics.strip().split())[:180],
    }


def version_summary(row: sqlite3.Row | Dict[str, Any]) -> Dict[str, Any]:
    data = version_detail(row)
    data.pop("lyrics", None)
    return data


class UserStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.path), timeout=20)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            conn.execute("PRAGMA journal_mode = WAL")
        except sqlite3.DatabaseError:
            # Some hosted filesystems disallow WAL. Plain SQLite mode is fine for beta use.
            pass
        return conn

    def _ensure_columns(self, conn: sqlite3.Connection, table: str, columns: Dict[str, str]) -> None:
        existing = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        for name, ddl in columns.items():
            if name not in existing:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}")

    def init_db(self) -> None:
        with self.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,
                    email TEXT NOT NULL UNIQUE,
                    display_name TEXT,
                    password_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS raps (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    lyrics TEXT NOT NULL,
                    coach_mode TEXT DEFAULT 'match',
                    metadata_json TEXT DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    deleted_at TEXT,
                    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS rap_versions (
                    id TEXT PRIMARY KEY,
                    rap_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    version_number INTEGER NOT NULL,
                    title TEXT NOT NULL,
                    lyrics TEXT NOT NULL,
                    coach_mode TEXT DEFAULT 'match',
                    metadata_json TEXT DEFAULT '{}',
                    change_note TEXT DEFAULT '',
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(rap_id) REFERENCES raps(id) ON DELETE CASCADE,
                    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_raps_user_updated ON raps(user_id, updated_at DESC);
                CREATE INDEX IF NOT EXISTS idx_raps_user_title ON raps(user_id, title);
                CREATE INDEX IF NOT EXISTS idx_rap_versions_rap ON rap_versions(rap_id, version_number DESC);
                CREATE INDEX IF NOT EXISTS idx_rap_versions_user ON rap_versions(user_id, created_at DESC);
                """
            )
            self._ensure_columns(conn, "raps", {
                "tags_json": "TEXT DEFAULT '[]'",
                "notes": "TEXT DEFAULT ''",
                "pinned": "INTEGER DEFAULT 0",
                "archived": "INTEGER DEFAULT 0",
                "last_score": "REAL",
                "last_snapshot_json": "TEXT DEFAULT '{}'",
                "last_snapshot_at": "TEXT",
            })
            self._ensure_columns(conn, "rap_versions", {
                "change_note": "TEXT DEFAULT ''",
            })

    def create_user(self, email: str, password: str, display_name: str = "") -> Dict[str, Any]:
        email = normalize_email(email)
        if not EMAIL_RE.match(email):
            raise ValueError("Enter a valid email address.")
        password = str(password or "")
        if len(password) < 8:
            raise ValueError("Password must be at least 8 characters.")
        now = utc_now()
        user_id = uuid.uuid4().hex
        display_name = str(display_name or "").strip()[:120] or email.split("@", 1)[0]
        pw_hash = generate_password_hash(password)
        try:
            with self.connect() as conn:
                conn.execute(
                    "INSERT INTO users (id, email, display_name, password_hash, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
                    (user_id, email, display_name, pw_hash, now, now),
                )
                row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        except sqlite3.IntegrityError as exc:
            raise ValueError("An account with that email already exists.") from exc
        return public_user(row) or {}

    def authenticate(self, email: str, password: str) -> Optional[Dict[str, Any]]:
        email = normalize_email(email)
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        if not row:
            return None
        if not check_password_hash(row["password_hash"], str(password or "")):
            return None
        return public_user(row)

    def get_user(self, user_id: str) -> Optional[Dict[str, Any]]:
        if not user_id:
            return None
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM users WHERE id = ?", (str(user_id),)).fetchone()
        return public_user(row)

    def _version_number(self, conn: sqlite3.Connection, rap_id: str) -> int:
        row = conn.execute("SELECT COALESCE(MAX(version_number), 0) + 1 FROM rap_versions WHERE rap_id = ?", (rap_id,)).fetchone()
        return int(row[0] or 1)

    def _insert_version(
        self,
        conn: sqlite3.Connection,
        user_id: str,
        rap_id: str,
        title: str,
        lyrics: str,
        coach_mode: str,
        metadata: Optional[Dict[str, Any]] = None,
        change_note: str = "",
    ) -> Dict[str, Any]:
        version_id = uuid.uuid4().hex
        version_number = self._version_number(conn, rap_id)
        now = utc_now()
        conn.execute(
            """
            INSERT INTO rap_versions (id, rap_id, user_id, version_number, title, lyrics, coach_mode, metadata_json, change_note, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (version_id, rap_id, user_id, version_number, title, lyrics, coach_mode or "match", _json_dump(metadata or {}), str(change_note or "")[:240], now),
        )
        row = conn.execute("SELECT * FROM rap_versions WHERE id = ?", (version_id,)).fetchone()
        return version_detail(row)

    def create_rap(
        self,
        user_id: str,
        title: str,
        lyrics: str,
        coach_mode: str = "match",
        metadata: Optional[Dict[str, Any]] = None,
        tags: Any = None,
        notes: str = "",
        pinned: bool = False,
        archived: bool = False,
        last_score: float | None = None,
        last_snapshot: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        lyrics = str(lyrics or "")
        title = clean_title(title, lyrics)
        metadata_json = _json_dump(metadata or {})
        tags_json = _json_dump(normalize_tags(tags))
        rap_id = uuid.uuid4().hex
        now = utc_now()
        last_snapshot_json = _json_dump(last_snapshot or {})
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO raps (
                    id, user_id, title, lyrics, coach_mode, metadata_json, created_at, updated_at,
                    tags_json, notes, pinned, archived, last_score, last_snapshot_json, last_snapshot_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    rap_id, user_id, title, lyrics, coach_mode or "match", metadata_json, now, now,
                    tags_json, str(notes or "")[:2000], 1 if pinned else 0, 1 if archived else 0,
                    last_score, last_snapshot_json, now if last_snapshot else None,
                ),
            )
            self._insert_version(conn, user_id, rap_id, title, lyrics, coach_mode or "match", metadata or {}, "Initial save")
            row = conn.execute(
                """
                SELECT r.*, (SELECT COUNT(*) FROM rap_versions v WHERE v.rap_id = r.id) AS version_count
                FROM raps r WHERE r.id = ? AND r.user_id = ?
                """,
                (rap_id, user_id),
            ).fetchone()
        return rap_detail(row)

    def list_raps(
        self,
        user_id: str,
        query: str = "",
        limit: int = 100,
        include_archived: bool = False,
        archived_only: bool = False,
        tag: str = "",
        sort: str = "updated_desc",
    ) -> List[Dict[str, Any]]:
        query = str(query or "").strip()
        limit = max(1, min(300, int(limit or 100)))
        tag = normalize_tags([tag])[0] if normalize_tags([tag]) else ""
        where = ["r.user_id = ?", "r.deleted_at IS NULL"]
        params: List[Any] = [user_id]
        if archived_only:
            where.append("COALESCE(r.archived, 0) = 1")
        elif not include_archived:
            where.append("COALESCE(r.archived, 0) = 0")
        if query:
            like = f"%{query}%"
            where.append("(r.title LIKE ? OR r.lyrics LIKE ? OR COALESCE(r.notes, '') LIKE ? OR COALESCE(r.tags_json, '') LIKE ?)")
            params.extend([like, like, like, like])
        if tag:
            where.append("COALESCE(r.tags_json, '') LIKE ?")
            params.append(f"%{tag}%")
        order_map = {
            "title": "LOWER(r.title) ASC",
            "created_desc": "r.created_at DESC",
            "created_asc": "r.created_at ASC",
            "score_desc": "COALESCE(r.last_score, -1) DESC, r.updated_at DESC",
            "words_desc": "LENGTH(r.lyrics) DESC",
            "updated_asc": "r.updated_at ASC",
            "updated_desc": "r.updated_at DESC",
        }
        order = order_map.get(sort, order_map["updated_desc"])
        sql = f"""
            SELECT r.*, (SELECT COUNT(*) FROM rap_versions v WHERE v.rap_id = r.id) AS version_count
            FROM raps r
            WHERE {' AND '.join(where)}
            ORDER BY COALESCE(r.pinned, 0) DESC, {order}
            LIMIT ?
        """
        params.append(limit)
        with self.connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [rap_summary(row) for row in rows]

    def get_rap(self, user_id: str, rap_id: str) -> Optional[Dict[str, Any]]:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT r.*, (SELECT COUNT(*) FROM rap_versions v WHERE v.rap_id = r.id) AS version_count
                FROM raps r WHERE r.id = ? AND r.user_id = ? AND r.deleted_at IS NULL
                """,
                (rap_id, user_id),
            ).fetchone()
        return rap_detail(row) if row else None

    def update_rap(
        self,
        user_id: str,
        rap_id: str,
        title: str | None = None,
        lyrics: str | None = None,
        coach_mode: str | None = None,
        metadata: Optional[Dict[str, Any]] = None,
        tags: Any = None,
        notes: str | None = None,
        pinned: bool | None = None,
        archived: bool | None = None,
        last_score: float | None = None,
        last_snapshot: Optional[Dict[str, Any]] = None,
        create_version: bool = True,
        change_note: str = "",
    ) -> Optional[Dict[str, Any]]:
        current = self.get_rap(user_id, rap_id)
        if not current:
            return None
        next_lyrics = str(lyrics if lyrics is not None else current.get("lyrics", ""))
        next_title = clean_title(title if title is not None else current["title"], next_lyrics)
        next_mode = str(coach_mode or current.get("coach_mode") or "match")
        next_metadata = metadata if metadata is not None else current.get("metadata", {})
        next_tags = normalize_tags(tags if tags is not None else current.get("tags", []))
        next_notes = str(notes if notes is not None else current.get("notes", ""))[:2000]
        next_pinned = current.get("pinned", False) if pinned is None else bool(pinned)
        next_archived = current.get("archived", False) if archived is None else bool(archived)
        now = utc_now()
        snapshot_json = _json_dump(last_snapshot if last_snapshot is not None else current.get("last_snapshot", {}))
        snapshot_at = now if last_snapshot is not None else current.get("last_snapshot_at")
        if last_score is None:
            last_score = current.get("last_score")
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE raps
                SET title = ?, lyrics = ?, coach_mode = ?, metadata_json = ?, updated_at = ?,
                    tags_json = ?, notes = ?, pinned = ?, archived = ?, last_score = ?,
                    last_snapshot_json = ?, last_snapshot_at = ?
                WHERE id = ? AND user_id = ? AND deleted_at IS NULL
                """,
                (
                    next_title, next_lyrics, next_mode, _json_dump(next_metadata or {}), now,
                    _json_dump(next_tags), next_notes, 1 if next_pinned else 0, 1 if next_archived else 0,
                    last_score, snapshot_json, snapshot_at, rap_id, user_id,
                ),
            )
            if create_version:
                self._insert_version(conn, user_id, rap_id, next_title, next_lyrics, next_mode, next_metadata or {}, change_note or "Saved revision")
            row = conn.execute(
                """
                SELECT r.*, (SELECT COUNT(*) FROM rap_versions v WHERE v.rap_id = r.id) AS version_count
                FROM raps r WHERE r.id = ? AND r.user_id = ?
                """,
                (rap_id, user_id),
            ).fetchone()
        return rap_detail(row) if row else None

    def create_version(self, user_id: str, rap_id: str, change_note: str = "Manual checkpoint") -> Optional[Dict[str, Any]]:
        current = self.get_rap(user_id, rap_id)
        if not current:
            return None
        with self.connect() as conn:
            version = self._insert_version(
                conn, user_id, rap_id, current["title"], current.get("lyrics", ""),
                current.get("coach_mode", "match"), current.get("metadata", {}), change_note,
            )
        return version

    def list_versions(self, user_id: str, rap_id: str, limit: int = 80) -> List[Dict[str, Any]]:
        limit = max(1, min(200, int(limit or 80)))
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM rap_versions
                WHERE user_id = ? AND rap_id = ?
                ORDER BY version_number DESC
                LIMIT ?
                """,
                (user_id, rap_id, limit),
            ).fetchall()
        return [version_summary(row) for row in rows]

    def get_version(self, user_id: str, rap_id: str, version_id: str) -> Optional[Dict[str, Any]]:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM rap_versions WHERE user_id = ? AND rap_id = ? AND id = ?",
                (user_id, rap_id, version_id),
            ).fetchone()
        return version_detail(row) if row else None

    def restore_version(self, user_id: str, rap_id: str, version_id: str) -> Optional[Dict[str, Any]]:
        version = self.get_version(user_id, rap_id, version_id)
        if not version:
            return None
        return self.update_rap(
            user_id, rap_id,
            title=version.get("title"),
            lyrics=version.get("lyrics", ""),
            coach_mode=version.get("coach_mode", "match"),
            metadata={**(version.get("metadata") or {}), "restored_from_version": version.get("version_number")},
            create_version=True,
            change_note=f"Restored version {version.get('version_number')}",
        )

    def delete_rap(self, user_id: str, rap_id: str) -> bool:
        now = utc_now()
        with self.connect() as conn:
            cur = conn.execute(
                "UPDATE raps SET deleted_at = ?, updated_at = ? WHERE id = ? AND user_id = ? AND deleted_at IS NULL",
                (now, now, rap_id, user_id),
            )
        return cur.rowcount > 0

    def duplicate_rap(self, user_id: str, rap_id: str) -> Optional[Dict[str, Any]]:
        source = self.get_rap(user_id, rap_id)
        if not source:
            return None
        return self.create_rap(
            user_id,
            title=clean_title(f"{source.get('title') or 'Untitled rap'} copy", source.get("lyrics", "")),
            lyrics=source.get("lyrics", ""),
            coach_mode=source.get("coach_mode", "match"),
            metadata={**(source.get("metadata") or {}), "duplicated_from": rap_id},
            tags=source.get("tags", []),
            notes=source.get("notes", ""),
            pinned=False,
            archived=False,
            last_score=source.get("last_score"),
            last_snapshot=source.get("last_snapshot"),
        )

    def library_stats(self, user_id: str) -> Dict[str, Any]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT r.*, (SELECT COUNT(*) FROM rap_versions v WHERE v.rap_id = r.id) AS version_count
                FROM raps r WHERE r.user_id = ? AND r.deleted_at IS NULL
                ORDER BY r.updated_at DESC
                """,
                (user_id,),
            ).fetchall()
            version_count = conn.execute("SELECT COUNT(*) FROM rap_versions WHERE user_id = ?", (user_id,)).fetchone()[0]
        summaries = [rap_summary(row) for row in rows]
        total_words = sum(item["word_count"] for item in summaries)
        total_lines = sum(item["line_count"] for item in summaries)
        active = [item for item in summaries if not item["archived"]]
        tags: Dict[str, int] = {}
        for item in summaries:
            for tag in item.get("tags", []):
                tags[tag] = tags.get(tag, 0) + 1
        return {
            "rap_count": len(summaries),
            "active_count": len(active),
            "archived_count": len(summaries) - len(active),
            "pinned_count": sum(1 for item in summaries if item.get("pinned")),
            "version_count": int(version_count or 0),
            "total_words": total_words,
            "total_lines": total_lines,
            "avg_words": round(total_words / max(1, len(summaries)), 1),
            "top_tags": sorted([{"tag": k, "count": v} for k, v in tags.items()], key=lambda x: (-x["count"], x["tag"]))[:20],
            "latest": summaries[:5],
        }

    def export_library(self, user_id: str) -> Dict[str, Any]:
        raps = []
        for summary in self.list_raps(user_id, include_archived=True, limit=300, sort="updated_desc"):
            detail = self.get_rap(user_id, summary["id"])
            if detail:
                detail["versions"] = self.list_versions(user_id, summary["id"], limit=200)
                raps.append(detail)
        return {
            "exported_at": utc_now(),
            "format": "nmc_saved_raps_v2",
            "raps": raps,
        }

    def import_library(self, user_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        raps = payload.get("raps") if isinstance(payload, dict) else None
        if not isinstance(raps, list):
            raise ValueError("Import JSON must contain a raps list.")
        created = []
        skipped = 0
        for item in raps[:200]:
            if not isinstance(item, dict):
                skipped += 1
                continue
            lyrics = str(item.get("lyrics") or "")
            if not lyrics.strip():
                skipped += 1
                continue
            rap = self.create_rap(
                user_id,
                title=clean_title(str(item.get("title") or ""), lyrics),
                lyrics=lyrics,
                coach_mode=str(item.get("coach_mode") or "match"),
                metadata={**(item.get("metadata") if isinstance(item.get("metadata"), dict) else {}), "imported_at": utc_now()},
                tags=item.get("tags", []),
                notes=str(item.get("notes") or ""),
                pinned=False,
                archived=bool(item.get("archived") or False),
                last_score=item.get("last_score"),
                last_snapshot=item.get("last_snapshot") if isinstance(item.get("last_snapshot"), dict) else None,
            )
            created.append(rap_summary(rap))
        return {"created": created, "created_count": len(created), "skipped_count": skipped}

    def stats(self) -> Dict[str, Any]:
        with self.connect() as conn:
            user_count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
            rap_count = conn.execute("SELECT COUNT(*) FROM raps WHERE deleted_at IS NULL").fetchone()[0]
            version_count = conn.execute("SELECT COUNT(*) FROM rap_versions").fetchone()[0]
        return {"users": user_count, "raps": rap_count, "versions": version_count, "db_path": str(self.path)}
