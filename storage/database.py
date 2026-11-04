"""
storage/database.py
قاعدة بيانات SQLite لتتبع المناقصات ومنع التكرار
"""

import hashlib
import logging
import os
import sqlite3
from datetime import datetime

from storage.tender_quality import is_valid_tender

logger = logging.getLogger(__name__)

DEFAULT_DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    "storage",
    "tenders.db",
)

#: Ø§Ù„Ø­Ø¯ Ø§Ù„Ø£Ù‚ØµÙ‰ Ù„Ù…Ø­Ø§ÙˆÙ„Ø§Øª ØªØ³Ù„ÙŠÙ… Ø§Ù„Ø¥Ø´Ø¹Ø§Ø± Ù‚Ø¨Ù„ Ø­Ø¬Ø¨ Ø§Ù„ØµÙÙ‚Ø© Ù†Ù‡Ø§Ø¦ÙŠØ§Ù‹.
MAX_DELIVERY_ATTEMPTS = 3

#: Ø¹Ø¨Ø§Ø±Ø§Øª ``ALTER TABLE`` Ù„Ù„Ù‚ÙˆØ§Ø¹Ø¯ Ø§Ù„Ù…Ù†Ø´Ø£Ø© Ù‚Ø¨Ù„ Ø¨Ù†ÙˆØ¯ Ø§Ù„Ù…Ø­Ø§ÙˆÙ„Ø§Øª ÙˆØ§Ù„Ø­Ø¬Ø¨.
MIGRATION_COLUMNS = (
    "ALTER TABLE tenders ADD COLUMN retry_count INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE tenders ADD COLUMN blocked INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE tenders ADD COLUMN last_error TEXT",
    "ALTER TABLE tenders ADD COLUMN last_attempt_at TEXT",
    "ALTER TABLE tenders ADD COLUMN reference TEXT",
    "ALTER TABLE tenders ADD COLUMN source TEXT",
    "ALTER TABLE tenders ADD COLUMN is_noise INTEGER NOT NULL DEFAULT 0",
)

#: Ø£Ø³Ù…Ø§Ø¡ Ø§Ù„Ø£Ø¹Ù…Ø¯Ø© Ø§Ù„ØªÙŠ ÙŠÙ†Ø´Ø¦Ù‡Ø§ Ø§Ù„ØªØ±Ø­ÙŠÙ„ØŒ Ø¨Ø§Ù„ØªØ±ØªÙŠØ¨ Ù†ÙØ³Ù‡.
MIGRATION_COLUMN_NAMES = tuple(
    statement.split("ADD COLUMN", 1)[1].split()[0] for statement in MIGRATION_COLUMNS
)


class TenderDatabase:
    """Ø¥Ø¯Ø§Ø±Ø© Ù‚Ø§Ø¹Ø¯Ø© Ø¨ÙŠØ§Ù†Ø§Øª Ø§Ù„Ù…Ù†Ø§Ù‚ØµØ§Øª"""

    def __init__(self, db_path: str = DEFAULT_DB_PATH):
        self.db_path = db_path
        db_dir = os.path.dirname(db_path)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)
        self._init_db()

    def _connect(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        """Ø¥Ù†Ø´Ø§Ø¡ Ø§Ù„Ø¬Ø¯Ø§ÙˆÙ„ Ø¥Ø°Ø§ Ù„Ù… ØªÙƒÙ† Ù…ÙˆØ¬ÙˆØ¯Ø©"""
        with self._connect() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS tenders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    fingerprint TEXT UNIQUE NOT NULL,
                    title TEXT NOT NULL,
                    organisation TEXT,
                    wilaya TEXT,
                    product TEXT,
                    deadline TEXT,
                    status TEXT,
                    link TEXT,
                    relevance_score INTEGER DEFAULT 0,
                    matched_families TEXT,
                    first_seen TEXT NOT NULL,
                    last_seen TEXT NOT NULL,
                    notified INTEGER DEFAULT 0,
                    retry_count INTEGER NOT NULL DEFAULT 0,
                    blocked INTEGER NOT NULL DEFAULT 0,
                    last_error TEXT,
                    last_attempt_at TEXT,
                    reference TEXT,
                    source TEXT,
                    is_noise INTEGER NOT NULL DEFAULT 0
                );

                CREATE INDEX IF NOT EXISTS idx_fingerprint ON tenders(fingerprint);
                CREATE INDEX IF NOT EXISTS idx_wilaya ON tenders(wilaya);
                CREATE INDEX IF NOT EXISTS idx_notified ON tenders(notified);
            """)
            conn.commit()
            self._migrate_schema(conn)
        logger.info(f"âœ… Ù‚Ø§Ø¹Ø¯Ø© Ø§Ù„Ø¨ÙŠØ§Ù†Ø§Øª Ø¬Ø§Ù‡Ø²Ø©: {self.db_path}")

    @staticmethod
    def _table_columns(conn) -> set[str]:
        """Ø£Ø³Ù…Ø§Ø¡ Ø£Ø¹Ù…Ø¯Ø© Ø¬Ø¯ÙˆÙ„ Ø§Ù„Ù…Ù†Ø§Ù‚ØµØ§Øª ÙƒÙ…Ø§ Ù‡ÙŠ Ø§Ù„Ø¢Ù† ÙÙŠ Ø§Ù„Ù‚Ø§Ø¹Ø¯Ø©."""
        return {row[1] for row in conn.execute("PRAGMA table_info(tenders)")}

    def _migrate_schema(self, conn):
        """ØªØ±Ø­ÙŠÙ„ Ù‚ÙˆØ§Ø¹Ø¯ Ù‚Ø¯ÙŠÙ…Ø© Ø¥Ù„Ù‰ Ø§Ù„Ù…Ø®Ø·Ø· Ø§Ù„Ø­Ø§Ù„ÙŠ (idempotent).

        ÙŠØ¶ÙŠÙ Ø£Ø¹Ù…Ø¯Ø© Ø§Ù„ØªØ³Ù„ÙŠÙ… ÙˆØ¬ÙˆØ¯Ø© Ø§Ù„Ø¨ÙŠØ§Ù†Ø§Øª
        Ø¨Ø£Ù…Ø§Ù† Ø¹Ù„Ù‰ Ø£ÙŠ Ù‚Ø§Ø¹Ø¯Ø© Ø£ÙÙ†Ø´Ø¦Øª Ù‚Ø¨Ù„ Ù‡Ø°Ø§ Ø§Ù„Ø¥ØµØ¯Ø§Ø±ØŒ ÙˆÙ„Ø§ ÙŠÙØ¹Ù„ Ø´ÙŠØ¦Ø§Ù‹ Ø¥Ù† ÙƒØ§Ù†Øª
        Ø§Ù„Ø£Ø¹Ù…Ø¯Ø© Ù…ÙˆØ¬ÙˆØ¯Ø©. SQLite Ù„Ø§ ÙŠØ¯Ø¹Ù… ``ADD COLUMN IF NOT EXISTS``ØŒ Ù„Ø°Ø§ ÙŠÙÙ‚Ø±Ø£
        Ø§Ù„Ù…Ø®Ø·Ø· Ø£ÙˆÙ„Ø§Ù‹ ÙˆÙŠÙÙ†ÙÙŽÙ‘Ø° ``ALTER TABLE`` ÙÙ‚Ø· Ù„Ù„Ø£Ø¹Ù…Ø¯Ø© Ø§Ù„Ù†Ø§Ù‚ØµØ©.

        Args:
            conn: Ø§ØªØµØ§Ù„ Ù…ÙØªÙˆØ­ Ø¹Ù„Ù‰ Ù‚Ø§Ø¹Ø¯Ø© Ø§Ù„Ø¨ÙŠØ§Ù†Ø§Øª.
        """
        columns = self._table_columns(conn)
        if set(MIGRATION_COLUMN_NAMES).issubset(columns):
            conn.execute("CREATE INDEX IF NOT EXISTS idx_blocked ON tenders(blocked)")
            return

        first_time = "retry_count" not in columns

        for name, statement in zip(MIGRATION_COLUMN_NAMES, MIGRATION_COLUMNS, strict=True):
            if name in columns:
                continue
            try:
                conn.execute(statement)
            except sqlite3.OperationalError as exc:
                # Ø¹Ù…Ù„ÙŠØªØ§Ù† Ù‚Ø¯ ØªØ¨Ø¯Ø¢Ù† Ù…Ø¹Ø§Ù‹: Ø§Ù„Ø«Ø§Ù†ÙŠØ© ØªØ±Ù‰ Ø§Ù„Ø¹Ù…ÙˆØ¯ Ù†Ø§Ù‚ØµØ§Ù‹ ÙØªÙ†Ø§Ù„ duplicate column
                if "duplicate column name" not in str(exc).lower():
                    raise
                logger.debug(f"Ø§Ù„Ø¹Ù…ÙˆØ¯ {name} Ø£ÙØ¶ÙŠÙ Ø¨Ø¹Ù…Ù„ÙŠØ© Ù…ÙˆØ§Ø²ÙŠØ©: {exc}")
            columns = self._table_columns(conn)

        conn.execute("CREATE INDEX IF NOT EXISTS idx_blocked ON tenders(blocked)")

        if first_time:
            self._block_stale_unnotified(conn)

        conn.commit()

    def _block_stale_unnotified(self, conn):
        """Ø­Ø¬Ø¨ Ø§Ù„ØµÙÙ‚Ø§Øª Ø§Ù„Ù‚Ø¯ÙŠÙ…Ø© ØºÙŠØ± Ø§Ù„Ù…ÙØ¨Ù„ÙŽÙ‘Øº Ø¹Ù†Ø¯ Ø£ÙˆÙ„ ØªØ±Ù‚ÙŠØ© Ù„Ù„Ù‚Ø§Ø¹Ø¯Ø©.

        ÙŠÙ…Ù†Ø¹ Â«Ù…ÙˆØ¬Ø© Ø§Ù„Ø¥Ø´Ø¹Ø§Ø±Ø§ØªÂ» Ø§Ù„Ù†Ø§ØªØ¬Ø© Ø¹Ù† Ø¥Ø¹Ø§Ø¯Ø© Ø¥Ø¯Ø±Ø§Ø¬ Ø§Ù„ØµÙÙ‚Ø§Øª Ø§Ù„ØªÙŠ Ù„Ù… ØªÙØ¨Ù„ÙŽÙ‘Øº
        Ù‚Ø·. Ù‚Ø±Ø§Ø± Ø§Ù„Ø­Ø¬Ø¨ ÙŠØ¯ÙˆÙŠ Ø¹Ø¨Ø± ``python -m storage.tools unblock --all``.

        Args:
            conn: Ø§ØªØµØ§Ù„ Ù…ÙØªÙˆØ­ Ø¹Ù„Ù‰ Ù‚Ø§Ø¹Ø¯Ø© Ø§Ù„Ø¨ÙŠØ§Ù†Ø§Øª.
        """
        cursor = conn.execute("UPDATE tenders SET blocked = 1 WHERE notified = 0")
        blocked_count = cursor.rowcount or 0
        if blocked_count:
            logger.warning(
                f"🔒 تم حجب {blocked_count} صفقة قديمة لتفادي موجة إشعارات: {self.db_path}"
            )
            logger.warning("🔓 لفك الحجب: python -m storage.tools unblock --all")

    @staticmethod
    def _fingerprint(tender: dict) -> str:
        """Ø¨ØµÙ…Ø© ÙØ±ÙŠØ¯Ø© Ù„ÙƒÙ„ Ù…Ù†Ø§Ù‚ØµØ© Ù„Ù…Ù†Ø¹ Ø§Ù„ØªÙƒØ±Ø§Ø±"""
        raw = "|".join(
            [
                str(tender.get("title", "")).strip().lower(),
                str(tender.get("organisation", "")).strip().lower(),
                str(tender.get("link", "")).strip().lower(),
            ]
        )
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    @staticmethod
    def _families_to_db_value(families: list[dict], fp: str) -> str:
        """ØªØ­ÙˆÙŠÙ„ ``matched_families`` Ø¥Ù„Ù‰ Ù†Øµ Ù…ÙØµÙˆÙ„ Ø¨ÙÙˆØ§ØµÙ„ Ù…Ø¹ ØªØ­Ù…Ù‘Ù„ ØºÙŠØ§Ø¨ ``id``.

        Args:
            families: Ù‚Ø§Ø¦Ù…Ø© Ø¹Ø§Ø¦Ù„Ø§Øª ØªØµÙ†ÙŠÙ ÙƒÙ…Ø§ ÙˆØ±Ø¯Øª Ù…Ù† ÙÙ„ØªØ±Ø© Ø§Ù„ØªØ³ÙˆÙŠÙ‚.
            fp: Ø¨ØµÙ…Ø© Ø§Ù„Ù…Ù†Ø§Ù‚ØµØ©ØŒ Ù„ØªÙˆØ¶ÙŠØ­ Ø±Ø³Ø§Ù„Ø© Ø§Ù„ØªØ­Ø°ÙŠØ± Ø¥Ù† Ù„Ø²Ù….

        Returns:
            Ù…Ø¹Ø±Ù‘ÙØ§Øª Ø§Ù„Ø¹Ø§Ø¦Ù„Ø§Øª Ù…ÙØµÙˆÙ„Ø© Ø¨ÙÙˆØ§ØµÙ„ØŒ Ø£Ùˆ Ù†Øµ ÙØ§Ø±Øº.
        """
        ids = []
        for family in families:
            family_id = str(family.get("id", "")).strip()
            if not family_id:
                logger.warning("عائلة تصنيف بلا معرّف id تم تجاوزها (بصمة %s): %s", fp[:12], family)
                continue
            ids.append(family_id)
        return ",".join(ids)

    def add_tender(self, tender: dict) -> bool:
        """Store a tender only when it meets the minimum quality requirements."""
        if not is_valid_tender(tender):
            return False
        fp = self._fingerprint(tender)
        now = datetime.now().isoformat()

        families = tender.get("matched_families", []) or []
        families_str = self._families_to_db_value(families, fp)

        with self._connect() as conn:
            cur = conn.execute("SELECT id FROM tenders WHERE fingerprint = ?", (fp,))
            existing = cur.fetchone()

            if existing:
                conn.execute(
                    "UPDATE tenders SET last_seen = ? WHERE fingerprint = ?",
                    (now, fp),
                )
                conn.commit()
                return False

            conn.execute(
                """
                INSERT INTO tenders (
                    fingerprint, title, organisation, wilaya, product,
                    deadline, status, link, relevance_score,
                    matched_families, first_seen, last_seen, notified,
                    reference, source
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)
                """,
                (
                    fp,
                    tender.get("title", ""),
                    tender.get("organisation", ""),
                    tender.get("wilaya") or None,
                    tender.get("product", ""),
                    tender.get("deadline") or None,
                    tender.get("status", ""),
                    tender.get("link", ""),
                    tender.get("relevance_score", 0),
                    families_str,
                    now,
                    now,
                    tender.get("reference") or tender.get("tender_number"),
                    tender.get("source"),
                ),
            )
            conn.commit()
            return True

    def mark_invalid_tenders_as_noise(self) -> int:
        """Soft-delete rows that fail the shared tender-quality check."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, deadline, reference, organisation, relevance_score, source, link"
                " FROM tenders WHERE is_noise = 0"
            ).fetchall()
            invalid_ids = [row["id"] for row in rows if not is_valid_tender(dict(row))]
            if not invalid_ids:
                return 0
            conn.executemany(
                "UPDATE tenders SET is_noise = 1 WHERE id = ?",
                ((row_id,) for row_id in invalid_ids),
            )
            return len(invalid_ids)

    def count_invalid_tenders(self) -> int:
        """Count active rows failing minimum tender-quality requirements."""
        return len(self._invalid_tender_ids())

    def _invalid_tender_ids(self) -> list[int]:
        """Return active row IDs that fail the shared quality check."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, deadline, reference, organisation, relevance_score, source, link"
                " FROM tenders WHERE is_noise = 0"
            ).fetchall()
        return [row["id"] for row in rows if not is_valid_tender(dict(row))]

    def mark_notified(self, tender: dict):
        """ØªØ­Ø¯ÙŠØ¯ Ø§Ù„Ù…Ù†Ø§Ù‚ØµØ© ÙƒÙ€ 'ØªÙ… Ø¥Ø´Ø¹Ø§Ø±Ù‡Ø§'"""
        fp = self._fingerprint(tender)
        with self._connect() as conn:
            conn.execute("UPDATE tenders SET notified = 1 WHERE fingerprint = ?", (fp,))
            conn.commit()

    def is_notified(self, tender: dict) -> bool:
        """Ù‡Ù„ ØªÙ… Ø¥Ø´Ø¹Ø§Ø± Ø§Ù„Ù…Ø³ØªØ®Ø¯Ù… Ø¨Ù‡Ø°Ù‡ Ø§Ù„Ù…Ù†Ø§Ù‚ØµØ©ØŸ"""
        fp = self._fingerprint(tender)
        with self._connect() as conn:
            cur = conn.execute("SELECT notified FROM tenders WHERE fingerprint = ?", (fp,))
            row = cur.fetchone()
            return bool(row and row["notified"])

    def register_failed_attempt(self, tender: dict, error: str = "") -> int:
        """ØªØ³Ø¬ÙŠÙ„ Ù…Ø­Ø§ÙˆÙ„Ø© ØªØ³Ù„ÙŠÙ… ÙØ§Ø´Ù„Ø©ØŒ ÙˆØ­Ø¬Ø¨ Ø§Ù„ØµÙÙ‚Ø© Ø¹Ù†Ø¯ ØªØ¬Ø§ÙˆØ² Ø§Ù„Ø­Ø¯Ù‘.

        Args:
            tender: Ø§Ù„Ù…Ù†Ø§Ù‚ØµØ© Ø§Ù„ØªÙŠ ÙØ´Ù„ Ø¥Ø±Ø³Ø§Ù„Ù‡Ø§.
            error: ÙˆØµÙ Ù…Ø®ØªØµØ± Ù„Ù„Ø®Ø·Ø£ØŒ ÙŠÙØ®Ø²ÙŽÙ‘Ù† Ù„Ø£ØºØ±Ø§Ø¶ Ø§Ù„ØªØ´Ø®ÙŠØµ.

        Returns:
            Ù‚ÙŠÙ…Ø© ``retry_count`` Ø¨Ø¹Ø¯ Ø§Ù„Ø²ÙŠØ§Ø¯Ø©ØŒ Ø£Ùˆ 0 Ø¥Ø°Ø§ Ù„Ù… ÙŠÙƒÙ† Ø§Ù„ØµÙ Ù…ÙˆØ¬ÙˆØ¯Ø§Ù‹.
        """
        fp = self._fingerprint(tender)
        now = datetime.now().isoformat()
        with self._connect() as conn:
            cursor = conn.execute(
                """
                UPDATE tenders
                SET retry_count = retry_count + 1, last_error = ?, last_attempt_at = ?
                WHERE fingerprint = ?
                """,
                (str(error)[:500], now, fp),
            )
            if not cursor.rowcount:
                logger.warning("Ù…Ø­Ø§ÙˆÙ„Ø© ØªØ³Ù„ÙŠÙ… Ù„ØµÙÙ‚Ø© ØºÙŠØ± Ù…Ø®Ø²ÙŽÙ‘Ù†Ø© (Ø¨ØµÙ…Ø© %s) â€” ØªÙØªØ¬Ø§Ù‡Ù„", fp[:12])
                return 0

            row = conn.execute(
                "SELECT retry_count FROM tenders WHERE fingerprint = ?", (fp,)
            ).fetchone()
            attempts = int(row["retry_count"]) if row else 0
            if attempts >= MAX_DELIVERY_ATTEMPTS:
                conn.execute("UPDATE tenders SET blocked = 1 WHERE fingerprint = ?", (fp,))
                logger.warning(
                    "ðŸ”’ Ø­ÙØ¬Ø¨Øª Ø§Ù„ØµÙÙ‚Ø© Ø¨Ø¹Ø¯ %d Ù…Ø­Ø§ÙˆÙ„Ø§Øª ÙØ§Ø´Ù„Ø© (Ø¨ØµÙ…Ø© %s): %s",
                    attempts,
                    fp[:12],
                    str(error)[:120],
                )
            conn.commit()
            return attempts

    def unblock_tender(self, fingerprint: str) -> bool:
        """ÙÙƒ Ø­Ø¬Ø¨ ØµÙÙ‚Ø© Ø¨Ø¹ÙŠÙ†Ù‡Ø§ Ø¹Ø¨Ø± Ø¨ØµÙ…ØªÙ‡Ø§.

        Args:
            fingerprint: Ø§Ù„Ø¨ØµÙ…Ø© Ø§Ù„Ù†ØµÙŠØ© Ù„Ù„ØµÙÙ‚Ø© (ÙˆÙ„ÙŠØ³ Ù‚Ø§Ù…ÙˆØ³ Ù…Ù†Ø§Ù‚ØµØ©).

        Returns:
            True Ø¥Ø°Ø§ ÙˆÙØ¬Ø¯Øª Ø§Ù„ØµÙÙ‚Ø© ÙˆÙÙÙƒ Ø­Ø¬Ø¨Ù‡Ø§.
        """
        with self._connect() as conn:
            cursor = conn.execute(
                "UPDATE tenders SET blocked = 0, retry_count = 0 WHERE fingerprint = ?",
                (fingerprint,),
            )
            conn.commit()
            return bool(cursor.rowcount)

    def unblock_all(self) -> int:
        """ÙÙƒ Ø­Ø¬Ø¨ ÙƒÙ„ Ø§Ù„ØµÙÙ‚Ø§Øª Ø§Ù„Ù…Ø­Ø¬ÙˆØ¨Ø©.

        Returns:
            Ø¹Ø¯Ø¯ Ø§Ù„ØµÙÙ‚Ø§Øª Ø§Ù„ØªÙŠ ÙÙÙƒ Ø­Ø¬Ø¨Ù‡Ø§.
        """
        with self._connect() as conn:
            cursor = conn.execute(
                "UPDATE tenders SET blocked = 0, retry_count = 0 WHERE blocked = 1"
            )
            conn.commit()
            unblocked = cursor.rowcount or 0
        if unblocked:
            logger.info("ðŸ”“ ÙÙÙƒ Ø­Ø¬Ø¨ %d ØµÙÙ‚Ø©", unblocked)
        return unblocked

    def blocked_tenders(self, limit: int = 50) -> list[dict]:
        """Ø¹Ø±Ø¶ Ø§Ù„ØµÙÙ‚Ø§Øª Ø§Ù„Ù…Ø­Ø¬ÙˆØ¨Ø© Ù…Ø¹ Ø³Ø¨Ø¨ Ø¢Ø®Ø± ÙØ´Ù„.

        Args:
            limit: Ø£Ù‚ØµÙ‰ Ø¹Ø¯Ø¯ ØµÙÙˆÙ ØªÙØ¹Ø§Ø¯.

        Returns:
            Ù‚Ø§Ø¦Ù…Ø© ØµÙÙˆÙ Ù…Ø®ØªØµØ±Ø© Ø¨Ø§Ù„Ù…Ø¹Ø±Ù‘Ù ÙˆØ§Ù„Ø¨ØµÙ…Ø© ÙˆØ§Ù„Ø¹Ù†ÙˆØ§Ù† ÙˆØ¹Ø¯Ø¯ Ø§Ù„Ù…Ø­Ø§ÙˆÙ„Ø§Øª.
        """
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT fingerprint, title, retry_count, last_error, last_attempt_at
                FROM tenders WHERE blocked = 1 AND is_noise = 0
                ORDER BY last_attempt_at DESC LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_new_tenders(self, tenders: list[dict]) -> list[dict]:
        """Ø¥Ø±Ø¬Ø§Ø¹ Ø§Ù„Ù…Ù†Ø§Ù‚ØµØ§Øª Ø§Ù„Ø¬Ø¯ÙŠØ¯Ø© ÙÙ‚Ø·"""
        return [t for t in tenders if not self.is_notified(t)]

    def stats(self) -> dict:
        """Ø¥Ø­ØµØ§Ø¦ÙŠØ§Øª Ø³Ø±ÙŠØ¹Ø©"""
        with self._connect() as conn:
            total = conn.execute(
                "SELECT COUNT(*) FROM tenders WHERE is_noise = 0"
            ).fetchone()[0]
            notified = conn.execute(
                "SELECT COUNT(*) FROM tenders WHERE notified = 1 AND is_noise = 0"
            ).fetchone()[0]

            today = datetime.now().strftime("%Y-%m-%d")
            today_count = conn.execute(
                "SELECT COUNT(*) FROM tenders WHERE first_seen LIKE ? AND is_noise = 0",
                (f"{today}%",),
            ).fetchone()[0]

            by_wilaya = conn.execute(
                """
                SELECT wilaya, COUNT(*) as count FROM tenders
                WHERE wilaya IS NOT NULL AND wilaya != '' AND is_noise = 0
                GROUP BY wilaya ORDER BY count DESC LIMIT 10
                """
            ).fetchall()

            return {
                "total": total,
                "notified": notified,
                "today": today_count,
                "new_unnotified": total - notified,
                "by_wilaya": [dict(r) for r in by_wilaya],
            }
