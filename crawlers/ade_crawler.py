import requests
from bs4 import BeautifulSoup
from .base_crawler import BaseCrawler
import logging

class ADECrawler(BaseCrawler):
    """
    كلاس خاص بجلب المناقصات من موقع ADE (Algérienne Des Eaux).
    """
    def __init__(self, base_url="https://www.ade.dz"):
        super().__init__(base_url)

    def fetch_page(self, url):
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            response = requests.get(url, headers=headers, timeout=15)
            response.raise_for_status()
            return response.text
        except requests.RequestException as e:
            logging.error(f"خطأ أثناء الاتصال بالموقع {url}: {e}")
            return None

    def parse_tenders(self, html_content):
        if not html_content:
            return []

        soup = BeautifulSoup(html_content, 'html.parser')
        tenders = []

        for item in soup.find_all('div', class_='tender-item'):
            title_elem = item.find('h3') or item.find('a')
            date_elem = item.find('span', class_='date')
            
            tenders.append({
                'title': title_elem.text.strip() if title_elem else 'بدون عنوان',
                'date': date_elem.text.strip() if date_elem else 'غير محدد'
            })

        return tenders

    def run(self):
        logging.info(f"بدء عملية جلب المناقصات من: {self.base_url}")
        html = self.fetch_page(self.base_url)
        if html:
            results = self.parse_tenders(html)
            logging.info(f"تم استخراج {len(results)} مناقصة بنجاح.")
            return results
        
        logging.warning("لم يتم الحصول على أي بيانات.")
        return []