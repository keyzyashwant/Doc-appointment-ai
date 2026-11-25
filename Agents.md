# doctor-appointment-ai

Monorepo: backend (FastAPI + Pipecat, SQLAlchemy 2.0 sync, SQLite, uv, Python 3.12)
and frontend (React + TS + Tailwind + Vite).

## Architecture (strict)
- Layers: API / voice tools -> services -> repositories -> models. The LLM never touches the DB;
  tools call services only. Services hold all business rules and raise domain exceptions with codes.
  Repositories contain queries only.
- Caller identity = phone number spoken aloud. No patient name, no login. Phones are strings,
  normalized in the service layer to +91XXXXXXXXXX.
- One active appointment per phone.
- Booking = one transaction: conditional slot UPDATE (status='available', check rowcount==1) + appointment insert.
  Cancel = mark appointment cancelled + release the slot.
- Voice tools return {ok, code, message, data}; they never raise to the LLM.
  book/cancel require phone_confirmed=true (the agent must read the number back first).
- Services publish events (appointment.booked / appointment.cancelled) after commit.

## Pipecat
Check current docs (docs.pipecat.ai) before writing pipeline code. Use settings=..., not deprecated params.
Transport: SmallWebRTC + Silero VAD + ElevenLabs realtime STT/TTS + Gemini.

## Conventions
Small files, no speculative abstractions, secrets only via .env (.env.example committed).
Run `uv run pytest` after backend changes.