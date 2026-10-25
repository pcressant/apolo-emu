"""Interface entre l'appareil émulé et un moteur vocal.

L'appareil produit des énoncés (`Utterance`) faits de texte et de marques. Le
backend les prononce dans l'ordre et signale leur progression par
`SpeechEvent`. Les paramètres restent exprimés en valeurs Apollo : la traduction
vers un moteur donné appartient au backend (voir mapping.py).
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Callable, Protocol, Union

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class VoiceParams:
    """Réglages Apollo qui influent sur la parole produite."""

    speed: int = 3  # @W 1-9
    pitch: int = 8  # @F 0-F
    pitch_step: int = 8  # @F+ = 16, @F- = 0, sinon 8
    volume: int = 6  # @A 0-F
    voice: int = 1  # @V 1-6 (0 = voix coupée)
    speaker: int = 0  # @K 0 masculin, 1 non masculin
    punct: int = 0  # @P
    spell: int = 0  # @S
    language: str = "en"  # langue de l'emplacement de ROM choisi par @=

    @property
    def silent(self) -> bool:
        return self.voice == 0


@dataclass(frozen=True)
class Mark:
    name: str


@dataclass(frozen=True)
class Pause:
    """Silence inséré (effets sonores @T, approximés)."""

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
    """kind : 'begin', 'mark', 'end' ou 'cancel'."""

    uid: int
    kind: str
    mark: str | None = None


EventSink = Callable[[SpeechEvent], None]


class SpeechBackend(Protocol):
    def set_event_sink(self, sink: EventSink) -> None: ...

    def speak(self, utt: Utterance) -> None:
        """Met l'énoncé en file, après ceux qui sont déjà en cours."""

    def cancel(self) -> None:
        """Arrête immédiatement la parole et vide la file."""

    async def start(self) -> None: ...

    async def close(self) -> None: ...


class NullBackend:
    """Backend sans son, qui termine chaque énoncé immédiatement.

    En pratique, sert d'ultime repli : l'invité reçoit quand même ses échos.
    """

    def __init__(self) -> None:
        self._sink: EventSink | None = None

    def set_event_sink(self, sink: EventSink) -> None:
        self._sink = sink

    def speak(self, utt: Utterance) -> None:
        log.info("PAROLE (sans son) %r", utt.text)
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
    """Backend sans son qui simule la durée de la parole (caractères par seconde).

    Les marques sont signalées quand le texte qui les précède a été « prononcé ».
    Sert au mode --backend simulated et aux tests d'intégration sans Speech Dispatcher.
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
        log.info("PAROLE (simulée) %r", utt.text)
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
