# Contrax

Check any contractor quote against public records and local prices — verdict, red flags, contractor research, and a ready-to-send counter-offer.

- **Frontend**: static HTML/CSS/JS (landing page, upload flow, report viewer). No framework, no build step.
- **Backend**: FastAPI + SQLite + Stripe + the Claude API.

## Run locally

```sh
cd backend
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env            # fill in keys (see below)
.venv/bin/uvicorn app.main:app --port 8080
# open http://localhost:8080
```

The backend serves the frontend too — one process, one port. With the default `.env` (`SKIP_PAYMENTS=true`, `MOCK_ANALYSIS=true`) the entire flow works with **no keys at all**: upload on `/check.html`, get a canned report on `/report.html`.

## Configuration & secrets

All secrets live in `backend/.env` (gitignored). See [backend/.env.example](backend/.env.example).

| Variable | Purpose |
|---|---|
| `ANTHROPIC_API_KEY` | Powers the analysis pipeline. Set `MOCK_ANALYSIS=false` once provided. |
| `STRIPE_SECRET_KEY` | Stripe Checkout. Set `SKIP_PAYMENTS=false` once provided. |
| `STRIPE_WEBHOOK_SECRET` | Verifies `checkout.session.completed`. Local dev: `stripe listen --forward-to localhost:8080/api/stripe/webhook` |
| `BASE_URL` | Public URL, used in Stripe redirect links. |
| `REPORT_PRICE_CENTS` | Price per report (default 1900 = $19). |

Never commit `backend/.env` or `js/config.js`.

## How a report happens

```
POST /api/quotes (photo/PDF/text + zip + trade)
  └─ SKIP_PAYMENTS ? analyze now : Stripe Checkout → webhook marks paid → analyze
analysis pipeline (backend/app/analyzer.py):
  1. extract  — Claude reads the document into structured JSON (vision/PDF)
  2. rules    — deterministic red flags in code (deposit %, license, scope…)
  3. research — Claude + web_search checks license records, complaints, local prices
  4. compose  — Claude writes the report + counter-offer against a strict JSON schema
GET /api/reports/{id} — poll until status=complete
```

Every uploaded quote is stored (`backend/data/`) — that accumulating dataset of real
quotes by trade/zip is the long-term moat.

## API

| Endpoint | Purpose |
|---|---|
| `GET /api/health` | Config sanity check |
| `POST /api/quotes` | multipart: `file` and/or `quote_text`, `zip_code`, `trade`, `email` |
| `GET /api/reports/{id}` | Status + report JSON when complete |
| `POST /api/stripe/webhook` | Stripe events |
| `POST /api/waitlist` | `{email}` |

## Deploy

Any host that runs a Python process (Railway, Render, Fly.io, a VPS). Set the env vars from `.env.example`, run `uvicorn app.main:app --host 0.0.0.0 --port $PORT --app-dir backend`, and point the Stripe webhook at `/api/stripe/webhook`. SQLite is fine for v1; swap for Postgres when volume demands it.

Before real users: set `SKIP_PAYMENTS=false`, `MOCK_ANALYSIS=false`, add rate limiting, and configure the waitlist (`js/config.js`, template in [js/config.example.js](js/config.example.js) — or point `WAITLIST_ENDPOINT` at `/api/waitlist`).

## Notes

- Example figures on the landing page are illustrative.
- Reports state pricing information, not legal or professional advice.
