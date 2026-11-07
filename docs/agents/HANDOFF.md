# HANDOFF: سجل تسليم المهام بين الوكلاء
> يكتب المنفذ (Kilo / Antigravity) هنا بعد الانتهاء من مهمة، قبل أن يطلب المراجعة.
> اقرأ أحدث سجل قبل البدء بأي مهمة جديدة.

---
## [مثال] مهمة: نقل storage/auth
- **المنفذ:** Kilo Code
- **الفرع:** chore/secure-auth-storage
- **ما تم إنجازه:**
  - نقل المجلد إلى المسار الخارجي `_secrets/`.
  - تحديث الكود لاستخدام `MARCHES_STATE_PATH`.
  - إضافة اختبارات للمسارات الافتراضية.
- **ما تم التحقق منه:**
  - `pytest`: 426 اختباراً ناجحاً.
  - `ruff check .`: نظيف.
  - الفرق (diff) خالٍ من المسارات المطلقة.
- **ملاحظات للمراجع (Gemini):**
  - يرجى التركيز على ملفات `crawlers/marches_publics_auth_crawler.py` و `scripts/marches_login.py`.

---
## مهمة: التعامل مع تحذير Starlette DeprecationWarning
- **المنفذ:** Kilo Code
- **الفرع:** chore/fix-starlette-deprecation
- **ما تم إنجازه:**
  - تحديد مصدر التحذير: Starlette 0.46.2 يقرأ `anyio.abc.BlockingPortal`، وهو alias مهمل في AnyIO 4.15.1.
  - التراجع عن تجربة ترقية FastAPI وStarlette، وإبقاء `requirements.txt` دون تغيير.
  - إضافة مرشح Pytest لتحذيرات DeprecationWarning المنبعثة من وحدات Starlette.
- **ما تم التحقق منه:**
  - `pytest -q`: 426 اختباراً ناجحاً، دون عرض التحذير بسبب المرشح.
  - `ruff check .` و`git diff --check`: ناجحان.
  - `pytest -q -W error::DeprecationWarning` ما زال يفشل عند التحميل؛ التحذير الأصلي جرى ترشيحه في إعداد Pytest، ولم يُصلح داخل Starlette.
---

## Important: فحص BAOSEM و BOMOP
- **المنفذ:** Kilo Code
- **الفرع:** chore/audit-baosem-bomop
- **ما تم إنجازه:**
  - فحص بالقراءة فقط (بدون تعديل) لـ `crawlers/baosem.py` و `crawlers/bomop.py` و `crawlers/public_tender_crawler.py` و `crawlers/base_crawler.py`.
  - بحث في `tests/` عن تغطية BAOSEM/BOMOP (من خلال الأسماء والاستيرادات).
  - إضافة سطر إلى قسم In Progress في `docs/agents/TASKS.md` §1.
- **ما تم التحقق منه (الأمر الجاهز):**
  - **الهيكلة:** كلا الزاحwinsnot فارغات (stubs)؛ كلاهما يرث من PublicTenderCrawler (الذي يرث من BaseCrawler)، ويستخدم requests + BeautifulSoup (وليس httpx ولا Playwright).
  - **الاستيراد:** كلاهما يستورد من `.public_tender_crawler` (المسار صحيح)، وليس من `crawlers.base` (غير موجود).
  - **TODO/FIXME:** لا توجد علامات في `baosem.py` / `bomop.py` / `public_tender_crawler.py`.
  - **التغطية:** اختبارات موجودة في `tests/test_public_tender_crawlers.py` (6 اختبارات)، وليس هناك files منفصلة `test_baosem.py`/`test_bomop.py`.
  - **الأخطار الملاحظة:** لا توجد أخطار فورية؛ كلا الزاحwinsame النمط (تحليل listing page)، والفرق فقط هو `BASE_URL` وسلسلة `source`.
  - **فراغات التغطية:** لا توجد اختبارات منفصلة لكل زاحف؛ التغطية مدمجة في `test_public_tender_crawlers.py`. لا توجد اختبارات ربط مع المواقع الحقيقية (وهي ممنوعة بالمركزية).
  - **الجودة:**
    - `ruff check .`: نظيف (All checks passed).
    - `pytest -q`: 426 passed (مطابق للbaseline).
    - `black --check webapp migrations tests/conftest.py tests/test_phase1_*.py`: 34 files unchanged.
    - `mypy webapp --ignore-missing-imports`: Success, no issues in 24 source files.
    - `git diff --check`: نظيف.
- **ملاحظات للمراجعة (Gemini):**
  - يرجى التركيز على `crawlers/baosem.py` و `crawlers/bomop.py` و `tests/test_public_tender_crawlers.py`.
  - التدقيق لم يُجرِ تعليمات على source code — الفرق (diff) docs-only (`TASKS.md`، `HANDOFF.md`).
  - أي إصلاحات لـ `crawlers/` يجب أن تكون في مهام منفصلة، بعد مراجعة التقرير.
