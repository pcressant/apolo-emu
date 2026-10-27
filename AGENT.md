English | [Français](AGENT-fr.md)

# Resuming work — Apolo-emu

This is the shared reference for agents working in this repository. `AGENTS.md` (Codex) and
`CLAUDE.md` (Claude Code) are symbolic links to this file: edit only `AGENT.md` to keep one
authoritative set of instructions. Keep its French translation in `AGENT-fr.md` consistent.
Communicate with the user in their language; write code comments and primary documentation in English.
French documentation uses the `-fr.md` suffix and links to its English counterpart.

The full requirements are in `docs/requirements.md`. This guide summarizes lasting rules;
when in doubt, the requirements take precedence.

## Goal

Apolo-emu emulates an **Apollo II hardware speech synthesizer** connected to a serial port,
as used by DOS, Windows and OS/2 screen readers in the 1990s. The goal is **protocol and behavioral
fidelity** (commands, replies, synchronization, flow control, quirks), not the exact voice.
The speech engine is eSpeak NG through Speech Dispatcher behind a replaceable interface.

This emulates one specific device; it is not a generic speech framework.

Priorities, in order:

1. Historical Apollo II protocol fidelity.
2. Compatibility with historical screen readers.
3. Reliable serial communication.
4. Correct speech synchronization.
5. Independence from QEMU and guest systems.
6. Ease of use through the integrated launcher.
7. Code quality and maintainability.

## Quick restart

1. Read this guide, then `git status --short` and `git log -6 --oneline`; preserve existing changes.
2. Consult `docs/` (protocol, architecture, compatibility, limitations) before changing behavior.
3. Make a focused change, run appropriate tests, and clearly distinguish automated tests,
   actual Speech Dispatcher tests and VM trials.
4. Update documentation and compatibility status when behavior changes. Record lasting pitfalls here,
   not a session diary.

## Repository map

| Path | Role |
|---|---|
| `apolo_emu/protocol.py` | pure tables/functions: patterns, `hex_value`, clauses |
| `apolo_emu/device.py` | device: two stages, registers, timeline, extensions |
| `apolo_emu/speech.py`, `mapping.py`, `ssip.py` | speech interface, SSIP mapping/client |
| `apolo_emu/transport.py` | Unix socket server/client, byte trace |
| `apolo_emu/app.py`, `launcher.py`, `cli.py` | assembly, QEMU launcher, CLI |
| `tests/` | unittest; `fakes.py` (fake backend), `fake_qemu.py`, `guest.py` (boot sector) |
| `docs/protocol.md` | protocol reference, source attributed for every point |
| `docs/compatibility.md`, `limitations.md`, `development-report.md` | status, limits, report |

Tests: `python3 -m unittest discover -s tests -t .` (about 4 s; uses QEMU if present).
Actual speech: `APOLO_EMU_SPEECHD=1 python3 -m unittest tests.test_speechd_integration`.
`nix-build` reruns the suite.

## Neighboring projects

- `../pc486`: DOS / Windows 3.11, Sonolect 7.11 and Épaulard. Since October 25, 2026,
  `scripts/pc486` launches Apolo-emu (`gateway_start`); Épaulard uses authentic `@E` echoes.
  The old `gateway/apollo2spd.py` remains in its Git history.
- `../os2`: OS/2 Warp 4, IBM Screen Reader/2 2.01; historical documentation under
  `../os2/media/screen-reader/apollo-source/` (`APOLLO.TXT`, `APOLLO2.TXT`), serial-port investigation
  and QEMU patch. `scripts/gateway` has launched Apolo-emu since October 25, 2026
  (unversioned directory; old `gateway/apollo2spd.py` retained but unused).

Strict rules:

- Read them freely. Modify them, touch their VMs/QEMU configuration or interrupt their processes
  only at the user's explicit request, following their own guides (`AGENT.md`, `docs/REPRISE.md`).
  Apolo-emu option/extension changes can affect them: inspect their scripts.
- Do not start their VMs without both necessity **and explicit user permission**.
- Their gateways are prototypes: distinguish correct behavior, approximations and errors;
  do not treat them as unquestionable references.
- Do not copy code blindly: understand it, validate it, and check license and provenance.

## Sources and traceability

Cross-check `APOLLO.TXT`, `APOLLO2.TXT`, IBM Screen Reader/2 Apollo archives/drivers, notes from both
projects, Linux Speakup drivers (`drivers/accessibility/speakup/`; verify actual driver names and
target models), and other public documentation.

- Never infer a command's meaning from its name alone; compare sources.
- Beware of same-named commands with different meanings on Apollo and Apollo II.
- Classify every documented behavior as historically documented, observed in drivers, deduced,
  necessarily approximated, or unknown.
- Compatibility status distinguishes implemented/verified, implemented but unverified on real
  Apollo II hardware, partial, unimplemented, and unknown/insufficiently documented.
- Prefer honestly documented emulation to unsupported compatibility claims.

## Architecture

```text
DOS / Windows / OS/2 VM → Apollo II driver → COM1 → QEMU UART
  → Unix socket → Apolo-emu (transport → protocol → speech backend)
  → Speech Dispatcher → eSpeak NG
```

- No internal QEMU device; **no QEMU modifications**.
- Emulation core independent of transport, QEMU, speech backend, guest OS and screen reader,
  with clearly separated responsibilities.
- Linux, Python, few dependencies, no root privileges, usable outside NixOS (optional Nix integration).
  No C rewrite.

## Protocol rules

- An **explicit-state parser** consumes a **byte stream**. Socket reads never correspond to complete
  commands: handle fragments, incomplete sequences, consecutive commands and control characters.
- Explicitly model persistent settings, resets, interruptions and guest replies.
- Log unknown commands clearly, without arbitrary behavior.
- No implicit encoding conversions or destructive text transformations.
- Synchronization, especially IBM Screen Reader/2's `@e`: distinguish reception, parsing, queuing,
  speech start, progress, completion and interruption. Replies should track actual progress where possible
  (study SSML and Speech Dispatcher `INDEX_MARKS`, checking real engine support). Otherwise provide
  deterministic behavior and document the limit.
- Avoid systematically creating one speech message per word.
- Non-authentic extensions (e.g. Épaulard's old `@I<c>`) must be isolated, documented and
  **disabled by default**, never changing an authentic Apollo II command's meaning.

## Serial transport and flow control

- Bidirectional Unix socket to QEMU.
- A socket carries bytes only, not RTS/CTS/DTR/DSR. Distinguish QEMU UART behavior, transport
  capabilities and Apollo II behavior. Do not claim full hardware flow control if the interface
  cannot provide it.

## Speech backend

Replaceable interface: text submission, immediate stop, rate, pitch, volume, progress and completion.
Document and test Apollo II to engine parameter mapping.

## QEMU launcher

- Standalone mode (e.g. `apolo-emu --socket PATH`) and launcher mode
  (`apolo-emu run -- qemu-system-i386 …`); interface may change for robustness.
- Per-instance socket, correct startup ordering, serial-port injection without conflicts,
  handled startup errors, forwarded signals, preserved exit codes, cleanup of its own resources only,
  no stale sockets, independent concurrent instances.
- Never kill a QEMU process it did not start, or abruptly stop a VM requiring clean guest shutdown.
- Impose no disk, memory, processor or guest configuration.

## Tests

- Fake speech backend for silent protocol tests, with precisely controlled progress.
- Cover parsing, fragments, multiple blocks, settings, interruption, reset, acknowledgments, replies,
  encoding, unknown commands, transport errors, reconnection, multiple instances, process/socket cleanup.
- Speech Dispatcher/QEMU integration where available, using an independent test VM.
  Automated tests must not depend on booting OS/2 or Windows 3.11.

## Expected documentation

README, Apollo II protocol, architecture, QEMU launcher including existing-command integration,
compatibility matrix, known limitations, installation, examples and source references.

## Method

Work autonomously through investigation → architecture → implementation → tests → QEMU integration →
report (features, sources, test results, fidelity limits, missing commands, gateway incompatibilities,
next improvements). No approval needed between phases, but strictly preserve neighboring projects.

## Known pitfalls

- `. , : ; ! ?` end clauses like CR: `?` in `@W?` terminates the clause. Many incorrect test
  expectations came from overlooking this.
- `*` matches any character including `@`: `@Mz@M2A` consumes the second `@` (intentional ROM behavior).
- Clause effects (echoes, `@c?` replies) wait for speech to reach them; tests must advance the fake
  backend (`begin`, `reach`, `finish`).
- `@I?` replies immediately, before echoes from pending clauses.
- eSpeak reports a final mark slightly before END: a trailing silent clause's actions execute at END,
  not at a mark.
- QEMU 10.2 permits two UARTs at the same address; `-serial none` consumes a port number.
  The launcher must count ports itself.
- With a socket chardev, the guest sees MSR = 0xB0 (CTS, DSR, DCD asserted): no flow control is possible.
- A neighboring VM may be running: do not touch it without permission. Clean OS/2 shutdown:
  desktop Shutdown menu, then QMP `quit` (see `../os2/docs/REPRISE.md`). For automated actual-speech
  trials, use SSIP `notification` priority and low volume.
