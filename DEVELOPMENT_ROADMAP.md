# DEVELOPMENT_ROADMAP — DZ-TENDERS-MVP

تاريخ التقييم: 2026-09-30 · النطاق: `main.py`, `crawlers/*`, `notifications/*`, `storage/*`, `tender_filter.py`, `config.py`, `tests/*`

---

## 1. الملخص التنفيذي

1. البنية جيدة على مستوى التصميم (طبقة إشعارات مجرّدة عبر `NotificationChannel`، جدول SQLite مفهرس، فلترة موزونة)، لكن التشغيل الحي غير مكتمل: `main.py` لا يسجّل المناقصات في قاعدة البيانات إطلاقاً، فكل مناقصة تُعتبر "جديدة" في كل دورة.
2. أخطر عيوب التشغيل: `build_notifier()` يقرأ `os.environ["TELEGRAM_BOT_TOKEN"]` مباشرةً قبل فحص `DRY_RUN` (main.py:71-73، main.py:105) فيسقط التطبيق بـ `KeyError` عند غياب المتغير، رغم أن `AppConfig` يوفّر `telegram_bot_token` (config.py:30).
3. ثلاثة كرولرز تُرجع بيانات مرجعية مُلفّقة كأنها نتائج حية (ona_crawler.py:83، algeria_tenders_crawler.py:116، marches_publics_crawler.py:35) — هذا يُفسد أي قرار تجاري مبني على التقرير.
4. المنطق مكرّر في 4 مواضع: `normalize_text` في 3 كرولرز، وقوائم الكلمات المفتاحية في 4 ملفات ومتناقضة بينها (`"نابيب"` خطأ إملائي في smart_crawler.py:38).
5. لا يوجد اختبار واحد لأي كرولر أو قناة إشعار أو تقرير Excel — التصنيف الحالي 4.8/10 والوصول للإنتاج يحتاج إغلاق المهام P0 الست الأولى (≈34 ساعة).

---

## 2. نقاط القوة

| # | النقطة | الدليل |
|---|--------|--------|
| S1 | تجريد الإشعارات يسمح بإضافة قناة (WhatsApp/Email) دون لمس بقية الكود | `notifications/base.py:13-24` (ABC) + `NotificationManager.broadcast` مع try/except لكل قناة (base.py:37-56) |
| S2 | مخطط قاعدة بيانات سليم مع فهارس على `fingerprint` و`wilaya` و`notified` | `storage/database.py:39-60` |
| S3 | بصمة SHA-256 مركّبة من (title, organisation, link) تمنع التكرار | `storage/database.py:64-74` |
| S4 | تطبيع عربي/لاتيني متقدّم: تشكيل، نبرات، أرقام هندية، حذف سوابق "ال"، كلماتوقف | `tender_filter.py:75-107` |
| S5 | تسجيل بيانات المصدر في `data/sources_master.json` مع تصنيف أولوية وحالة، مع `SourcesLoader` بواجهة استعلام نظيفة | `sources/loader.py:33-65` |
| S6 | `AppConfig` مجمّد (`frozen=True`) ومركّز، و`DRY_RUN` افتراضيه `True` (آمن) | `config.py:22-46` |
| S7 | طبقات بديلة متوفرة بالفعل: `telegram_notifier.py`، `whatsapp_notifier.py`، `SmartCrawler` — لا حاجة لبنائها من الصفر | `run_smart_scraper.py`, `crawlers/smart_crawler.py` |

---

## 3. نقاط الضعف (مرتبة خطورة)

### حرجة (تمنع التشغيل الصحيح)

- **W1 — المناقصات لا تُحفظ في قاعدة البيانات أبداً.** `main.py` يستدعي `store.is_new_or_changed` (main.py:116) ثم `store.mark_notified` (main.py:136) مباشرة. `mark_notified` ينفّذ `UPDATE` فقط (database.py:122-127) على صف غير موجود. النتيجة: صفر إدراجات، وصفر تصفية عبر الدورات → إشعار بكل مناقصة في كل تشغيل.
- **W2 — انهيار فوري عند غياب التوكن.** `build_notifier()` (main.py:67-75) يُستدعى في السطر 105 قبل فرع `dry_run` في السطر 127 → `KeyError: 'TELEGRAM_BOT_TOKEN'` حتى في وضع Dry-Run. كما أن `AppConfig.telegram_bot_token` مُعرَّف ولا يُستخدم.
- **W3 — بيانات مرجعية مُلفّقة تُقدَّم كنتائج حقيقية.** `ona_crawler.py:81-93`، `algeria_tenders_crawler.py:114-146`، `marches_publics_crawler.py:33-47` تعيد مناقصات بتواريخ آجلة ثابتة وروابط主场 عامة. لا وسم `is_sample` ولا `source_status`، فيصل المستخدم إشعاراً يظنه صفقة حقيقية.
- **W4 — الكلمات المفتاحية العربية في `ONACrawler` مستحيلة المطابقة.** `normalize_text` يطبّع NFD ثم `encode("ascii","ignore")` (ona_crawler.py:33-39) فيحذف العربية بالكامل، بينما `self.keywords` يحوي `"قنوات"`, `"تطهير"`, `"أنابيب"` (ona_crawler.py:26-27). النتيجة: لا تطابق عربي إطلاقاً؛ والفرنسية وحدها تعمل.
- **W5 —_html غير مُهرَّم في رسائل تلغرام.** `TelegramNotifier.send_message` يستخدم `parse_mode="HTML"` (telegram_notifier.py:22) والعناوين تُمرَّر خاماً من مواقع خارجية؛ أي `&` أو `<` في عنوان يفشل إرسال الرسالة بخطأ 400 من الواجهة، وتُعاد النتيجة `False` فقط دون تفاصيل (telegram_notifier.py:26-30).

### عالية

- **W6 — `verify=False` وتعطيل تحذيرات TLS.** `algeria_tenders_crawler.py:57`، `smart_crawler.py:79` مع `urllib3.disable_warnings(...)` في أعلى الملفين (سطر 11/16). يقبل اتصالاً مشفّراً بمُعرِّف غير موثوق — أي MitM على تجميع الصفحات الواردة للمستخدم.
- **W7 — مساران تنفيذيان متناقضان.** `main.py` (3 كرولرز ثابتة، جدول تلغرام، Excel) و`run_smart_scraper.py` (كل المصادر، رسالة نصية فقط) يشتركان في نفس الجدول `storage/tenders.db`. تشغيلهما بالتناوب يولّد إشعارات مكررة وصناديق بريد مزدحمة.
- **W8 — لا إعادة محاولة (retry) ولا backoff في أي طبقة شبكة.** كل `requests.get` بمحاولة واحدة فقط؛ تعطّل مؤقت (5xx، timeout) يُسقط مصدراً كاملاً لدورة كاملة.
- **W9 — تباين في عقد الإرجاع.** `fetch_page` يُعيد `None` (ade_crawler.py:25، ona_crawler.py:49) أو `""` (smart_crawler.py:84) أو يرمي؛ المتصلون يفحصون بطرق مختلفة (`if html` مقابل `if not html`).
- **W10 — إزالة التكرار بالعنوان فقط.** `main.py:57` يبني `dict` بمفتاح `title`، فتصطدم مناقصتان مختلفتان من جهتين لهما العنوان نفسه وتُحذف إحداهما بصمت.
- **W11 — سباق SELECT-then-INSERT في `add_tender`.** database.py:85-118: فحص ثم إدراج في اتصالين منفصلين؛ تشغيلان متزامنان يُنتجان `IntegrityError` على `fingerprint UNIQUE`. الحل: `INSERT ... ON CONFLICT DO UPDATE`.

### متوسطة

- **W12 — تضارب إعدادات السجل.** `logging.basicConfig` يُستدعى في `main.py:37` و`base_crawler.py:3` و`run_smart_scraper.py:20`، بينما `setup_logging` (main.py:98) يتولّى اللوجنة فعلياً؛ أول `basicConfig` يفوز ويبتلع الباقي.
- **W13 — استخدام `logging` الجذري داخل الكرولرز** (`logging.error(...)` في ade_crawler.py:24، ona_crawler.py:48، algeria_tenders_crawler.py:61) بدل `logger = logging.getLogger(__name__)`؛ يتعذّر توجيه سجل كرولر بعينه.
- **W14 — `build_excel_report` يكتب دائماً `tenders_results.xlsx`** (excel_report.py:24) فيفصلreports متتالية، ويعيد `None` رغم التصريح `-> str` (سطر 24 vs 28). لا مسار إخراج في `AppConfig`.
- **W15 — تكرار الكود بين الكرولرز.** `normalize_text` مكرر حرفياً في 3 ملفات، والقوائم في 4 ملفات بطول من 9 إلى 55 كلمة مفتاحية، مع تناقضات: `"نابيب"` (smart_crawler.py:38)، `"انابيب"` بلا همزة (algeria_tenders_crawler.py:39) مقابل `"أنابيب"` elsewhere.
- **W16 — تباين جودة الإخراج بين الكرولرز.** `ade_crawler.parse_tenders` يُنتج حقلي `title`/`date` فقط (ade_crawler.py:38-43) بينما بقية الكرولرز تُنتج 7 حقول؛ الحقول الناقصة تصبح `NaN` في تقرير Excel.
- **W17 — لا تحقق من مدخلات HTTP** كما تشترط AGENTS.md (Pydantic/zod): مخرجات كل كرولر `dict` خام بلا مخطط. AGENTS.md بند 9.
- **W18 — تبعيات في `requirements.txt` غير مستخدمة** (flask, gunicorn، lxml) Meanwhile المشروع CLI؛ و`pytest` غير مثبّت في البيئة (فشل `python -m pytest`: `No module named pytest`) رغم أن `pyproject.toml:14` يعرّف pytest.

---

## 4. التقييم (/10)

| المحور | الدرجة | التبرير المختصر |
|--------|-------:|-----------------|
| جودة الكود (Code Quality) | **5** | بنية طبقية سليمة وواجهات مجرّدة جيدة (S1)، لكن تكرار في 4 ملفات (W15)، غياب type hints في كل الكرولرز contrary لـ PEP 8/strict style في AGENTS.md، وتعارض عقد إرجاع (W9)، وحقل مفقود في كرولر (W16). |
| معالجة الأخطاء (Error Handling) | **4** | `except Exception` عارٍ في كل الكرولرز و`telegram_notifier.py:28,41` يبتلع السبب دون نوعه؛ لا retry/backoff (W8)؛ لا logging لـ `traceback`؛ الأخطاء لا تُترجم إلى حالة pipeline واضحة؛ فشل الإرسال لا يوقف loop (main.py:135-136) فيُعلّم كمُرسَل حتى لو فشل. |
| الأمان (Security) | **4** | لا أسرار في الكود (التزام AGENTS.md بند 8 ✓)، لكن `verify=False` في موضعين مع تعطيل التحذيرات (W6)، التوكن داخل URL قد يُسجَّل عبر سجلات HTTP الوسيطة، لا masking للتوكن في الأخطاء، لا rate-limiting على تلغرام، ولا تحقق من مدخلات HTTP (W17). |
| التوثيق (Documentation) | **6** | كل ملف عام يحمل docstring عربي واضح، و`NotificationChannel`/`AppConfig` موثّقة جيداً؛ لكن `base_crawler.py` لا يوثّق العقد (لا 어떤 حقول تُعاد؟)، و`README.md` يتوقف عند السطر 29 (بنية المشروع واستخدامها غير موثّقة)، ولا دليل نشر/تشغيل مجدول. |
| قابلية الصيانة (Maintainability) | **4** | مساران تنافسيان على نفس الجدول (W7)، طبقة توافق `storage/db.py` بـ 7 ألقاب تحذيرية لنفس الدالة (db.py:52-78)، تضارب logging (W12)، قوائم كلمات مفتاحية غير مُدارة مركزياً (W15)، وصفر اختبارات للكرولرز والإشعارات. |

**المتوسط العام: 4.6 / 10**

---

## 5. المهام التطويرية مرتبة بالأولوية

### P0 — إصلاحات تمنع التشغيل الخاطئ (شرط الإنتاج)

| # | المهمة | الحل الملموس | ساعات | المتطلبات المسبقة |
|---|--------|---------------|------:|-----------------|
| **T1** | إصلاح دورة حياة التخزين | في `main.py.run()`: بعد اختيار `new_or_changed` وحصول الإرسال، استدعِ `store.save_many(new_or_changed)` (أو `add_tender` لكل عنصر) **قبل** `mark_notified`؛ واستبدل استدعاء `mark_notified` بـ `store.mark_sent(tender)` الموجود في `storage/db.py:28` حتى يضمن الإدراج والترقيم معاً. أضف `tests/test_main.py::test_run_persists_new_tenders` يثبت أن `save_many` تُستدعى وأن `is_new_or_changed` تُعيد `False` في الدورة الثانية. | 4 | — |
| **T2** | إصلاح انهيار التوكن | احذف استدعاء `os.environ[...]` من `build_notifier` (main.py:71-72) وغيّر التوقيع إلى `build_notifier(config: AppConfig)` مع `token = config.telegram_bot_token or ""`، وأضف في `config.py` التحقق: يقرأ `AppConfig` قيم `dry_run=True` أو نقص التوكن → `notifier = None` بدل رفع الاستثناء. أضف اختباراً لـ `build_notifier` عند غياب كل المتغيرات. | 3 | T1 |
| **T3** | وسم البيانات المرجعية وإيقافها | أضف `"is_sample": True` و`"source_status": "reference"` لكل عنصر في البيانات المرجعية الثلاثة، وحجبها في `main.py.apply_filter` (أو خطوة `drop_reference_data`) ما لم تكن `INCLUDE_SAMPLES=true`. البديل الأنظف: نقلها إلى `data/samples.json` واستدعاؤها فقط عبر `--demo`. اختبار: `test_sample_tenders_are_excluded`. | 4 | T1 |
| **T4** | إصلاح التطبيع العربي | أنشئ `crawlers/text_utils.py` بدالة `normalize_for_match(text)` ترجّع **نموذجين**: `latin` (NFD + ascii ignore، للاستعمال الفرنسي) و`arabic` (تطبيع الهمزات والتاء المربوطة/alef forms بلا حذف). في `ONACrawler.run` (ona_crawler.py:58-62) قارن النصوص العربية على النموذج العربي. اختبار: عنوان عربي فيه `"أنابيب"` يجب أن يُطابق. | 5 | — |
| **T5** | تفعيل `verify` وإلغاء التعتيم | احذف `verify=False` من `algeria_tenders_crawler.py:57` و`smart_crawler.py:79`، واحذف سطري `urllib3.disable_warnings`. إن كان موقع فعلاً يحمل شهادة معطوبة، استثنِه في قائمة صريحة `INSECURE_HOSTS` في `config.py` بدل تعطيل التحقق عالمياً. | 2 | — |
| **T6** | إصلاح HTML في تلغرام | أضف `html.escape()` على كل نص يُدمج في الرسالة (العناوين في `build_summary_message` main.py:92، و`run_smart_scraper.py:92`) أو بدّل `parse_mode` إلى `None` وحذف وسوم `<b>`. اختر مسار الهروب لأنه يحافظ على التنسيق. اختبار: عنوان يحوي `<` و`&` يُهرَّب في المخرجات. | 2 | — |

**مجموع P0: 20 ساعة**

### P1 — متطلبات الإنتاج (الموثوقية والملاحظة)

| # | المهمة | الحل الملموس | ساعات | المتطلبات المسبقة |
|---|--------|---------------|------:|-----------------|
| **T7** | طبقة HTTP مشتركة بإعادة محاولة | أنشئ `crawlers/http_client.py`: `fetch(url) -> str` باستخدام `requests.Session` مع `urllib3.util.Retry(total=3, backoff_factor=0.8, status_forcelist=[429,500,502,503,504])`، ومهلة موحّدة، و`raise_for_status()`. حدّث الكرولرز الأربعة لاستخدامه وإلغاء دوالها المتكررة. | 6 | T5 |
| **T8** | توحيد عقد الكرولر والتحقق من المخرجات | أضف `models.py` بـ dataclass `Tender` و`TenderField` Pydantic (يلزم بند 9 في AGENTS.md): `title`, `organisation`, `wilaya`, `product`, `deadline`, `status`, `link`, `is_sample=False`. كل `run()` يُعيد `list[Tender]`، و`main.py`/`excel_report.py` يتعاملان مع النموذج. يُغلق W16 ويجعل `is_new_or_changed` يعتمد على حقول مؤكدة. | 8 | T3, T4 |
| **T9** | توحيد الكلمات المفتاحية والتطبيع | أنشئ `data/keywords.json` واحداً (مصدر واحد للحقيقة) يحمّله `SmartCrawler` وكل الكرولرز عبر `sources/loader.py`-نمط قائم، ويصلح `"نابيب"`→`"أنابيب"` و`"انابيب"`→`"أنابيب"`. اختبار: كل كرولر يستخدم نفس المجموعة. | 3 | T4 |
| **T10** | جدولة ومراقبة | أضف `scheduler.py` بمجدول يومي (cron: `0 7 * * *`) مع `--once` للاختبار، واحترام `Retry-After` من تلغرام، وفحص صحة عبر `db.stats()` في نهاية كل دورة. موثّق في README. | 5 | T1, T7 |
| **T11** | تغطية اختبارات للكرولرز والإشعارات | اختبار لكل كرولر عبر `responses` أو `unittest.mock` على `requests.get` مع HTML في `tests/fixtures/*.html`: ADE (استخراج `div.tender-item`)، ONA (تطابق عربي ولاتيني)، algeriamarches (تحويل نسبي بـ `urljoin`، استبعاد `javascript:`)، smart crawler. اختبار `ExcelWriter` على أنماط أعمدة وهمية، واختبار `NotificationManager.broadcast` عند فشل قناة. | 8 | T8 |

**مجموع P1: 30 ساعة**

### P2 — الجودة والتوزيع

| # | المهمة | الحل الملموس | ساعات | المتطلبات المسبقة |
|---|--------|---------------|------:|-----------------|
| **T12** | توحيد logging وإزالة التكرار | احذف `basicConfig` من `base_crawler.py:3` و`main.py:37` و`run_smart_scraper.py:20`؛ استبدل `logging.error(...)` بـ `logger = logging.getLogger(__name__)` في الكرولرز الأربعة؛ فعّل handler في `logging_config.py` فقط. | 3 | T1 |
| **T13** | دمج المسارين التنفيذيين | احذف `run_smart_scraper.py` كمسار مستقل، أو حوّله إلى غلاف رفيع يستدعي `main.run()` مع قائمة مصادر من `SourcesLoader` — مسار واحد، جدول واحد، إشعار واحد لكل مناقصة. | 4 | T1, T9 |
| **T14** | مسار إ出力 للتقارير وإصلاح العقد | أضف `report_dir` إلى `AppConfig`، واجعل `build_excel_report` يُعيد `str` دائماً (وليس `None`)، ويكتب باسم مؤرّخ، ويفصل تقرير المناقصات عن ورقة إحصائية بـ `db.stats()`. | 3 | T1 |
| **T15** | CI وتدقيق التبعيات | `.github/workflows/ci.yml`: `ruff check` + `ruff format --check` + `mypy` + `pytest` على Python 3.11/3.12. ثبّت `pytest` و`ruff` و`mypy` في `requirements-dev.txt` (مفقودة/غير مثبّتة). احذف flask/gunicorn/lxml غير المستخدمة أو انقلها لـ `requirements-web.txt`. فحص Snyk قبل كل إضافة (بند 10 في AGENTS.md). | 5 | T11 |
| **T16** | إكمال التوثيق | أكمل `README.md` بعد السطر 29: شجرة المشروع، متغيرات البيئة كاملة، أمثلة تشغيل، نموذج `Tender`، سياسة إعادة المحاولة، وضع DRY_RUN. حدّثه مع كل تغيير في الواجهات العامة (بند 18 في AGENTS.md). | 3 | T8, T10 |

**مجموع P2: 18 ساعة**

---

## 6. خارطة زمنية مقترحة

| المرحلة | المحتوى | الساعات التراكمية |
|---------|---------|-------------------:|
| **أسبوع 1** | T1, T2, T3, T5, T6 (إصلاحات حرجة) | 15 |
| **أسبوع 2** | T4, T7, T12 (التطبيع العربي + طبقة HTTP + logging) | 14 → 29 |
| **أسبوع 3** | T8, T9, T11 (النموذج، الكلمات، الاختبارات) | 19 → 48 |
| **أسبوع 4** | T10, T13, T14 (الجدولة، الدمج، التقارير) | 12 → 60 |
| **أسبوع 5** | T15, T16 (CI، التوثيق) | 8 → 68 |

**الحد الأدنى للإنتاج: 48 ساعة** (T1–T11). ما بعد ذلك تحسين نوعي.

---

## 7. معايير قبول "جاهز للإنتاج"

- [ ] `python main.py` بدون `TELEGRAM_BOT_TOKEN` لا ينهار (T2)
- [ ] دورة ثانية لا تُنتج أي إشعار مكرر (T1)
- [ ] لا تُرسل أي مناقصة موسومة `is_sample` للمستخدم (T3)
- [ ] لا يوجد `verify=False` ولا `disable_warnings` في الشيفرة (T5)
- [ ] كلمات مفتاحية عربية تُطابق فعلياً في `ONACrawler` (T4)
- [ ] `pytest` يمرّ محلياً وفي CI، ويغطي كل كرولر (T11, T15)
- [ ] `ruff` و`mypy` نظيفان على `main.py`, `crawlers/`, `notifications/`, `storage/` (T15)
- [ ] ملف Excel يُبنى في مسار قابل للتهيئة، و`build_excel_report` يُعيد `str` دائماً (T14)