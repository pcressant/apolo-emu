English | [Français](compatibilite-fr.md)

# Compatibility matrix

No actual Apollo II was available. “Verified” therefore means:

- At least two independent sources agree ([protocol.md](protocol.md)).
- An automated test covers the implementation.

**Statuses:**

| Status | Meaning |
|---|---|
| VERIFIED | implemented and verified as defined above |
| UNVERIFIED | implemented, but not verified on actual Apollo II hardware: one source or deduction |
| PARTIAL | partially emulated |
| NOT IMPLEMENTED | not implemented |
| UNKNOWN | unknown or insufficiently documented |

**Sources:**

| Code | Source |
|---|---|
| DOC | Dolphin documentation |
| ROM | ROM 2.01 decompilation |
| PIL | historical drivers and software |

## Connection and flow

| Feature | Status | Sources | Notes |
|---|---|---|---|
| Ctrl-X, Ctrl-A: mute | VERIFIED | DOC, ROM, PIL | clears buffers, stops speech, preserves index counter; works within an `@` sequence |
| CR: clause end | VERIFIED | DOC, ROM, PIL | |
| `. , : ; ! ?`: clause end | VERIFIED | DOC (TB25), ROM | |
| 220/250-byte limits, carried-over `@` | UNVERIFIED | ROM | |
| Text without CR or punctuation | VERIFIED | DOC, ROM | waits indefinitely as on hardware; prototypes spoke after 0.3 s |
| Sequential reading, effects at each clause start | UNVERIFIED | DOC (TB25 §6.2), ROM | deduction; see protocol.md §2.3 |
| Control codes treated as spaces | UNVERIFIED | ROM | |
| Code page | PARTIAL | ROM, PIL | configurable, CP437 default; only ASCII uses the ROM's mapping rules |
| Alternating RTS/CTS, CTS drop after each byte | NOT IMPLEMENTED | DOC | impossible over a socket; QEMU UART sees CTS asserted (MSR = 0xB0, measured) |
| NAK (0x15) on empty read | NOT IMPLEMENTED | DOC, ROM | requires knowledge of RTS |
| Input buffer overflow | PARTIAL | DOC, ROM | logged without data loss |
| Parallel connection, PC 2 card, NULL/SOH/ACK protocol | NOT IMPLEMENTED | DOC | out of scope: serial port only |
| Power-on sound/beep, self-test | NOT IMPLEMENTED | DOC | |

## Commands

| Command | Parsing | Rendering | Sources | Notes |
|---|---|---|---|---|
| `@I?` | VERIFIED | — | DOC, ROM, PIL | immediate reply: `I` + 2 hex digits, low nibble first + `T`/`M` |
| `T`/`M` while receiving unpunctuated text | UNKNOWN | — | DOC ≠ ROM | `--talking-rule doc` (default) or `rom` |
| `@I+` | VERIFIED | — | DOC, ROM, PIL | incremented on reception, decremented at an SSML mark; reset on first `@I+` after muting |
| `@Ec` | VERIFIED | — | DOC, ROM, PIL | raw byte returned; echoes from discarded clauses are lost |
| `@E` timing | UNVERIFIED | — | DOC, ROM | at the start of its clause; `--extension word-echo` gives the exact position |
| `@c?` | VERIFIED | — | DOC, ROM | letters `A B C D F H K M P Q R S V W X Z = $`; manual example `A60` reproduced |
| `@C?` (Juno battery) | UNVERIFIED | — | DOC, ROM | returns 0: no self-test fault |
| `@Z?` (switches) | UNVERIFIED | — | ROM | returns 0 |
| `@L` | PARTIAL | — | DOC, ROM | exact format; record contents approximated (country code, configurable versions, empty banks set to `0`) |
| `@?` | PARTIAL | PARTIAL | DOC, ROM | speaks configurable text (`--version-text`), not actual versions |
| `@Wd` | VERIFIED | PARTIAL | DOC, ROM, PIL | 1–9; `@W0` and `@Wb` rejected as in the ROM; approximate rate |
| `@Fh` | VERIFIED | PARTIAL | DOC, ROM | approximate pitch |
| `@F+`, `@F-` | UNVERIFIED | PARTIAL | DOC, ROM | small, non-cumulative offset (ROM) |
| `@Ah` | VERIFIED | PARTIAL | DOC, ROM | synchronized with speech (splits message); Apollo I's same-named `@A` is not emulated |
| `@Vd` | VERIFIED | PARTIAL | DOC, ROM | SSIP voice type; individual preset voice settings unknown |
| `@V0` | VERIFIED | VERIFIED | DOC, ROM | speech disabled; echoes and indexes continue |
| `@Pb` | VERIFIED | PARTIAL | DOC, ROM | `PUNCTUATION all` or `none`; punctuation names come from engine |
| `@Sb` | VERIFIED | PARTIAL | DOC, ROM | `SPELLING`; ROM's automatic spelling of vowel-less words not reproduced |
| `@=d,` | VERIFIED | PARTIAL | DOC, ROM | changes bank language (`--languages`); empty banks ignored; ROM change without reset |
| `@Kb` | VERIFIED | PARTIAL | DOC, ROM | contributes to voice type |
| `@Ro`, `@R` letter + hex | UNVERIFIED | NOT IMPLEMENTED | DOC, ROM | stored, queryable, no audible effect |
| `@Qd`, `@Dh` | VERIFIED | NOT IMPLEMENTED | DOC, ROM | stored and queryable; pauses not rendered |
| `@Bd` | VERIFIED | NOT IMPLEMENTED | DOC, ROM | synchronized with speech; stored |
| `@Mhh`, `@$o`, `@u d hh±` | UNVERIFIED | NOT IMPLEMENTED | DOC, ROM | stored; one-digit `@u` recognized without effect (ROM); `@M` default: hex 14 (ROM), 16 (manual) |
| `@Hb` | VERIFIED | NOT IMPLEMENTED | DOC, ROM | hypermode not emulated |
| `@Xb` | VERIFIED | NOT IMPLEMENTED | DOC, ROM | phonetic mode not emulated; text read as received |
| `_K_AE_T` phonemes in text | NOT IMPLEMENTED | NOT IMPLEMENTED | DOC | read as text |
| `@Th` | VERIFIED | PARTIAL | DOC, ROM | effects replaced with 60–500 ms pauses |
| `@Tx` | UNVERIFIED | VERIFIED | DOC, ROM | 100 ms pause |
| `@J` | UNVERIFIED | — | DOC | soft reset, documented in 1998, absent from ROM 2.01 |
| `@Gb`, `@+c`, `@I^` | VERIFIED | — | DOC, ROM | recognized, no effect (ROM 2) |
| `@Y m r p b` | NOT IMPLEMENTED | — | DOC | baud rate change: irrelevant over a socket; remains text as in ROM 2.01 |
| unrecognized command (`@wb`, `@IA`, `@@44-`…) | VERIFIED | UNVERIFIED | ROM | remains text as on hardware; `@` is silent without `@P1` |
| `@!c` (Apollo I) | NOT IMPLEMENTED | — | DOC | escape character: no effect on Apollo II (`@+c` ignored) |
| `@@dh±` (Apollo I) | NOT IMPLEMENTED | — | DOC | replaced by `@u` on Apollo II |
| `@T` self-test, `@A` amplitude stepping, `@Vb` speech on/off (Apollo I) | NOT IMPLEMENTED | — | DOC | same names: only Apollo II meanings are emulated |
