"""Pure Apollo II protocol tables and functions.

Tables follow UK ROM V2.01 4.04 as described by the Dolphin-Apollo-II-Reborn
decompilation, cross-checked against Dolphin documentation (docs/protocol.md).
Nothing here depends on the transport or speech engine.
"""

from __future__ import annotations

from dataclasses import dataclass

CTRL_A = 0x01
CTRL_X = 0x18
MUTE_BYTES = frozenset((CTRL_A, CTRL_X))
CR = 0x0D
SPACE = 0x20
DEFAULT_CMD_CHAR = 0x40  # '@'

# Clause terminators (ROM: boot_get_clause / take_byte).
CLAUSE_PUNCT = frozenset(b".,:;!?")
CLAUSE_SPACE_END = 220  # from this point, a space or @ ends the clause
CLAUSE_FULL = 250  # maximum clause length

HEX_DIGITS = b"0123456789ABCDEF"


def upcase(b: int) -> int:
    """ASCII equivalent of cmd_case_map (the only part used by patterns)."""
    if 0x61 <= b <= 0x7A:
        return b - 0x20
    if b == 0x5B:
        return 0x28
    if b == 0x5D:
        return 0x29
    if b < 0x20 and b not in (CR, 0x1B):
        return SPACE
    if b == 0x7F:
        return SPACE
    return b


def hex_value(b: int) -> int:
    """Protocol numeric value, including out-of-range results.

    Intervals describe observed inputs and outputs rather than simulating
    the synthesizer processor's arithmetic instructions.
    """
    a = upcase(b)
    if ord(":") <= a <= ord("@"):
        return 35
    if ord("A") <= a <= 192:
        return a - ord("A") + 10
    return (a - ord("0")) % 256


def hex_reply(value: int) -> bytes:
    """Byte value as two hexadecimal digits, low nibble first (ser_tx_hex)."""
    value &= 0xFF
    return bytes((HEX_DIGITS[value & 0x0F], HEX_DIGITS[value >> 4]))


# Patterns: '*' matches any character, '#' a digit; compared after upcase().
IMMEDIATE_PATTERNS: tuple[tuple[bytes, str], ...] = (
    (b"I+", "index_add"),
    (b"I?", "index_query"),
)

# Deferred table in ROM order (first match wins).
DEFERRED_PATTERNS: tuple[tuple[bytes, str], ...] = (
    (b"?", "version"),
    (b"*?", "query"),
    (b"A*", "volume"),
    (b"D*", "phrase_pause"),
    (b"E*", "echo"),
    (b"F*", "pitch"),
    (b"H#", "hyper"),
    (b"M**", "mark_space"),
    (b"P#", "punct"),
    (b"Q#", "word_pause"),
    (b"R#", "prosody"),
    (b"R***", "prosody_param"),
    (b"S#", "spell"),
    (b"V#", "voice"),
    (b"W#", "speed"),
    (b"X#", "phonetic"),
    (b"U#*+", "formant"),
    (b"U#*-", "formant"),
    (b"U#**+", "formant"),
    (b"U#**-", "formant"),
    (b"$#", "source"),
    (b"B#", "voicing"),
    (b"I+", "index_mark"),
    (b"T*", "sound"),
    (b"=#", "bank"),
    (b"L", "languages"),
    (b"K#", "speaker"),
    (b"G#", "ignore"),
    (b"I^", "ignore"),
    (b"+*", "ignore"),
)

# Documented (1998 manual) but absent from ROM 2.01; appended last.
SOFT_RESET_PATTERN = (b"J", "soft_reset")

# Extensions disabled by default (docs/extensions.md), always after authentic patterns.
EXT_EPAULARD_INDEX = (b"I*", "ext_epaulard_index")
EXT_LENIENT_SPEED = (b"W*", "speed")


def match_pattern(pattern: bytes, data: bytes, pos: int) -> int:
    """Matched length of `pattern` at `data[pos:]`, or 0.

    Patterns extending past the clause end are not recognized. The ROM reads
    residual buffer contents there: a documented approximation.
    """
    if pos + len(pattern) > len(data):
        return 0
    for i, p in enumerate(pattern):
        u = upcase(data[pos + i])
        if p == 0x2A:  # *
            continue
        if p == 0x23:  # #
            if not 0x30 <= u <= 0x39:
                return 0
            continue
        if u != p:
            return 0
    return len(pattern)


def match_table(table: tuple[tuple[bytes, str], ...], data: bytes, pos: int) -> tuple[str, int] | None:
    for pattern, name in table:
        n = match_pattern(pattern, data, pos)
        if n:
            return name, n
    return None


def immediate_state(buf: bytes) -> str | None:
    """Immediate-command state: 'partial', command name, or None if no pattern matches."""
    partial = False
    for pattern, name in IMMEDIATE_PATTERNS:
        if len(buf) > len(pattern):
            continue
        if all(upcase(b) == p for b, p in zip(buf, pattern)):
            if len(buf) == len(pattern):
                return name
            partial = True
    return "partial" if partial else None


@dataclass(frozen=True)
class Command:
    """Deferred command recognized within a clause."""

    name: str
    raw: bytes  # recognized bytes after command character, preserving case
    position: int  # position in clause text, before which the command applies

    @property
    def arg(self) -> int:
        """Last recognized byte: argument as received by the ROM handler."""
        return self.raw[-1]


@dataclass
class Clause:
    """Parsed clause: raw text bytes and positioned commands."""

    text: bytes
    commands: list[Command]
    ended_by_cr: bool
    raw_length: int


def scan_clause(
    raw: bytes,
    cmd_char: int,
    table: tuple[tuple[bytes, str], ...],
    ended_by_cr: bool = False,
) -> Clause:
    """cmd_scan_clause: remove recognized commands; leave unknown commands in text."""
    text = bytearray()
    commands: list[Command] = []
    x = 0
    while x < len(raw):
        b = raw[x]
        x += 1
        if b != cmd_char:
            text.append(b)
            continue
        found = match_table(table, raw, x)
        if found is None:
            text.append(b)
            continue
        name, n = found
        commands.append(Command(name, bytes(raw[x : x + n]), len(text)))
        x += n
    return Clause(bytes(text), commands, ended_by_cr, len(raw))


class ClauseAccumulator:
    """Split the stream into clauses (boot_get_clause).

    Complete clauses are returned; bytes of an incomplete clause wait
    indefinitely, just as on the device.
    """

    def __init__(self) -> None:
        self.buf = bytearray()
        self.carry: int | None = None

    def reset(self) -> None:
        self.buf.clear()
        self.carry = None

    @property
    def pending(self) -> int:
        return len(self.buf)

    def push(self, b: int, cmd_char: int) -> tuple[bytes, bool] | None:
        """Add a byte; return (clause, ended_by_CR) when complete."""
        if not self.buf and self.carry is not None:
            self.buf.append(self.carry)
            self.carry = None
        if b == CR:
            return self._end(True)
        self.buf.append(b)
        n = len(self.buf) + 1  # the ROM counts boot_clause's initial space
        if b in CLAUSE_PUNCT or n >= CLAUSE_FULL:
            return self._end(False)
        if n >= CLAUSE_SPACE_END:
            if b == SPACE:
                return self._end(False)
            if b == cmd_char:
                self.buf.pop()
                self.carry = b
                return self._end(False)
        return None

    def _end(self, by_cr: bool) -> tuple[bytes, bool]:
        clause = bytes(self.buf) + b" "
        self.buf.clear()
        return clause, by_cr
