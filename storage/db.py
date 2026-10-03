"""Backward-compatible storage module.

Older code imports:
    from storage.db import TenderStore

The current implementation is:
    storage.database.TenderDatabase
"""

from .database import TenderDatabase


class TenderStore(TenderDatabase):
    """Compatibility wrapper around TenderDatabase."""

    def is_new_or_changed(self, tender: dict) -> bool:
        """هل تحتاج المناقصة إلى إشعار؟

        تُعيد ``True`` في حالتين فقط: المناقصة غير مخزَّنة إطلاقاً، أو مخزَّنة
        ولم تُبلَّغ بعد ولم تُحجب (``notified=0`` و ``blocked=0``). الصفقة
        المحجوبة أو المُبلَّغة سابقاً تُعيد ``False``.

        تنبيه: البصمة الحالية ``title|organisation|link`` لا تكتشف تغيّر الأجل
        أو السعر، فاسم الدالة يَعِد بأكثر مما تفعل.
        """
        # TODO(FUTURE-T4): كشف تغيّر المحتوى ببصمة ثانية — DEVELOPMENT_ROADMAP T4
        fingerprint = self._fingerprint(tender)

        with self._connect() as conn:
            row = conn.execute(
                "SELECT notified, blocked FROM tenders WHERE fingerprint = ? LIMIT 1",
                (fingerprint,),
            ).fetchone()

        if row is None:
            return True
        return not row["notified"] and not row["blocked"]

    def mark_sent(self, tender: dict) -> None:
        """Save tender and mark it as sent/notified."""
        self.add_tender(tender)
        self.mark_notified(tender)

    def is_sent(self, tender: dict) -> bool:
        """Return True if tender was already sent/notified."""
        return self.is_notified(tender)

    def count(self) -> int:
        """Return total number of stored tenders."""
        with self._connect() as conn:
            row = conn.execute("SELECT COUNT(*) AS total FROM tenders").fetchone()

        return int(row["total"] if row else 0)

    def close(self) -> None:
        """Compatibility no-op.

        TenderDatabase uses context-managed SQLite connections,
        so there is no persistent connection to close.
        """
        return None

    def save(self, tender: dict) -> bool:
        """Compatibility alias for add_tender."""
        return self.add_tender(tender)

    def upsert(self, tender: dict) -> bool:
        """Compatibility alias for add_tender."""
        return self.add_tender(tender)

    def save_tender(self, tender: dict) -> bool:
        """Compatibility alias for add_tender."""
        return self.add_tender(tender)

    def upsert_tender(self, tender: dict) -> bool:
        """Compatibility alias for add_tender."""
        return self.add_tender(tender)

    def add_or_update(self, tender: dict) -> bool:
        """Compatibility alias for add_tender."""
        return self.add_tender(tender)

    def save_many(self, tenders: list[dict]) -> int:
        """Save multiple tenders and return inserted count."""
        return sum(1 for tender in tenders if self.add_tender(tender))

    def upsert_many(self, tenders: list[dict]) -> int:
        """Compatibility alias for save_many."""
        return self.save_many(tenders)


__all__ = ["TenderDatabase", "TenderStore"]
