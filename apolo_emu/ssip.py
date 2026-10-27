"""Speech Dispatcher backend: asynchronous SSIP client without external dependencies.

Each utterance becomes an SSML message. Marks return as 700 (INDEX MARK)
events when speech reaches them. Apollo settings are mapped by mapping.Mapping
and sent only when changed.

If Speech Dispatcher becomes unreachable, current utterances are declared
finished so the guest receives echoes instead of waiting indefinitely.
This policy is logged and documented in docs/limitations.md.
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
from collections import deque
from dataclasses import dataclass, field
from xml.sax.saxutils import escape, quoteattr

from .mapping import Mapping
from .speech import EventSink, Mark, Pause, SpeechEvent, Utterance

log = logging.getLogger(__name__)


def default_address() -> str:
    env = os.environ.get("SPEECHD_ADDRESS")
    if env:
        return env
    runtime = os.environ.get("XDG_RUNTIME_DIR") or f"/run/user/{os.getuid()}"
    return f"unix_socket:{runtime}/speech-dispatcher/speechd.sock"


def to_ssml(utt: Utterance) -> str:
    out = ["<speak>"]
    for p in utt.parts:
        if isinstance(p, Mark):
            out.append(f"<mark name={quoteattr(p.name)}/>")
        elif isinstance(p, Pause):
            out.append(f'<break time="{p.ms}ms"/>')
        else:
            out.append(escape(p))
    out.append("</speak>")
    return "".join(out)


def escape_data(text: str) -> str:
    """SPEAK body: a lone dot ends the message, so double leading dots."""
    lines = text.replace("\r", " ").split("\n")
    return "\r\n".join("." + line if line.startswith(".") else line for line in lines)


class SSIPError(Exception):
    pass


@dataclass
class _Pending:
    future: asyncio.Future
    uid: int | None = None  # SPEAK awaiting its identifier
    lines: list[str] = field(default_factory=list)


class SSIPBackend:
    def __init__(
        self,
        address: str | None = None,
        client_name: str = "apolo-emu",
        module: str | None = None,
        synthesis_voice: str | None = None,
        priority: str = "message",
        mapping: Mapping | None = None,
        autospawn: bool = True,
        connect_timeout: float = 5.0,
    ) -> None:
        self.address = address or default_address()
        self.client_name = client_name
        self.module = module
        self.synthesis_voice = synthesis_voice
        self.priority = priority
        self.mapping = mapping or Mapping()
        if synthesis_voice:
            self.mapping = Mapping(**{**self.mapping.__dict__, "use_voice_type": False})
        self.autospawn = autospawn
        self.connect_timeout = connect_timeout
        self._sink: EventSink | None = None
        self._ops: asyncio.Queue | None = None
        self._worker: asyncio.Task | None = None
        self._reader_task: asyncio.Task | None = None
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._pending: deque[_Pending] = deque()
        self._msg_to_uid: dict[str, int] = {}
        self._queued: set[int] = set()  # queued utterances, not yet submitted
        self._sent: set[int] = set()  # submitted utterances, not yet finished
        self._applied: dict[str, str] = {}
        self._spawned = False
        self._closing = False
        self.connected = asyncio.Event()

    # ------------------------------------------------------------ interface

    def set_event_sink(self, sink: EventSink) -> None:
        self._sink = sink

    def speak(self, utt: Utterance) -> None:
        self._queued.add(utt.uid)
        self._queue().put_nowait(("speak", utt))

    def cancel(self) -> None:
        # Discard unsent SPEAK requests; CANCEL stops the rest.
        q = self._queue()
        kept = []
        while not q.empty():
            op = q.get_nowait()
            if op[0] == "speak":
                self._queued.discard(op[1].uid)
            else:
                kept.append(op)
        for op in kept:
            q.put_nowait(op)
        q.put_nowait(("cancel", None))

    async def start(self) -> None:
        self._queue()
        self._worker = asyncio.create_task(self._work(), name="ssip-worker")
        try:
            await self._ensure_connected()
        except (OSError, SSIPError) as e:
            log.warning("Speech Dispatcher unreachable (%s): retry on next utterance", e)

    async def close(self) -> None:
        self._closing = True
        if self._worker:
            self._worker.cancel()
            await asyncio.gather(self._worker, return_exceptions=True)
        if self._writer:
            try:
                await self._command("QUIT", timeout=1.0, check=False)
            except Exception:
                pass
        await self._disconnect("fermeture")

    # -------------------------------------------------------- connection

    def _queue(self) -> asyncio.Queue:
        if self._ops is None:
            self._ops = asyncio.Queue()
        return self._ops

    async def _open(self):
        kind, _, rest = self.address.partition(":")
        if kind == "unix_socket":
            return await asyncio.open_unix_connection(rest)
        if kind == "inet_socket":
            host, _, port = rest.rpartition(":")
            return await asyncio.open_connection(host or "127.0.0.1", int(port or 6560))
        raise SSIPError(f"unrecognized Speech Dispatcher address: {self.address}")

    async def _ensure_connected(self) -> None:
        if self._writer is not None:
            return
        try:
            reader, writer = await asyncio.wait_for(self._open(), self.connect_timeout)
        except (FileNotFoundError, ConnectionRefusedError):
            if not (self.autospawn and not self._spawned and shutil.which("speech-dispatcher")):
                raise
            self._spawned = True
            log.info("starting Speech Dispatcher (speech-dispatcher --spawn)")
            proc = await asyncio.create_subprocess_exec(
                "speech-dispatcher", "--spawn",
                stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
            )
            await proc.wait()
            for _ in range(50):
                try:
                    reader, writer = await self._open()
                    break
                except (FileNotFoundError, ConnectionRefusedError):
                    await asyncio.sleep(0.1)
            else:
                raise
        self._reader, self._writer = reader, writer
        self._reader_task = asyncio.create_task(self._read_loop(reader), name="ssip-reader")
        self._applied = {}
        await self._command(f"SET self CLIENT_NAME {os.environ.get('USER', 'user')}:{self.client_name}:main")
        if self.module:
            await self._command(f"SET self OUTPUT_MODULE {self.module}")
        await self._command(f"SET self PRIORITY {self.priority}")
        await self._command("SET self SSML_MODE on")
        await self._command("SET self NOTIFICATION all on")
        self.connected.set()
        log.info("connected to Speech Dispatcher (%s)", self.address)

    async def _disconnect(self, reason: str) -> None:
        writer, self._writer, self._reader = self._writer, None, None
        self.connected.clear()
        if self._reader_task and self._reader_task is not asyncio.current_task():
            self._reader_task.cancel()
        self._reader_task = None
        if writer is not None:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass
        while self._pending:
            p = self._pending.popleft()
            if not p.future.done():
                p.future.set_exception(SSIPError(reason))
        self._msg_to_uid.clear()
        self._release_outstanding(reason)

    def _release_outstanding(self, reason: str) -> None:
        uids, self._sent = sorted(self._sent), set()
        if uids and not self._closing:
            log.warning("Speech Dispatcher (%s): %d utterance(s) declared finished", reason, len(uids))
        for uid in uids:
            self._emit(SpeechEvent(uid, "end"))

    # ---------------------------------------------------------- protocol

    async def _send(self, data: bytes, uid: int | None = None, timeout: float = 10.0) -> list[str]:
        if self._writer is None:
            raise SSIPError("not connected")
        fut = asyncio.get_running_loop().create_future()
        self._pending.append(_Pending(fut, uid))
        self._writer.write(data)
        await self._writer.drain()
        return await asyncio.wait_for(fut, timeout)

    async def _command(self, line: str, timeout: float = 10.0, check: bool = True) -> list[str]:
        lines = await self._send(line.encode("utf-8") + b"\r\n", timeout=timeout)
        if check and not lines[-1][:1] == "2":
            raise SSIPError(f"{line!r} : {lines[-1]}")
        return lines

    async def _read_loop(self, reader: asyncio.StreamReader) -> None:
        block: list[str] = []
        try:
            while True:
                raw = await reader.readline()
                if not raw:
                    break
                line = raw.decode("utf-8", "replace").rstrip("\r\n")
                block.append(line)
                if len(line) < 4 or line[3] != " ":
                    continue
                lines, block = block, []
                if line.startswith("7"):
                    self._event(lines)
                elif self._pending:
                    p = self._pending.popleft()
                    if p.uid is not None and line.startswith("225"):
                        msg_id = lines[0][4:]
                        self._msg_to_uid[msg_id] = p.uid
                    if not p.future.done():
                        p.future.set_result(lines)
                else:
                    log.debug("unexpected SSIP reply: %s", lines)
        except (ConnectionError, asyncio.IncompleteReadError) as e:
            log.debug("SSIP reading interrupted: %s", e)
        except asyncio.CancelledError:
            return
        if not self._closing:
            await self._disconnect("connection lost")

    def _event(self, lines: list[str]) -> None:
        code = lines[-1][:3]
        msg_id = lines[0][4:] if len(lines) >= 2 else ""
        uid = self._msg_to_uid.get(msg_id)
        if uid is None:
            log.debug("SSIP event for unknown message: %s", lines)
            return
        if code == "701":
            self._emit(SpeechEvent(uid, "begin"))
        elif code == "700" and len(lines) >= 4:
            self._emit(SpeechEvent(uid, "mark", lines[2][4:]))
        elif code in ("702", "703"):
            self._msg_to_uid.pop(msg_id, None)
            self._sent.discard(uid)
            self._emit(SpeechEvent(uid, "end" if code == "702" else "cancel"))

    def _emit(self, ev: SpeechEvent) -> None:
        if self._sink is not None:
            try:
                self._sink(ev)
            except Exception:  # a device error must not stop the backend
                log.exception("error processing %s", ev)

    # ------------------------------------------------------------ worker

    async def _work(self) -> None:
        q = self._queue()
        while True:
            op, arg = await q.get()
            uid = arg.uid if op == "speak" else None
            try:
                if op == "speak":
                    if uid not in self._queued:
                        continue  # canceled before submission
                    self._queued.discard(uid)
                    await self._ensure_connected()
                    self._sent.add(uid)
                    await self._speak(arg)
                elif op == "cancel" and self._writer is not None:
                    await self._command("CANCEL self")
            except asyncio.CancelledError:
                raise
            except (OSError, SSIPError, asyncio.TimeoutError) as e:
                reason = str(e) or type(e).__name__
                log.warning("Speech Dispatcher: %s", reason)
                await self._disconnect(reason)
                if uid is not None and uid not in self._sent:
                    self._emit(SpeechEvent(uid, "end"))  # never spoken: the guest must not wait
                await asyncio.sleep(0.5)

    async def _speak(self, utt: Utterance) -> None:
        wanted = self.mapping.settings(utt.params)
        for key, value in wanted.items():
            if self._applied.get(key) != value:
                lines = await self._command(f"SET self {key} {value}", check=False)
                if not lines[-1].startswith("2"):
                    log.warning("SET %s %s rejected: %s", key, value, lines[-1])
                self._applied[key] = value
                if key == "LANGUAGE" and self.synthesis_voice:
                    await self._command(f"SET self SYNTHESIS_VOICE {self.synthesis_voice}", check=False)
        lines = await self._command("SPEAK", check=False)
        if not lines[-1].startswith("230"):
            log.warning("SPEAK rejected: %s", lines[-1])
            self._sent.discard(utt.uid)
            self._emit(SpeechEvent(utt.uid, "end"))
            return
        body = escape_data(to_ssml(utt))
        lines = await self._send(body.encode("utf-8") + b"\r\n.\r\n", uid=utt.uid)
        if not lines[-1].startswith("225"):
            log.warning("SPEAK rejected: %s", lines[-1])
            self._sent.discard(utt.uid)
            self._emit(SpeechEvent(utt.uid, "end"))
            return
        log.debug("SSIP %s <- utterance %d: %r", lines[0][4:], utt.uid, utt.text)
