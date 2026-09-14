"""
storage/database.py
قاعدة بيانات SQLite لتتبع المناقصات ومنع التكرار
"""

import sqlite3
import logging
import os
import hashlib
from datetime import datetime
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)

DEFAULT_DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    "storage",
    "tenders.db",
)


class TenderDatabase:
    """إدارة قاعدة بيانات المناقصات"""

    def __init__(self, db_path: str = DEFAULT_DB_PATH):
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._init_db()

    def _connect(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        """إنشاء الجداول إذا لم تكن موجودة"""
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
                    notified INTEGER DEFAULT 0
                );

                CREATE INDEX IF NOT EXISTS idx_fingerprint ON tenders(fingerprint);
                CREATE INDEX IF NOT EXISTS idx_wilaya ON tenders(wilaya);
                CREATE INDEX IF NOT EXISTS idx_notified ON tenders(notified);
            """)
            conn.commit()
        logger.info(f"✅ قاعدة البيانات جاهزة: {self.db_path}")

    @staticmethod
    def _fingerprint(tender: Dict) -> str:
        """بصمة فريدة لكل مناقصة لمنع التكرار"""
        raw = "|".join([
            str(tender.get("title", "")).strip().lower(),
            str(tender.get("organisation", "")).strip().lower(),
            str(tender.get("link", "")).strip().lower(),
        ])
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def add_tender(self, tender: Dict) -> bool:
        """إضافة مناقصة. Returns True إذا كانت جديدة، False إذا مكررة."""
        fp = self._fingerprint(tender)
        now = datetime.now().isoformat()

        families = tender.get("matched_families", [])
        families_str = ",".join([f["id"] for f in families]) if families else ""

        with self._connect() as conn:
            cur = conn.execute(
                "SELECT id FROM tenders WHERE fingerprint = ?", (fp,)
            )
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
                    matched_families, first_seen, last_seen, notified
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
                """,
                (
                    fp,
                    tender.get("title", ""),
                    tender.get("organisation", ""),
                    tender.get("wilaya", ""),
                    tender.get("product", ""),
                    tender.get("deadline", ""),
                    tender.get("status", ""),
                    tender.get("link", ""),
                    tender.get("relevance_score", 0),
                    families_str,
                    now,
                    now,
                ),
            )
            conn.commit()
            return True

    def mark_notified(self, tender: Dict):
        """تحديد المناقصة كـ 'تم إشعارها'"""
        fp = self._fingerprint(tender)
        with self._connect() as conn:
            conn.execute(
                "UPDATE tenders SET notified = 1 WHERE fingerprint = ?", (fp,)
            )
            conn.commit()

    def is_notified(self, tender: Dict) -> bool:
        """هل تم إشعار المستخدم بهذه المناقصة؟"""
        fp = self._fingerprint(tender)
        with self._connect() as conn:
            cur = conn.execute(
                "SELECT notified FROM tenders WHERE fingerprint = ?", (fp,)
            )
            row = cur.fetchone()
            return bool(row and row["notified"])

    def get_new_tenders(self, tenders: List[Dict]) -> List[Dict]:
        """إرجاع المناقصات الجديدة فقط"""
        return [t for t in tenders if not self.is_notified(t)]

    def stats(self) -> Dict:
        """إحصائيات سريعة"""
        with self._connect() as conn:
            total = conn.execute("SELECT COUNT(*) FROM tenders").fetchone()[0]
            notified = conn.execute(
                "SELECT COUNT(*) FROM tenders WHERE notified = 1"
            ).fetchone()[0]

            today = datetime.now().strftime("%Y-%m-%d")
            today_count = conn.execute(
                "SELECT COUNT(*) FROM tenders WHERE first_seen LIKE ?",
                (f"{today}%",),
            ).fetchone()[0]

            by_wilaya = conn.execute(
                """
                SELECT wilaya, COUNT(*) as count FROM tenders
                WHERE wilaya IS NOT NULL AND wilaya != ''
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