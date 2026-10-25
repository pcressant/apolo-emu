"""Modèle de l'appareil Apollo II.

Deux étages, comme dans le firmware (docs/etat-des-connaissances.md §2) :

1. Étage communication, octet par octet : mute (Ctrl-A, Ctrl-X), commandes
   immédiates @I+ et @I?, tout le reste vers le tampon d'entrée.
2. Étage proposition : découpage en propositions, commandes différées, puis
   parole. Les propositions sont prononcées l'une après l'autre ; les effets
   attachés à une proposition (échos @E, réponses, réglages) prennent effet quand
   la parole l'atteint.

La classe ne fait aucune entrée-sortie : elle reçoit des octets (feed) et des
événements du moteur vocal (on_speech_event), et produit des réponses (reply)
et des énoncés (backend.speak).
"""

from __future__ import annotations

import logging
import time
from collections import deque
from dataclasses import dataclass, field, replace
from typing import Callable

from . import protocol as P
from .speech import Mark, Pause, SpeechBackend, SpeechEvent, Utterance, VoiceParams

log = logging.getLogger(__name__)

# Extensions non authentiques, désactivées par défaut (docs/extensions.md).
EXTENSIONS = {
    "epaulard-index": "@I<c> renvoie c à la fin de la prochaine proposition terminée par CR (Épaulard).",
    "word-echo": "@E renvoie son octet à sa position exacte dans la parole, et non au début de la proposition.",
    "lenient-speed": "@W accepte un chiffre hexadécimal : 0 vaut 1, A à F valent 9 (profils Screen Reader/2).",
    "burst-interrupt": "un nouvel envoi après un silence interrompt la parole en cours (Sonolect).",
}

# Langues par défaut des emplacements de ROM et indicatifs téléphoniques utilisés par @L.
LANGUAGE_CODES = {
    "en": "00044", "en-gb": "00044", "en-us": "00001", "fr": "00033", "de": "00049",
    "es": "00034", "it": "00039", "nl": "00031", "pt": "00351", "sv": "00046",
    "da": "00045", "no": "00047", "fi": "00358", "cy": "10044",
}

SOUND_PAUSE_MS = (60, 120, 250, 500)  # @T : durée selon les deux bits bas (approximation)
SOUND_X_PAUSE_MS = 100  # @Tx : « pause d'environ 100 ms » (manuel 1998)


@dataclass
class DeviceConfig:
    codepage: str = "cp437"
    languages: dict[int, str] = field(default_factory=lambda: {1: "en"})
    extensions: frozenset[str] = frozenset()
    # 'doc' : T = parole en cours ou propositions complètes en attente (TB25, manuel).
    # 'rom' : T aussi quand une proposition inachevée est en cours de réception (ROM 2.01).
    talking_rule: str = "doc"
    version_text: str = "Apolo emu, Apollo 2"
    engine_version: str = "0201"
    rom_version: str = "0404"
    dip_switches: int = 0
    buffer_size: int = 6144  # anneau d'entrée de la ROM 2.01 ; au-delà, un vrai Apollo perd des données
    burst_gap: float = 0.04

    def __post_init__(self) -> None:
        unknown = set(self.extensions) - set(EXTENSIONS)
        if unknown:
            raise ValueError(f"extensions inconnues : {', '.join(sorted(unknown))}")
        if self.talking_rule not in ("doc", "rom"):
            raise ValueError("talking_rule doit valoir 'doc' ou 'rom'")


@dataclass
class Registers:
    """Réglages de l'appareil, valeurs brutes (interrogeables par @c?)."""

    speed: int = 3
    pitch: int = 8
    pitch_step: int = 8
    volume: int = 6
    prosody: int = 3
    word_pause: int = 0
    phrase_pause: int = 0x0B
    voice: int = 1
    speaker: int = 0
    mark_space: int = 0x14
    voicing: int = 8
    source: int = 0
    spell: int = 0
    punct: int = 0
    hyper: int = 0
    phonetic: int = 0
    bank: int = 1
    prosody_params: dict[str, int] = field(default_factory=dict)
    formants: dict[int, int] = field(default_factory=dict)

    def copy(self) -> "Registers":
        return replace(self, prosody_params=dict(self.prosody_params), formants=dict(self.formants))


QUERY_LETTERS = {
    "A": "volume", "B": "voicing", "D": "phrase_pause", "F": "pitch", "H": "hyper",
    "K": "speaker", "M": "mark_space", "P": "punct", "Q": "word_pause", "R": "prosody",
    "S": "spell", "V": "voice", "W": "speed", "X": "phonetic", "$": "source",
}
# C (batterie du Juno, auto-test sur l'Apollo 2), Z (interrupteurs) et = (emplacement) sont traités à part.

Action = Callable[[], None]


@dataclass
class _Spoken:
    utt: Utterance
    marks: list[tuple[str, list[Action]]]
    raw_bytes: int
    started: bool = False
    done: bool = False


@dataclass
class _Immediate:
    actions: list[Action]
    raw_bytes: int


class ApolloDevice:
    def __init__(
        self,
        backend: SpeechBackend,
        reply: Callable[[bytes], None] | None = None,
        config: DeviceConfig | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.config = config or DeviceConfig()
        self.backend = backend
        self.reply_sink = reply
        self.clock = clock
        backend.set_event_sink(self.on_speech_event)
        self._next_uid = 1
        self._next_mark = 1
        self.power_on()

    # ------------------------------------------------------------------ état

    def power_on(self) -> None:
        """Mise sous tension : réglages par défaut, tampons vides."""
        self.live = Registers()  # état effectif (atteint par la parole)
        self.projected = Registers()  # état après les propositions déjà analysées
        self.cmd_char = P.DEFAULT_CMD_CHAR
        self.cmd_mode = False
        self.cmd_buf = bytearray()
        self.clauses = P.ClauseAccumulator()
        self.index_count = 0
        self.index_reset = False
        self.timeline: deque[_Spoken | _Immediate] = deque()
        self.batch: list[_Spoken | _Immediate] = []
        self.ext_pending_echo: int | None = None
        self.last_rx = float("-inf")
        self._overflow_warned = False
        self._pumping = False
        self._pending_mark_actions: dict[str, list[Action]] = {}

    def _table(self) -> tuple[tuple[bytes, str], ...]:
        table = list(P.DEFERRED_PATTERNS)
        ext = self.config.extensions
        if "lenient-speed" in ext:
            table[table.index((b"W#", "speed"))] = P.EXT_LENIENT_SPEED
        table.append(P.SOFT_RESET_PATTERN)
        if "epaulard-index" in ext:
            table.append(P.EXT_EPAULARD_INDEX)
        return tuple(table)

    @property
    def talking(self) -> bool:
        if any(isinstance(e, _Spoken) for e in self.timeline) or self.batch:
            return True
        return self.config.talking_rule == "rom" and self.clauses.pending > 0

    def reply(self, data: bytes) -> None:
        log.debug("RÉPONSE %s", data.hex(" "))
        if self.reply_sink is not None:
            self.reply_sink(data)

    # ------------------------------------------------- étage communication

    def feed(self, data: bytes) -> None:
        """Octets reçus de l'ordinateur, dans l'ordre, en morceaux quelconques."""
        if not data:
            return
        now = self.clock()
        if (
            "burst-interrupt" in self.config.extensions
            and now - self.last_rx > self.config.burst_gap
            and data[0] not in P.MUTE_BYTES
            and self.talking
            and self.clauses.pending == 0
        ):
            log.debug("burst-interrupt : interruption implicite")
            self.mute()
        self.last_rx = now
        for b in data:
            self._receive(b)
        self._flush_batch()

    def _receive(self, b: int) -> None:
        if b in P.MUTE_BYTES:
            self.mute()
            return
        if b == self.cmd_char:
            if self.cmd_mode:
                log.debug("« @ » répété : le premier est perdu (comme sur la ROM)")
            self.cmd_mode = True
            self.cmd_buf.clear()
            return
        if not self.cmd_mode:
            self._to_input(b)
            return
        self.cmd_buf.append(b)
        state = P.immediate_state(bytes(self.cmd_buf))
        if state == "partial":
            return
        self.cmd_mode = False
        if state == "index_query":
            self.reply(b"I" + P.hex_reply(self.index_count) + (b"T" if self.talking else b"M"))
            return
        if state == "index_add":
            if self.index_reset:
                self.index_count = 0
                self.index_reset = False
            self.index_count = (self.index_count + 1) & 0xFF
        # @I+ et toute séquence non immédiate passent dans le tampon d'entrée.
        pending = bytes(self.cmd_buf)
        self._to_input(self.cmd_char)
        for c in pending:
            self._to_input(c)

    def mute(self) -> None:
        """Ctrl-A / Ctrl-X : silence immédiat, tampons vidés, compteur d'index conservé."""
        had_speech = any(isinstance(e, _Spoken) for e in self.timeline)
        self.cmd_mode = False
        self.cmd_buf.clear()
        self.clauses.reset()
        self.cmd_char = P.DEFAULT_CMD_CHAR
        self.index_reset = True
        self.ext_pending_echo = None
        lost = len(self.batch) + sum(1 for e in self.timeline if not (isinstance(e, _Spoken) and e.started))
        self.batch.clear()
        self.timeline.clear()
        self.projected = self.live.copy()
        if had_speech:
            self.backend.cancel()
        if lost:
            log.debug("mute : %d élément(s) de parole abandonné(s)", lost)

    def _to_input(self, b: int) -> None:
        done = self.clauses.push(b, self.cmd_char)
        if done is not None:
            raw, by_cr = done
            self._clause(P.scan_clause(raw, self.cmd_char, self._table(), by_cr))

    # ---------------------------------------------------- étage proposition

    def _clause(self, clause: P.Clause) -> None:
        reg = self.projected
        start: list[Action] = []  # effets au début de la proposition

        # Les commandes de l'étage proposition agissent sur toute la proposition :
        # elles sont appliquées d'abord, à l'état projeté.
        positioned = [cmd for cmd in clause.commands if not self._phrase_command(cmd, reg, start)]

        # Puis le texte, coupé par les commandes synchronisées avec la parole.
        # Un changement de volume ouvre un nouveau segment (nouveaux réglages du moteur).
        segments: list[list] = [[]]
        seg_params: list[VoiceParams] = [self._voice_params(reg)]
        text = clause.text
        cursor = 0
        for cmd in positioned:
            if cmd.position > cursor:
                segments[-1].append(self._decode(text[cursor : cmd.position], reg))
                cursor = cmd.position
            parts = segments[-1]
            v = P.hex_value(cmd.arg)
            if cmd.name == "volume":
                if v >= 0x10:
                    continue
                reg.volume = v
                parts.append(self._new_mark([lambda v=v: setattr(self.live, "volume", v)]))
                new_params = self._voice_params(reg)
                if new_params != seg_params[-1]:
                    if any(isinstance(p, str) for p in parts):
                        segments.append([])
                        seg_params.append(new_params)
                    else:
                        seg_params[-1] = new_params
            elif cmd.name == "voicing":
                if v < 10:
                    reg.voicing = v
                    parts.append(self._new_mark([lambda v=v: setattr(self.live, "voicing", v)]))
            elif cmd.name == "index_mark":
                parts.append(self._new_mark([self._index_spoken]))
            elif cmd.name == "sound":
                if v < 0x10:
                    parts.append(Pause(SOUND_PAUSE_MS[v & 3]))
                    log.info("@T%X : effet sonore remplacé par un silence", v)
                elif upcase_char(cmd.arg) == "X":
                    parts.append(Pause(SOUND_X_PAUSE_MS))
            elif cmd.name == "echo":  # extension word-echo
                parts.append(self._new_mark([self._echo_action(cmd.arg)]))
            elif cmd.name == "version":
                parts.append(" " + self.config.version_text + " ")
        if len(text) > cursor:
            segments[-1].append(self._decode(text[cursor:], reg))

        for i, (parts, vp) in enumerate(zip(segments, seg_params)):
            self._enqueue(self._make_entry(vp, parts, start if i == 0 else [], clause.raw_length if i == 0 else 0))
        if "epaulard-index" in self.config.extensions:
            self._epaulard_clause(clause)
        self._check_backlog()

    def _phrase_command(self, cmd: P.Command, reg: Registers, start: list[Action]) -> bool:
        """Applique une commande de l'étage proposition. Renvoie False si elle est positionnée."""
        name = cmd.name
        v = P.hex_value(cmd.arg)
        if name in ("volume", "voicing", "index_mark", "sound", "version"):
            return False
        if name == "echo":
            if "word-echo" in self.config.extensions:
                return False
            start.append(self._echo_action(cmd.arg))
        elif name == "speed":
            if "lenient-speed" in self.config.extensions:
                v = 1 if v == 0 else min(v, 9) if v < 0x10 else v
            if 1 <= v <= 9:
                self._set(reg, start, speed=v)
            else:
                log.info("@W%s rejeté par la ROM (plage 1-9)", chr(cmd.arg))
        elif name == "pitch":
            if cmd.arg == ord("+"):
                self._set(reg, start, pitch_step=0x10)
            elif cmd.arg == ord("-"):
                self._set(reg, start, pitch_step=0)
            elif v < 0x10:
                self._set(reg, start, pitch=v, pitch_step=8)
        elif name == "phrase_pause":
            if v < 0x10:
                self._set(reg, start, phrase_pause=v)
        elif name == "word_pause":
            if v < 10:
                self._set(reg, start, word_pause=v)
        elif name == "prosody":
            if v < 8:
                self._set(reg, start, prosody=v)
        elif name == "prosody_param":
            letter = chr(P.upcase(cmd.raw[1]))
            if "A" <= letter <= "Z":
                value = ((P.hex_value(cmd.raw[2]) << 4) + P.hex_value(cmd.raw[3])) & 0xFF
                reg.prosody_params[letter] = value
                start.append(lambda letter=letter, value=value: self.live.prosody_params.__setitem__(letter, value))
        elif name == "mark_space":
            hi, lo = P.hex_value(cmd.raw[1]), P.hex_value(cmd.raw[2])
            if hi < 4 and lo < 0x10:
                self._set(reg, start, mark_space=(hi << 4) | lo)
        elif name in ("spell", "punct", "hyper", "phonetic", "speaker"):
            if v <= 1:
                self._set(reg, start, **{name: v})
                if name == "hyper" and v:
                    log.info("@H1 : l'hypermode n'est pas émulé")
                if name == "phonetic" and v:
                    log.info("@X1 : le mode phonétique n'est pas émulé ; le texte est lu tel quel")
        elif name == "source":
            if v < 8:
                self._set(reg, start, source=v)
        elif name == "voice":
            if v == 0:
                self._set(reg, start, voice=0)
            elif v <= 6:
                # Préréglages : table du locuteur et source (ROM) ; voisement, rapport cyclique
                # et hauteur propres à chaque voix inconnus, donc conservés.
                self._set(reg, start, voice=v, speaker=1 if v >= 4 else 0, source=7 if v >= 4 else 0)
        elif name == "formant":
            d = P.hex_value(cmd.raw[1])
            digits = cmd.raw[2:-1]
            sign = cmd.raw[-1]
            if len(digits) == 2 and d < 10:
                value = (P.hex_value(digits[0]) << 4) + P.hex_value(digits[1])
                if value < 0x100:
                    reg.formants[d] = value if sign == ord("+") else -value
            # La forme à un chiffre est reconnue mais sans effet (ROM).
        elif name == "bank":
            if v in self.config.languages:
                self._set(reg, start, bank=v)
            else:
                log.info("@=%d : emplacement de ROM vide, ignoré", v)
        elif name == "query":
            start.append(lambda letter=cmd.raw[0]: self._query(letter))
        elif name == "languages":
            start.append(self._list_languages)
        elif name == "soft_reset":
            fresh = Registers(bank=reg.bank)
            self._set(reg, start, **{k: getattr(fresh, k) for k in QUERY_LETTERS.values()})
        elif name == "ext_epaulard_index":
            pass  # traité dans _epaulard_clause
        elif name == "ignore":
            log.debug("@%s sans effet (ROM 2)", cmd.raw.decode("latin-1"))
        else:  # pragma: no cover - table et gestionnaires sont tenus en accord
            log.warning("commande sans gestionnaire : %s", cmd)
        return True

    def _set(self, reg: Registers, start: list[Action], **values: int) -> None:
        for k, v in values.items():
            setattr(reg, k, v)

        def apply(values: dict[str, int] = dict(values)) -> None:
            for k, v in values.items():
                setattr(self.live, k, v)

        start.append(apply)

    def _epaulard_clause(self, clause: P.Clause) -> None:
        """Extension epaulard-index : la marque revient quand la parole jusqu'au CR est finie."""
        for cmd in clause.commands:
            if cmd.name == "ext_epaulard_index":
                self.ext_pending_echo = cmd.arg
        if clause.ended_by_cr and self.ext_pending_echo is not None:
            echo = self._echo_action(self.ext_pending_echo)
            self.ext_pending_echo = None
            self._enqueue(_Immediate([echo], 0))

    # ------------------------------------------------------------- actions

    def _echo_action(self, arg: int) -> Action:
        return lambda: self.reply(bytes((arg,)))

    def _index_spoken(self) -> None:
        if self.index_count:
            self.index_count -= 1

    def _query(self, letter: int) -> None:
        ch = chr(P.upcase(letter))
        if ch in QUERY_LETTERS:
            value = getattr(self.live, QUERY_LETTERS[ch])
        elif ch == "C":
            value = 0  # échec de l'auto-test : jamais
        elif ch == "Z":
            value = self.config.dip_switches
        elif ch == "=":
            value = self.live.bank
        else:
            log.info("@%s? : réglage non interrogeable, pas de réponse", ch)
            return
        self.reply(ch.encode("latin-1") + P.hex_reply(value))

    def _list_languages(self) -> None:
        out = bytearray(b"L" + P.hex_reply(7) + P.hex_reply(14))
        for slot in range(1, 8):
            lang = self.config.languages.get(slot)
            if lang is None:
                out += b"0" * 14  # contenu réel d'un emplacement vide : inconnu
            else:
                code = LANGUAGE_CODES.get(lang.lower(), "00000")
                out += (code + "0" + self.config.engine_version + self.config.rom_version).encode("ascii")
        out.append(P.CR)
        self.reply(bytes(out))

    # ------------------------------------------------------ chronologie

    def _new_mark(self, actions: list[Action]) -> Mark:
        name = f"m{self._next_mark}"
        self._next_mark += 1
        self._pending_mark_actions[name] = actions
        return Mark(name)

    def _voice_params(self, reg: Registers) -> VoiceParams:
        return VoiceParams(
            speed=reg.speed,
            pitch=reg.pitch,
            pitch_step=reg.pitch_step,
            volume=reg.volume,
            voice=reg.voice,
            speaker=reg.speaker,
            punct=reg.punct,
            spell=reg.spell,
            language=self.config.languages.get(reg.bank, "en"),
        )

    def _decode(self, data: bytes, reg: Registers) -> str:
        out = []
        for ch in data.decode(self.config.codepage, errors="replace"):
            if ord(ch) < 0x20 or ord(ch) == 0x7F:
                out.append(" ")  # la ROM traite les codes de contrôle comme des espaces
            elif ch == "@" and not reg.punct:
                out.append(" ")  # caractère de commande resté dans le texte : muet sans @P1
            else:
                out.append(ch)
        return "".join(out)

    def _make_entry(self, vp: VoiceParams, parts: list, start: list[Action], raw: int) -> _Spoken | _Immediate:
        # Les actions des marques sont retrouvées par nom.
        marks: list[tuple[str, list[Action]]] = []
        if start:
            head = Mark(f"m{self._next_mark}")
            self._next_mark += 1
            parts = [head] + parts
            marks.append((head.name, start))
        actions_by_name = self._pending_mark_actions
        for p in parts:
            if isinstance(p, Mark) and p.name in actions_by_name:
                marks.append((p.name, actions_by_name.pop(p.name)))
        spoken = not vp.silent and self._has_content(parts, vp)
        if not spoken:
            return _Immediate([a for _, acts in marks for a in acts], raw)
        utt = Utterance(self._next_uid, vp, list(parts))
        self._next_uid += 1
        return _Spoken(utt, marks, raw)

    @staticmethod
    def _has_content(parts: list, vp: VoiceParams) -> bool:
        for p in parts:
            if isinstance(p, Pause):
                return True
            if isinstance(p, str):
                for ch in p:
                    if ch.isalnum() or (vp.punct and not ch.isspace()):
                        return True
        return False

    def _enqueue(self, entry: _Spoken | _Immediate) -> None:
        """Ajoute au lot ; fusionne les énoncés consécutifs aux réglages identiques.

        Un seul message fluide pour le moteur, avec des marques aux bons endroits. Les
        propositions muettes situées entre deux textes fusionnés deviennent une marque
        à la jonction ; en fin de lot, elles restent des éléments séparés, exécutés à
        la fin effective de la parole (événement END).
        """
        if isinstance(entry, _Spoken):
            k = len(self.batch)
            while k and isinstance(self.batch[k - 1], _Immediate):
                k -= 1
            if k and isinstance(self.batch[k - 1], _Spoken) and self.batch[k - 1].utt.params == entry.utt.params:
                prev = self.batch[k - 1]
                for imm in self.batch[k:]:
                    name = f"m{self._next_mark}"
                    self._next_mark += 1
                    prev.utt.parts.append(Mark(name))
                    prev.marks.append((name, imm.actions))
                    prev.raw_bytes += imm.raw_bytes
                del self.batch[k:]
                prev.utt.parts.extend(entry.utt.parts)
                prev.marks.extend(entry.marks)
                prev.raw_bytes += entry.raw_bytes
                return
        self.batch.append(entry)

    def _flush_batch(self) -> None:
        batch, self.batch = self.batch, []
        for entry in batch:
            self.timeline.append(entry)
            if isinstance(entry, _Spoken):
                self.backend.speak(entry.utt)
        self._pump()

    def _pump(self) -> None:
        """Exécute les éléments prêts en tête de chronologie, dont les actions des
        propositions muettes qui attendaient la fin de la parole précédente."""
        if self._pumping:
            return
        self._pumping = True
        try:
            while self.timeline:
                head = self.timeline[0]
                if isinstance(head, _Immediate):
                    self.timeline.popleft()
                    for action in head.actions:
                        action()
                elif head.done:
                    self.timeline.popleft()
                else:
                    break
        finally:
            self._pumping = False

    def on_speech_event(self, ev: SpeechEvent) -> None:
        """Progression signalée par le moteur vocal."""
        idx = next((i for i, e in enumerate(self.timeline) if isinstance(e, _Spoken) and e.utt.uid == ev.uid), None)
        if idx is None:
            log.debug("événement ignoré (énoncé abandonné) : %s", ev)
            return
        # Le moteur parle dans l'ordre : tout ce qui précède est terminé.
        for i in range(idx):
            prev = self.timeline[i]
            if isinstance(prev, _Spoken) and not prev.done:
                self._finish(prev)
        entry = self.timeline[idx]
        assert isinstance(entry, _Spoken)
        if ev.kind == "begin":
            entry.started = True
        elif ev.kind == "mark":
            entry.started = True
            self._fire_until(entry, ev.mark)
        elif ev.kind == "end":
            self._finish(entry)
        elif ev.kind == "cancel":
            entry.marks.clear()
            entry.done = True
        self._pump()

    def _fire_until(self, entry: _Spoken, mark: str | None) -> None:
        names = [n for n, _ in entry.marks]
        if mark not in names:
            log.debug("marque inconnue %r", mark)
            return
        upto = names.index(mark) + 1
        fired, entry.marks = entry.marks[:upto], entry.marks[upto:]
        for _, actions in fired:
            for action in actions:
                action()

    def _finish(self, entry: _Spoken) -> None:
        entry.started = True
        fired, entry.marks = entry.marks, []
        entry.done = True
        for _, actions in fired:
            for action in actions:
                action()

    def _check_backlog(self) -> None:
        backlog = self.clauses.pending + sum(
            e.raw_bytes for e in self.timeline if not (isinstance(e, _Spoken) and e.started)
        ) + sum(e.raw_bytes for e in self.batch)
        if backlog > self.config.buffer_size and not self._overflow_warned:
            self._overflow_warned = True
            log.warning(
                "%d octets en attente : un véritable Apollo II (tampon de %d octets) aurait perdu des données",
                backlog, self.config.buffer_size,
            )
        elif backlog <= self.config.buffer_size // 2:
            self._overflow_warned = False


def upcase_char(b: int) -> str:
    return chr(P.upcase(b))
