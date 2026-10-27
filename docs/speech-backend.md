English | [Français](backend-vocal-fr.md)

# Speech backend

## Speech Dispatcher (`--backend ssip`, default)

`ssip.py` implements an SSIP client directly, without the Python `speechd` module.

**Connection:** `$SPEECHD_ADDRESS`, otherwise `$XDG_RUNTIME_DIR/speech-dispatcher/speechd.sock`.
If the socket is missing, Apolo-emu runs `speech-dispatcher --spawn` once
(disable with `--no-autospawn`).

**Initialization:**

```text
SET self CLIENT_NAME user:apolo-emu:main
SET self OUTPUT_MODULE …          (if --module is set)
SET self PRIORITY message         (--priority)
SET self SSML_MODE on
SET self NOTIFICATION all on
```

- **`message` priority:** utterances follow each other without cancellation. Muting sends `CANCEL self`,
  which stops only Apolo-emu's messages.
- **Each utterance becomes an SSML message:**
  `<speak>text<mark name="m12"/>more text<break time="100ms"/></speak>`.
  - Text is XML-escaped; a leading dot on a line is doubled as required by SSIP.
  - Case, whitespace and punctuation are otherwise preserved.
- **Received events:** 701 (BEGIN) becomes `begin`; 700 (INDEX MARK) becomes `mark`;
  702 (END) becomes `end`; 703 (CANCELED) becomes `cancel`.
- **Settings:** sent before a message when different from the last applied settings, and resent
  after reconnection.

### Marks and synchronization: verification

Verified on the host on October 25, 2026 (Speech Dispatcher 0.12.1, espeak-ng module):

- SSML `<mark/>` elements return as event 700 **when speech reaches them**
  (initial probe, then `tests/test_speechd_integration.py`).
- A two-sentence message with an intermediate `@I+` produced the initial echo,
  `@I?` → `I10T` during speech, the second sentence's echo at its start, and the final echo after speech ended.

**If a module does not support marks**, none arrive. Attached actions then run at END:
synchronization remains ordered but is less precise.

**Connection failure:**

- If Speech Dispatcher stops or becomes unreachable, submitted unfinished utterances are declared
  finished and the decision is logged. The guest receives echoes rather than waiting indefinitely.
- The next message triggers reconnection.
- Rejected messages are handled the same way.

## Parameter mapping (`mapping.py`)

No measurements of the actual hardware are available. The mappings follow three principles:

- Apollo defaults map to engine defaults.
- Extreme values map to extreme values.
- Progression is monotonic.

They are checked by `tests/test_mapping.py` and adjustable with `--rate-offset`, `--pitch-offset`,
`--volume-offset` and `--no-volume`.

| Apollo | Range, default | SSIP | Formula |
|---|---|---|---|
| `@W` rate | 1–9, 3 (about 80–580 words/min) | `RATE` -100..100 | W ≤ 3: (W−3)×35; W > 3: (W−3)×100/6. W1 = −70, W3 = 0, W9 = +100. |
| `@F` pitch | 0–F, 8 | `PITCH` | (F−8)×12.5. F0 = −100, F8 = 0, FF = +88. |
| `@F+`, `@F-` | small, non-cumulative offset | `PITCH` | +10 or −10 until the next `@Fh` |
| `@A` volume | 0–F, 6 | `VOLUME` | A×200/15 − 100. A0 = −100, A6 = −20, AA = +33, AF = +100. |
| `@V1`–`@V3` | male voices | `VOICE_TYPE` | `MALE1`–`MALE3` |
| `@V4`–`@V6` | non-male voices | `VOICE_TYPE` | `FEMALE1`–`FEMALE3` |
| `@V0` | speech disabled | — | nothing is sent to the engine; echoes and indexes behave as if speech were instantaneous |
| `@P1` / `@P0` | spoken punctuation | `PUNCTUATION` | `all` / `none` |
| `@S1` / `@S0` | spelling | `SPELLING` | `on` / `off` |
| `@=n` | ROM bank | `LANGUAGE` | bank language from `--languages` (e.g. `1=en,2=fr`) |

- **Volume** is relative to the hardware knob. The ROM starts at 6; the manual calls A normal.
  Default volume is therefore slightly below the engine's default; `--volume-offset` compensates.
- **With `--voice`** (a named engine voice), `VOICE_TYPE` is no longer sent: the chosen voice overrides `@V`.
- **An `@` left in text**, meaning an unrecognized command, is replaced by a space when punctuation
  is disabled. A modern engine would otherwise say “at”, whereas the device treats it as silent punctuation.

## Other backends

- **`--backend simulated`**: silent output. Speech duration is simulated at `--cps` characters per second,
  with marks reported at their positions. Used for trials and integration tests.
- **`--backend null`**: silent output. Each utterance finishes immediately.

To implement another backend, see the interface in [architecture.md](architecture.md).
