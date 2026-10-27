English | [Français](references-fr.md)

# References

These documents informed Apolo-emu's design. Implemented behavior is attributed in
[protocol.md](protocol.md). The implementation aims to reproduce the device's observable interface
without embedding its firmware. Consultation of a decompilation is explicitly disclosed; this is not
a clean-room implementation. The initial similarity of the numeric conversion to that source and
its reformulation are described in [publication.md](publication.md).

The `../os2` and `../pc486` paths below record provenance in the development environment.
Those projects are not included and are not needed to install Apolo-emu or run its automated tests.

## Dolphin documentation (primary sources)

| Document | Date | Location consulted |
|---|---|---|
| *Brief guide to the Apollo speech synthesiser* (APOLLO.TXT), Release 1 | February 1989 (1992 file) | `../os2/media/screen-reader/apollo-source/APOLLO.TXT`, from `ZIP.zip` → `APOLLO.ZIP` (Internet Archive item “IBMScreenReader”) |
| *Technical Bulletin 25 — Pre-Release Information for the Apollo II* (APOLLO2.TXT) | February 4, 1993 | same archive |
| *Dolphin Speech Synthesizer User Guide — Series 2 Synthesizers* (Apollo 2, PC 2, Juno), ROM 2A onward | 1998 | http://www.perkristian.net/misc/On-line_Series_2_Speech_Synthesizer_manual.htm ; https://archive.org/details/DolphinApollo2Manual |

These documents state no license. They are not copied into this repository.

## Firmware

- **Dolphin-Apollo-II-Reborn:** decompilation of ROM UK V2.01 4.04 (Mitsubishi 740 processor),
  produced with LLM assistance and validated frame by frame against the ROM.
  - https://github.com/rommix0/Dolphin-Apollo-II-Reborn, commit `4bd78b4e2cb59bab9977adfc03939e9cddd5b78b`.
  - Files consulted: `src/firmware/ser.c`, `boot_input.c`, `cmd_scan.c`, `cmd_match.c`, `cmd_imm.c`,
    `cmd_reply.c`, `cmd_set.c`, `tn_convert.c`, `par_play.c`, `boot.c`, `data/cmd_data.c`,
    and `ghidra740/annotations/command.txt`.
  - A secondary source with no declared license, used to identify behavioral facts.

## Drivers and software

- **Linux Speakup**, `drivers/accessibility/speakup/speakup_apollo.c` (Kirk Reiser, David Borowski; v2.21),
  `synth.c`, `spk_ttyio.c`, old `serialio.c`, and `speakup_dectlk.c` for comparison.
  - https://github.com/torvalds/linux, master as of October 25, 2026. Last Speakup commit:
    `97a551fa49682a33cc2fb6c5699a9175663803cf`. Last `speakup_apollo.c` commit:
    `5e3e27f040ec3611db14a5efe23c9108831c38be`.
  - Versions 2.6.37, 4.4 and 4.19 consulted for history.
- **emacspeak-ss 1.12.1** (James R. Van Zandt): `apollo.in`, `ping-apollo.c`, `README.apollo`, `ChangeLog`.
  - https://deb.debian.org/debian/pool/main/e/emacspeak-ss/
  - January 12, 1999 flow-control message:
    https://www.cs.vassar.edu/~priestdo/emacspeak/list.archive.1999/msg00009.html
- **IBM Screen Reader/2 2.01:** `APOLLO2.TTS` and `APOLLO.TTS` profiles, decoded by comparison with
  the DECtalk profile; “Synthesizers Supported by Screen Reader.txt”; ERR0021 message.
  - Files in `../os2/media/screen-reader/extracted/SRD22/`.
- **Sonolect 7.11:** emitted sequences from disassembly and `pc486` project logs
  (`../pc486/docs/protocole-apollo.md`, `../pc486/logs/`).
- **Épaulard:** `../pc486/epaulard/src/epaulard.c` (`say_mark`, `sa_*`, `com_read` functions).

## Neighboring prototypes and investigations

- `../pc486/gateway/apollo2spd.py` and `../os2/gateway/apollo2spd.py`: prototype gateways,
  no declared license.
- `../os2/docs/REPRISE.md` and `../os2/tools/qemu-serial-loopback-msr.patch`: investigation
  of QEMU's loopback-mode MSR behavior.

## Host checks

- SSML marks and `INDEX_MARKS` events with Speech Dispatcher 0.12.1 and espeak-ng, October 25, 2026.
- QEMU 10.2.4 serial options: two UARTs at the same location without errors; `-serial none` consumes
  a port number; `reconnect-ms` behavior; MSR = 0xB0 with a socket chardev.
