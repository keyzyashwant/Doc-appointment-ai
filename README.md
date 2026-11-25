# doctor-appointment-ai

Monorepo for a voice-assisted doctor appointment desk. The backend owns scheduling data. The frontend is a single reception dashboard. Voice and booking services are not implemented yet.

## Layout

- `backend/` — FastAPI, SQLAlchemy, SQLite
- `frontend/` — Vite, React, TypeScript, Tailwind

## Backend

Requires Python 3.12 and [uv](https://docs.astral.sh/uv/).

```bash
cd backend
copy .env.example .env
uv sync
uv run uvicorn app.main:app --reload
```

The API listens on `http://127.0.0.1:8000`. Startup creates tables and seeds doctors and slots. Seeding does nothing if doctors already exist.

## Frontend

```bash
cd frontend
npm install
npm run dev
```

The dev server proxies `/api` to the backend.

## Configuration

Copy `backend/.env.example` to `backend/.env`.

- `ELEVENLABS_API_KEY`
- `GOOGLE_API_KEY`
- `DATABASE_URL` (defaults to a SQLite file in `backend/`)
