"""
storage/delivery.py
المقطع الحرج الموحّد لكل مسارات التنفيذ: ترحيل + حفظ + إرسال + وسم.

كانت كل نقطة دخول (``main.py``، ``run_smart_scraper.py``، ``test_run.py``)
تكرّر نفس التسلسل: تقرأ «ما الجديد؟» وتحفظ ثم ترسل ثم توسم. التكرار هو ما
سماح بإرسال نفس المناقصة مرتين حين يتقاطع تشغيلان، لأنه لا يمرّ كلٌّ منهما
بمنطق واحد محمي.

هذه الوحدة تفرض تسلسلاً واحداً محمياً بقفل واحد، وتترك لكل نقطة دخول حرية
اختيار طريقة الإرسال عبر دالة ``send``.

قواعد ملزمة لصيانة هذه الوحدة:

- هذه هي الدالة الوحيدة المسؤولة عن دورة حياة التسليم.
- أي entrypoint جديد يجب أن يستدعي deliver() بدلاً من تكرار المنطق.
- التعديل على منطق mark_sent/register_failed_attempt يجب أن يحدث هنا فقط.

ملاحظة تصميمية: يُمرَّر مسار القاعدة صراحةً إلى ``deliver`` ولا يُستنتج من
المصنع. الاستنتاج من مصنع مجهول يخفض القفل على ملف غير الملف الذي يفتحه
التخزين فعلاً، وهو أسوأ من غياب القفل: طمأنينة كاذبة.
"""

import logging
import os
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from typing import Any

from .lock import DbLockTimeout, db_lock, lock_timeout_seconds

logger = logging.getLogger(__name__)

#: لا توجد صفقات تستحق الإشعار.
STATUS_EMPTY = "empty"
#: حُفظت الصفقات ولم يُرسل شيء (وضع Dry-Run أو غياب إعدادات الإرسال).
STATUS_SKIPPED = "skipped"
#: نجح الإرسال ووُسِمت الصفقات.
STATUS_SENT = "sent"
#: فشل الإرسال وسُجِّلت محاولة فاشلة لكل صفقة.
STATUS_FAILED = "failed"
#: قاعدة البيانات محجوبة أثناء كل المهلة — لم تُكتب أي صفقة.
STATUS_LOCKED = "locked"

#: ``send(pending) -> (success, error)`` — تُنفَّذ داخل القفل.
Sender = Callable[[list[dict]], "tuple[bool, str]"]

#: ``store_factory() -> TenderStore`` — تُستدعى داخل القفل لا خارجه.
StoreFactory = Callable[[], Any]


@dataclass
class DeliveryOutcome:
    """نتيجة محاولة التسليم الموحّدة.

    Attributes:
        status: إحدى الثوابت ``STATUS_*`` أعلاه.
        pending: الصفقات التي رآها هذا الإصدار جديدة (قد تكون محفوظة بلا إرسال).
        inserted: عدد الصفقات التي أُدرجت فعلياً في القاعدة.
        error: سبب الفشل أو نصّ مهلة القفل.
        total: إجمالي الصفقات في القاعدة بعد المحاولة.
    """

    status: str
    pending: list[dict] = field(default_factory=list)
    inserted: int = 0
    error: str = ""
    total: int = 0

    @property
    def is_locked_out(self) -> bool:
        """هل أُلغيت الدورة بسبب حجز القاعدة من عملية أخرى؟"""
        return self.status == STATUS_LOCKED


def _total_in_db(store: Any) -> int:
    """إجمالي الصفقات في القاعدة، مع تراجع إلى ``stats`` عند غياب ``count``."""
    counter = getattr(store, "count", None)
    if callable(counter):
        return int(counter())

    stats = getattr(store, "stats", None)
    if callable(stats):
        return int(stats().get("total", 0))
    return 0


def _close(store: Any) -> None:
    """إغلاق المخزن إن كان يوفّر ذلك."""
    closer = getattr(store, "close", None)
    if callable(closer):
        closer()


def _deliver_locked(
    store: Any,
    tenders: Sequence[dict],
    send: Sender | None,
    dry_run: bool,
    on_pending: Callable[[list[dict]], None] | None,
) -> DeliveryOutcome:
    """تنفيذ التسلسل الحرج. يجب استدعاؤه والتزامه بقفل قاعدة البيانات."""
    pending = [tender for tender in tenders if store.is_new_or_changed(tender)]
    if not pending:
        logger.info("✅ لا توجد صفقات تستحق الإشعار")
        return DeliveryOutcome(status=STATUS_EMPTY, total=_total_in_db(store))

    inserted = store.save_many(pending)
    logger.info("💾 حُفظت %d صفقة في القاعدة", inserted)

    if on_pending is not None:
        on_pending(pending)

    if dry_run:
        logger.warning("DRY_RUN=true: تخطّي الإرسال")
        return DeliveryOutcome(
            status=STATUS_SKIPPED,
            pending=pending,
            inserted=inserted,
            total=_total_in_db(store),
        )

    if send is None:
        logger.warning("تخطّي الإرسال: لا مُرسّل متاح")
        return DeliveryOutcome(
            status=STATUS_SKIPPED,
            pending=pending,
            inserted=inserted,
            total=_total_in_db(store),
        )

    success, error = send(pending)
    if success:
        for tender in pending:
            store.mark_sent(tender)
        logger.info("📤 وُسمت %d صفقة كمُرسَلة", len(pending))
        status = STATUS_SENT
    else:
        for tender in pending:
            store.register_failed_attempt(tender, error)
        logger.warning("فشل الإرسال عبر كل القنوات — سُجّلت محاولة فاشلة لكل صفقة: %s", error)
        status = STATUS_FAILED

    return DeliveryOutcome(
        status=status,
        pending=pending,
        inserted=inserted,
        error=error,
        total=_total_in_db(store),
    )


def deliver(
    db_path: str | os.PathLike[str],
    store_factory: StoreFactory,
    tenders: Iterable[dict],
    send: Sender | None = None,
    *,
    dry_run: bool = False,
    on_pending: Callable[[list[dict]], None] | None = None,
    timeout: float | None = None,
    label: str = "",
) -> DeliveryOutcome:
    """ترحيل الصفقات وتسليمها تحت قفل حصري واحد.

    Args:
        db_path: مسار قاعدة البيانات — نفس الملف الذي يفتحه ``store_factory``.
        store_factory: مصنع قاعدة البيانات. **يُستدعى داخل القفل** لأن
            ``TenderDatabase.__init__`` ينشئ الجداول ويزيحها — فتح القاعدة
            قبل القفل خرق للمقطع الحرج.
        tenders: الصفقات المرشّحة بعد الفلترة.
        send: دالة الإرسال تُعيد ``(نجاح، سبب_الخطأ)`` وتُنفَّذ داخل القفل.
            عند None يُتخطّى الإرسال بعد الحفظ.
        dry_run: حفظ بلا إرسال.
        on_pending: تُستدعى بالصفقات الجديدة داخل القفل، بعد الحفظ وقبل
            الإرسال — لتوليد تقرير Excel مثلاً.
        timeout: مهلة انتظار القفل بالثواني. عند None تُقرأ من البيئة.
        label: وصف السكربت في رسائل القفل.

    Returns:
        DeliveryOutcome؛ و``status`` يساوي ``STATUS_LOCKED`` إذا حجزت عملية
        أخرى القاعدة حتى انتهت المهلة، وفي هذه الحالة لم يُكتب أي شيء.
    """
    target = os.fspath(db_path)

    try:
        with db_lock(target, timeout=timeout, label=label):
            store = store_factory()
            try:
                return _deliver_locked(store, tenders, send, dry_run, on_pending)
            finally:
                _close(store)
    except DbLockTimeout as exc:
        logger.error("🔒 %s", exc)
        return DeliveryOutcome(status=STATUS_LOCKED, error=str(exc))


__all__ = [
    "STATUS_EMPTY",
    "STATUS_FAILED",
    "STATUS_LOCKED",
    "STATUS_SENT",
    "STATUS_SKIPPED",
    "DeliveryOutcome",
    "deliver",
    "lock_timeout_seconds",
]
