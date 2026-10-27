English | [Français](protocole-fr.md)

# Apollo II protocol — current knowledge

This document records what is known about the Apollo II protocol. Written during phase 1, it is the
implementation reference, identifying each fact's source and confidence level. Sources are listed
in [references.md](references.md).

## Confidence levels

| Code | Meaning |
|---|---|
| **[DOC]** | Confirmed by historical Dolphin documentation: APOLLO.TXT (1989/1992), Technical Bulletin 25 (APOLLO2.TXT, 1993), *Series 2 Synthesizers User Guide* (1998). |
| **[ROM]** | Observed in the UK V2.01 4.04 firmware decompilation (*Dolphin-Apollo-II-Reborn*). A secondary source produced with LLM assistance and validated against the ROM frame by frame. Covers one ROM version. |
| **[PIL]** | Observed in an existing driver: Speakup, emacspeak-ss, Screen Reader/2 profile, Sonolect, `pc486` and `os2` prototypes. |
| **[DED]** | Deduced through analysis or cross-checking. |
| **[APP]** | Necessary emulator approximation. |
| **[INC]** | Unknown or insufficiently documented. |

The original source codes are retained across both language versions for traceability.

## 1. Serial connection

- Default format: 9600 baud, 8 data bits, no parity, 1 stop bit [DOC] [PIL]
  (Speakup, emacspeak, IBM, Épaulard).
- **Apollo I:** jumper-selectable 300, 1200, 9600 or 19200 baud [DOC].
- **Apollo II:** software selection with `@Y`: 300–57600 baud, parity, 7 or 8 bits, then 5 synchronization
  bytes [DOC, 1998 manual]. `@Y` is absent from the ROM 2.01 command table [ROM].
- **Alternating, bidirectional RTS/CTS handshaking** [DOC, TB25 §5.1; manual appendix 6]:
  - The PC is the link master.
  - **To transmit**, it raises RTS and waits for CTS. Apollo briefly lowers CTS after each received byte.
  - **To read**, it lowers RTS. Apollo raises CTS while transmitting, then lowers it. If nothing is pending,
    Apollo sends NAK (0x15) [DOC 1998] [ROM].
  - DSR appears only in the 1998 manual's pinout, not in the described protocols [DOC].
  - Actual signal polarity is uncertain: James Van Zandt interprets “raise” as “assert” [PIL emacspeak] [INC].
- The firmware has no “buffer full” signal. Busy (CTS) is active only while processing a byte,
  and the input ring has no overflow check [ROM].
  - APOLLO.TXT gives an 8 KB Apollo I buffer; excess data is lost [DOC].
  - The ROM 2.01 ring occupies about 6 KB ($2100–$38FF) [ROM].
- **Speakup:** forces CRTSCTS and never reads the link; when the tty fills, pulses RTS and waits 40 s [PIL].
- **Sonolect and Épaulard** do not use hardware flow control [PIL].
- **Screen Reader/2** requires CTS and DSR for output: OS/2's COM.SYS waits for them [PIL os2].

### What QEMU does (socket chardev)

- Unix sockets carry only bytes. QEMU does not forward the guest's RTS/DTR to the device or let the device
  drive CTS, DSR or DCD.
- Without `TIOCMGET`, the emulated UART retains its reset MSR: DCD, DSR and CTS permanently asserted
  [PIL os2] [DED, `hw/char/serial.c` analysis].
- QEMU does not pace bytes at the selected baud rate. It reads the socket only while its receive FIFO
  has space [DED].
- The `os2` project's QEMU patch (`tools/qemu-serial-loopback-msr.patch`) fixes missing MSR delta bits
  and MSI interrupts on entering loopback (MCR.LOOP). COM.SYS needs these to detect CTS and DSR.
  **This is QEMU behavior, not Apollo behavior.**

**Consequences for Apolo-emu [APP]:**

- Hardware flow control cannot be emulated or observed: CTS is always seen as asserted.
- The emulator cannot throttle the guest. It accepts all input and can only log that real hardware
  would have overflowed.
- Empty-read NAK is meaningless without RTS and is not emulated.

## 2. Two processing stages

This distinction is central to Apolo-emu's design.

### 2.1 Communication stage (on receipt of each byte)

Confirmed by [DOC, TB25 §6.2.1], detailed by [ROM].

- **Ctrl-A (0x01) or Ctrl-X (0x18): mute.**
  - Clear the input ring and stop speech immediately.
  - Discard the current clause.
  - Restore `@` as the command character.
  - Preserve the index counter, with a flag to reset on the next `@I+` [DOC] [ROM].
  - This works even within an `@` sequence [ROM].
  - Replies already queued in the output ring are not erased [ROM].
- **`@`: enter immediate-command mode.**
  - Compare subsequent bytes case-insensitively against `I+` and `I?`, the only immediate patterns [ROM].
    TB25 also lists `@=n` as immediate [DOC], but ROM 2.01 treats it as deferred [ROM].
  - `@I?` replies **immediately** with `I` + counter + `T` or `M`, leaving no text [DOC] [ROM].
  - `@I+`: the first after muting resets the counter. The counter then increments by 1, and `@I+`
    passes into the text for decrementing during speech [DOC] [ROM].
  - **Every other sequence**, e.g. `@e`, `@W`, `@IA`, passes unchanged into the input ring [ROM].
  - A second `@` restarts command mode: the first is lost [ROM].
- **Every other byte** enters the input ring [ROM].

### 2.2 Clause stage (also called “phrase” in the documentation)

Confirmed by [DOC] (APOLLO.TXT, TB25 §6.2), detailed by [ROM].

- **Clause terminators** [ROM]:
  - CR, which is not retained;
  - any of `.` `,` `:` `;` `!` `?`;
  - a length of 250 bytes;
  - from 220 bytes onward, a space or `@`; in the latter case, carry `@` into the next clause.
  - A trailing space is appended to the clause.
- APOLLO.TXT requires CR for speech; TB25 refers to not yet having received a comma or period [DOC].
  **Text without CR or punctuation waits indefinitely** [DED].
- Reading is **sequential** [ROM]: parse a clause, convert it, speak it **to completion**, then move on.
- **Deferred `@` commands** are recognized while parsing the clause [ROM]:
  - Match a fixed ordered table against uppercase-mapped text; the first match wins.
  - `*` matches any character; `#` matches a digit.
  - Remove recognized commands from the text.
  - **Unrecognized commands remain in the text**, including `@`.
- **Execution timing** [DOC TB25 §6.2.2] [ROM]:
  - Most commands execute during conversion, immediately before speaking. A command in the middle
    of a clause therefore affects the entire clause.
  - **Speech-synchronized** exceptions: `@A` (volume), `@B` (voicing), `@T` (sound effect), `@I+` (decrement).
  - TB25 also calls `@V` and `@$` synchronized [DOC], but ROM 2.01 applies them during conversion [ROM].

### 2.3 `@E` echo

- `@Ec` returns byte `c` when processed, before the line is spoken. To detect completion,
  send `text<CR>@Ex<CR>` [DOC APOLLO.TXT].
- On Apollo II, `@E` is still handled at the clause stage [DOC TB25 §6.2] [ROM].
- Sequential reading implies that **the echo is sent when processing its clause begins**, immediately
  after the preceding clause's speech ends [DED, from ROM and DOC].
- The argument is returned raw, without uppercase mapping [ROM].
- An `@E` in a clause erased by muting is never returned [ROM].
- Screen Reader/2 sends `@e<TAB>` before each word without intermediate CR, ending the sentence with `.`
  and CR [PIL os2]. On real hardware, **all echoes within one clause would be sent together at its start** [DED].
- Both prototypes split speech into one message per word and return one echo per word; this is not faithful.
- Whether SRD2 waits for these echoes before continuing is unknown [INC].

### 2.4 `@I+` and `@I?` indexes

Sources: [DOC TB25 §1, 1998 manual] and [ROM].

- **Counter:** one byte, counting received but not yet spoken units. Increment on `@I+` reception;
  decrement when speech reaches the mark, never below 0.
- **`@I?` reply:** 4 bytes: `I`, two hexadecimal counter digits, then `T` or `M`.
  - Digits are **low nibble first** [ROM]. TB25 only specifies two ASCII characters; the 1998 manual
    explicitly gives low-then-high order for `@c?`.
  - A–F case is unknown; uppercase is assumed [INC].
- **`T` and `M` meaning:**
  - Documentation allows buffered text with an `M` reply if no punctuation has arrived [DOC].
  - The ROM gives `T` while accumulating a clause [ROM].
  - **Contradiction [INC].** Apolo-emu follows the documentation: `T` means speech active or complete
    clauses pending. This is configurable.
- Muting preserves the counter; the first subsequent `@I+` resets it [DOC].

### 2.5 Queries

Sources: [DOC 1998] and [ROM].

- **`@c?`:** three-byte reply: letter followed by hexadecimal value, low nibble first.
  - Valid letters: `A B C D F H K M P Q R S V W X Z = $`.
  - Other letters receive no reply [ROM].
  - Manual example: `@A?` → `A60`, matching power-on volume 6 [ROM]. **Two independent sources agree.**
  - `@C?` reports Juno battery status. Apollo 2 has no battery.
- **`@L`:** language list: `L`, record count (7) and record size (14) in low-nibble-first hexadecimal
  (`70E0`), seven 14-byte records, then CR [DOC] [ROM]. Exact empty-bank contents are unknown [INC].
- **`@?`:** **speaks** the ROM version numbers; sends nothing on the serial link [DOC].

## 3. Apollo II commands

Implementation status is tracked in [compatibility.md](compatibility.md). This table compares
ROM 2.01 syntax with the documentation.

| Command | ROM pattern | Effect | ROM default | Sources and notes |
|---|---|---|---|---|
| `@Wd` | `W#` | rate 1–9 (about 80–580 words/min) | 3 | DOC 1998 (APOLLO.TXT: hexadecimal `@Wh`, Apollo I). Speakup sends 1–9; SRD2 sends `@w0`…`@wf`, with `0`, `b`, `f` rejected by ROM. |
| `@Fh`, `@F+`, `@F-` | `F*` | pitch center 0–F; `+`/`-` set a small non-cumulative offset | 8 | DOC, ROM |
| `@Ah` | `A*` | volume 0–F, relative to knob, synchronized with speech | 6 | **Same name:** Apollo I's argumentless `@A` cycles amplitudes [DOC]. Manual calls A normal; ROM starts at 6. |
| `@Ro` | `R#`, `R***` | prosody 0–7, or parameter (letter + 2 hex digits) | 3 | DOC, ROM |
| `@Sb` | `S#` | spelling | 0 | DOC |
| `@Pb` | `P#` | spoken punctuation | 0 | DOC |
| `@Qd` | `Q#` | inter-word pause, 0–9 | 0 | DOC |
| `@Dh` | `D*` | end-of-clause pause, 0–F | B | DOC 1998; APOLLO.TXT used `@,h`. |
| `@Bd` | `B#` | voicing 0–8, synchronized | 8 | DOC, ROM |
| `@Vd` | `V#` | preset voice 1–6; `@V0` disables speech | 1 | DOC; APOLLO.TXT: `@Vb` speech on/off. |
| `@Kb` | `K#` | speaker table, male or non-male | 0 | DOC 1998. Speakup initializes with `@K1`. |
| `@Mhh` | `M**` | duty cycle, 0–3F | 14 (hex) | DOC 1998 says 16. **Discrepancy [INC].** |
| `@$o` | `$#` | source and filter, 0–7 | 0 | DOC |
| `@u d hh±` | `U#*±`, `U#**±` | formants | — | DOC 1998; APOLLO.TXT: `@@dh±`. |
| `@Hb` | `H#` | hypermode | 0 | DOC |
| `@Xb` | `X#` | phonetic mode | 0 | DOC |
| `@Th` | `T*` | sound effect 0–F; `@Tx` pauses about 100 ms | — | **Same name:** Apollo I's `@T` starts a self-test loop [DOC]. |
| `@=d,` | `=#` | ROM bank, hence language | 1 | DOC; comma ends clause. |
| `@Ec` | `E*` | echo | — | see §2.3 |
| `@I+`, `@I?` | immediate | index | — | see §2.4 |
| `@c?`, `@L`, `@?` | `*?`, `L`, `?` | queries | — | see §2.5 |
| `@J` | absent | soft reset | — | DOC 1998 only, absent from ROM 2.01. **[INC]** |
| `@Gb`, `@+c`, `@I^` | `G#`, `+*`, `I^` | no effect since ROM 2 | — | DOC 1998, ROM. TB25 described `@G` (greeting); APOLLO.TXT described `@!c` (escape character). |
| `@Y…` | absent | serial settings | — | DOC 1998 only |
| Ctrl-A, Ctrl-X | immediate | mute | — | DOC, ROM |

**`cmd_hex_value` results [ROM]:**

- `0`–`9` yield 0–9; `A`–`Z` yield 10–35, case-insensitively.
- `:` through `@` yield 35.
- Each command silently rejects values outside its own range.

## 4. Characters and encoding

- ROM `cmd_case_map` [ROM]:
  - uppercases lowercase letters and some accented code-page-437 letters;
  - maps `[ ]` to `( )`;
  - maps control codes other than CR/ESC, and several codes above 0x7F, to spaces.
- The SRD2 profile contains value 437 [PIL]. Sonolect and Épaulard send CP850 [PIL].
- **Apolo-emu choices [APP]:** configurable CP437 decoding by default; preserve original case
  for the modern engine; no destructive normalization.

## 5. What the software actually sends

| Software | Sequences | Source |
|---|---|---|
| Speakup | `@R3@D0@K1\r`, then `@W`, `@F`, `@A` (lowercase hex), `@V`, `@=n,`; flush = tty flush + Ctrl-X; `\r` added at the next space | PIL |
| emacspeak-ss | init `@W3@F8@R3@S0@P0@Q0@B8@Db@V1`; `@I+` marks, `@I?` queries until `I00M`; `@E.` and `@A?`…`@$?` at startup | PIL |
| Screen Reader/2 | init `@=1\r @w4\r`, then `@=3` (voice selection); rate `@w0`…`@wf`, volume `@a1`…`@a9`, pitch `@f0`…`@ff`, voice `@=1`…`@=6`, `@r6`, `@r7`; mute Ctrl-A/Ctrl-X; `@e<TAB>` before every word | PIL |
| Sonolect 7.11 | `^X@W4@A3@F9.`, text, CR; never reads link; no Ctrl-X while typing | PIL |
| Épaulard | **Non-authentic extension:** `@I<c>.` before text, waits for `c` after speech. Real Apollo II would speak `@IA.`. | PIL |

## 6. Prototypes: correct behavior, approximations and errors

The gateways (`../pc486/gateway/apollo2spd.py`, `../os2/gateway/apollo2spd.py`) are nearly identical.

- **Correct:** Ctrl-X cancels; CR starts speech; `@E` returns its byte after preceding speech and
  loses it on cancellation; settings are replayed after SSIP reconnection.
- **Approximations:** arbitrary rate/pitch/volume formulas; one echo per word; LF treated as CR;
  speech after 0.3 s idle; interruption between bursts (`burst_gap`, pc486); normalized whitespace.
- **Errors relative to Apollo II:**
  - `@@` becomes `@`.
  - Arguments always have one character: `M**` and `U…` unsupported.
  - Ctrl-X/Ctrl-A swallowed within `@` sequences.
  - No `@I?`, `@c?` or `@L` replies.
  - `@I<c>` (pc486) changes the meaning of `@I`.
  - Punctuation does not end clauses, although `@W4@A3@F9.` depends on it.
  - `@V`, `@P`, `@S`, `@=` ignored.
- **License:** none declared. The gateway code was written in those projects; Apolo-emu draws
  on the knowledge rather than copying their code.

## 7. Main difficulties

1. **Synchronization.** Apollo speaks one clause at a time and emits echoes/index decrements as speech
   progresses. A modern engine accepts complete messages.
   - SSML `<mark/>` and Speech Dispatcher `INDEX_MARKS` (event 700) were verified with eSpeak NG
     on October 25, 2026, Speech Dispatcher 0.12.1: they follow actual speech progress.
   - Marks can therefore be placed at clause starts and `@I+` positions within a single fluent message.
2. **Flow control:** impossible over the socket (§1).
3. **Same command names, different meanings** between Apollo I, Apollo II and ROM versions:
   `@A`, `@T`, `@V`, `@W`, `@G`, `@!`/`@+`, `@@`/`@u`.
4. **Parameter mapping:** no hardware rate/pitch measurements; mappings are documented, configurable approximations.
5. **Prototype extensions** (Épaulard's `@I<c>`, Sonolect burst interruption, SRD2 hexadecimal rate)
   must remain isolated and disabled by default.
