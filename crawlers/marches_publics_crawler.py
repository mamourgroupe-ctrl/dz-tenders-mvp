import logging
from .base_crawler import BaseCrawler


class MarchesPublicsCrawler(BaseCrawler):
    """
    كرولر للمناقصات العمومية
    ملاحظة: الموقع الرسمي يستخدم Next.js (JavaScript) 
    لذا نعتمد حاليا على بيانات مرجعية.
    سنضيف Playwright في تحديث لاحق.
    """

    def __init__(self, base_url="https://www.marches-publics.gov.dz"):
        super().__init__(base_url)
        self.keywords = [
            'pvc', 'pehd', 'tuyau', 'conduite', 'raccord',
            'eau', 'assainissement', 'irrigation',
            'نابيب', 'مياه', 'قنوات', 'صرف', 'ري', 'خزانات'
        ]

    def run(self):
        logging.info("MarchesPublicsCrawler: بيانات مرجعية (الموقع يستخدم Next.js)")
        tenders = [{
            "title": "Fourniture de conduites PEHD pour adduction d'eau potable",
            "organisation": "وزارة الموارد المائية",
            "wilaya": "الجزائر",
            "product": "PEHD Pipes",
            "deadline": "2026-10-30",
            "status": "مفتوحة",
            "link": "https://www.marches-publics.gov.dz"
        }]
        logging.info(f"تم العثور على {len(tenders)} مناقصة.")
        return tenders
