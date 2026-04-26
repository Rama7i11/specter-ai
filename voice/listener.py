"""
Specter Voice Listener
======================
Wake word  : "Hey Jarvis" (OpenWakeWord pretrained ONNX — no cloud, no auth)
             Loads hey_specter_ai.onnx automatically if present.
Wake button: Polls GET /voice/wake-status every 500 ms (Argon physical button
             via Particle webhook → POST /voice/wake → backend).
Proactive  : Polls GET /voice/pending-briefing every 1 s.
             If an unspoken alert is waiting AND no Realtime session is active
             → opens a proactive session to
             speak the briefing to the operator, then stays listening for commands.
On wake    : Raw WebSocket → OpenAI Realtime API (gpt-4o-realtime-*).
             Mic (16 kHz PCM16) → OpenAI → speaker (24 kHz PCM16).
             Server VAD handles turn detection.
             OpenAI calls execute_defensive_command(N) → POST /voice/command.

Session lifetime
  - Normal (wake-triggered)    : closes 8 s after response.done with no new speech
  - Proactive (briefing-triggered): closes 6 s after response.done with no new speech
  - Hard cap: MAX_SESSION_SECS (60 s) regardless of activity; warns at 50 s
  - Dead-connection guard: DEAD_CONN_TIMEOUT (60 s) if OpenAI sends nothing
  After any close, ONLY OpenWakeWord runs locally. No transcription, no OpenAI.
  User must say "Hey Jarvis" or press the button to re-open.

_session_active (threading.Event) prevents concurrent sessions:
  set before asyncio.run(session), cleared after. All three trigger paths
  (OWW, button, briefing) honour it.
"""

import asyncio
import base64
import json
import os
import queue as sync_queue
import sys
import threading
from pathlib import Path

import httpx
import numpy as np
import sounddevice as sd
import websockets
import websockets.exceptions
from dotenv import load_dotenv
from openwakeword.model import Model

# ── Config ───────────────────────────────────────────────────────────────────
_REPO_ROOT = Path(__file__).parent.parent
load_dotenv(dotenv_path=_REPO_ROOT / ".env")

OPENAI_API_KEY        = os.getenv("OPENAI_API_KEY", "")
OPENAI_REALTIME_MODEL = os.getenv("OPENAI_REALTIME_MODEL", "gpt-4o-realtime-preview")
BACKEND_URL           = os.getenv("BACKEND_URL", "http://localhost:8000")

MIC_RATE             = 16_000
PLAYBACK_RATE        = 24_000
CHANNELS             = 1
CHUNK_SAMPLES        = 1280     # 80 ms @ 16 kHz — OpenWakeWord required chunk
WAKE_THRESHOLD       = 0.7
OWW_FLUSH_FRAMES     = 4        # silence frames fed to OWW after wake (~320 ms)

POST_RESPONSE_IDLE            = 8.0    # s after response.done → close (normal session)
POST_RESPONSE_IDLE_PROACTIVE  = 6.0    # s after response.done → close (proactive session)
MAX_SESSION_SECS              = 60.0   # hard session cap
DEAD_CONN_TIMEOUT             = 60.0   # ws.recv() dead-connection guard

_WS_ENDPOINT = "wss://api.openai.com/v1/realtime"

_SYSTEM_INSTRUCTIONS = (
    "You are Specter AI, defensive cybersecurity assistant for Team Aegis. "
    "Be terse and tactical — short military-style replies. "
    "The user runs an active SOC. "
    "Available commands: "
    "Command 1: Block attacker IP (use for SQL injection or general intrusion). "
    "Command 2: Reset all defenses (clear blocks, unlock accounts) for re-demo. "
    "Command 3: Status report (last alerts, current state). "
    "Command 4: Lock user account (use for brute force or credential attacks). "
    "When they say natural phrasings like 'block them', 'lock the user', "
    "'reset everything', map to the right number. "
    "Immediately call execute_defensive_command WITHOUT confirming verbally first. "
    "After the function returns its result, briefly speak that result. "
    "Don't pad with filler. "
    "When critical alerts (severity 9-10) trigger, Specter automatically escalates "
    "to PagerDuty. The incident appears in the on-call team's queue. "
    "Mention this when reporting status if PagerDuty incidents exist."
)

_SESSION_UPDATE: dict = {
    "type": "session.update",
    "session": {
        "modalities": ["audio", "text"],
        "instructions": _SYSTEM_INSTRUCTIONS,
        "voice": "alloy",
        "input_audio_format": "pcm16",
        "output_audio_format": "pcm16",
        "input_audio_transcription": {"model": "whisper-1"},
        "turn_detection": {
            "type": "server_vad",
            "threshold": 0.85,
            "prefix_padding_ms": 300,
            "silence_duration_ms": 1200,
        },
        "tools": [
            {
                "type": "function",
                "name": "execute_defensive_command",
                "description": "Execute a defensive cybersecurity action by command number",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "command": {
                            "type": "integer",
                            "description": "1=block IP, 2=reset defenses, 3=status report, 4=lock user account",
                        },
                        "ip": {
                            "type": "string",
                            "description": "Optional IP for command 1",
                        },
                        "username": {
                            "type": "string",
                            "description": "Optional username to lock for command 4. Omit to auto-detect from most recent brute force alert.",
                        },
                    },
                    "required": ["command"],
                },
            }
        ],
        "tool_choice": "auto",
    },
}

# ── Thread-safe mic queue ─────────────────────────────────────────────────────
_mic_q: sync_queue.Queue[bytes] = sync_queue.Queue(maxsize=200)

# ── Session concurrency guard (set while a Realtime WS is open) ──────────────
_session_active: threading.Event = threading.Event()

# ── Wake-button event ─────────────────────────────────────────────────────────
_wake_button_event: threading.Event = threading.Event()

# ── Pending briefing (written by poll thread, read+cleared by main loop) ─────
_briefing_state: dict        = {"text": None, "alert_id": None}
_briefing_lock:  threading.Lock = threading.Lock()

# ── Push-to-mute: True while Specter is playing audio back ────────────────────
# Set by _receive_loop on response.audio.delta; cleared on response.done.
# _send_loop drops mic frames silently during this window.
_specter_speaking: bool = False


def _mic_callback(indata: np.ndarray, frames: int, time_info, status) -> None:
    try:
        _mic_q.put_nowait(indata.tobytes())
    except sync_queue.Full:
        pass


# ── Backend state push (fire-and-forget) ─────────────────────────────────────
async def _post_specter_state(state_str: str, level: float = 0.0) -> None:
    try:
        async with httpx.AsyncClient(timeout=1.0) as client:
            await client.post(
                f"{BACKEND_URL}/voice/state",
                json={"state": state_str, "level": level},
            )
    except Exception:
        pass  # never break the listener on dashboard plumbing


# ── Backend call ──────────────────────────────────────────────────────────────
async def _call_backend(command: int, ip: str | None, username: str | None = None) -> str:
    args: dict = {}
    if ip:
        args["ip"] = ip
    if username:
        args["username"] = username
    payload: dict = {"command": command, "args": args}
    try:
        async with httpx.AsyncClient() as client:
            r = await client.post(
                f"{BACKEND_URL}/voice/command", json=payload, timeout=5
            )
            return r.json().get("result", "Command executed.")
    except Exception as exc:  # noqa: BLE001
        return f"Backend error: {exc}"


# ── Audio playback ────────────────────────────────────────────────────────────
def _play_pcm_blocking(data: bytes) -> None:
    samples = np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0
    sd.play(samples, samplerate=PLAYBACK_RATE, blocking=True)


async def _play_pcm(data: bytes) -> None:
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, _play_pcm_blocking, data)


# ── Wake-button polling ───────────────────────────────────────────────────────
async def _poll_wake_button() -> None:
    async with httpx.AsyncClient() as client:
        while True:
            try:
                if not _session_active.is_set():
                    r = await client.get(f"{BACKEND_URL}/voice/wake-status", timeout=2)
                    if r.json().get("wake_requested"):
                        ack = await client.post(f"{BACKEND_URL}/voice/wake-ack", timeout=2)
                        if ack.json().get("consumed"):
                            print("[WAKE]   Button press — activating Specter AI", flush=True)
                            _wake_button_event.set()
            except Exception:
                pass  # backend may not be up yet — poll will retry automatically
            await asyncio.sleep(0.5)


# ── Proactive briefing polling ────────────────────────────────────────────────
async def _poll_pending_briefing() -> None:
    """
    Every 1 s, fetch the next unspoken alert briefing from the backend.
    Fires whenever a briefing is queued and no session is active.
    hardware_mode is NOT checked here — briefings are informational and always
    speak regardless of wearable dial position. Only defense execution (cmds 1/2/4)
    requires DEFENSE_READY mode.
    """
    async with httpx.AsyncClient() as client:
        while True:
            try:
                if not _session_active.is_set():
                    r    = await client.get(f"{BACKEND_URL}/voice/pending-briefing", timeout=2)
                    data = r.json()
                    if data.get("briefing"):
                        with _briefing_lock:
                            # Only set if main loop has already consumed the previous one
                            if _briefing_state["text"] is None:
                                _briefing_state["text"]     = data["briefing"]
                                _briefing_state["alert_id"] = data.get("alert_id")
            except Exception:
                pass  # backend may not be up yet — poll will retry automatically
            await asyncio.sleep(1.0)


# ── Post-response idle close ──────────────────────────────────────────────────
async def _idle_close(ws, delay: float) -> None:
    await asyncio.sleep(delay)
    print(f"[IDLE-TIMER] expired — closing", flush=True)
    print(
        f"[SESSION] no activity for {int(delay)}s — closing OpenAI connection",
        flush=True,
    )
    try:
        await ws.close()
    except Exception:
        pass


# ── WebSocket send loop ───────────────────────────────────────────────────────
async def _send_loop(ws) -> None:
    while True:
        chunk: bytes | None = None
        while chunk is None:
            try:
                chunk = _mic_q.get_nowait()
            except sync_queue.Empty:
                await asyncio.sleep(0.05)
        if _specter_speaking:
            continue  # drop frame — Specter is speaking, mute mic to prevent echo
        try:
            await ws.send(json.dumps({
                "type":  "input_audio_buffer.append",
                "audio": base64.b64encode(chunk).decode("ascii"),
            }))
        except websockets.exceptions.ConnectionClosed:
            return  # WS closed by idle/max timer — exit cleanly, no traceback


# ── WebSocket receive loop ────────────────────────────────────────────────────
async def _receive_loop(
    ws,
    briefing_text: str | None = None,
    post_response_idle: float = POST_RESPONSE_IDLE,
) -> None:
    """
    Handle all server → client events.

    briefing_text: if set, sent as a proactive system message once session.updated
                   is received, causing Specter to speak unprompted.
    post_response_idle: seconds of silence after response.done before closing.
                        Use POST_RESPONSE_IDLE_PROACTIVE for briefing-triggered sessions.

    Idle timer logic:
      response.done        → start countdown (post_response_idle)
      response.audio.delta → cancel timer (model still speaking in multi-turn)
      speech_started       → cancel timer (user speaking — keep session alive)
      Timer fires          → _idle_close() closes WS → ConnectionClosed breaks loop
    """
    global _specter_speaking
    audio_buf:    bytearray          = bytearray()
    fn_args_buf:  dict[str, str]     = {}
    idle_task:    asyncio.Task | None = None
    briefing_sent: bool              = False

    def _start_idle() -> None:
        nonlocal idle_task
        if idle_task and not idle_task.done():
            idle_task.cancel()
        print(f"[IDLE-TIMER] starting ({int(post_response_idle)}s)", flush=True)
        idle_task = asyncio.create_task(_idle_close(ws, post_response_idle))

    def _cancel_idle(reason: str = "") -> None:
        nonlocal idle_task
        if idle_task and not idle_task.done():
            idle_task.cancel()
            print(f"[IDLE-TIMER] cancelled ({reason})", flush=True)
        idle_task = None

    try:
        while True:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=DEAD_CONN_TIMEOUT)
            except asyncio.TimeoutError:
                print(
                    f"[SESSION] dead connection ({int(DEAD_CONN_TIMEOUT)}s no events) — closing",
                    flush=True,
                )
                break
            except websockets.exceptions.ConnectionClosed:
                print("[SESSION] closed — WS connection terminated", flush=True)
                break

            try:
                msg: dict = json.loads(raw)
            except json.JSONDecodeError:
                continue

            t = msg.get("type", "")

            # ── Session lifecycle ──────────────────────────────────────
            if t in ("session.created", "session.updated"):
                print("[REALTIME] session ready", flush=True)
                # Proactive path: speak the briefing immediately after session config applied
                if briefing_text and not briefing_sent and t == "session.updated":
                    briefing_sent = True
                    await ws.send(json.dumps({
                        "type": "conversation.item.create",
                        "item": {
                            "type":    "message",
                            "role":    "user",
                            "content": [{
                                "type": "input_text",
                                "text": (
                                    f"Speak this exactly to the user — they have not spoken yet, "
                                    f"you are proactively briefing them: {briefing_text} "
                                    f"After speaking, await their command."
                                ),
                            }],
                        },
                    }))
                    await ws.send(json.dumps({
                        "type":     "response.create",
                        "response": {"modalities": ["audio", "text"]},
                    }))
                    print("[BRIEFING] spoke briefing — switching to listening mode", flush=True)

            # ── User speech ────────────────────────────────────────────
            elif t == "input_audio_buffer.speech_started":
                _cancel_idle("speech_started")
                asyncio.create_task(_post_specter_state("LISTENING", 0.6))
                print("[USER]   speaking...", flush=True)

            elif t == "input_audio_buffer.speech_stopped":
                asyncio.create_task(_post_specter_state("THINKING", 0.3))

            elif t == "conversation.item.input_audio_transcription.completed":
                transcript = msg.get("transcript", "").strip()
                if transcript:
                    print(f'[USER]   "{transcript}"', flush=True)

            # ── Assistant audio ────────────────────────────────────────
            elif t == "response.audio.delta":
                if not _specter_speaking:
                    asyncio.create_task(_post_specter_state("HACKING", 0.8))
                _specter_speaking = True       # mute mic while Specter speaks
                _cancel_idle("audio.delta")    # model still speaking — don't start countdown yet
                delta = msg.get("delta", "")
                if delta:
                    audio_buf.extend(base64.b64decode(delta))

            elif t == "response.audio.done":
                if audio_buf:
                    data_snap = bytes(audio_buf)
                    audio_buf.clear()
                    await _play_pcm(data_snap)

            elif t == "response.audio_transcript.done":
                transcript = msg.get("transcript", "").strip()
                if transcript:
                    print(f'[SPEAK]  "{transcript}"', flush=True)

            # ── Tool / function call ───────────────────────────────────
            elif t == "response.function_call_arguments.delta":
                call_id = msg.get("call_id", "")
                fn_args_buf[call_id] = fn_args_buf.get(call_id, "") + msg.get("delta", "")

            elif t == "response.function_call_arguments.done":
                call_id  = msg.get("call_id", "")
                name     = msg.get("name", "execute_defensive_command")
                raw_args = fn_args_buf.pop(call_id, msg.get("arguments", "{}"))

                try:
                    args = json.loads(raw_args)
                except json.JSONDecodeError:
                    args = {}

                cmd      = int(args.get("command", 0))
                ip       = args.get("ip")       or None
                username = args.get("username") or None

                print(f"[TOOL]   {name}(cmd={cmd}, ip={ip}, username={username})", flush=True)
                result = await _call_backend(cmd, ip, username)
                print(f"[POST]   /voice/command → {result}", flush=True)

                await ws.send(json.dumps({
                    "type": "conversation.item.create",
                    "item": {
                        "type":    "function_call_output",
                        "call_id": call_id,
                        "output":  result,
                    },
                }))
                await ws.send(json.dumps({"type": "response.create"}))

            # ── Turn complete → start idle countdown ───────────────────
            elif t == "response.done":
                _specter_speaking = False      # unmute mic — Specter finished speaking
                print("[DONE]   response complete", flush=True)
                _start_idle()

            # ── Error ──────────────────────────────────────────────────
            elif t == "error":
                err = msg.get("error", {})
                print(f"[ERROR]  {err.get('type')}: {err.get('message')}", flush=True)
                break

    finally:
        _specter_speaking = False  # always unmute on session exit
        _cancel_idle()

    if audio_buf:
        await _play_pcm(bytes(audio_buf))


# ── OpenAI Realtime session ───────────────────────────────────────────────────
async def _run_realtime_session(briefing_text: str | None = None) -> None:
    """
    Open a Realtime WebSocket session.
    briefing_text: if provided, Specter speaks it immediately (proactive mode)
                   and then stays listening. Idle timeout is longer.
    """
    while not _mic_q.empty():
        _mic_q.get_nowait()

    post_idle = POST_RESPONSE_IDLE_PROACTIVE if briefing_text else POST_RESPONSE_IDLE
    uri       = f"{_WS_ENDPOINT}?model={OPENAI_REALTIME_MODEL}"
    label     = "proactive briefing" if briefing_text else OPENAI_REALTIME_MODEL
    print(f"[REALTIME] connecting to OpenAI ({label})...", flush=True)

    asyncio.create_task(_post_specter_state("LISTENING", 0.4))

    try:
        async with websockets.connect(
            uri,
            additional_headers={
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "OpenAI-Beta":   "realtime=v1",
            },
            open_timeout=15,
            close_timeout=5,
            ping_interval=None,
        ) as ws:
            await ws.send(json.dumps(_SESSION_UPDATE))

            send_task    = asyncio.create_task(_send_loop(ws))
            receive_task = asyncio.create_task(
                _receive_loop(ws, briefing_text=briefing_text, post_response_idle=post_idle)
            )

            async def _max_session_close() -> None:
                await asyncio.sleep(MAX_SESSION_SECS - 10)
                print("[SESSION] 10s until max duration close...", flush=True)
                await asyncio.sleep(10)
                print(
                    f"[SESSION] {int(MAX_SESSION_SECS)}s max duration reached — closing",
                    flush=True,
                )
                try:
                    await ws.close()
                except Exception:
                    pass

            max_dur_task = asyncio.create_task(_max_session_close())

            done, pending = await asyncio.wait(
                [send_task, receive_task, max_dur_task],
                return_when=asyncio.FIRST_COMPLETED,
            )
            for task in pending:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

    except websockets.exceptions.WebSocketException as exc:
        print(f"[REALTIME] WebSocket error: {exc}", flush=True)
    except OSError as exc:
        print(f"[REALTIME] Network error: {exc}", flush=True)
    except Exception as exc:  # noqa: BLE001
        print(f"[REALTIME] Unexpected error: {exc}", flush=True)
    finally:
        try:
            asyncio.create_task(_post_specter_state("ASLEEP", 0.0))
        except RuntimeError:
            pass  # event loop may be closing


# ── Main: OpenWakeWord loop ───────────────────────────────────────────────────
def main() -> None:
    if not OPENAI_API_KEY:
        print("[ERROR] OPENAI_API_KEY not set. Add it to .env and restart.", flush=True)
        sys.exit(1)

    print(f"[SPECTER] Voice listener  model={OPENAI_REALTIME_MODEL}", flush=True)

    custom = Path(__file__).parent / "hey_specter_ai.onnx"
    if custom.exists():
        model_spec = str(custom)
        model_key  = "hey_specter_ai"
        print(f"[OWW]    Custom model: {custom.name}", flush=True)
    else:
        model_spec = "hey_jarvis"
        model_key  = "hey_jarvis"
        print("[OWW]    hey_specter_ai.onnx not found — using 'hey_jarvis' fallback", flush=True)
        print(f"[OWW]    Say 'Hey Jarvis' to activate (threshold={WAKE_THRESHOLD})", flush=True)

    oww = Model(wakeword_models=[model_spec], inference_framework="onnx")
    print(f"[OWW]    Model ready ({model_key})", flush=True)

    _silence_frame = np.zeros(CHUNK_SAMPLES, dtype=np.int16)

    # Background daemon threads — each runs its own asyncio event loop
    threading.Thread(
        target=lambda: asyncio.run(_poll_wake_button()),
        daemon=True, name="wake-button-poll",
    ).start()
    threading.Thread(
        target=lambda: asyncio.run(_poll_pending_briefing()),
        daemon=True, name="briefing-poll",
    ).start()
    print(f"[BTN]    Button polling active → {BACKEND_URL}/voice/wake-status", flush=True)
    print(f"[ALERT]  Briefing polling active → {BACKEND_URL}/voice/pending-briefing", flush=True)

    def _flush_oww_and_queue() -> None:
        for _ in range(OWW_FLUSH_FRAMES):
            oww.predict(_silence_frame)
        while not _mic_q.empty():
            _mic_q.get_nowait()

    with sd.InputStream(
        samplerate=MIC_RATE,
        channels=CHANNELS,
        dtype="int16",
        blocksize=CHUNK_SAMPLES,
        callback=_mic_callback,
    ):
        print("[IDLE]   Listening for wake word only (no transcription active)\n", flush=True)

        while True:
            # ── Priority 1: physical button ──────────────────────────────
            if _wake_button_event.is_set():
                _wake_button_event.clear()
                _session_active.set()
                _flush_oww_and_queue()
                asyncio.run(_run_realtime_session())
                _session_active.clear()
                print(
                    "[IDLE]   Listening for wake word only (no transcription active)\n",
                    flush=True,
                )
                continue

            # ── Priority 2: proactive briefing ───────────────────────────
            briefing_to_speak = None
            briefing_alert_id = None
            with _briefing_lock:
                if _briefing_state["text"] and not _session_active.is_set():
                    briefing_to_speak        = _briefing_state["text"]
                    briefing_alert_id        = _briefing_state["alert_id"]
                    _briefing_state["text"]     = None
                    _briefing_state["alert_id"] = None

            if briefing_to_speak:
                print(
                    f"[BRIEFING] new alert id={briefing_alert_id} — opening proactive session",
                    flush=True,
                )
                _session_active.set()
                _flush_oww_and_queue()
                asyncio.run(_run_realtime_session(briefing_text=briefing_to_speak))
                _session_active.clear()
                print(
                    "[IDLE]   Listening for wake word only (no transcription active)\n",
                    flush=True,
                )
                continue

            # ── Priority 3: OpenWakeWord ─────────────────────────────────
            try:
                chunk_bytes = _mic_q.get(timeout=0.1)
            except sync_queue.Empty:
                continue

            chunk = np.frombuffer(chunk_bytes, dtype=np.int16)
            pred  = oww.predict(chunk)

            score = max(
                pred.get(model_key, 0.0),
                pred.get("hey_jarvis", 0.0),
            )

            if score > WAKE_THRESHOLD:
                print(f"\n[WAKE]   score={score:.3f} — activating Specter AI", flush=True)
                _session_active.set()
                _flush_oww_and_queue()
                asyncio.run(_run_realtime_session())
                _session_active.clear()
                print(
                    "[IDLE]   Listening for wake word only (no transcription active)\n",
                    flush=True,
                )


if __name__ == "__main__":
    main()
