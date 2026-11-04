"""Crawler for BAOSEM public tender listings."""

from .public_tender_crawler import PublicTenderCrawler, run_cli

BASE_URL = "https://baosem.com/site/appels-doffres/"


class BAOSEMCrawler(PublicTenderCrawler):
    """Fetch and parse publicly visible BAOSEM tender listings."""

    def __init__(self):
        """Initialize the crawler with the BAOSEM listing URL."""
        super().__init__(BASE_URL, "BAOSEM")


def main(argv: list[str] | None = None) -> int:
    """Run the BAOSEM command-line crawler."""
    return run_cli(BAOSEMCrawler, argv)


if __name__ == "__main__":
    raise SystemExit(main())
