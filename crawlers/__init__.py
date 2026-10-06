from .ade_crawler import ADECrawler
from .algeria_tenders_crawler import AlgeriaTendersCrawler
from .base_crawler import BaseCrawler
from .google_news_crawler import GoogleNewsCrawler
from .marches_publics_auth_crawler import MarchesPublicsAuthCrawler
from .marches_publics_crawler import MarchesPublicsCrawler
from .ona_crawler import ONACrawler
from .safqatic_crawler import SafqaticCrawler

__all__ = [
    "BaseCrawler",
    "ADECrawler",
    "ONACrawler",
    "AlgeriaTendersCrawler",
    "GoogleNewsCrawler",
    "MarchesPublicsAuthCrawler",
    "MarchesPublicsCrawler",
    "SafqaticCrawler",
]
