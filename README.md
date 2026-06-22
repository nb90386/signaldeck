# SignalDeck — Real-Time Startup Metrics Dashboard

[![Tests](https://img.shields.io/badge/tests-11%2F11%20passing-brightgreen)]()
[![Python](https://img.shields.io/badge/python-3.13-blue)]()

A polished analytics dashboard with event ingestion, time series charts, conversion funnels, cohort analysis, and real-time activity feed.

## ✨ Features

| Feature | Description |
|---------|-------------|
| 📊 **KPI Cards** | Total events, users, signups, revenue, conversion rate |
| 📈 **Time Series** | Bar charts for events over 30 days |
| 🔄 **Conversion Funnel** | Page view → Signup → Purchase |
| 📊 **Event Breakdown** | Events by type with counts |
| ⚡ **Real-Time Feed** | Live activity stream (last hour) |
| 🔔 **Alert Rules** | Configurable threshold alerts |
| 📄 **Top Pages** | Most visited pages with share % |

## 🚀 Quick Start

```bash
cd project4-signal-deck/backend
pip install fastapi sqlalchemy pytest httpx
python main.py
# Open http://localhost:9004
# POST /api/seed to generate demo data
```

## 🧪 Tests

```bash
cd project4-signal-deck
pytest tests/ -v
# 11 tests, all passing
```

## 🛠️ Tech Stack

- **Backend**: Python 3.13, FastAPI, SQLAlchemy, SQLite
- **Frontend**: Vanilla JS, CSS bar charts, live refresh
- **Analytics**: Custom time series, funnel, cohort engine

## 📄 License

MIT
