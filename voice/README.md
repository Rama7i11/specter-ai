# Voice — OpenWakeWord + Gemini Live Bridge

## Wake Word

**Default (demo fallback):** `hey_jarvis` — uses the pre-trained ONNX model bundled
with OpenWakeWord. No account, no training, no cloud required.

**Preferred:** A custom `hey_specter_ai` model can be trained with OpenWakeWord's
training pipeline (see https://github.com/dscripka/openWakeWord#custom-models).
If a file named `hey_specter_ai.onnx` is present in this directory, the listener
loads it automatically. Otherwise it falls back to `hey_jarvis` and logs a warning.

## Audio Requirements

- Microphone: any device recognized by PyAudio (16kHz, mono, 16-bit PCM)
- Speaker/headphones: default output device
- Tested on Windows 11 with USB headset

## Flow

```
Mic ──16kHz PCM──▶ OpenWakeWord
                        │ wake detected
                        ▼
              WebSocket → backend /voice/live
                        │
              backend ──▶ Gemini Live API (gemini-2.0-flash-live-001)
                        │
              Gemini audio response ──▶ headphones
```

## Dependencies

```
pip install openwakeword pyaudio websockets numpy
```

PyAudio on Windows often needs the binary wheel:
```
pip install pipwin && pipwin install pyaudio
```

## Running

```powershell
cd voice
python listener.py
```

Say "Hey Specter AI" (or "Hey Jarvis" if using fallback) to activate.
The listener prints `[WAKE]` when triggered and `[END]` when Gemini finishes responding.
