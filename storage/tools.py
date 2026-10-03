"""
storage/tools.py
أدوات إدارية للتعامل مع جدول المناقصات.

الاستخدام:
    python -m storage.tools unblock --all
    python -m storage.tools unblock --fp <fingerprint>
    python -m storage.tools blocked
"""

import argparse
import sys

from config import AppConfig

from .database import TenderDatabase

UNBLOCK_HINT = "لعرض الصفقات المحجوبة: python -m storage.tools blocked"


def _build_parser() -> argparse.ArgumentParser:
    """بناء محلّل وسائط الأوامر."""
    parser = argparse.ArgumentParser(
        prog="python -m storage.tools",
        description="أدوات إدارية لقاعدة بيانات المناقصات",
    )
    parser.add_argument(
        "--db",
        default=None,
        help="مسار قاعدة البيانات (افتراضياً من DB_PATH أو storage/tenders.db)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    unblock = sub.add_parser("unblock", help="فك حجب صفقات محجوبة")
    unblock.add_argument("--all", action="store_true", help="فك حجب كل الصفقات المحجوبة")
    unblock.add_argument("--fp", default=None, help="بصمة صفقة واحدة (SHA-256) لفك حجبها")

    blocked = sub.add_parser("blocked", help="عرض الصفقات المحجوبة")
    blocked.add_argument("--limit", type=int, default=50, help="أقصى عدد صفوف تُعرض")
    return parser


def _resolve_db_path(override: str | None) -> str:
    """تحديد مسار قاعدة البيانات: الوسيط أولاً، ثم إعداد التطبيق."""
    if override:
        return override
    return AppConfig.from_env().db_path


def _run_unblock(store: TenderDatabase, args: argparse.Namespace) -> int:
    """تنفيذ أمر ``unblock``.

    Args:
        store: اتصال بقاعدة البيانات.
        args: الوسائط المحلَّلة.

    Returns:
        رمز خروج العملية (0 نجاح، 1 خطأ في الاستخدام، 2 لم تُطابَق أي صفقة).
    """
    if args.all and args.fp:
        print("لا يمكن الجمع بين --all و --fp", file=sys.stderr)
        return 1
    if not args.all and not args.fp:
        print("حدّد --all أو --fp", file=sys.stderr)
        print(UNBLOCK_HINT, file=sys.stderr)
        return 1

    if args.all:
        count = store.unblock_all()
        print(f"🔓 فُك حجب {count} صفقة")
        return 0

    if store.unblock_tender(args.fp):
        print(f"🔓 فُك حجب الصفقة {args.fp[:12]}…")
        return 0

    print(f"لم يُعثر على صفقة بالبصمة {args.fp}", file=sys.stderr)
    print(UNBLOCK_HINT, file=sys.stderr)
    return 2


def _run_blocked(store: TenderDatabase, args: argparse.Namespace) -> int:
    """تنفيذ أمر ``blocked``.

    Args:
        store: اتصال بقاعدة البيانات.
        args: الوسائط المحلَّلة.

    Returns:
        رمز خروج العملية (0 دائماً ما لم يفشل الفتح).
    """
    rows = store.blocked_tenders(limit=args.limit)
    if not rows:
        print("لا توجد صفقات محجوبة.")
        return 0

    print(f"{len(rows)} صفقة محجوبة:\n")
    for row in rows:
        print(f"- {row['fingerprint'][:12]}… | {row['title'][:60]}")
        print(f"    المحاولات: {row['retry_count']} | آخر محاولة: {row['last_attempt_at']}")
        if row["last_error"]:
            print(f"    الخطأ: {row['last_error'][:120]}")
    print(f"\n{UNBLOCK_HINT}")
    return 0


def main(argv: list[str] | None = None) -> int:
    """نقطة دخول سطر الأوامر.

    Args:
        argv: الوسائط (افتراضياً ``sys.argv[1:]``).

    Returns:
        رمز خروج العملية.
    """
    args = _build_parser().parse_args(argv)
    store = TenderDatabase(db_path=_resolve_db_path(args.db))
    print(f"القاعدة: {store.db_path}")

    if args.command == "unblock":
        return _run_unblock(store, args)
    return _run_blocked(store, args)


if __name__ == "__main__":
    raise SystemExit(main())
