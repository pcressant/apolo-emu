English | [Français](cahier-des-charges-fr.md)

# Apolo-emu project: Apollo II speech synthesizer emulator

## Context

I want to create an independent project named **Apolo-emu**.

The goal is to reproduce as faithfully as possible the behavior of an **Apollo II hardware speech
synthesizer**, as used with DOS, Windows and OS/2 screen readers in the 1990s.

This goes beyond turning serial-port text into speech. Emulate the historical device's protocol,
commands, replies, synchronization, flow control and, where possible, quirks.

A modern engine such as eSpeak NG through Speech Dispatcher can produce speech. Exact voice timbre
is not required; protocol and behavioral compatibility matter. The project must be standalone,
reusable and independent of the screen readers using it.

## 1. Existing projects to examine

Two neighboring projects contain working experiments:

- `../pc486`: DOS / Windows 3.11, Sonolect 7.11 and Épaulard.
- `../os2`: OS/2 Warp 4 with IBM Screen Reader/2 2.01.

They have Apollo II to Speech Dispatcher gateways which work at least partially but are experimental.
**Read both projects freely to understand their operation and recover existing knowledge.**

However:

- Do not modify files in `../pc486` or `../os2`.
- Do not modify their VMs, interrupt their processes or change their QEMU configurations.
- Do not regard their implementations as unquestionable references.

Identify correct behavior, approximations and errors in these prototypes.
Create the new project in its own `Apolo-emu` directory.

## 2. Research before implementation

Examine available documentation and sources before implementing anything.

### Apollo documentation

Historical Apollo/Apollo II documents are under `../os2/media/screen-reader/apollo-source/`.
`APOLLO.TXT` and `APOLLO2.TXT` are particularly relevant. Also inspect the original archives,
IBM Screen Reader/2 Apollo drivers and notes in both neighboring projects.

Identify precisely:

- Serial protocol and communication parameters.
- Configuration and pronunciation commands.
- Rate, volume and pitch commands.
- Character and encoding handling.
- Reset and interruption mechanisms.
- Synchronization and acknowledgment mechanisms.
- Identification commands, if any.
- Hardware flow-control behavior.
- Differences between Apollo and Apollo II.

Beware of commands with identical names but different meanings across versions.

### Linux Speakup sources

Inspect the Linux kernel's Speakup code, particularly Apollo synthesizer drivers under
`drivers/accessibility/speakup/`. It can reveal initialization sequences, actual commands,
transmission delays, buffer management, flow control and hardware quirks.

Verify actual driver names and targets rather than assuming all target the same Apollo model.
Use official kernel sources as needed. Other relevant public documentation and historical drivers
may also be researched.

**Never infer a command from its name alone: compare sources.**

### Traceability

Distinguish:

1. Behavior confirmed by historical documentation.
2. Behavior observed in existing drivers.
3. Behavior deduced through analysis.
4. Necessary approximations.
5. Still-unknown features.

I prefer honestly documented emulation to assumed full compatibility.

## 3. General architecture

The project must be independent of QEMU. QEMU already emulates UART controllers: no internal
QEMU device or QEMU code modification is needed.

```text
DOS / Windows / OS/2 virtual machine
                |
         Apollo II driver
                |
             COM1
                |
        QEMU-emulated UART
                |
           Unix socket
                |
          Apolo-emu
                |
       Protocol emulation
                |
          Speech backend
                |
       Speech Dispatcher
                |
           eSpeak NG
```

Apolo-emu behaves as the peripheral connected to the serial port. The emulation core must be
independent of serial transport, QEMU, speech engine, guest OS and screen reader.
Separate responsibilities clearly.

## 4. Protocol emulation

Implement a real protocol parser with explicit internal state. Correctly handle:

- Received commands, including commands fragmented across reads.
- Incomplete sequences and control characters.
- Persistent parameters and rate/voice changes.
- Interruptions and resets.
- Guest replies and speech synchronization.

Never assume one socket read is a complete command. Treat the protocol as a byte stream.
Log unknown commands clearly, without arbitrary behavior.

### Synchronization

Pay particular attention to echo/synchronization mechanisms, especially Screen Reader/2's `@e`.
Synchronization replies should follow actual synthesis progress as closely as possible.

Distinguish byte reception, protocol parsing, text queuing, synthesis start, progress, completion
and interruption. Investigate SSML marks and Speech Dispatcher `INDEX_MARKS`; verify real support
in the chosen engine.

If exact synchronization is impossible, document the limit and use deterministic behavior without
claiming guarantees the backend cannot provide. Avoid systematically splitting speech into one
message per word when a more fluent solution is possible.

### Historical compatibility

At the time of these requirements, Épaulard uses experimental extensions, especially around `@I`.
They must not silently change authentic Apollo II command meanings. Necessary extensions must
be isolated, documented and disabled by default. Historical-driver compatibility takes priority.

## 5. Serial transport and flow control

Communicate with QEMU over a bidirectional Unix socket. Study how QEMU exposes UART modem signals
and flow control to the selected backend.

**A Unix socket carries bytes, but does not itself reproduce RTS, CTS, DTR or DSR.**

Clearly distinguish QEMU emulation, QEMU-to-Apolo-emu transport and Apollo II behavior.
Do not claim complete hardware flow control if the interface cannot drive the relevant signals.

Study the `../os2` serial investigation and QEMU patch to understand which behavior belongs to QEMU
and which belongs to the Apollo emulator. Do not modify QEMU in this project.

## 6. Speech backend

Start with Speech Dispatcher and eSpeak NG, behind a replaceable backend interface.
Support, as far as possible:

- Text submission and immediate interruption.
- Rate, pitch and volume settings.
- Progress and completion notifications.

Determine how to map Apollo II parameters to the modern engine; document the mapping and make it
testable. Avoid destructive text transformations and implicit encoding conversions.

## 7. Integrated QEMU launcher

Users should be able to start Apolo-emu and a VM without manually managing sockets and processes.
Provide two modes.

### Standalone mode

Start the emulator alone with a configurable Unix socket. Proposed interface:

```bash
apolo-emu --socket /tmp/apollo.sock
```

### Launcher mode

Coordinated emulator/QEMU startup. Possible interface:

```bash
apolo-emu run -- qemu-system-i386 [options]
```

These are interface proposals; adjust them if another design is more robust.

The launcher must:

- Create a per-instance socket and start components in the correct order.
- Add/configure the QEMU serial port without conflicting with existing options.
- Handle startup errors and correctly propagate shutdown signals.
- Clean up its own resources and avoid stale sockets.
- Preserve useful exit codes and support independent concurrent instances.

Never arbitrarily kill existing QEMU processes or abruptly stop a VM requiring clean guest shutdown.
Document integration with existing QEMU commands. Impose no specific disk, memory, CPU or guest configuration.

## 8. Tests

Provide a thorough automated suite covering:

- Apollo command parsing, fragmented commands and consecutive commands in one block.
- Synthesis settings, interruptions, resets and acknowledgments.
- Guest replies, encodings and unknown commands.
- Transport errors, reconnection and multiple instances.
- Process and socket cleanup.

Use a fake speech backend for silent protocol tests, with precisely simulated speech progress.
Also provide Speech Dispatcher and, where possible, QEMU integration tests. Automated testing must
not routinely depend on fully booting OS/2 or Windows 3.11.

### Historical-software validation

The existing projects can later serve as test beds: Sonolect 7.11 under DOS, IBM Screen Reader/2 2.01
under OS/2, Épaulard under Windows 3.11. **Do not start or modify their VMs without necessity
and explicit permission.** Start with unit tests and serial-stream simulations.

## 9. Documentation

At minimum: project README, Apollo II protocol, architecture, QEMU launcher, command compatibility
matrix, known limitations, installation, usage examples and source references.

Compatibility status must distinguish implemented/verified, implemented but unverified on real Apollo II,
partially emulated, unimplemented, and unknown/insufficiently documented commands.

## 10. Development constraints

Target Linux. Python is appropriate if performance and event handling suffice; do not rewrite in C
just to be closer to the hardware.

Favor simple architecture, readable code, few dependencies, clear interfaces, reproducible tests,
useful logging and no root privileges. Require no QEMU modifications. Support use outside NixOS,
with optional Nix integration.

Do not blindly copy existing code: check the license and provenance of reused material.

## 11. Working method

Work autonomously in phases:

1. **Investigation:** inspect both projects, historical documents and Speakup; record current
   knowledge and main difficulties.
2. **Architecture:** define internal interfaces, protocol model, serial transport and speech backend.
3. **Implementation:** build incrementally, reusing relevant prototype parts only when their behavior
   is understood and validated.
4. **Tests:** run automated tests, fix problems and verify robustness.
5. **QEMU integration:** implement the launcher and validate with an independent test VM.
6. **Report:** implemented features, historical sources, test results, fidelity limits, missing commands,
   gateway incompatibilities found and relevant next improvements.

## 12. Priorities

1. Historical Apollo II protocol fidelity.
2. Compatibility with historical screen readers.
3. Reliable serial communication.
4. Correct speech synchronization.
5. Independence from QEMU and guest systems.
6. Ease of use through the integrated launcher.
7. Code quality and maintainability.

Do not pursue exact voice timbre at the expense of these goals. Do not turn the project into a generic
speech framework. **The goal is to emulate a specific device: Apollo II.**

Use the two working prototypes, historical documentation and drivers to build coherent emulation
rather than another collection of workarounds. Begin investigation and continue autonomously without
approval at every phase, while strictly preserving neighboring projects.

**Expected result: a standalone, functional, documented and tested Apolo-emu project that can act
as a virtual Apollo II synthesizer for historical software.**
