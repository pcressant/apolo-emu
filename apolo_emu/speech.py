"""Interface between the emulated device and a speech engine.

The device produces utterances containing text and marks. The backend speaks
them in order and reports progress through SpeechEvent. Parameters remain in
Apollo units: mapping them to a particular engine is the backend's job
(see mapping.py).
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Callable, Protocol, Union

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class VoiceParams:
    """Apollo settings affecting speech output."""

    speed: int = 3  # @W 1-9
    pitch: int = 8  # @F 0-F
    pitch_step: int = 8  # @F+ = 16, @F- = 0, otherwise 8
    volume: int = 6  # @A 0-F
    voice: int = 1  # @V 1-6 (0 = speech disabled)
    speaker: int = 0  # @K 0 male, 1 non-male
    punct: int = 0  # @P
    spell: int = 0  # @S
    language: str = "en"  # language of the ROM bank selected by @=

    @property
    def silent(self) -> bool:
        return self.voice == 0


@dataclass(frozen=True)
class Mark:
    name: str


@dataclass(frozen=True)
class Pause:
    """Inserted pause (approximation of @T sound effects)."""

    ms: int


Part = Union[str, Mark, Pause]


@dataclass
class Utterance:
    uid: int
    params: VoiceParams
    parts: list[Part] = field(default_factory=list)

    @property
    def text(self) -> str:
        return "".join(p for p in self.parts if isinstance(p, str))

    @property
    def marks(self) -> list[str]:
        return [p.name for p in self.parts if isinstance(p, Mark)]


@dataclass(frozen=True)
class SpeechEvent:
    """kind: 'begin', 'mark', 'end' or 'cancel'."""

    uid: int
    kind: str
    mark: str | None = None


EventSink = Callable[[SpeechEvent], None]


class SpeechBackend(Protocol):
    def set_event_sink(self, sink: EventSink) -> None: ...

    def speak(self, utt: Utterance) -> None:
        """Queue the utterance after those already in progress."""

    def cancel(self) -> None:
        """Stop speech immediately and clear the queue."""

    async def start(self) -> None: ...

    async def close(self) -> None: ...


class NullBackend:
    """Silent backend that finishes every utterance immediately.

    A last-resort fallback: the guest still receives its echoes.
    """

    def __init__(self) -> None:
        self._sink: EventSink | None = None

    def set_event_sink(self, sink: EventSink) -> None:
        self._sink = sink

    def speak(self, utt: Utterance) -> None:
        log.info("SPEECH (silent) %r", utt.text)
        if self._sink:
            self._sink(SpeechEvent(utt.uid, "begin"))
            self._sink(SpeechEvent(utt.uid, "end"))

    def cancel(self) -> None:
        pass

    async def start(self) -> None:
        pass

    async def close(self) -> None:
        pass


class SimulatedBackend:
    """Silent backend simulating speech duration in characters per second.

    Marks are reported when the preceding text has been "spoken".
    Used for --backend simulated and integration tests without Speech Dispatcher.
    """

    def __init__(self, cps: float = 15.0) -> None:
        self.cps = cps
        self._sink: EventSink | None = None
        self._queue: list[Utterance] = []
        self._task = None
        self._wakeup = None

    def set_event_sink(self, sink: EventSink) -> None:
        self._sink = sink

    def speak(self, utt: Utterance) -> None:
        log.info("SPEECH (simulated) %r", utt.text)
        self._queue.append(utt)
        if self._wakeup is not None:
            self._wakeup.set()

    def cancel(self) -> None:
        queue, self._queue = self._queue, []
        if self._task is not None:
            self._task.cancel()
            self._task = None
        for utt in queue:
            self._emit(SpeechEvent(utt.uid, "cancel"))
        self._ensure_task()

    def _emit(self, ev: SpeechEvent) -> None:
        if self._sink:
            self._sink(ev)

    def _ensure_task(self) -> None:
        if self._task is None:
            self._wakeup = asyncio.Event()
            self._task = asyncio.get_running_loop().create_task(self._run())

    async def _run(self) -> None:
        while True:
            while not self._queue:
                self._wakeup.clear()
                await self._wakeup.wait()
            utt = self._queue[0]
            self._emit(SpeechEvent(utt.uid, "begin"))
            for p in utt.parts:
                if isinstance(p, str):
                    await asyncio.sleep(len(p) / self.cps)
                elif isinstance(p, Pause):
                    await asyncio.sleep(p.ms / 1000)
                elif isinstance(p, Mark):
                    self._emit(SpeechEvent(utt.uid, "mark", p.name))
            self._queue.pop(0)
            self._emit(SpeechEvent(utt.uid, "end"))

    async def start(self) -> None:
        self._ensure_task()

    async def close(self) -> None:
        if self._task is not None:
            self._task.cancel()
            self._task = None
