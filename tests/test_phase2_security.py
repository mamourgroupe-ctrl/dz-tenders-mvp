"""Security hardening: verified TLS, atomic tender inserts, headers, limits."""

from __future__ import annotations

import re
import threading
from pathlib import Path

import pytest
from sqlalchemy import func, select

import crawlers.http as crawler_http
from crawlers.http import verify_setting
from storage.database import TenderDatabase
from webapp.models import ContactMessage


@pytest.fixture(autouse=True)
def _clean_tls_env(monkeypatch):
    """Every test starts with the documented secure defaults."""
    for name in [key for key in __import__("os").environ if key.startswith("CRAWLER_")]:
        monkeypatch.delenv(name, raising=False)
    crawler_http._warned_sources.clear()


def _scan_crawlers() -> list[tuple[Path, int, str]]:
    offenders: list[tuple[Path, int, str]] = []
    for path in sorted(Path("crawlers").glob("*.py")):
        if path.name == "http.py":
            continue  # documents the historical risk in its docstring
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if "verify=False" in line or "disable_warnings" in line:
                offenders.append((path, number, line.strip()))
    return offenders


def test_no_crawler_disables_tls_verification() -> None:
    offenders = _scan_crawlers()
    assert offenders == [], f"insecure TLS calls remain: {offenders}"


def test_crawler_http_module_does_not_filter_warnings() -> None:
    source = Path("crawlers/http.py").read_text(encoding="utf-8")
    assert "disable_warnings" not in source
    assert "filterwarnings" not in source


def test_verification_is_enabled_by_default() -> None:
    assert verify_setting() is True
    assert verify_setting("algeria_tenders") is True


def test_ca_bundle_is_honoured(monkeypatch) -> None:
    monkeypatch.setenv("CRAWLER_CA_BUNDLE", "/etc/ssl/private-ca.pem")
    assert verify_setting() == "/etc/ssl/private-ca.pem"


def test_per_source_opt_out(monkeypatch) -> None:
    monkeypatch.setenv("CRAWLER_VERIFY_SSL_SMART_CRAWLER", "false")
    # The source name is normalised: smart-crawler -> SMART_CRAWLER.
    assert verify_setting("smart-crawler") is False
    assert verify_setting("another_source") is True


def test_global_switch(monkeypatch) -> None:
    monkeypatch.setenv("CRAWLER_VERIFY_SSL", "false")
    assert verify_setting() is False
    monkeypatch.setenv("CRAWLER_VERIFY_SSL", "true")
    assert verify_setting() is True


def test_crawler_get_passes_verify(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_get(url, **kwargs):
        captured.update(url=url, **kwargs)
        return object()

    monkeypatch.setattr(crawler_http.requests, "get", fake_get)
    crawler_http.get("https://example.dz", source="ade", headers={"A": "b"}, timeout=5)
    assert captured["verify"] is True
    assert captured["timeout"] == 5


def test_parallel_inserts_keep_one_row(tmp_path) -> None:
    """The old SELECT-then-INSERT lost this race and raised IntegrityError."""
    db = TenderDatabase(str(tmp_path / "legacy.db"))
    tender = {
        "title": "مناقصة أنابيب",
        "organisation": "ADE",
        "wilaya": "الجزائر",
        "link": "https://example.dz/t/1",
    }
    results: list[bool] = []
    errors: list[BaseException] = []
    barrier = threading.Barrier(8)

    def worker() -> None:
        try:
            barrier.wait(timeout=5)
            results.append(db.add_tender(dict(tender)))
        except BaseException as exc:  # pragma: no cover - failure path
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    assert errors == []
    assert results.count(True) == 1
    with db._connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM tenders").fetchone()[0] == 1


def test_duplicate_insert_refreshes_last_seen(tmp_path) -> None:
    db = TenderDatabase(str(tmp_path / "dupes.db"))
    tender = {
        "title": "خزانات",
        "organisation": "ONA",
        "link": "https://example.dz/t/2",
    }
    assert db.add_tender(dict(tender)) is True
    assert db.add_tender(dict(tender)) is False
    with db._connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM tenders").fetchone()[0] == 1


def test_web_responses_carry_security_headers(client, seeded) -> None:
    for path in ("/", "/annonces", "/contact", "/connexion"):
        response = client.get(path)
        assert response.headers["X-Content-Type-Options"] == "nosniff"
        assert response.headers["X-Frame-Options"] == "DENY"
        assert "default-src 'self'" in response.headers["Content-Security-Policy"]
        assert response.headers["Permissions-Policy"]
        assert response.headers["Cross-Origin-Opener-Policy"] == "same-origin"


def test_search_rate_limit(client, settings, seeded) -> None:
    limit = settings.search_rate_limit
    for _ in range(limit):
        assert client.get("/annonces", params={"q": "مناقصة"}).status_code == 200
    throttled = client.get("/annonces", params={"q": "مناقصة"})
    assert throttled.status_code == 429
    assert "محاولات كثيرة" in throttled.text
    # An empty query is not throttled.
    assert client.get("/annonces").status_code == 200


def test_archive_browsing_is_rate_limited(client, settings, seeded) -> None:
    for _ in range(settings.search_rate_limit):
        assert client.get("/archives").status_code == 200
    throttled = client.get("/archives")
    assert throttled.status_code == 429
    assert "محاولات كثيرة" in throttled.text


def test_contact_form_stores_message(client, seeded) -> None:
    client.get("/contact")
    token = client.cookies.get("dz_csrf")
    response = client.post(
        "/contact",
        data={
            "csrf_token": token,
            "name": "أمين بوزيد",
            "email": "amine@example.dz",
            "phone": "0555 12 34 56",
            "subject": "استفسار عن الاشتراك",
            "message": "أريد معرفة تفاصيل صيغة الذهب والقطاعات المشمولة.",
        },
    )
    assert response.status_code == 200
    assert "تم إرسال رسالتك" in response.text
    message = seeded.scalar(select(ContactMessage))
    assert message is not None
    assert message.email == "amine@example.dz"
    assert message.phone == "+213555123456"
    assert message.ip_hash and len(message.ip_hash) == 64


def test_contact_form_requires_csrf(client, seeded) -> None:
    response = client.post(
        "/contact",
        data={
            "name": "أمين",
            "email": "amine@example.dz",
            "message": "رسالة بدون رمز الحماية.",
        },
    )
    assert response.status_code == 400
    assert seeded.scalar(select(func.count(ContactMessage.id))) == 0


@pytest.mark.parametrize(
    "payload,expected",
    [
        ({"name": "أ", "email": "a@b.dz", "message": "رسالة صالحة للاختبار"}, "الاسم"),
        ({"name": "أمين", "email": "not-an-email", "message": "رسالة صالحة"}, "البريد"),
        (
            {
                "name": "أمين",
                "email": "a@b.dz",
                "phone": "12",
                "message": "رسالة صالحة",
            },
            "الهاتف",
        ),
        ({"name": "أمين", "email": "a@b.dz", "message": "قصيرة"}, "الرسالة"),
    ],
)
def test_contact_form_validation(client, seeded, payload, expected) -> None:
    client.get("/contact")
    token = client.cookies.get("dz_csrf")
    response = client.post("/contact", data={"csrf_token": token, **payload})
    assert response.status_code == 400
    assert expected in response.text
    assert seeded.scalar(select(func.count(ContactMessage.id))) == 0


def test_contact_rate_limit(client, settings, seeded) -> None:
    client.get("/contact")
    token = client.cookies.get("dz_csrf")
    payload = {
        "csrf_token": token,
        "name": "أمين بوزيد",
        "email": "amine@example.dz",
        "message": "رسالة اختبار ضمن حدّ المعدل المسموح.",
    }
    for _ in range(settings.contact_rate_limit):
        assert client.post("/contact", data=payload).status_code == 200
    throttled = client.post("/contact", data=payload)
    assert throttled.status_code == 429
    assert (
        seeded.scalar(select(func.count(ContactMessage.id)))
        == settings.contact_rate_limit
    )


def test_contact_honeypot_is_silently_ignored(client, seeded) -> None:
    client.get("/contact")
    token = client.cookies.get("dz_csrf")
    response = client.post(
        "/contact",
        data={
            "csrf_token": token,
            "website": "https://spam.example",
            "name": "بوت",
            "email": "bot@example.dz",
            "message": "رسالة مزعجة أطول من عشرة أحرف.",
        },
    )
    assert response.status_code == 200
    assert seeded.scalar(select(func.count(ContactMessage.id))) == 0


def test_api_security_headers(tmp_path) -> None:
    from fastapi.testclient import TestClient

    from api.main import create_app

    db = TenderDatabase(str(tmp_path / "api.db"))
    db.add_tender({"title": "T", "organisation": "O", "link": "https://example.dz/1"})
    with TestClient(create_app(db_path=str(tmp_path / "api.db"))) as client:
        response = client.get("/health")
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["Content-Security-Policy"].startswith("default-src 'none'")
    assert response.headers["Referrer-Policy"] == "no-referrer"


def test_contact_message_table_has_indexes() -> None:
    from webapp.models import ContactMessage as Model

    index_columns = {
        tuple(column.name for column in index.columns)
        for index in Model.__table__.indexes
    }
    assert any("created_at" in columns for columns in index_columns)


def test_no_hardcoded_secret_like_literals() -> None:
    """Cheap guard against committing real credentials."""
    pattern = re.compile(
        r"(sk_live_|AKIA[0-9A-Z]{16}|-----BEGIN [A-Z ]*PRIVATE KEY-----)"
    )
    hits = [
        path
        for path in list(Path("webapp").rglob("*.py"))
        + list(Path("crawlers").rglob("*.py"))
        if pattern.search(path.read_text(encoding="utf-8"))
    ]
    assert hits == []
