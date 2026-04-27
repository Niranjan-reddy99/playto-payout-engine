# Playto Payout Engine

A production-grade financial backend with a React dashboard. Built to demonstrate: ledger-based accounting, concurrent overdraft prevention via PostgreSQL row locks, idempotent payouts via a two-layer Redis+DB strategy, and a state-machine-enforced payout lifecycle processed by Celery workers.

---

## Prerequisites

- Docker & Docker Compose
- Python 3.11+ (for local dev)
- Node 18+ (for local frontend dev)

---

## Quick Start (Docker)

> **Note:** Docker Compose uses ports 8001 (API), 5175 (frontend), 5433 (Postgres), 6380 (Redis) to avoid conflicts with other local services.

```bash
git clone <repo>
cd playto-payout-engine

# Start all 5 services (api, worker, beat, db, redis, frontend)
docker-compose up --build

# In a second terminal — run migrations and seed data
docker-compose exec api python manage.py migrate
docker-compose exec api python manage.py seed_data
```

Open http://localhost:5175 — sign in with any seeded credential below.

---

## Manual Local Setup

### Backend

```bash
cd backend
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# Requires a running Postgres and Redis
export DATABASE_URL=postgresql://postgres:postgres@localhost:5432/playto
export REDIS_URL=redis://localhost:6379/0

python manage.py migrate
python manage.py seed_data

# Terminal 1: API
python manage.py runserver 8001

# Terminal 2: Celery worker
celery -A playto worker -l info

# Terminal 3: Celery beat (scheduled tasks)
celery -A playto beat -l info --scheduler django_celery_beat.schedulers:DatabaseScheduler
```

### Frontend

```bash
cd frontend
npm install
VITE_API_URL=http://localhost:8001 npm run dev
```

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/balance/` | Merchant's available, held, total balance |
| GET | `/api/v1/payouts/` | List last 50 payouts |
| POST | `/api/v1/payouts/` | Create a payout (requires `Idempotency-Key` header) |
| GET | `/api/v1/payouts/<uuid>/` | Get a single payout |
| GET | `/api/v1/ledger/` | Last 100 ledger entries |

Authentication: Django session auth. Use `/api-auth/login/` to authenticate.

**Example payout request:**
```bash
curl -X POST http://localhost:8001/api/v1/payouts/ \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: $(uuidgen)" \
  -b "sessionid=<your-session>" \
  -d '{"amount_paise": 50000, "bank_account_id": "HDFC_SAVINGS_001"}'
```

---

## Test Credentials

Seeded by `python manage.py seed_data`:

| Username | Password | Starting balance |
|----------|----------|-----------------|
| acme_merchant | testpass123 | ~₹3,750 available |
| byte_merchant | testpass123 | ~₹4,550 available |
| nova_merchant | testpass123 | ~₹2,950 available |

---

## Running Tests

```bash
cd backend
source venv/bin/activate

# Idempotency tests (SQLite, no external services needed)
DATABASE_URL=sqlite:///./test.db python manage.py test payouts.tests.test_idempotency --verbosity=2

# Concurrency tests (requires PostgreSQL — run via Docker)
docker-compose exec api python manage.py test payouts.tests.test_concurrency --verbosity=2

# All tests via Docker
docker-compose exec api python manage.py test payouts.tests --verbosity=2
```

---

## Architecture Notes

See `EXPLAINER.md` for a deep-dive on the lock strategy, ledger design, and idempotency approach.
