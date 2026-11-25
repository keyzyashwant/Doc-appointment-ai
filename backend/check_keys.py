import os
import httpx
from dotenv import load_dotenv

load_dotenv()
g, m = os.getenv("GOOGLE_API_KEY"), os.getenv("GEMINI_MODEL")
e, v = os.getenv("ELEVENLABS_API_KEY"), os.getenv("ELEVENLABS_VOICE_ID")
print("present:", {"GOOGLE_API_KEY": bool(g), "GEMINI_MODEL": m, "ELEVENLABS_API_KEY": bool(e), "VOICE_ID": v})

r = httpx.post(
    f"https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent",
    headers={"x-goog-api-key": g or ""},
    json={"contents": [{"parts": [{"text": "Say hi"}]}]},
    timeout=30,
)
print("gemini:", r.status_code, r.text[:200])

r = httpx.post(
    f"https://api.elevenlabs.io/v1/text-to-speech/{v}",
    headers={"xi-api-key": e or ""},
    json={"text": "Hello", "model_id": "eleven_flash_v2_5"},
    timeout=30,
)
print("elevenlabs tts:", r.status_code, len(r.content), "" if r.status_code == 200 else r.text[:200])