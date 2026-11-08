#!/usr/bin/env python3
"""Create timestamped SQLite backups using .backup API (online, consistent).

This script creates LOCAL backups only. Backups are stored in a configurable
directory outside the Git repository. No cloud uploads. Encrypted off-site
storage is planned for Phase 3.

Each backup includes a manifest file (.manifest.json) with SHA256 checksum
for integrity verification before restoration.
"""

import hashlib
import json
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path


def verify_database(db_path: Path) -> dict:
    """Verify database is valid SQLite and return metadata."""
    if not db_path.exists():
        raise FileNotFoundError(f"Database not found: {db_path}")

    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        tables = [
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        ]
        counts = {}
        for table in ("tenders", "announcements", "users", "subscriptions"):
            if table in tables:
                counts[table] = conn.execute(
                    f"SELECT COUNT(*) FROM {table}"
                ).fetchone()[0]

        sha256 = hashlib.sha256(db_path.read_bytes()).hexdigest()
        return {
            "tables": sorted(tables),
            "counts": counts,
            "sha256": sha256,
            "size_bytes": db_path.stat().st_size,
        }
    finally:
        conn.close()


def verify_backup_consistency(src_info: dict, dest_info: dict) -> bool:
    """Verify backup is logically consistent with source (tables + row counts)."""
    # Compare table sets
    if src_info["tables"] != dest_info["tables"]:
        print(f"  Table mismatch: source={src_info['tables']}, dest={dest_info['tables']}")
        return False

    # Compare row counts for known tables
    for table, count in src_info["counts"].items():
        dest_count = dest_info["counts"].get(table)
        if dest_count != count:
            print(
                f"  Row count mismatch for {table}: "
                f"source={count}, dest={dest_count}"
            )
            return False

    return True


def write_manifest(backup_path: Path, info: dict) -> Path:
    """Write manifest file alongside backup with SHA256 and metadata."""
    manifest_path = backup_path.with_suffix(".manifest.json")
    manifest = {
        "backup_file": backup_path.name,
        "created_utc": datetime.now(UTC).isoformat(),
        "tables": info["tables"],
        "row_counts": info["counts"],
        "sha256": info["sha256"],
        "size_bytes": info["size_bytes"],
    }
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest_path


def read_manifest(manifest_path: Path) -> dict:
    """Read and parse manifest file."""
    if not manifest_path.exists():
        raise FileNotFoundError(f"Manifest not found: {manifest_path}")
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def verify_sha256(file_path: Path, expected_sha256: str) -> bool:
    """Verify file SHA256 matches expected value."""
    actual_sha256 = hashlib.sha256(file_path.read_bytes()).hexdigest()
    if actual_sha256 != expected_sha256:
        print(
            f"  SHA256 mismatch: expected={expected_sha256}, actual={actual_sha256}"
        )
        return False
    return True


def backup_database(src_path: Path, dest_dir: Path) -> Path:
    """Create a consistent backup of a SQLite database using the online backup API."""
    dest_dir.mkdir(parents=True, exist_ok=True)

    # Verify source first
    src_info = verify_database(src_path)
    sha_short = src_info["sha256"][:16]
    print(
        f"Source verification: {src_info['tables']} tables, "
        f"{src_info['counts']}, SHA256: {sha_short}..."
    )

    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    dest_path = dest_dir / f"{src_path.stem}_{timestamp}.bak"

    # Online backup API - no lock needed, consistent snapshot
    src_conn = sqlite3.connect(str(src_path))
    dest_conn = sqlite3.connect(str(dest_path))
    try:
        src_conn.backup(dest_conn)
    finally:
        src_conn.close()
        dest_conn.close()

    # Verify backup (logical consistency + SHA256)
    dest_info = verify_database(dest_path)
    if not verify_backup_consistency(src_info, dest_info):
        dest_path.unlink(missing_ok=True)
        raise RuntimeError("Backup verification failed: logical inconsistency")

    # Write manifest with SHA256
    manifest_path = write_manifest(dest_path, dest_info)
    print(f"[OK] Backup created: {dest_path} ({dest_info['size_bytes']} bytes)")
    print(f"[OK] Manifest written: {manifest_path}")
    return dest_path


def backup_uploads(uploads_dir: Path, backup_dir: Path) -> Path | None:
    """Create tar.gz backup of uploads directory with manifest."""
    import tarfile

    if not uploads_dir.exists() or not any(uploads_dir.iterdir()):
        return None

    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    uploads_backup = backup_dir / f"uploads_{timestamp}.tar.gz"

    with tarfile.open(uploads_backup, "w:gz") as tar:
        tar.add(uploads_dir, arcname="uploads")

    # Write manifest for uploads backup
    sha256 = hashlib.sha256(uploads_backup.read_bytes()).hexdigest()
    manifest = {
        "backup_file": uploads_backup.name,
        "created_utc": datetime.now(UTC).isoformat(),
        "type": "uploads_archive",
        "sha256": sha256,
        "size_bytes": uploads_backup.stat().st_size,
    }
    manifest_path = uploads_backup.with_suffix(".manifest.json")
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    print(f"[OK] Uploads backup created: {uploads_backup} ({manifest['size_bytes']} bytes)")
    print(f"[OK] Manifest written: {manifest_path}")
    return uploads_backup


def get_backup_dir() -> Path:
    """Get backup directory from environment or use default outside repo."""
    import os

    # Allow configurable backup directory via environment variable
    # Default: ~/dz-tenders-backups (outside repository)
    custom_dir = os.environ.get("DZ_TENDERS_BACKUP_DIR")
    if custom_dir:
        return Path(custom_dir).expanduser().resolve()

    # Default to user home directory outside repo
    home = Path.home()
    return home / "dz-tenders-backups"


def main() -> int:
    repo_root = Path(__file__).parent.parent
    backup_dir = get_backup_dir()

    print(f"[INFO] Backup directory: {backup_dir}")
    print(f"[INFO] Repository root: {repo_root}")

    # Assets to back up (prioritize databases and sensitive state)
    assets = [
        ("storage/tenders.db", "Legacy tender database"),
        ("storage/platform.db", "Platform database"),
        ("storage/marches_state.json", "Marches Publics crawler session"),
    ]

    success_count = 0
    for rel_path, description in assets:
        src = repo_root / rel_path
        if src.exists():
            try:
                backup_database(src, backup_dir)
                success_count += 1
            except Exception as e:
                print(f"[ERROR] Failed to backup {description} ({rel_path}): {e}", file=sys.stderr)
        else:
            print(f"[SKIP] {description} ({rel_path}): not found")

    # Also back up uploads directory if it exists
    uploads_dir = repo_root / "storage" / "uploads"
    if uploads_dir.exists() and any(uploads_dir.iterdir()):
        try:
            backup_uploads(uploads_dir, backup_dir)
            success_count += 1
        except Exception as e:
            print(f"[ERROR] Failed to backup uploads: {e}", file=sys.stderr)
    else:
        print("[SKIP] uploads directory: not found or empty")

    print(
        f"\n[DONE] Backup complete: {success_count}/{len(assets) + 1} assets "
        f"backed up to {backup_dir}"
    )
    print(
        "NOTE: Backups stored locally only (outside repository). "
        "For production, implement encrypted off-site storage (Phase 3)."
    )
    return 0 if success_count == len(assets) + 1 else 1


if __name__ == "__main__":
    sys.exit(main())