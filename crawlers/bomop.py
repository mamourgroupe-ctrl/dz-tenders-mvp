"""Crawler for BOMOP public tender listings."""

from .public_tender_crawler import PublicTenderCrawler, run_cli

BASE_URL = "https://bomop.anep.dz/"


class BOMOPCrawler(PublicTenderCrawler):
    """Fetch and parse publicly visible BOMOP tender listings."""

    def __init__(self):
        """Initialize the crawler with the BOMOP home URL."""
        super().__init__(BASE_URL, "BOMOP")


def main(argv: list[str] | None = None) -> int:
    """Run the BOMOP command-line crawler."""
    return run_cli(BOMOPCrawler, argv)


if __name__ == "__main__":
    raise SystemExit(main())
