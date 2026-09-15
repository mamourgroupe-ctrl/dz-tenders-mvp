"""
sources/loader.py
Load and query sources from data/sources_master.json
"""

import json
import os
import logging
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)

DEFAULT_FILE = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    "data", "sources_master.json"
)


class SourcesLoader:
    """Load and query tender sources"""

    def __init__(self, sources_file: str = DEFAULT_FILE):
        self.sources_file = sources_file
        self.sources = self._load()
        logger.info(f"Loaded {len(self.sources)} sources")

    def _load(self) -> List[Dict]:
        try:
            with open(self.sources_file, encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError:
            logger.error(f"Not found: {self.sources_file}")
            return []

    def by_priority(self, priority: str) -> List[Dict]:
        return [s for s in self.sources if str(s.get("pri")) == str(priority)]

    def by_category(self, category: str) -> List[Dict]:
        return [s for s in self.sources if s.get("cat") == category]

    def by_wilaya(self, wilaya: str) -> List[Dict]:
        return [s for s in self.sources if wilaya in str(s.get("w", ""))]

    def crawlable(self, priority: Optional[str] = None) -> List[Dict]:
        """Return sources not blocked from server"""
        sources = self.by_priority(priority) if priority else self.sources
        blocked = {"live_but_blocked_from_sandbox", "unreachable_from_this_host"}
        return [s for s in sources if s.get("st") not in blocked]

    def with_tender_page(self, priority: Optional[str] = None) -> List[Dict]:
        sources = self.by_priority(priority) if priority else self.sources
        return [s for s in sources if s.get("tp")]

    def stats(self) -> Dict:
        by_pri, by_cat, by_st = {}, {}, {}
        for s in self.sources:
            by_pri[str(s.get("pri"))] = by_pri.get(str(s.get("pri")), 0) + 1
            by_cat[s.get("cat")] = by_cat.get(s.get("cat"), 0) + 1
            by_st[s.get("st")] = by_st.get(s.get("st"), 0) + 1

        return {
            "total": len(self.sources),
            "by_priority": by_pri,
            "by_category": by_cat,
            "by_status": by_st,
            "with_tender_page": sum(1 for s in self.sources if s.get("tp")),
        }


if __name__ == "__main__":
    import json as j
    loader = SourcesLoader()
    print(j.dumps(loader.stats(), ensure_ascii=False, indent=2))
