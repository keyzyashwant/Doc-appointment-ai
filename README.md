# Doctor Appointment AI

A voice-enabled appointment desk for a multi-specialty clinic. Reception staff can check doctor availability, book appointments, and cancel them from a browser dashboard. The frontend handles the call and live status; the FastAPI backend owns scheduling rules and data.

## Architecture

```text
Browser microphone / speaker
	<-> SmallWebRTC transport (/api/offer)
	<-> Pipecat voice pipeline
			 Incoming audio: ElevenLabs Realtime STT
				 -> Google Gemini (model selected by GEMINI_MODEL)
				 -> availability / booking / cancellation tools
				 -> services -> repositories -> SQLite
			 Outgoing response: Gemini -> ElevenLabs TTS
				 -> Pipecat -> SmallWebRTC -> browser speaker

Committed appointment events -> event bus -> WebSocket -> dashboard
```

The LLM calls voice tools; it does not access the database. Tools call services, where business rules live. Repositories contain database queries. Booking atomically claims an available slot and creates the appointment; cancellation releases the slot.

The LLM provider is Google Gemini via Pipecat's `GoogleLLMService`. Its exact model ID is configured with `GEMINI_MODEL`. This workspace currently uses `gemini-3.5-flash-lite`; the safe environment template selects `gemini-2.5-flash`. Change the variable to a model available to your Google AI Studio project.

## Requirements

- Python 3.12 and [uv](https://docs.astral.sh/uv/)
- Node.js and npm (Node 22 LTS recommended)
- Browser microphone access for voice calls
- ElevenLabs and Google AI Studio accounts for live voice and Gemini

## Backend Setup

From the repository root, create `backend/.env` and set the variables listed under [Configuration](#configuration). A local `backend/.env.example` may be copied as a starting point if available. The current `.gitignore` excludes that example file, so a fresh clone may not contain it. Do not put credentials in source control.

PowerShell:

```powershell
cd backend
uv sync --extra dev
uv run uvicorn app.main:app --reload
```

The API listens at `http://127.0.0.1:8000`. Startup validates the voice-provider configuration, creates SQLite tables, and seeds sample doctors and slots when the database has no doctors.

## Frontend Setup

In a second terminal from the repository root:

```powershell
cd frontend
npm ci
npm run dev
```

Open the Vite URL printed in the terminal, usually `http://localhost:5173`. The dev server proxies `/api` and `/ws` to `http://127.0.0.1:8000`; set `VITE_BACKEND_URL` if the backend runs elsewhere. Browsers require microphone permission; localhost is treated as a secure context for development.

## Configuration

Set these variables in `backend/.env`. The README and example template intentionally contain no provider credentials.

| Variable | Required | Purpose and where to get it |
| --- | --- | --- |
| `ELEVENLABS_API_KEY` | Yes | Secret used by realtime STT and TTS. Create it in [ElevenLabs API key settings](https://elevenlabs.io/app/settings/api-keys). |
| `GOOGLE_API_KEY` | Yes | Secret for Gemini API access. Create one in [Google AI Studio](https://aistudio.google.com/app/apikey). |
| `GEMINI_MODEL` | Yes | Gemini model ID, not a credential. Use a model enabled for your project; see [Gemini models](https://ai.google.dev/gemini-api/docs/models). The template uses `gemini-2.5-flash`. |
| `ELEVENLABS_VOICE_ID` | Yes | Voice identifier, not an API key. Choose a voice from the [ElevenLabs Voice Library](https://elevenlabs.io/voice-library) and use its ID. |
| `ELEVENLABS_TTS_MODEL` | No | ElevenLabs TTS model ID; the application default is `eleven_flash_v2_5`. Select a supported model from [ElevenLabs model documentation](https://elevenlabs.io/docs/models). |
| `DATABASE_URL` | No | SQLAlchemy database URL. Defaults to `sqlite:///./doctor_appointment.db`, stored in `backend/`. |
| `CORS_ORIGINS` | No | JSON list of allowed frontend origins. Defaults to localhost ports 5173. |
| `TIMEZONE` | No | Present in the example for clarity; clinic scheduling currently uses `Asia/Kolkata` in code and does not read this setting. |
| `LOG_LEVEL` | No | Present in the example, but not currently loaded from settings; logging uses its code default. |

The application refuses startup when `ELEVENLABS_API_KEY`, `ELEVENLABS_VOICE_ID`, `GOOGLE_API_KEY`, or `GEMINI_MODEL` is missing. Keep real credentials only in the ignored local `.env` file and rotate any credential that has been exposed.

## Tests and Checks

From the repository root:

```powershell
cd backend
uv run pytest
```

Frontend typecheck and production build:

```powershell
cd frontend
npm run build
```

## Known Limitations

- SQLite and `create_all` are intended for local development; there is no migration workflow or production database configuration included.
- Seed data is inserted only when there are no doctor records. Adding a doctor manually prevents the seed routine from filling other sample doctors or slots.
- The seed schedule is a short demo horizon of 30-minute slots, not a live clinic calendar integration.
- Caller identity is a spoken phone number. There is no account login or SMS ownership verification; `phone_confirmed` is supplied by the voice agent.
- A phone number can have only one active appointment.
- The assistant handles scheduling only, not medical advice. Provider credentials, quotas, browser permissions, network access, and supported model availability are required for live calls.
