from pathlib import Path

from playwright.async_api import async_playwright


class BaseCrawler:
    def __init__(self, site_name: str):
        self.site_name = site_name
        # تحديد مسار حفظ الجلسة بناءً على اسم الموقع
        self.session_dir = Path("storage/auth")
        self.session_dir.mkdir(parents=True, exist_ok=True)
        self.session_file = self.session_dir / f"{self.site_name}_state.json"

    async def start_browser(self):
        self.playwright = await async_playwright().start()
        # تشغيل المتصفح (يمكن جعله headless=True في بيئة الإنتاج)
        self.browser = await self.playwright.chromium.launch(headless=False)

        # تحميل الجلسة إذا كانت موجودة
        if self.session_file.exists():
            print(f"✅ تم تحميل الجلسة المحفوظة لـ {self.site_name}")
            self.context = await self.browser.new_context(storage_state=str(self.session_file))
        else:
            print(f"⚠️ لا توجد جلسة لـ {self.site_name}، سيتم إنشاء جلسة جديدة.")
            self.context = await self.browser.new_context()

        self.page = await self.context.new_page()

    async def save_session(self):
        """حفظ الجلسة بعد تسجيل الدخول الناجح"""
        await self.context.storage_state(path=str(self.session_file))
        print(f"💾 تم حفظ الجلسة بنجاح في: {self.session_file}")

    async def close(self):
        await self.browser.close()
        await self.playwright.stop()


# مثال على كيفية الاستخدام في ملف ade_crawler.py
# class AdeCrawler(BaseCrawler):
#     def __init__(self):
#         super().__init__(site_name="ade") # سيحفظ الجلسة في storage/auth/ade_state.json
