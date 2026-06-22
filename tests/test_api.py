"""
SignalDeck — API Tests
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

import pytest
from fastapi.testclient import TestClient
from main import app, Base, engine, SessionLocal, generate_events

client = TestClient(app)

@pytest.fixture(autouse=True)
def clean_db():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)


class TestRoot:
    def test_root(self):
        r = client.get("/")
        assert r.status_code == 200
        assert r.json()["app"] == "SignalDeck"


class TestIngest:
    def test_ingest_event(self):
        r = client.post("/api/events/ingest", json={"event_type": "page_view", "user_id": "u1", "properties": {}})
        assert r.status_code == 200
        assert r.json()["ok"] is True

    def test_ingest_multiple(self):
        for i in range(10):
            client.post("/api/events/ingest", json={"event_type": "page_view", "user_id": f"u{i}"})
        r = client.get("/api/dashboard/summary")
        assert r.json()["total_events"] == 10


class TestSeed:
    def test_seed(self):
        r = client.post("/api/seed")
        assert r.status_code == 200
        assert r.json()["ok"] is True
        # Second seed should skip
        r2 = client.post("/api/seed")
        assert "Already has" in r2.json()["message"]


class TestDashboard:
    def test_summary(self):
        db = SessionLocal()
        generate_events(db, 100)
        db.close()
        r = client.get("/api/dashboard/summary")
        assert r.status_code == 200
        data = r.json()
        assert data["total_events"] == 100
        assert "unique_users" in data
        assert "conversion_rate" in data
        assert "top_pages" in data

    def test_timeseries(self):
        db = SessionLocal()
        generate_events(db, 50)
        db.close()
        r = client.get("/api/dashboard/timeseries?event_type=page_view&days=30")
        assert r.status_code == 200
        data = r.json()
        assert len(data) > 0
        assert all("date" in d and "count" in d for d in data)

    def test_funnel(self):
        db = SessionLocal()
        generate_events(db, 200)
        db.close()
        r = client.get("/api/dashboard/funnel")
        assert r.status_code == 200
        data = r.json()
        assert len(data) == 3
        assert data[0]["step"] == "page_view"

    def test_events_by_type(self):
        db = SessionLocal()
        generate_events(db, 100)
        db.close()
        r = client.get("/api/dashboard/events-by-type")
        assert r.status_code == 200
        data = r.json()
        assert sum(data.values()) == 100

    def test_realtime(self):
        client.post("/api/events/ingest", json={"event_type": "page_view", "user_id": "u1"})
        r = client.get("/api/dashboard/realtime")
        assert r.status_code == 200
        assert len(r.json()) > 0


class TestAlerts:
    def test_create_alert(self):
        r = client.post("/api/alerts", json={"name": "Test Alert", "metric": "events_per_hour", "condition": "lt", "threshold": 5})
        assert r.status_code == 200
        assert r.json()["id"] > 0

    def test_get_alerts(self):
        client.post("/api/alerts", json={"name": "Low events", "metric": "events_per_hour", "condition": "lt", "threshold": 1})
        r = client.get("/api/alerts")
        assert r.status_code == 200
        data = r.json()
        assert len(data["rules"]) > 0
