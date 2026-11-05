# Playbook: كيفية إضافة مصدر مناقصات (Crawler) جديد
> اتبع هذه الخطوات بالترتيب. لا تتجاوز أي خطوة.
> المرجع الأساسي للكود هو `crawlers/base_crawler.py`.

1. **التحقق من المتطلبات:**
   - هل الموقع يحتاج تسجيل دخول؟ إذا نعم، استخدم نمط `marches_publics_auth_crawler.py` وادعم `MARCHES_STATE_PATH`.
   - هل الموقع يحتوي على API؟ إذا نعم، استخدم `httpx` بدلاً من Playwright.
2. **إنشاء الملف:**
   - أنشئ ملفاً في `crawlers/` باسم `[source_name]_crawler.py`.
   - اجعل الكلاس يرث من `BaseCrawler`.
   - عرّف `BASE_URL` و `SECTOR`.
3. **كتابة دالة التحليل:**
   - نفذ دالة `parse_tenders(html_or_json)` لاستخراج قائمة المناقصات.
   - أضف الفحوصات الأمنية (عدم تشغيل HTML/JS غير موثوق).
4. **الاختبارات (إجباري):**
   - أنشئ ملف اختبار في `tests/test_[source_name]_crawler.py`.
   - استخدم `fixtures` من مجلد `tests/fixtures/`. لا تتصل بالموقع الحقيقي أبداً في الاختبارات.
5. **التسجيل في الموزع:**
   - أضف الزاحف الجديد إلى `crawlers/smart_crawler.py` أو `main.py`.
6. **بوابة الجودة:**
   - شغّل `pytest tests/test_[source_name]_crawler.py -q`.
   - شغّل `ruff check .`.
7. **التسليم:**
   - اكتب في `docs/agents/HANDOFF.md` ما تم إنجازه.
   - ادفع الفرع وانتظر مراجعة Gemini.
