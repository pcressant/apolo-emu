"""Tables et fonctions pures du protocole Apollo II.

Les tables suivent la ROM UK V2.01 4.04 telle que la décrit la décompilation
« Dolphin-Apollo-II-Reborn », recoupée avec la documentation Dolphin (voir
docs/protocole.md). Rien ici ne dépend du transport ni du moteur vocal.
"""

from __future__ import annotations

from dataclasses import dataclass

CTRL_A = 0x01
CTRL_X = 0x18
MUTE_BYTES = frozenset((CTRL_A, CTRL_X))
CR = 0x0D
SPACE = 0x20
DEFAULT_CMD_CHAR = 0x40  # « @ »

# Fin de proposition (ROM : boot_get_clause / take_byte).
CLAUSE_PUNCT = frozenset(b".,:;!?")
CLAUSE_SPACE_END = 220  # à partir d'ici, une espace ou un @ termine la proposition
CLAUSE_FULL = 250  # longueur maximale d'une proposition

HEX_DIGITS = b"0123456789ABCDEF"


def upcase(b: int) -> int:
    """Équivalent de cmd_case_map pour la partie ASCII (la seule utile aux motifs)."""
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
    """cmd_hex_value : 0-9 pour les chiffres, 10-35 pour A-Z, valeurs hors plage sinon."""
    a = upcase(b)
    if 0x3A <= a < 0x41:
        a = 0x5A  # « : » à « @ » comptent comme Z
    d = (a - 0x41) & 0xFF
    return (d + 0x11) & 0xFF if d & 0x80 else (d + 0x0A) & 0xFF


def hex_reply(value: int) -> bytes:
    """Valeur d'un octet en deux chiffres hexadécimaux, quartet bas d'abord (ser_tx_hex)."""
    value &= 0xFF
    return bytes((HEX_DIGITS[value & 0x0F], HEX_DIGITS[value >> 4]))


# Motifs : « * » n'importe quel caractère, « # » un chiffre ; comparés après upcase().
IMMEDIATE_PATTERNS: tuple[tuple[bytes, str], ...] = (
    (b"I+", "index_add"),
    (b"I?", "index_query"),
)

# Table différée, dans l'ordre de la ROM (la première correspondance l'emporte).
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

# Documentée (manuel 1998) mais absente de la ROM 2.01 ; ajoutée en dernier.
SOFT_RESET_PATTERN = (b"J", "soft_reset")

# Extensions désactivées par défaut (docs/extensions.md), toujours après les motifs authentiques.
EXT_EPAULARD_INDEX = (b"I*", "ext_epaulard_index")
EXT_LENIENT_SPEED = (b"W*", "speed")


def match_pattern(pattern: bytes, data: bytes, pos: int) -> int:
    """Longueur reconnue de `pattern` à `data[pos:]`, ou 0.

    Un motif qui dépasse la fin de la proposition n'est pas reconnu. La ROM lit
    alors le contenu résiduel de son tampon : approximation documentée.
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
    """Mode commande immédiate : 'partial', le nom de la commande, ou None si aucun motif ne convient."""
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
    """Commande différée reconnue dans une proposition."""

    name: str
    raw: bytes  # octets reconnus après le caractère de commande, sans changement de casse
    position: int  # position dans le texte de la proposition (avant laquelle elle s'applique)

    @property
    def arg(self) -> int:
        """Dernier octet reconnu : l'argument tel que le reçoit le gestionnaire de la ROM."""
        return self.raw[-1]


@dataclass
class Clause:
    """Proposition analysée : texte (octets bruts) et commandes positionnées."""

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
    """cmd_scan_clause : retire les commandes reconnues ; une commande inconnue reste dans le texte."""
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
    """Découpage du flux en propositions (boot_get_clause).

    feed() renvoie les propositions complètes ; les octets d'une proposition
    inachevée restent en attente indéfiniment, comme sur l'appareil.
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
        """Ajoute un octet ; renvoie (proposition, terminée_par_CR) si elle est complète."""
        if not self.buf and self.carry is not None:
            self.buf.append(self.carry)
            self.carry = None
        if b == CR:
            return self._end(True)
        self.buf.append(b)
        n = len(self.buf) + 1  # la ROM compte l'espace initiale de boot_clause
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
