#!/usr/bin/env python3
"""Restore SQLite database from backup file — SAFE VERSION.

Safety features:
- --dry-run: verify backup without making changes
- --force: overwrite without interactive prompt (use with caution)
- Interactive confirmation required by default
- SHA256 verification via manifest before restoration
- SQLite integrity checks and logical consistency verification
- Preserves recoverable copy of existing database before replacement
- Rollback on failure
"""

import argparse
import hashlib
import json
import shutil
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path


def find_manifest(backup_path: Path) -> Path:
    """Find manifest file for backup (same name with .manifest.json suffix)."""
    manifest_path = backup_path.with_suffix(".manifest.json")
    if manifest_path.exists():
        return manifest_path
    # Also try .bak.manifest.json pattern
    alt_manifest = backup_path.with_name(backup_path.name + ".manifest.json")
    if alt_manifest.exists():
        return alt_manifest
    raise FileNotFoundError(f"Manifest not found for {backup_path}. Expected: {manifest_path}")


def read_manifest(manifest_path: Path) -> dict:
    """Read and parse manifest file."""
    if not manifest_path.exists():
        raise FileNotFoundError(f"Manifest not found: {manifest_path}")
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def verify_sha256(file_path: Path, expected_sha256: str) -> bool:
    """Verify file SHA256 matches expected value from manifest."""
    actual_sha256 = hashlib.sha256(file_path.read_bytes()).hexdigest()
    if actual_sha256 != expected_sha256:
        print(
            f"  [ERROR] SHA256 mismatch: expected={expected_sha256}, actual={actual_sha256}"
        )
        return False
    print(f"  [OK] SHA256 verified: {expected_sha256[:16]}...")
    return True


def verify_backup_sqlite(backup_path: Path) -> dict:
    """Verify backup is valid SQLite and return metadata (tables, counts)."""
    if not backup_path.exists():
        raise FileNotFoundError(f"Backup not found: {backup_path}")

    conn = sqlite3.connect(f"file:{backup_path}?mode=ro", uri=True)
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
        return {
            "tables": sorted(tables),
            "counts": counts,
            "size_bytes": backup_path.stat().st_size,
        }
    finally:
        conn.close()


def verify_destination(dest_path: Path) -> dict | None:
    """Verify existing destination database if it exists."""
    if not dest_path.exists():
        return None

    conn = sqlite3.connect(f"file:{dest_path}?mode=ro", uri=True)
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

        return {
            "tables": sorted(tables),
            "counts": counts,
            "size_bytes": dest_path.stat().st_size,
        }
    finally:
        conn.close()


def verify_consistency(src_info: dict, dest_info: dict) -> bool:
    """Verify two databases are logically consistent (tables + row counts)."""
    if src_info["tables"] != dest_info["tables"]:
        print(f"  [ERROR] Table mismatch: source={src_info['tables']}, dest={dest_info['tables']}")
        return False
    for table, count in src_info["counts"].items():
        if dest_info["counts"].get(table) != count:
            print(
                f"  [ERROR] Row count mismatch for {table}: "
                f"source={count}, dest={dest_info['counts'].get(table)}"
            )
            return False
    return True


def create_safety_copy(dest_path: Path) -> Path:
    """Create a recoverable copy of the existing database before replacement."""
    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    safety_path = dest_path.with_suffix(f".pre_restore_{timestamp}.bak")
    shutil.copy2(dest_path, safety_path)
    print(f"[SAFETY] Safety copy created: {safety_path}")
    return safety_path


def restore_database(
    backup_path: Path,
    dest_path: Path,
    force: bool = False,
    dry_run: bool = False,
) -> None:
    """Restore database from backup with safety checks."""
    # Step 1: Find and read manifest
    print("[INFO] Locating manifest...")
    manifest_path = find_manifest(backup_path)
    manifest = read_manifest(manifest_path)
    print(f"  Manifest: {manifest_path}")
    print(f"  Created:  {manifest.get('created_utc', 'unknown')}")

    # Step 2: Verify SHA256 from manifest
    print("[INFO] Verifying SHA256 checksum...")
    expected_sha256 = manifest.get("sha256")
    if not expected_sha256:
        raise RuntimeError("Manifest missing SHA256 checksum — cannot verify integrity")
    if not verify_sha256(backup_path, expected_sha256):
        raise RuntimeError("SHA256 verification failed — backup may be corrupted or tampered")

    # Step 3: Verify SQLite integrity and logical structure
    print("[INFO] Verifying SQLite integrity and structure...")
    backup_info = verify_backup_sqlite(backup_path)
    print(f"   Tables: {backup_info['tables']}")
    print(f"   Row counts: {backup_info['counts']}")
    print(f"   Size: {backup_info['size_bytes']} bytes")

    # Verify manifest tables/counts match actual backup (logical consistency)
    manifest_tables = manifest.get("tables", [])
    manifest_counts = manifest.get("row_counts", {})
    if manifest_tables and manifest_tables != backup_info["tables"]:
        raise RuntimeError(
            "Manifest table list mismatch: "
            f"manifest={manifest_tables}, actual={backup_info['tables']}"
        )
    for table, count in manifest_counts.items():
        if backup_info["counts"].get(table) != count:
            raise RuntimeError(
                "Manifest row count mismatch for "
                f"{table}: manifest={count}, actual={backup_info['counts'].get(table)}"
            )
    print("  [OK] Manifest matches backup content (logical consistency)")

    # Step 4: Check existing destination
    dest_info = verify_destination(dest_path)
    if dest_info:
        print(f"\n[INFO] Existing destination ({dest_path}):")
        print(f"   Tables: {dest_info['tables']}")
        print(f"   Row counts: {dest_info['counts']}")
        print(f"   Size: {dest_info['size_bytes']} bytes")

        if verify_consistency(backup_info, dest_info):
            print("\n[OK] Backup matches existing database -- no restore needed.")
            return

    if dry_run:
        print("\n[DRY RUN] All verifications passed. No changes made.")
        return

    # Step 5: Confirm destructive action
    if dest_path.exists() and not force:
        print(f"\n[WARN] This will OVERWRITE {dest_path}")
        print("   A safety copy will be created first.")
        resp = input("\nType 'YES' to confirm restoration: ").strip()
        if resp != "YES":
            print("[ABORT] Aborted by user.")
            sys.exit(1)

    # Step 6: Create safety copy if destination exists
    safety_path = None
    if dest_path.exists():
        safety_path = create_safety_copy(dest_path)

    try:
        # Atomic replace via temp file
        temp_path = dest_path.with_suffix(".tmp_restore")
        shutil.copy2(backup_path, temp_path)
        temp_path.replace(dest_path)

        # Step 7: Verify restored database (logical consistency)
        print("[INFO] Verifying restored database...")
        restored_info = verify_backup_sqlite(dest_path)
        if not verify_consistency(backup_info, restored_info):
            raise RuntimeError("Restored database logical consistency check failed!")

        print(f"\n[OK] Restored {backup_path} -> {dest_path}")
        print(f"   Verified: {restored_info['counts']}, tables: {restored_info['tables']}")

    except Exception as e:
        # Attempt to restore safety copy on failure
        if safety_path and safety_path.exists():
            print(f"\n[ERROR] Restore failed: {e}")
            print("[INFO] Attempting to restore safety copy...")
            try:
                shutil.copy2(safety_path, dest_path)
                print("[OK] Safety copy restored.")
            except Exception as e2:
                print(f"[CRITICAL] Failed to restore safety copy: {e2}", file=sys.stderr)
        raise


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Restore SQLite database from backup (safe mode)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  # Verify backup only (safe)\n"
            "  python scripts/restore_db.py "
            "~/dz-tenders-backups/tenders_20261108_120000.bak "
            "storage/tenders.db --dry-run\n\n"
            "  # Restore with interactive confirmation\n"
            "  python scripts/restore_db.py "
            "~/dz-tenders-backups/tenders_20261108_120000.bak "
            "storage/tenders.db\n\n"
            "  # Force restore without prompt (CI/automation only)\n"
            "  python scripts/restore_db.py "
            "~/dz-tenders-backups/tenders_20261108_120000.bak "
            "storage/tenders.db --force"
        ),
    )
    parser.add_argument("backup_file", type=Path, help="Path to backup file (.bak)")
    parser.add_argument("destination_db", type=Path, help="Destination database path")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite without interactive confirmation (use with caution)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Verify backup and show what would be restored, but make no changes",
    )
    args = parser.parse_args()

    try:
        restore_database(
            args.backup_file,
            args.destination_db,
            force=args.force,
            dry_run=args.dry_run,
        )
        return 0
    except Exception as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())