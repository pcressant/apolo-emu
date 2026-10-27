English | [Français](extensions-fr.md)

# Extensions (non-authentic)

Extensions reproduce prototype gateway behavior or accommodate software that does not follow
the ROM 2.01 protocol exactly. They follow three rules:

- They are **disabled by default**.
- Each is enabled with `--extension NAME`.
- They **never change** an authentic Apollo II command's meaning. Their patterns follow the ROM
  patterns: `@I+`, `@I?` and `@I^` retain their meanings.

List them with `apolo-emu --list-extensions`.

## `epaulard-index`

This is the old `pc486` gateway's `@I<c>` extension, used by Épaulard until October 25, 2026.
The development version of Épaulard now uses the authentic `@E` echo; the extension remains for older versions.

- **What Épaulard sent:** `^X`, then `@IA.`, then text and CR. It waits for byte `A` after the text
  has finished speaking, and stops waiting after cancellation.
- **On a real Apollo II**, `@IA.` is not a command: the device would say “I A” and return nothing.
- **With the extension:**
  - `@I` followed by a character other than `+`, `?` or `^` stores that character.
  - It is returned at the actual end of speech (END event) for the next CR-terminated clause.
  - It is never returned after muting.
- **Authentic equivalent:** `text<CR>@Ec<CR>` (APOLLO.TXT), without an extension.
  This is what the modified Épaulard sends now.

## `word-echo`

- **On the device**, `@E` is processed at the start of its clause. Screen Reader/2 places `@e<TAB>`
  before each word: all echoes from a clause therefore arrive together at its start.
- **With the extension**, each echo is returned when speech reaches its exact position, using an SSML mark.
  This provides word-by-word tracking without splitting speech.
- **More precise than the hardware.**

## `lenient-speed`

- The Screen Reader/2 Apollo 2 profile sets speed with `@w0`, `@w2`…`@w9`, `@wb` and `@wf`.
- ROM 2.01 accepts only digits 1–9:
  - `@w0` is ignored.
  - `@wb` and `@wf` are not recognized and remain in the text.
- **With the extension**, `@W` accepts any character: 0 maps to 1, and A–F map to 9.
- Another ROM version may have accepted hexadecimal speed, like the Apollo I's `@Wh`.
  This has not been established.

## `burst-interrupt`

This reproduces the `pc486` gateway's `--burst-gap` behavior.

- **The need:** Sonolect never sends Ctrl-X while typing. On real hardware, key echoes would accumulate.
- **With the extension:** if input arrives while speech is active, no incomplete clause is being received,
  and more than 40 ms have elapsed since the last byte, current speech is interrupted as with muting.
- **Exception:** speech is never interrupted while an `@E` echo or `epaulard-index` mark is pending.
  The guest then synchronizes its own queue, as Épaulard does during “read all”, and sends Ctrl-X
  when it wants to stop. The same configuration therefore works for Sonolect and Épaulard.
- This is a heuristic without a hardware equivalent.
