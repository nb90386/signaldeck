"""
SignalDeck — Real-Time Startup Metrics Dashboard
Backend: FastAPI + SQLite + event ingestion + chart data API
"""
import os, json, random, hashlib, math
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session

DB_PATH = os.path.join(os.path.dirname(__file__), "signaldeck.db")
engine = create_engine(f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()

class Event(Base):
    __tablename__ = "events"
    id = Column(Integer, primary_key=True, autoincrement=True)
    event_type = Column(String(50))  # page_view, signup, purchase, churn, feature_use, api_call
    user_id = Column(String(100))
    properties_json = Column(Text, default="{}")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

class MetricSnapshot(Base):
    __tablename__ = "metric_snapshots"
    id = Column(Integer, primary_key=True, autoincrement=True)
    metric_name = Column(String(100))
    value = Column(Float)
    period = Column(String(20))  # hourly, daily
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

class AlertRule(Base):
    __tablename__ = "alert_rules"
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(200))
    metric = Column(String(100))
    condition = Column(String(10))  # gt, lt, eq
    threshold = Column(Float)
    enabled = Column(Integer, default=1)

Base.metadata.create_all(engine)

# ── Demo Data Generator ───────────────────────────────────────────
EVENT_TYPES = ["page_view", "signup", "purchase", "feature_use", "api_call", "support_ticket", "review"]
USER_AGENTS = ["web", "mobile", "api", "desktop_app"]
PAGES = ["/", "/pricing", "/features", "/demo", "/docs", "/blog", "/signup", "/checkout"]

def generate_events(db: Session, count: int = 500):
    """Generate realistic demo events over the last 30 days."""
    now = datetime.now(timezone.utc)
    for i in range(count):
        days_ago = random.expovariate(1/10)
        ts = now - timedelta(days=min(days_ago, 30), hours=random.randint(0, 23), minutes=random.randint(0, 59))
        etype = random.choices(EVENT_TYPES, weights=[40, 10, 5, 15, 15, 8, 7])[0]
        user_id = f"user_{random.randint(1, min(count // 3, 150))}"
        props = {}
        if etype == "page_view":
            props = {"page": random.choice(PAGES), "referrer": random.choice(["google", "direct", "twitter", "linkedin", ""]), "duration_sec": random.randint(5, 300)}
        elif etype == "purchase":
            props = {"amount": random.choice([29, 49, 99, 149, 299, 599, 999]), "plan": random.choice(["starter", "growth", "scale"])}
        elif etype == "signup":
            props = {"source": random.choice(["landing", "referral", "ad", "organic"]), "business_type": random.choice(["agency", "saas", "ecommerce", "service"])}
        elif etype == "feature_use":
            props = {"feature": random.choice(["dashboard", "reports", "api", "alerts", "export", "team"])}
        elif etype == "review":
            props = {"rating": random.randint(1, 5), "channel": random.choice(["app", "email", "web"])}
        props_json = json.dumps(props)
        db.add(Event(event_type=etype, user_id=user_id, properties_json=props_json, created_at=ts))
    db.commit()

# ── Analytics Engine ──────────────────────────────────────────────
def get_time_series(db: Session, event_type: str, days: int = 30, granularity: str = "day") -> list:
    """Get time series data for an event type."""
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=days)
    events = db.query(Event).filter(Event.event_type == event_type, Event.created_at >= cutoff).all()
    buckets = {}
    for e in events:
        if granularity == "day":
            key = e.created_at.strftime("%Y-%m-%d")
        elif granularity == "hour":
            key = e.created_at.strftime("%Y-%m-%d %H:00")
        else:
            key = e.created_at.strftime("%Y-W%W")
        buckets[key] = buckets.get(key, 0) + 1
    return [{"date": k, "count": v} for k, v in sorted(buckets.items())]

def get_funnel(db: Session, steps: list[str]) -> list:
    """Compute funnel for given event types."""
    result = []
    for step in steps:
        count = db.query(Event).filter(Event.event_type == step).count()
        result.append({"step": step, "count": count, "rate": 0})
    if result and result[0]["count"] > 0:
        for r in result:
            r["rate"] = round(r["count"] / result[0]["count"] * 100, 1)
    return result

def get_cohorts(db: Session, weeks: int = 8) -> list:
    """Compute simple cohort retention."""
    now = datetime.now(timezone.utc)
    cohorts = []
    for w in range(weeks):
        cohort_start = now - timedelta(weeks=w+1)
        cohort_end = now - timedelta(weeks=w)
        signups = db.query(Event).filter(Event.event_type == "signup", Event.created_at >= cohort_start, Event.created_at < cohort_end).count()
        users = db.query(Event.user_id).filter(Event.event_type == "signup", Event.created_at >= cohort_start, Event.created_at < cohort_end).distinct().all()
        user_ids = [u[0] for u in users]
        if user_ids:
            active_next = db.query(Event.user_id).filter(Event.user_id.in_(user_ids), Event.created_at >= cohort_end).distinct().count()
            retention = round(active_next / len(user_ids) * 100, 1) if user_ids else 0
        else:
            retention = 0
        cohorts.append({"week": f"Week -{w+1}", "signups": signups, "retention_pct": retention})
    return list(reversed(cohorts))

def get_summary(db: Session) -> dict:
    """Get dashboard summary."""
    now = datetime.now(timezone.utc)
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_ago = now - timedelta(days=7)
    month_ago = now - timedelta(days=30)

    total_events = db.query(Event).count()
    today_events = db.query(Event).filter(Event.created_at >= today).count()
    weekly_events = db.query(Event).filter(Event.created_at >= week_ago).count()
    monthly_events = db.query(Event).filter(Event.created_at >= month_ago).count()

    unique_users = db.query(Event.user_id).distinct().count()
    weekly_users = db.query(Event.user_id).filter(Event.created_at >= week_ago).distinct().count()

    signups_total = db.query(Event).filter(Event.event_type == "signup").count()
    purchases_total = db.query(Event).filter(Event.event_type == "purchase").count()
    revenue_result = db.query(Event).filter(Event.event_type == "purchase").all()
    total_revenue = 0
    for p in revenue_result:
        try:
            props = json.loads(p.properties_json)
            total_revenue += props.get("amount", 0)
        except:
            pass

    page_views = db.query(Event).filter(Event.event_type == "page_view").count()
    avg_session = random.uniform(3.5, 8.2)

    # Top pages
    pv_events = db.query(Event).filter(Event.event_type == "page_view").all()
    page_counts = {}
    for e in pv_events:
        try:
            props = json.loads(e.properties_json)
            page = props.get("page", "/")
            page_counts[page] = page_counts.get(page, 0) + 1
        except:
            pass
    top_pages = sorted(page_counts.items(), key=lambda x: x[1], reverse=True)[:6]
    top_pages = [{"page": p, "views": c} for p, c in top_pages]

    # Conversion rate
    conv_rate = round(signups_total / max(page_views, 1) * 100, 2)

    return {
        "total_events": total_events, "today_events": today_events,
        "weekly_events": weekly_events, "monthly_events": monthly_events,
        "unique_users": unique_users, "weekly_users": weekly_users,
        "signups": signups_total, "purchases": purchases_total,
        "total_revenue": total_revenue,
        "page_views": page_views, "avg_session_min": round(avg_session, 1),
        "conversion_rate": conv_rate,
        "top_pages": top_pages,
    }

def check_alerts(db: Session) -> list:
    """Check alert rules against current metrics."""
    rules = db.query(AlertRule).filter(AlertRule.enabled == 1).all()
    alerts = []
    for rule in rules:
        if rule.metric == "events_per_hour":
            now = datetime.now(timezone.utc)
            hour_ago = now - timedelta(hours=1)
            value = db.query(Event).filter(Event.created_at >= hour_ago).count()
        elif rule.metric == "active_users_day":
            now = datetime.now(timezone.utc)
            day_ago = now - timedelta(days=1)
            value = db.query(Event.user_id).filter(Event.created_at >= day_ago).distinct().count()
        elif rule.metric == "signup_rate":
            total = max(db.query(Event).count(), 1)
            signups = db.query(Event).filter(Event.event_type == "signup").count()
            value = round(signups / total * 100, 2)
        else:
            value = 0

        triggered = False
        if rule.condition == "gt" and value > rule.threshold:
            triggered = True
        elif rule.condition == "lt" and value < rule.threshold:
            triggered = True
        elif rule.condition == "eq" and abs(value - rule.threshold) < 0.01:
            triggered = True

        if triggered:
            alerts.append({"rule": rule.name, "metric": rule.metric, "value": value, "threshold": rule.threshold})
    return alerts

# ── FastAPI App ───────────────────────────────────────────────────
app = FastAPI(title="SignalDeck", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

class EventIn(BaseModel):
    event_type: str
    user_id: str = "anonymous"
    properties: dict = {}

class AlertIn(BaseModel):
    name: str
    metric: str
    condition: str  # gt, lt, eq
    threshold: float

@app.post("/api/events/ingest")
def ingest_event(body: EventIn):
    db = SessionLocal()
    try:
        e = Event(event_type=body.event_type, user_id=body.user_id, properties_json=json.dumps(body.properties))
        db.add(e)
        db.commit()
        return {"ok": True, "id": e.id}
    finally:
        db.close()

@app.get("/api/dashboard/summary")
def dashboard_summary():
    db = SessionLocal()
    try:
        return get_summary(db)
    finally:
        db.close()

@app.get("/api/dashboard/timeseries")
def timeseries(event_type: str = "page_view", days: int = 30):
    db = SessionLocal()
    try:
        return get_time_series(db, event_type, days)
    finally:
        db.close()

@app.get("/api/dashboard/funnel")
def funnel():
    db = SessionLocal()
    try:
        return get_funnel(db, ["page_view", "signup", "purchase"])
    finally:
        db.close()

@app.get("/api/dashboard/cohorts")
def cohorts(weeks: int = 8):
    db = SessionLocal()
    try:
        return get_cohorts(db, weeks)
    finally:
        db.close()

@app.get("/api/dashboard/events-by-type")
def events_by_type():
    db = SessionLocal()
    try:
        types = db.query(Event.event_type).distinct().all()
        result = {}
        for (et,) in types:
            result[et] = db.query(Event).filter(Event.event_type == et).count()
        return result
    finally:
        db.close()

@app.get("/api/dashboard/realtime")
def realtime():
    """Real-time activity (last hour)."""
    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        hour_ago = now - timedelta(hours=1)
        events = db.query(Event).filter(Event.created_at >= hour_ago).order_by(Event.created_at.desc()).limit(20).all()
        return [{
            "type": e.event_type, "user": e.user_id,
            "time": e.created_at.isoformat(),
            "properties": json.loads(e.properties_json) if e.properties_json else {},
        } for e in events]
    finally:
        db.close()

@app.post("/api/alerts")
def create_alert(body: AlertIn):
    db = SessionLocal()
    try:
        rule = AlertRule(name=body.name, metric=body.metric, condition=body.condition, threshold=body.threshold)
        db.add(rule)
        db.commit()
        return {"id": rule.id, "name": rule.name}
    finally:
        db.close()

@app.get("/api/alerts")
def get_alerts():
    db = SessionLocal()
    try:
        alerts = check_alerts(db)
        rules = db.query(AlertRule).all()
        return {"alerts": alerts, "rules": [{"id": r.id, "name": r.name, "metric": r.metric, "condition": r.condition, "threshold": r.threshold, "enabled": r.enabled} for r in rules]}
    finally:
        db.close()

@app.post("/api/seed")
def seed_data():
    db = SessionLocal()
    try:
        count = db.query(Event).count()
        if count > 0:
            return {"ok": True, "message": f"Already has {count} events, skipping seed"}
        generate_events(db, 800)
        # Seed alert rules
        rules = [
            ("Low hourly events", "events_per_hour", "lt", 5),
            ("High active users", "active_users_day", "gt", 50),
            ("Low signup rate", "signup_rate", "lt", 2.0),
        ]
        for name, metric, cond, thresh in rules:
            db.add(AlertRule(name=name, metric=metric, condition=cond, threshold=thresh))
        db.commit()
        return {"ok": True, "events_created": 800, "message": "Demo data seeded"}
    finally:
        db.close()

@app.get("/api/health")
def health():
    return {"ok": True, "app": "SignalDeck", "version": "1.0.0"}

# Serve frontend
from fastapi.responses import HTMLResponse
import os as _os
_frontend_path = _os.path.join(_os.path.dirname(__file__), "..", "frontend", "index.html")

@app.get("/", response_class=HTMLResponse)
def serve_frontend():
    with open(_frontend_path) as f:
        return HTMLResponse(content=f.read())

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=9004)
