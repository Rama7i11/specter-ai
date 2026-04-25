# SPECTER-AI Voice Listener

## Wake Word

**Fallback (demo default): `hey_jarvis`**  
Uses OpenWakeWord's bundled pretrained ONNX model. No training, no account, no cloud.  
Say **"Hey Jarvis"** to activate Specter AI.

**Preferred: custom `hey_specter_ai` model**  
If `voice/hey_specter_ai.onnx` exists, the listener loads it automatically and
switches the activation phrase to **"Hey Specter AI"**. The fallback is still
detected as a secondary path so the demo always works.

Training a custom model takes ~2 hours on Google Colab. See:
  https://github.com/dscripka/openWakeWord#custom-models

---

## Flow

```
Mic (16 kHz, mono, int16)
  │
  ▼ continuous 80 ms chunks
OpenWakeWord (hey_jarvis / hey_specter_ai)
  │  score > 0.5
  ▼
Gemini Live API  ←→  gemini-2.0-flash-live-001  (bidirectional PCM over WebSocket)
  │
  ├── Audio out → Speaker (24 kHz PCM)
  │
  └── Tool call: execute_defensive_command(N)
        │
        ▼
      POST http://localhost:8000/voice/command
        {"command": N, "args": {...}}
```

---

## Voice Commands

Say the wake word, wait for the session-open confirmation, then:

| You say | Gemini calls | Backend action |
|---------|-------------|----------------|
| "Run command one" | `execute_defensive_command(1)` | Block last attacker IP |
| "Run command one, IP 1.2.3.4" | `execute_defensive_command(1, ip="1.2.3.4")` | Block specific IP |
| "Run command two" | `execute_defensive_command(2)` | Clear all IP blocks |
| "Run command three" | `execute_defensive_command(3)` | Speak status report |

---

## Windows Setup

### 1. Install Python 3.11+ and run the helper script

```powershell
.\scripts\start-voice.ps1
```

### 2. PortAudio (required by sounddevice)

`sounddevice` on Windows needs PortAudio. The start script tries `pipwin` automatically.
If that fails, install the wheel manually:

```powershell
pip install pipwin
pipwin install pyaudio
```

Or download a pre-built wheel from:
  https://www.lfd.uci.edu/~gohlke/pythonlibs/#pyaudio

### 3. Selecting the right microphone

List devices:
```powershell
cd voice
.\.venv\Scripts\Activate.ps1
python -c "import sounddevice as sd; print(sd.query_devices())"
```

If your headset is not the default device, add to `.env`:
```
SOUNDDEVICE_INDEX=3   # replace with your device number
```

Then in `listener.py`, pass `device=int(os.getenv("SOUNDDEVICE_INDEX", -1))` to
`sd.InputStream`. (`-1` means system default.)

### 4. Windows mic permissions

If PortAudio opens but returns silence:
- Settings → Privacy → Microphone → allow app access
- In some setups, running as Administrator resolves permission issues

### 5. OpenWakeWord first-run download

OWW downloads ONNX model weights on first run (~10 MB). Ensure internet access
the first time, then works offline.

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `sounddevice.PortAudioError` | Install PortAudio via pipwin (see above) |
| `[ERROR] GEMINI_API_KEY not set` | Add key to repo-root `.env` |
| Wake word never fires | Lower `WAKE_THRESHOLD` in listener.py (try `0.3`) |
| Gemini session error 404 | Wrong model name — check `GEMINI_LIVE_MODEL` in `.env` |
| Audio playback garbled | Wrong sample rate — Gemini outputs 24 kHz; `PLAYBACK_RATE` must match |
| `[WARN] Model not in model list` | API key may lack Live API access; verify in Google AI Studio |
