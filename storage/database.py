"""
storage/database.py
قاعدة بيانات SQLite لتتبع المناقصات ومنع التكرار
"""

import hashlib
import logging
import os
import sqlite3
from datetime import datetime

logger = logging.getLogger(__name__)

DEFAULT_DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    "storage",
    "tenders.db",
)

#: الحد الأقصى لمحاولات تسليم الإشعار قبل حجب الصفقة نهائياً.
MAX_DELIVERY_ATTEMPTS = 3

#: عبارات ``ALTER TABLE`` للقواعد المنشأة قبل بنود المحاولات والحجب.
MIGRATION_COLUMNS = (
    "ALTER TABLE tenders ADD COLUMN retry_count INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE tenders ADD COLUMN blocked INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE tenders ADD COLUMN last_error TEXT",
    "ALTER TABLE tenders ADD COLUMN last_attempt_at TEXT",
)

#: أسماء الأعمدة التي ينشئها الترحيل، بالترتيب نفسه.
MIGRATION_COLUMN_NAMES = tuple(
    statement.split("ADD COLUMN", 1)[1].split()[0] for statement in MIGRATION_COLUMNS
)


class TenderDatabase:
    """إدارة قاعدة بيانات المناقصات"""

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
                    notified INTEGER DEFAULT 0,
                    retry_count INTEGER NOT NULL DEFAULT 0,
                    blocked INTEGER NOT NULL DEFAULT 0,
                    last_error TEXT,
                    last_attempt_at TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_fingerprint ON tenders(fingerprint);
                CREATE INDEX IF NOT EXISTS idx_wilaya ON tenders(wilaya);
                CREATE INDEX IF NOT EXISTS idx_notified ON tenders(notified);
            """)
            conn.commit()
            self._migrate_schema(conn)
        logger.info(f"✅ قاعدة البيانات جاهزة: {self.db_path}")

    @staticmethod
    def _table_columns(conn) -> set[str]:
        """أسماء أعمدة جدول المناقصات كما هي الآن في القاعدة."""
        return {row[1] for row in conn.execute("PRAGMA table_info(tenders)")}

    def _migrate_schema(self, conn):
        """ترحيل قواعد قديمة إلى المخطط الحالي (idempotent).

        يضيف ``retry_count`` و``blocked`` و``last_error`` و``last_attempt_at``
        بأمان على أي قاعدة أُنشئت قبل هذا الإصدار، ولا يفعل شيئاً إن كانت
        الأعمدة موجودة. SQLite لا يدعم ``ADD COLUMN IF NOT EXISTS``، لذا يُقرأ
        المخطط أولاً ويُنفَّذ ``ALTER TABLE`` فقط للأعمدة الناقصة.

        Args:
            conn: اتصال مفتوح على قاعدة البيانات.
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
                # عمليتان قد تبدآن معاً: الثانية ترى العمود ناقصاً فتنال duplicate column
                if "duplicate column name" not in str(exc).lower():
                    raise
                logger.debug(f"العمود {name} أُضيف بعملية موازية: {exc}")
            columns = self._table_columns(conn)

        conn.execute("CREATE INDEX IF NOT EXISTS idx_blocked ON tenders(blocked)")

        if first_time:
            self._block_stale_unnotified(conn)

        conn.commit()

    def _block_stale_unnotified(self, conn):
        """حجب الصفقات القديمة غير المُبلَّغ عند أول ترقية للقاعدة.

        يمنع «موجة الإشعارات» الناتجة عن إعادة إدراج الصفقات التي لم تُبلَّغ
        قط. قرار الحجب يدوي عبر ``python -m storage.tools unblock --all``.

        Args:
            conn: اتصال مفتوح على قاعدة البيانات.
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
        """بصمة فريدة لكل مناقصة لمنع التكرار"""
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
        """تحويل ``matched_families`` إلى نص مفصول بفواصل مع تحمّل غياب ``id``.

        Args:
            families: قائمة عائلات تصنيف كما وردت من فلترة التسويق.
            fp: بصمة المناقصة، لتوضيح رسالة التحذير إن لزم.

        Returns:
            معرّفات العائلات مفصولة بفواصل، أو نص فارغ.
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
        """إضافة مناقصة. Returns True إذا كانت جديدة، False إذا مكررة."""
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

    def mark_notified(self, tender: dict):
        """تحديد المناقصة كـ 'تم إشعارها'"""
        fp = self._fingerprint(tender)
        with self._connect() as conn:
            conn.execute("UPDATE tenders SET notified = 1 WHERE fingerprint = ?", (fp,))
            conn.commit()

    def is_notified(self, tender: dict) -> bool:
        """هل تم إشعار المستخدم بهذه المناقصة؟"""
        fp = self._fingerprint(tender)
        with self._connect() as conn:
            cur = conn.execute("SELECT notified FROM tenders WHERE fingerprint = ?", (fp,))
            row = cur.fetchone()
            return bool(row and row["notified"])

    def register_failed_attempt(self, tender: dict, error: str = "") -> int:
        """تسجيل محاولة تسليم فاشلة، وحجب الصفقة عند تجاوز الحدّ.

        Args:
            tender: المناقصة التي فشل إرسالها.
            error: وصف مختصر للخطأ، يُخزَّن لأغراض التشخيص.

        Returns:
            قيمة ``retry_count`` بعد الزيادة، أو 0 إذا لم يكن الصف موجوداً.
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
                logger.warning("محاولة تسليم لصفقة غير مخزَّنة (بصمة %s) — تُتجاهل", fp[:12])
                return 0

            row = conn.execute(
                "SELECT retry_count FROM tenders WHERE fingerprint = ?", (fp,)
            ).fetchone()
            attempts = int(row["retry_count"]) if row else 0
            if attempts >= MAX_DELIVERY_ATTEMPTS:
                conn.execute("UPDATE tenders SET blocked = 1 WHERE fingerprint = ?", (fp,))
                logger.warning(
                    "🔒 حُجبت الصفقة بعد %d محاولات فاشلة (بصمة %s): %s",
                    attempts,
                    fp[:12],
                    str(error)[:120],
                )
            conn.commit()
            return attempts

    def unblock_tender(self, fingerprint: str) -> bool:
        """فك حجب صفقة بعينها عبر بصمتها.

        Args:
            fingerprint: البصمة النصية للصفقة (وليس قاموس مناقصة).

        Returns:
            True إذا وُجدت الصفقة وفُك حجبها.
        """
        with self._connect() as conn:
            cursor = conn.execute(
                "UPDATE tenders SET blocked = 0, retry_count = 0 WHERE fingerprint = ?",
                (fingerprint,),
            )
            conn.commit()
            return bool(cursor.rowcount)

    def unblock_all(self) -> int:
        """فك حجب كل الصفقات المحجوبة.

        Returns:
            عدد الصفقات التي فُك حجبها.
        """
        with self._connect() as conn:
            cursor = conn.execute(
                "UPDATE tenders SET blocked = 0, retry_count = 0 WHERE blocked = 1"
            )
            conn.commit()
            unblocked = cursor.rowcount or 0
        if unblocked:
            logger.info("🔓 فُك حجب %d صفقة", unblocked)
        return unblocked

    def blocked_tenders(self, limit: int = 50) -> list[dict]:
        """عرض الصفقات المحجوبة مع سبب آخر فشل.

        Args:
            limit: أقصى عدد صفوف تُعاد.

        Returns:
            قائمة صفوف مختصرة بالمعرّف والبصمة والعنوان وعدد المحاولات.
        """
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT fingerprint, title, retry_count, last_error, last_attempt_at
                FROM tenders WHERE blocked = 1 ORDER BY last_attempt_at DESC LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_new_tenders(self, tenders: list[dict]) -> list[dict]:
        """إرجاع المناقصات الجديدة فقط"""
        return [t for t in tenders if not self.is_notified(t)]

    def stats(self) -> dict:
        """إحصائيات سريعة"""
        with self._connect() as conn:
            total = conn.execute("SELECT COUNT(*) FROM tenders").fetchone()[0]
            notified = conn.execute("SELECT COUNT(*) FROM tenders WHERE notified = 1").fetchone()[0]

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
