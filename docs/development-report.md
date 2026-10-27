English | [Français](bilan-fr.md)

# Development report (October 25, 2026)

## Implemented features

- **Apollo II device** (`device.py`, `protocol.py`): a two-stage model following ROM 2.01
  and Dolphin documentation.
  - Communication: Ctrl-A/Ctrl-X mute, immediate `@I+` and `@I?` commands.
  - Clauses terminated by CR or punctuation; deferred command table in ROM order.
  - Unrecognized commands remain in text.
  - Distinct clause-stage and speech-synchronized commands.
  - Queryable registers (`@c?`), language list (`@L`), `@E` echoes and indexes.
- **Synchronization:** an SSML mark at the start of each clause with effects and at every `@I+`;
  effects occur when Speech Dispatcher reports reaching them. Clauses from one read form a single
  message, never systematically one message per word.
- **Speech Dispatcher backend** (`ssip.py`): dependency-free SSIP client, settings mapped by
  `mapping.py`, reconnection, nonblocking fallback for the guest, automatic Speech Dispatcher startup
  if absent.
- **Silent backends:** `simulated` (simulated duration) and `null`.
- **Transport** (`transport.py`): listening or connecting Unix socket, one connection at a time,
  stale-socket detection and byte logging.
- **QEMU launcher** (`launcher.py`): per-instance directory and socket, port added with
  `-device isa-serial,index=N`, conflict detection, signal forwarding, preserved exit codes,
  abandoned-instance cleanup and concurrent independent instances.
- **Four isolated extensions**, disabled by default: `epaulard-index`, `word-echo`,
  `lenient-speed`, `burst-interrupt`.
- **Optional Nix integration** (`default.nix`); also works outside NixOS with Python ≥ 3.10.

## Sources consulted

See [references.md](references.md): Dolphin APOLLO.TXT, Technical Bulletin 25 and 1998 Series 2 manual;
ROM 2.01 decompilation; Speakup; emacspeak-ss; Screen Reader/2 profiles; Sonolect and Épaulard
as investigated in neighboring projects.

## Test results

At the time of this report, `python3 -m unittest discover -s tests -t .` reported **112 tests, all passing**.
One test is skipped by default: actual speech, enabled with `APOLO_EMU_SPEECHD=1`.
It also passed when run separately. The later publication-preparation run is recorded in
[publication.md](publication.md).

| File | Coverage |
|---|---|
| `test_protocol.py` | `hex_value`, hexadecimal replies, patterns, clause parsing/splitting and length limits |
| `test_device.py` | byte fragments, multi-command blocks, settings, mute within commands, echoes, indexes, queries, `@J`, synchronized volume, effects, languages, encodings, unknown commands, overflow, extensions |
| `test_mapping.py` | parameter mapping |
| `test_ssip.py` | fake SSIP server: initialization, SSML, settings sent once, events, cancellation, connection loss/recovery, rejection, unreachable engine |
| `test_transport.py` | socket requests, fragments, permissions, second-client rejection, reconnection with state retained, replies lost while disconnected, connecting-mode reconnection, stale sockets |
| `test_launcher.py` | QEMU arguments/conflicts, exit codes, missing QEMU, cleanup, three concurrent instances, SIGTERM forwarding, `wait` policy, abandoned directories |
| `test_qemu_integration.py` | **real QEMU 10.2.4**, independent boot-sector VM: 9600 baud 8N1 UART, MSR = 0xB0, `@I?` → `I10T` during speech, `@E` after completion, COM2 beside existing COM1 |
| `test_speechd_integration.py` | **real Speech Dispatcher and eSpeak NG**: echo/index ordering and timing |

`nix-build` reruns the suite in Nix's sandbox with the same result.

**Historical software trials** (October 25, 2026, assessed by ear by the user under 86Box):

- Sonolect 7.11 under MS-DOS 6.22 works (startup announcement, prompt, typing, reading), with
  `--language fr --codepage cp850 --extension burst-interrupt --no-volume`.
- Épaulard under Windows 3.11, modified for authentic `@E` echoes, works, including “read all”.
- Screen Reader/2 under OS/2 has not yet been tried with Apolo-emu.

## Fidelity limits

See [limitations.md](limitations.md). Main limits: voice, prosody and effects differ from hardware;
no hardware flow control over a socket; parsing details based on a single ROM; uncertain `T`/`M`
meaning in `@I?`; `@E` timing deduced rather than measured.

## Missing or approximate commands

- **Not implemented:** `@Y` serial settings, empty-read NAK, RTS/CTS handshaking, `_XX` phonemes,
  `@X` mode and `@H` hypermode.
- **Stored without audible effect:** `@Q`, `@D`, `@R`, `@B`, `@M`, `@$`, `@u`.
- **Approximated:** `@T` (pauses), `@?` (configurable text), `@L` contents.

## Incompatibilities found in existing gateways

These concern `../pc486/gateway/apollo2spd.py` and its `../os2/gateway/` copy.

1. **`@I<c>` (Épaulard)** is not an Apollo II command: actual hardware would say “I A”.
   Authentic `@I+`/`@I?` are unsupported by the prototypes. `epaulard-index` reproduces their behavior;
   `text<CR>@E<c><CR>` replaces it without an extension.
2. **Punctuation does not end clauses** in the prototypes, although Sonolect ends settings with
   `.` (`@W4@A3@F9.`), which matters to ROM parsing.
3. **The `os2` prototype splits speech word by word** to track `@e<TAB>`. Real Apollo II would send
   those echoes together at the clause start; Apolo-emu does so in one message.
4. **Incorrect parsing:** `@@` becomes `@`; one-character arguments only (`@M**`, `@u…` unsupported);
   Ctrl-X/Ctrl-A swallowed after `@` (IBM's `@^A^X` would lose Ctrl-X); LF treated as CR;
   speech after 0.3 s without CR; normalized whitespace.
5. **No replies** to `@I?`, `@c?`, `@L`; only `@E` returns a byte.
6. **Screen Reader/2** sends `@w0`, `@wb`, `@wf`, rejected by ROM 2.01 but accepted by prototypes
   (`lenient-speed` here).
7. **Minor `os2` gateway inconsistencies:** English default despite a French comment;
   README claims `@r0..@r7` in APOLLO2.TTS, which contains only `@r6`/`@r7`;
   leftover dead code from the `@I` extension.

## Relevant next improvements

1. **Historical-software validation**, with permission: Sonolect/Épaulard (`pc486`), Screen Reader/2 (`os2`),
   using `--trace` to compare actual sequences with assumptions. Check whether Screen Reader/2 waits
   for `@e` echoes, and whether clause tracking suffices or `word-echo` is needed.
2. **Épaulard:** completed October 25, 2026: sends `text CR @E<c> CR`, no extension needed.
   `pc486` and `os2` now launch Apolo-emu instead of their gateways.
3. **`@D`/`@Q` pauses:** implement as SSML `<break>` after calibration.
4. **`@T` effects:** short audio files (SSML `<audio>` or Speech Dispatcher sound icons), if supported.
5. **ROM profiles:** select another variant (2A, US) when documentation or another ROM warrants it.
6. **`-readconfig` parsing** in the launcher.
