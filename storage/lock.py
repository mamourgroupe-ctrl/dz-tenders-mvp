"""
storage/lock.py
قفل ملفي حصري يمنع تشغيل عمليتين على قاعدة بيانات واحدة في الوقت نفسه.

التعارض هنا منطقي لا تلف: كل عملية تقرأ «ما الجديد؟» ثم تكتب «أُرسلت»،
فلو تداخلت عمليتان بين القراءة والكتابة لتُرسل المناقصة نفسها مرتين،
والقفل يغطي هذه النافذة كاملة.

يعتمد على المكتبة القياسية فقط (``msvcrt`` على Windows، ``fcntl`` على POSIX)
متجنباً تبعية جديدة، وقفل الملف يُحرَّر تلقائياً عند إغلاق المقبض حتى لو
قُتلت العملية — بخلاف ``O_CREAT|O_EXCL`` الذي يترك قفلاً يتيماً.

حدود معروفة: القفل موثوق على أنظمة الملفات المحلية فقط. على NFS أو SMB قد
لا يوفّر ``flock`` حصرية، فلا تعتمد عليه هناك.
"""

import contextlib
import logging
import os
import time
from collections.abc import Iterator

logger = logging.getLogger(__name__)

#: ``EX_TEMPFAIL`` — خطأ مؤقت، والمجدولة تستطيع إعادة المحاولة لاحقاً.
LOCK_TIMEOUT_EXIT_CODE = 75

#: مهلة افتراضية بالثواني. أوسع من دورة كاملة (~18s في السجل) بأكثر من
#: خمسين ضعفاً، حتى لا يتحوّل التعارض العابر إلى إسقاط متكرر للإشعارات.
DEFAULT_LOCK_TIMEOUT_SECONDS = 900

#: الفترة بين محاولات التقاط القفل.
_POLL_INTERVAL = 0.5

#: الفترة بين رسالتَي الانتظار.
_LOG_INTERVAL = 30.0


class DbLockTimeout(TimeoutError):
    """تعذّر التقاط قفل قاعدة البيانات قبل انتهاء المهلة."""


def lock_path_for(db_path: str | os.PathLike[str]) -> str:
    """مسار ملف القفل المرافق لقاعدة بيانات.

    Args:
        db_path: مسار ملف قاعدة البيانات.

    Returns:
        مسار ملف القفل: نفس مسار القاعدة مع اللاحقة ``.lock``.
    """
    return f"{os.fspath(db_path)}.lock"


def lock_timeout_seconds() -> float:
    """قراءة مهلة انتظار القفل من البيئة.

    Returns:
        قيمة ``LOCK_TIMEOUT_SECONDS``، أو الافتراضي عند غيابها أو صحتها.
    """
    raw = os.getenv("LOCK_TIMEOUT_SECONDS")
    if not raw:
        return float(DEFAULT_LOCK_TIMEOUT_SECONDS)

    try:
        value = float(raw)
    except ValueError:
        logger.warning("LOCK_TIMEOUT_SECONDS=%r غير رقم — يُتجاهل", raw)
        return float(DEFAULT_LOCK_TIMEOUT_SECONDS)

    if value <= 0:
        logger.warning("LOCK_TIMEOUT_SECONDS=%r يجب أن يكون موجباً — يُتجاهل", raw)
        return float(DEFAULT_LOCK_TIMEOUT_SECONDS)
    return value


def _try_acquire(handle) -> bool:
    """محاولة التقاط القفل حصرياً بلا انتظار.

    Args:
        handle: مقبض ملف القفل مفتوح للقراءة والكتابة.

    Returns:
        True عند نجاح الالتقاط، False إذا كان محجوزاً.
    """
    if os.name == "nt":
        import msvcrt

        handle.seek(0)
        try:
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            return False
        return True

    import fcntl

    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        return False
    return True


def _release(handle) -> None:
    """تحرير القفل؛ الفشل هنا لا يُهمّ لأن إغلاق المقبض يحرّره أصلاً."""
    if os.name == "nt":
        import msvcrt

        handle.seek(0)
        with contextlib.suppress(OSError):
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        return

    import fcntl

    with contextlib.suppress(OSError):
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


@contextlib.contextmanager
def db_lock(
    db_path: str | os.PathLike[str],
    *,
    timeout: float | None = None,
    label: str = "",
) -> Iterator[str]:
    """حجز قاعدة البيانات حصرياً حتى نهاية السياق.

    Args:
        db_path: مسار قاعدة البيانات المراد حجزها.
        timeout: مهلة الانتظار بالثواني. عند None تُقرأ من البيئة.
        label: وصف يظهر في رسائل الانتظار (اسم السكربت مثلاً).

    Yields:
        مسار ملف القفل المستخدم.

    Raises:
        DbLockTimeout: إذا لم يُحجز القفل قبل انتهاء المهلة. لا يُكتب شيء
            على القاعدة إطلاقاً عند هذا الفشل — تخطّي دورة قابل لإعادة
            المحاولة، بخلاف الإرسال المزدوج الذي لا يمكن التراجع عنه.
    """
    target = lock_path_for(db_path)
    limit = lock_timeout_seconds() if timeout is None else float(timeout)
    who = f" [{label}]" if label else ""
    started = time.monotonic()
    next_log = started + _LOG_INTERVAL

    directory = os.path.dirname(target)
    if directory:
        os.makedirs(directory, exist_ok=True)

    with open(target, "a+b") as handle:
        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write(b"\0")
            handle.flush()

        while not _try_acquire(handle):
            waited = time.monotonic() - started
            if waited >= limit:
                raise DbLockTimeout(
                    f"قاعدة البيانات محجوبة منذ {waited:.0f}s{who} "
                    f"(المهلة {limit:.0f}s) — أُلغيت الدورة بلا كتابة"
                )
            if time.monotonic() >= next_log:
                logger.warning(
                    "🔒 في انتظار قفل %s منذ %.0fs%s — عملية أخرى تشغل القاعدة",
                    target,
                    waited,
                    who,
                )
                next_log = time.monotonic() + _LOG_INTERVAL
            time.sleep(_POLL_INTERVAL)

        logger.debug("🔓 حُجز %s%s", target, who)
        try:
            yield target
        finally:
            _release(handle)
            logger.debug("🔓 أُطلق %s%s", target, who)


__all__ = [
    "DEFAULT_LOCK_TIMEOUT_SECONDS",
    "LOCK_TIMEOUT_EXIT_CODE",
    "DbLockTimeout",
    "db_lock",
    "lock_path_for",
    "lock_timeout_seconds",
]
