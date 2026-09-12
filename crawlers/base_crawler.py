import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class BaseCrawler:
    """
    الكلاس الأساسي (Base Class) لجميع الكرولرز في المشروع
    """
    def __init__(self, base_url):
        self.base_url = base_url

    def fetch_page(self, url):
        raise NotImplementedError("يجب تطبيق هذه الدالة في الكلاس الفرعي")

    def parse_tenders(self, html_content):
        raise NotImplementedError("يجب تطبيق هذه الدالة في الكلاس الفرعي")

    def run(self):
        raise NotImplementedError("يجب تطبيق هذه الدالة في الكلاس الفرعي")