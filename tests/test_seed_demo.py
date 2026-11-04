import sqlite3

from scripts.seed_demo import main


def test_seed_demo_uses_db_path_environment_variable(tmp_path, monkeypatch):
    """Seed the configured database path rather than the repository default."""
    db_path = tmp_path / "persistent" / "tenders.db"
    monkeypatch.setenv("DB_PATH", str(db_path))

    assert main() == 0

    assert db_path.is_file()
    with sqlite3.connect(db_path) as connection:
        tender_count = connection.execute("SELECT COUNT(*) FROM tenders").fetchone()[0]

    assert tender_count == 41
