"""Compatibility layer for older storage imports.

Older code uses:
    from storage.db import TenderStore

Current implementation uses:
    storage.database.TenderDatabase
"""

from .database import TenderDatabase


class TenderStore(TenderDatabase):
    """Backward-compatible wrapper around TenderDatabase."""

    def is_new_or_changed(self, tender: dict) -> bool:
        """Return True if the tender does not already exist in the database."""
        fingerprint = self._fingerprint(tender)

        with self._connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM tenders WHERE fingerprint = ? LIMIT 1",
                (fingerprint,),
            ).fetchone()

        return row is None

    def mark_sent(self, tender: dict) -> None:
        """Backward-compatible alias for mark_notified."""
        self.mark_notified(tender)

    def is_sent(self, tender: dict) -> bool:
        """Backward-compatible alias for is_notified."""
        return self.is_notified(tender)

    def count(self) -> int:
        """Return number of stored tenders."""
        with self._connect() as conn:
            row = conn.execute("SELECT COUNT(*) AS total FROM tenders").fetchone()

        return int(row["total"] if row else 0)

    def close(self) -> None:
        """Backward-compatible no-op.

        TenderDatabase opens SQLite connections with context managers,
        so there is no persistent connection to close.
        """
        return None

    def save(self, tender: dict) -> bool:
        """Backward-compatible alias for add_tender."""
        return self.add_tender(tender)

    def upsert(self, tender: dict) -> bool:
        """Backward-compatible alias for add_tender."""
        return self.add_tender(tender)

    def save_tender(self, tender: dict) -> bool:
        """Backward-compatible alias for add_tender."""
        return self.add_tender(tender)

    def upsert_tender(self, tender: dict) -> bool:
        """Backward-compatible alias for add_tender."""
        return self.add_tender(tender)

    def add_or_update(self, tender: dict) -> bool:
        """Backward-compatible alias for add_tender."""
        return self.add_tender(tender)

    def save_many(self, tenders: list[dict]) -> int:
        """Save multiple tenders and return number of newly inserted tenders."""
        return sum(1 for tender in tenders if self.add_tender(tender))

    def upsert_many(self, tenders: list[dict]) -> int:
        """Backward-compatible alias for save_many."""
        return self.save_many(tenders)


__all__ = ["TenderDatabase", "TenderStore"]
