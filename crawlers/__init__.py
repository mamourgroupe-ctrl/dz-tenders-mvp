from .ade_crawler import ADECrawler
from .algeria_tenders_crawler import AlgeriaTendersCrawler
from .base_crawler import BaseCrawler
from .marches_publics_crawler import MarchesPublicsCrawler
from .ona_crawler import ONACrawler

__all__ = [
    "BaseCrawler",
    "ADECrawler",
    "ONACrawler",
    "AlgeriaTendersCrawler",
    "MarchesPublicsCrawler",
]
