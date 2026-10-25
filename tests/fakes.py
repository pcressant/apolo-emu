"""Faux backend vocal : enregistre les énoncés et laisse le test piloter la progression."""

from __future__ import annotations

from apolo_emu.speech import Mark, SpeechEvent, Utterance


class FakeBackend:
    def __init__(self) -> None:
        self.sink = None
        self.queue: list[Utterance] = []  # énoncés reçus et pas encore terminés
        self.spoken: list[Utterance] = []  # tous les énoncés reçus
        self.cancels = 0

    def set_event_sink(self, sink) -> None:
        self.sink = sink

    def speak(self, utt: Utterance) -> None:
        self.queue.append(utt)
        self.spoken.append(utt)

    def cancel(self) -> None:
        self.cancels += 1
        queue, self.queue = self.queue, []
        for utt in queue:
            self.sink(SpeechEvent(utt.uid, "cancel"))

    async def start(self) -> None:
        pass

    async def close(self) -> None:
        pass

    # --- pilotage par le test

    @property
    def texts(self) -> list[str]:
        return [u.text for u in self.spoken]

    def begin(self) -> Utterance:
        utt = self.queue[0]
        self.sink(SpeechEvent(utt.uid, "begin"))
        return utt

    def reach(self, n: int) -> None:
        """La parole atteint la n-ième marque (à partir de 0) de l'énoncé en cours."""
        utt = self.queue[0]
        self.sink(SpeechEvent(utt.uid, "mark", utt.marks[n]))

    def finish(self) -> Utterance:
        utt = self.queue.pop(0)
        self.sink(SpeechEvent(utt.uid, "end"))
        return utt

    def finish_all(self) -> None:
        while self.queue:
            self.finish()

    def mark_positions(self, utt: Utterance) -> list[tuple[str, str]]:
        """(nom de marque, texte qui la précède) pour vérifier les positions."""
        out, text = [], ""
        for p in utt.parts:
            if isinstance(p, Mark):
                out.append((p.name, text))
            elif isinstance(p, str):
                text += p
        return out
