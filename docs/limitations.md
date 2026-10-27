English | [Français](limitations-fr.md)

# Known limitations

## Fidelity

- **Voice and prosody:** the voice comes from eSpeak NG. The following are not reproduced:
  - the hardware's absolute rates, pitches and volumes;
  - `@Q` and `@D` pauses;
  - `@R` prosody, `@B` voicing, `@M` duty cycle, `@$` source and `@u` formants;
  - `@H` hypermode, `@X` phonetic mode and `_XX` phonemes.

  These settings are only stored and can be queried.
- **`@T` sound effects:** replaced with pauses.
- **Reading rules:** pronunciation, automatic spelling of words without vowels, punctuation names
  and number processing come from the engine rather than the Apollo.
- **One reference ROM:** parsing details follow the UK 2.01 ROM, known through a decompilation
  (a secondary source). Other ROMs (2A, US versions, other languages) may differ. For example,
  `@J` and `@Y`, documented in 1998, are absent from this ROM.
- **`@L` and `@?` contents:** approximated.
- **`T` and `M` in `@I?` replies** while receiving unpunctuated text: sources disagree
  (`--talking-rule` option).

## Synchronization

- **Granularity:** synchronization depends on engine SSML marks, verified with eSpeak NG.
  With a module that does not support marks, echoes and index decrements arrive at the end
  of the message rather than at their positions.
- **SSIP messages:** clauses received in one read form one message. Clauses received in separate
  reads (very slow, byte-by-byte input) form successive messages, which Speech Dispatcher
  plays with a short gap.
- **Speech engine failure:** if Speech Dispatcher becomes unreachable, current utterances are
  declared finished. The guest receives echoes even though nothing was spoken, avoiding a hang.

## Serial connection

- **No flow control:** the guest sees CTS permanently asserted and the emulator cannot throttle it.
  Input that would overflow a real Apollo II is logged without dropping data
  (see [serial-transport.md](serial-transport.md)).
- **Baud rate has no effect:** QEMU does not pace bytes. `@Y` is not emulated.
- **Replies sent while disconnected** are lost.
- **OS/2 QEMU patch:** the loopback-mode MSR defect must be fixed in QEMU, as in the `os2` project.
  Apolo-emu cannot fix it.

## Launcher

- `-readconfig` and serial ports defined in configuration files are not parsed.
- `-device isa-serial` without `index` can conflict with the selected port: the launcher warns,
  but cannot know which port QEMU will assign.
- A signal cannot request a clean shutdown of DOS, Windows 3.x or OS/2: these systems do not
  support ACPI. Use `--on-signal wait`, then shut down the guest manually.
