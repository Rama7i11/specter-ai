"""
Specter Voice Listener
======================
Wake word : "Hey Jarvis" (OpenWakeWord pretrained ONNX — no cloud, no auth)
            Loads hey_specter_ai.onnx automatically if present. See README.md.
On wake   : Raw WebSocket → Gemini Live BidiGenerateContent endpoint.
            Mic (16 kHz PCM) → Gemini → speaker (24 kHz PCM).
            Gemini calls execute_defensive_command(N) which POSTs to backend.
Timeout   : 30 s with no messages from Gemini closes the session.

Protocol reference:
  wss://generativelanguage.googleapis.com/ws/
      google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContent
      ?key=<API_KEY>

  Frame 1 (client → server): {"setup": {...}}
  Subsequent client frames:  {"realtimeInput": {"mediaChunks": [{"mimeType": "audio/pcm;rate=16000", "data": "<b64>"}]}}
  Tool response frames:      {"toolResponse": {"functionResponses": [{"id": "...", "response": {...}}]}}
  Server frames:             {"setupComplete": {}}, {"serverContent": {...}}, {"toolCall": {...}}
"""

import asyncio
import base64
import json
import os
import queue as sync_queue
import sys
from pathlib import Path

import httpx
import numpy as np
import sounddevice as sd
import websockets
import websockets.exceptions
from dotenv import load_dotenv
from openwakeword.model import Model

# ── Config ──────────────────────────────────────────────────────────────────
_REPO_ROOT = Path(__file__).parent.parent
load_dotenv(dotenv_path=_REPO_ROOT / ".env")

GEMINI_API_KEY  = os.getenv("GEMINI_API_KEY", "")
BACKEND_URL     = os.getenv("BACKEND_URL", "http://localhost:8000")
GEMINI_MODEL    = os.getenv("GEMINI_LIVE_MODEL", "gemini-live-2.5-flash-native-audio")

MIC_RATE        = 16_000   # Hz  — what Gemini Live expects as input
PLAYBACK_RATE   = 24_000   # Hz  — Gemini Live audio output sample rate
CHANNELS        = 1
CHUNK_SAMPLES   = 1280     # 80 ms @ 16 kHz — OpenWakeWord's expected chunk size
WAKE_THRESHOLD  = 0.5
SILENCE_TIMEOUT = 30.0     # seconds of no Gemini messages → close session

_WS_ENDPOINT = (
    "wss://generativelanguage.googleapis.com/ws/"
    "google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContent"
)

SYSTEM_PROMPT = (
    "You are Specter, a defensive cybersecurity assistant for Team Aegis. "
    "Be terse and tactical. The user runs an active SOC. "
    "When the user says 'run command one', 'run command two', or 'run command three', "
    "immediately call execute_defensive_command with that number — no confirmation needed. "
    "After the function returns its result string, speak it back in one or two short sentences."
)

# ── Gemini session setup message ────────────────────────────────────────────
# Built once at import time; GEMINI_MODEL is already resolved from .env.
_SETUP_MSG: dict = {
    "setup": {
        "model": f"models/{GEMINI_MODEL}",
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {
                "voiceConfig": {
                    "prebuiltVoiceConfig": {"voiceName": "Aoede"}
                }
            },
        },
        "systemInstruction": {
            "parts": [{"text": SYSTEM_PROMPT}]
        },
        "tools": [
            {
                "functionDeclarations": [
                    {
                        "name": "execute_defensive_command",
                        "description": (
                            "Execute a Specter defensive action. "
                            "1 = block the attacker's IP address. "
                            "2 = reset all IP blocks (re-demo). "
                            "3 = speak a status report of recent alerts."
                        ),
                        "parameters": {
                            "type": "OBJECT",
                            "properties": {
                                "command": {
                                    "type": "INTEGER",
                                    "description": "1 (block IP), 2 (reset), or 3 (status report)",
                                },
                                "ip": {
                                    "type": "STRING",
                                    "description": (
                                        "IP address to block. "
                                        "Only required for command 1. "
                                        "Omit to let backend use the last alert IP."
                                    ),
                                },
                            },
                            "required": ["command"],
                        },
                    }
                ]
            }
        ],
    }
}

# ── Thread-safe mic queue ────────────────────────────────────────────────────
# sounddevice callback (audio thread) puts bytes here.
# Async send loop drains it and forwards to Gemini.
_mic_q: sync_queue.Queue[bytes] = sync_queue.Queue(maxsize=200)


def _mic_callback(indata: np.ndarray, frames: int, time_info, status) -> None:
    try:
        _mic_q.put_nowait(indata.tobytes())
    except sync_queue.Full:
        pass  # drop under back-pressure — never block the audio thread


# ── Backend call ─────────────────────────────────────────────────────────────
async def _call_backend(command: int, ip: str | None) -> str:
    payload: dict = {"command": command, "args": {"ip": ip} if ip else {}}
    try:
        async with httpx.AsyncClient() as client:
            r = await client.post(
                f"{BACKEND_URL}/voice/command", json=payload, timeout=5
            )
            return r.json().get("result", "Command executed.")
    except Exception as exc:  # noqa: BLE001
        return f"Backend error: {exc}"


# ── Audio playback (runs in executor so it doesn't block the event loop) ────
def _play_pcm_blocking(data: bytes) -> None:
    """Decode 16-bit LE PCM at PLAYBACK_RATE and play through default speaker."""
    samples = np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0
    sd.play(samples, samplerate=PLAYBACK_RATE, blocking=True)


async def _play_pcm(data: bytes) -> None:
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, _play_pcm_blocking, data)


# ── WebSocket send loop ──────────────────────────────────────────────────────
async def _send_loop(ws) -> None:
    """Drain _mic_q and forward PCM chunks to Gemini as base64 JSON frames."""
    while True:
        # Poll in 50 ms slices so CancelledError can interrupt cleanly
        chunk: bytes | None = None
        while chunk is None:
            try:
                chunk = _mic_q.get_nowait()
            except sync_queue.Empty:
                await asyncio.sleep(0.05)

        frame = {
            "realtimeInput": {
                "mediaChunks": [
                    {
                        "mimeType": "audio/pcm;rate=16000",
                        "data": base64.b64encode(chunk).decode("ascii"),
                    }
                ]
            }
        }
        await ws.send(json.dumps(frame))


# ── WebSocket receive loop ───────────────────────────────────────────────────
async def _receive_loop(ws) -> None:
    """
    Handle all server-to-client frames:
    - setupComplete   : log that session is ready
    - serverContent   : accumulate audio chunks; play on turnComplete
    - toolCall        : dispatch to backend; send toolResponse
    Exits on SILENCE_TIMEOUT or WebSocket close.
    """
    audio_buf: bytearray = bytearray()

    while True:
        try:
            raw = await asyncio.wait_for(ws.recv(), timeout=SILENCE_TIMEOUT)
        except asyncio.TimeoutError:
            print(
                f"[SPECTER] {int(SILENCE_TIMEOUT)}s of silence — closing session",
                flush=True,
            )
            break
        except websockets.exceptions.ConnectionClosed:
            print("[SPECTER] Connection closed by server.", flush=True)
            break

        try:
            msg: dict = json.loads(raw)
        except json.JSONDecodeError:
            continue

        # ── Session ready ──────────────────────────────────────────────
        if "setupComplete" in msg:
            print("[SPECTER] Session open — speak your command.", flush=True)
            continue

        # ── Audio / text response ──────────────────────────────────────
        if "serverContent" in msg:
            sc = msg["serverContent"]

            for part in sc.get("modelTurn", {}).get("parts", []):
                inline = part.get("inlineData", {})
                mime   = inline.get("mimeType", "")

                if mime.startswith("audio/pcm") and "data" in inline:
                    audio_buf.extend(base64.b64decode(inline["data"]))

                if "text" in part:
                    print(f"[SPECTER] {part['text']}", flush=True)

            # turnComplete signals end of Gemini's current turn → flush audio
            if sc.get("turnComplete") and audio_buf:
                data_snap = bytes(audio_buf)
                audio_buf.clear()
                await _play_pcm(data_snap)

        # ── Function / tool call ───────────────────────────────────────
        if "toolCall" in msg:
            responses = []
            for fn in msg["toolCall"].get("functionCalls", []):
                name = fn.get("name", "")
                if name == "execute_defensive_command":
                    args    = fn.get("args", {})
                    cmd     = int(args.get("command", 0))
                    ip      = args.get("ip") or None
                    call_id = fn.get("id", "")
                    print(
                        f"[CMD]    execute_defensive_command(cmd={cmd}, ip={ip})",
                        flush=True,
                    )
                    result = await _call_backend(cmd, ip)
                    print(f"[CMD]    result: {result}", flush=True)
                    responses.append(
                        {"id": call_id, "response": {"output": {"result": result}}}
                    )

            if responses:
                await ws.send(
                    json.dumps(
                        {"toolResponse": {"functionResponses": responses}}
                    )
                )


# ── Gemini Live session ──────────────────────────────────────────────────────
async def _run_gemini_session() -> None:
    # Flush stale mic audio buffered during OWW → Gemini transition
    while not _mic_q.empty():
        _mic_q.get_nowait()

    uri = f"{_WS_ENDPOINT}?key={GEMINI_API_KEY}"
    print(f"[SPECTER] Connecting to {GEMINI_MODEL}...", flush=True)

    try:
        async with websockets.connect(
            uri,
            open_timeout=15,
            close_timeout=5,
            ping_interval=None,   # Gemini Live handles its own keepalive
        ) as ws:
            # Frame 1 must be the setup message
            await ws.send(json.dumps(_SETUP_MSG))

            send_task    = asyncio.create_task(_send_loop(ws))
            receive_task = asyncio.create_task(_receive_loop(ws))

            # _receive_loop exits on silence/close; _send_loop runs forever
            done, pending = await asyncio.wait(
                [send_task, receive_task],
                return_when=asyncio.FIRST_COMPLETED,
            )
            for t in pending:
                t.cancel()
                try:
                    await t
                except asyncio.CancelledError:
                    pass

    except websockets.exceptions.WebSocketException as exc:
        print(f"[SPECTER] WebSocket error: {exc}", flush=True)
    except OSError as exc:
        print(f"[SPECTER] Network error: {exc}", flush=True)
    except Exception as exc:  # noqa: BLE001
        print(f"[SPECTER] Unexpected error: {exc}", flush=True)

    print("[SPECTER] Session closed — returning to wake-word listening.", flush=True)


# ── Main: OpenWakeWord loop ──────────────────────────────────────────────────
def main() -> None:
    if not GEMINI_API_KEY:
        print("[ERROR] GEMINI_API_KEY not set. Add it to .env and restart.", flush=True)
        sys.exit(1)

    print(f"[SPECTER] Voice listener  model={GEMINI_MODEL}", flush=True)

    # Wake-word model selection
    custom = Path(__file__).parent / "hey_specter_ai.onnx"
    if custom.exists():
        model_spec = str(custom)
        model_key  = "hey_specter_ai"
        print(f"[OWW]    Custom model: {custom.name}", flush=True)
    else:
        model_spec = "hey_jarvis"
        model_key  = "hey_jarvis"
        print("[OWW]    hey_specter_ai.onnx not found — using 'hey_jarvis' fallback", flush=True)
        print("[OWW]    Say 'Hey Jarvis' to activate Specter.", flush=True)

    oww = Model(wakeword_models=[model_spec], inference_framework="onnx")
    print(f"[OWW]    Model ready ({model_key})", flush=True)

    with sd.InputStream(
        samplerate=MIC_RATE,
        channels=CHANNELS,
        dtype="int16",
        blocksize=CHUNK_SAMPLES,
        callback=_mic_callback,
    ):
        print("[IDLE]   Waiting for wake word...\n", flush=True)

        while True:
            try:
                chunk_bytes = _mic_q.get(timeout=1.0)
            except sync_queue.Empty:
                continue

            chunk = np.frombuffer(chunk_bytes, dtype=np.int16)
            pred  = oww.predict(chunk)

            # Accept score from either key (handles named and path-loaded models)
            score = max(
                pred.get(model_key, 0.0),
                pred.get("hey_jarvis", 0.0),
            )

            if score > WAKE_THRESHOLD:
                print(f"\n[WAKE]   score={score:.3f} — activating Specter", flush=True)
                asyncio.run(_run_gemini_session())
                print("[IDLE]   Waiting for wake word...\n", flush=True)


if __name__ == "__main__":
    main()
