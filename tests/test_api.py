"""Tests for the read-only FastAPI backend (temporary synthetic DBs only)."""

import hashlib
import sqlite3
from datetime import date

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from api.mapping import products_from_text, row_to_tender
from api.models import ProductCode
from storage.database import TenderDatabase

TODAY = date(2026, 10, 13)

ROWS = [
    # title, organisation, wilaya, product, deadline, status, link, score, first_seen
    (
        "اقتناء أنابيب PVC لشبكة المياه",
        "ADE",
        "الجزائر",
        "PVC Pipes",
        "2026-10-20",
        "مفتوحة",
        "https://example.dz/1",
        90,
        "2026-10-12 10:00:00",
    ),
    (
        "Fourniture de tubes PEHD",
        "ONA",
        "وهران",
        "PEHD Pipes",
        "2026-10-15",
        "مفتوحة",
        "https://example.dz/2",
        75,
        "2026-10-12 09:00:00",
    ),
    (
        "Supply of plastic tanks",
        "SONATRACH",
        "ورقلة",
        "Plastic Tanks",
        "2026-09-01",
        "مفتوحة",
        "https://example.dz/3",
        40,
        "2026-10-01 08:00:00",
    ),
    (
        "أشغال أنابيب وخزانات",
        "ADE",
        "الجزائر",
        "أنابيب PVC/PEHD وخزانات",
        "2026-12-01",
        "غير محدد",
        "not-a-url",
        60,
        "2026-09-20 08:00:00",
    ),
]


def _make_db(path, rows=ROWS) -> str:
    TenderDatabase(db_path=str(path))  # real project schema initialization
    conn = sqlite3.connect(path)
    for index, row in enumerate(rows, start=1):
        conn.execute(
            """
            INSERT INTO tenders (
                fingerprint, title, organisation, wilaya, product, deadline,
                status, link, relevance_score, matched_families, first_seen, last_seen
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, '', ?, ?)
            """,
            (f"fp{index}", *row, row[-1]),
        )
    conn.commit()
    conn.close()
    return str(path)


@pytest.fixture()
def client(tmp_path):
    db = _make_db(tmp_path / "test.db")
    app = create_app(db_path=db, today_provider=lambda: TODAY)
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture()
def empty_client(tmp_path):
    db = _make_db(tmp_path / "empty.db", rows=[])
    app = create_app(db_path=db, today_provider=lambda: TODAY)
    return TestClient(app, raise_server_exceptions=False)


# ── Health & database availability ──────────────────────────────────────────


def test_health_ok(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "available", "tenders": 4}
    assert client.get("/api/health").status_code == 200


def test_health_empty_database(empty_client):
    response = empty_client.get("/health")
    assert response.status_code == 200
    assert response.json()["tenders"] == 0


def test_missing_database_is_503_and_never_created(tmp_path):
    missing = tmp_path / "missing.db"
    app = create_app(db_path=str(missing), today_provider=lambda: TODAY)
    missing_client = TestClient(app, raise_server_exceptions=False)
    assert missing_client.get("/health").status_code == 503
    for path in ("/api/tenders", "/api/stats/summary", "/api/tenders/1"):
        response = missing_client.get(path)
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "database_unavailable"
        assert "message" in response.json()["error"]
    assert not missing.exists()


# ── Tender listing, mapping & contract ──────────────────────────────────────


def test_list_tenders_envelope_and_mapping(client):
    response = client.get("/api/tenders")
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"items", "total", "page", "pageSize", "pages"}
    assert body["total"] == 4 and body["page"] == 1 and body["pageSize"] == 20
    assert body["pages"] == 1
    first = body["items"][0]  # newest first_seen first
    assert set(first) == {
        "id",
        "titleAr",
        "titleFr",
        "organisation",
        "organisationShort",
        "wilaya",
        "deadline",
        "publicationDate",
        "products",
        "score",
        "priority",
        "status",
        "description",
        "source",
        "sourceUrl",
        "latitude",
        "longitude",
        "reference",
        "estimatedValue",
    }
    assert first["titleAr"] == "اقتناء أنابيب PVC لشبكة المياه"
    assert first["titleFr"] == ""  # Arabic title has no fabricated French twin
    assert first["products"] == ["PVC_PIPES"]
    assert first["score"] == 90 and first["priority"] == 1
    assert first["status"] == "closing_soon"  # deadline 7 days after TODAY
    assert first["publicationDate"] == "2026-10-12"
    assert first["sourceUrl"] == "https://example.dz/1"
    # Never fabricated from data the DB does not store.
    assert first["latitude"] is None and first["longitude"] is None
    assert first["estimatedValue"] is None and first["reference"] is None
    assert first["description"] is None and first["source"] is None


def test_mapping_latin_title_and_invalid_link(client):
    body = client.get("/api/tenders", params={"wilaya": "ورقلة"}).json()
    (item,) = body["items"]
    assert item["titleFr"] == "Supply of plastic tanks"
    assert item["titleAr"] == "Supply of plastic tanks"  # heading fallback
    assert item["products"] == ["PE_TANKS"]
    assert item["status"] == "closed"  # deadline before TODAY
    assert item["priority"] == 3

    body = client.get("/api/tenders", params={"search": "وخزانات"}).json()
    (mixed,) = body["items"]
    assert mixed["products"] == ["PVC_PIPES", "PEHD_PIPES", "PE_TANKS"]
    assert mixed["sourceUrl"] is None  # non-HTTP link is not exposed as URL


def test_get_tender_and_unknown_ids(client):
    assert client.get("/api/tenders/1").json()["id"] == "1"
    for unknown in ("9999", "abc", "1%20OR%201=1", "-1"):
        response = client.get(f"/api/tenders/{unknown}")
        assert response.status_code == 404, unknown
        assert response.json()["error"]["code"] == "not_found"


def test_frontend_contract_paths_and_fields(client):
    """OpenAPI exposes exactly the paths src/lib/api.ts calls."""
    paths = client.get("/openapi.json").json()["paths"]
    for path in (
        "/api/tenders",
        "/api/tenders/{tender_id}",
        "/api/stats/summary",
        "/api/stats/by-wilaya",
        "/api/stats/by-product",
        "/api/stats/timeline",
        "/health",
    ):
        assert path in paths


# ── Pagination & validation ─────────────────────────────────────────────────


def test_pagination_slicing_and_bounds(client):
    page1 = client.get("/api/tenders", params={"page": 1, "page_size": 2}).json()
    page2 = client.get("/api/tenders", params={"page": 2, "page_size": 2}).json()
    assert page1["pages"] == 2 and len(page1["items"]) == 2
    assert len(page2["items"]) == 2
    assert {i["id"] for i in page1["items"]}.isdisjoint({i["id"] for i in page2["items"]})
    beyond = client.get("/api/tenders", params={"page": 99, "page_size": 2}).json()
    assert beyond["items"] == [] and beyond["total"] == 4


@pytest.mark.parametrize(
    "params",
    [
        {"page": 0},
        {"page": -1},
        {"page_size": 0},
        {"page_size": 101},
        {"priority": 0},
        {"priority": 4},
        {"product": "BOGUS"},
        {"date_from": "13-10-2026"},
        {"date_from": "2026-10-20", "date_to": "2026-10-01"},
        {"search": "x" * 201},
    ],
)
def test_invalid_filters_return_consistent_422(client, params):
    response = client.get("/api/tenders", params=params)
    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "validation_error"
    assert body["error"]["details"]  # field-level detail without user input echo
    assert "x" * 50 not in response.text


def test_supported_filters(client):
    by_wilaya = client.get("/api/tenders", params={"wilaya": "الجزائر"}).json()
    assert by_wilaya["total"] == 2
    by_product = client.get("/api/tenders", params={"product": "PE_TANKS"}).json()
    assert by_product["total"] == 2
    by_priority = client.get("/api/tenders", params={"priority": 1}).json()
    assert by_priority["total"] == 1
    by_dates = client.get(
        "/api/tenders", params={"date_from": "2026-10-01", "date_to": "2026-10-31"}
    ).json()
    assert by_dates["total"] == 2
    by_search = client.get("/api/tenders", params={"search": "PEHD"}).json()
    assert by_search["total"] == 1  # title search, row 2


# ── Injection resistance & read-only behaviour ──────────────────────────────


def test_sql_injection_attempts_are_inert(client, tmp_path):
    for term in ("' OR 1=1 --", "%", "_", "'; DROP TABLE tenders; --"):
        response = client.get("/api/tenders", params={"search": term})
        assert response.status_code == 200
        assert response.json()["total"] == 0, term
    assert client.get("/api/tenders").json()["total"] == 4  # table intact


def test_api_requests_do_not_modify_database(client, tmp_path):
    db = tmp_path / "test.db"
    before = hashlib.sha256(db.read_bytes()).hexdigest()
    client.get("/api/tenders")
    client.get("/api/tenders/1")
    client.get("/api/stats/summary")
    client.post("/api/tenders", json={"title": "nope"})  # no write routes exist
    assert hashlib.sha256(db.read_bytes()).hexdigest() == before


def test_no_write_methods_on_tenders(client):
    for method in ("post", "put", "patch", "delete"):
        response = getattr(client, method)("/api/tenders")
        assert response.status_code in (404, 405)


# ── Empty database & statistics from fixture data ───────────────────────────


def test_empty_database_responses(empty_client):
    body = empty_client.get("/api/tenders").json()
    assert body == {"items": [], "total": 0, "page": 1, "pageSize": 20, "pages": 1}
    assert empty_client.get("/api/stats/summary").json() == {
        "total": 0,
        "active": 0,
        "priority1": 0,
        "priority2": 0,
        "priority3": 0,
        "change": 0.0,
    }
    assert empty_client.get("/api/stats/by-wilaya").json() == []
    products = empty_client.get("/api/stats/by-product").json()
    assert [point["count"] for point in products] == [0, 0, 0]
    timeline = empty_client.get("/api/stats/timeline").json()
    assert len(timeline) == 30 and all(point["tenders"] == 0 for point in timeline)


def test_statistics_from_fixture_data(client):
    summary = client.get("/api/stats/summary").json()
    assert summary["total"] == 4
    assert summary["active"] == 3  # one deadline in the past
    assert (summary["priority1"], summary["priority2"], summary["priority3"]) == (1, 1, 2)

    by_wilaya = client.get("/api/stats/by-wilaya").json()
    assert by_wilaya[0] == {"wilaya": "الجزائر", "count": 2, "percentage": 50}
    assert sum(point["count"] for point in by_wilaya) == 4

    by_product = client.get("/api/stats/by-product").json()
    assert [(p["product"], p["count"]) for p in by_product] == [
        ("PVC_PIPES", 2),
        ("PEHD_PIPES", 2),
        ("PE_TANKS", 2),
    ]
    assert by_product[0]["label"] == "أنابيب PVC"
    assert by_product[0]["color"] == "#1a5490"

    timeline = client.get("/api/stats/timeline").json()
    assert len(timeline) == 30
    assert timeline[-1]["date"] == "2026-10-13"
    counts = {point["date"]: point["tenders"] for point in timeline}
    assert counts["2026-10-12"] == 2 and counts["2026-10-01"] == 1
    assert sum(counts.values()) == 4  # all fixture rows are inside the window


# ── CORS ────────────────────────────────────────────────────────────────────


def test_cors_allows_configured_origin_without_credentials(tmp_path):
    db = _make_db(tmp_path / "cors.db", rows=[])
    app = create_app(
        db_path=db, cors_origins=["https://dashboard.example"], today_provider=lambda: TODAY
    )
    cors_client = TestClient(app, raise_server_exceptions=False)
    allowed = cors_client.get("/api/tenders", headers={"Origin": "https://dashboard.example"})
    assert allowed.headers["access-control-allow-origin"] == "https://dashboard.example"
    assert "access-control-allow-credentials" not in allowed.headers
    denied = cors_client.get("/api/tenders", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in denied.headers


# ── Pure mapping helpers ────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("PVC Pipes", [ProductCode.PVC_PIPES]),
        ("PEHD Pipes", [ProductCode.PEHD_PIPES]),
        ("Plastic Tanks", [ProductCode.PE_TANKS]),
        ("PE/PEHD/PVC", [ProductCode.PVC_PIPES, ProductCode.PEHD_PIPES]),
        ("FITTINGS", []),
        ("غير محدد", []),
        (None, []),
        ("", []),
    ],
)
def test_products_from_text(text, expected):
    assert products_from_text(text) == expected


def test_row_to_tender_handles_missing_fields():
    tender = row_to_tender({"id": 7, "title": "T", "first_seen": None}, TODAY)
    assert tender.id == "7"
    assert tender.deadline is None and tender.publicationDate == ""
    assert tender.products == [] and tender.score == 0 and tender.priority == 3
    assert tender.sourceUrl is None
