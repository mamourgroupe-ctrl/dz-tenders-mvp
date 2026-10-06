"""marches_login.py — Save authenticated session for marches-publics.gov.dz."""

from pathlib import Path

from playwright.sync_api import sync_playwright

STORAGE = Path("storage/marches_state.json")
STORAGE.parent.mkdir(parents=True, exist_ok=True)

SITE_URL = "https://marches-publics.gov.dz/"

print("=" * 70)
print("Marches Publics — Session Saver")
print("=" * 70)
print(f"1. A visible browser will open at: {SITE_URL}")
print("2. Log in manually with YOUR account.")
print("3. After you're fully logged in, come back here.")
print("4. Press ENTER to save the session.")
print()

with sync_playwright() as p:
    browser = p.chromium.launch(channel="msedge", headless=False)
    context = browser.new_context(ignore_https_errors=True)
    page = context.new_page()
    page.goto(SITE_URL, wait_until="domcontentloaded", timeout=60000)
    print("Browser opened. Please log in...")
    input("Press ENTER here once logged in... ")
    context.storage_state(path=str(STORAGE))
    print(f"\nSession saved: {STORAGE.resolve()}")
    print(f"Size: {STORAGE.stat().st_size} bytes")
    browser.close()
