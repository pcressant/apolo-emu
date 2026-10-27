English | [Français](architecture-fr.md)

# Architecture

## Modules

| Module | Role | Dependencies |
|---|---|---|
| `protocol.py` | Pure tables and functions: command patterns, `hex_value`, hexadecimal replies, clause accumulation (`ClauseAccumulator`) and parsing (`scan_clause`) | none |
| `device.py` | **The device**: communication and clause stages, registers, speech timeline and replies | `protocol`, `speech` |
| `speech.py` | Speech backend interface (`SpeechBackend`, `Utterance`, `SpeechEvent`, `VoiceParams`) and silent backends (`NullBackend`, `SimulatedBackend`) | none |
| `mapping.py` | Maps Apollo settings to SSIP settings | `speech` |
| `ssip.py` | Speech Dispatcher backend: asynchronous SSIP client, SSML and events | `speech`, `mapping` |
| `transport.py` | Unix socket server or client, stale sockets and byte logging | `device` |
| `app.py` | Builds a complete emulator from options; standalone mode | all |
| `launcher.py` | QEMU launcher: arguments, instance directory, signals and cleanup | `app` |
| `cli.py` | Command-line interface | `app`, `launcher` |

The core (`protocol`, `device`) performs no I/O and knows nothing about QEMU, the socket,
Speech Dispatcher or the guest system. It is synchronous and can be tested byte by byte.

## Interfaces

```python
# Device
device = ApolloDevice(backend, reply=callable_bytes, config=DeviceConfig(...))
device.feed(data: bytes)                # received bytes, in arbitrary chunks
device.on_speech_event(ev: SpeechEvent) # progress reported by the backend
# replies: reply(bytes); speech: backend.speak(Utterance), backend.cancel()

# Speech backend (speech.SpeechBackend)
set_event_sink(sink)      # sink(SpeechEvent(uid, "begin" | "mark" | "end" | "cancel", mark))
speak(utt: Utterance)     # queue after utterances already in progress
cancel()                  # stop immediately and clear the queue
async start(), async close()
```

An `Utterance` is a sequence of text (`str`), marks (`Mark(name)`) and pauses (`Pause(ms)`).
Its `VoiceParams` use **Apollo values**; mapping them is the backend's responsibility.

To support another engine, implement these five methods. Report at least `end` for every utterance;
`mark` and `begin` improve precision.

## Device model

The firmware processes data in two stages (see [protocol.md](protocol.md) §2):

1. **Communication stage** (`_receive`), byte by byte:
   - Ctrl-A and Ctrl-X call `mute()`.
   - `@` enters immediate-command mode: `@I?` replies immediately and `@I+` increments the counter.
   - Everything else goes into the input buffer.
2. **Clause stage** (`_clause`):
   - `ClauseAccumulator` splits the stream at CR, punctuation and length limits.
   - `scan_clause` removes recognized commands.
   - `_phrase_command` applies clause-stage commands to the **projected state**.
   - Speech-synchronized commands (`@A`, `@B`, `@I+`, `@T`) become marks or pauses at their positions.

### Two register states

- `projected`: the state after all clauses parsed so far. It determines utterance settings at construction time.
- `live`: the state reached by speech. Actions update it as speech progresses; `@c?` queries read this state.

After muting, `projected` becomes equal to `live` again. Settings from discarded clauses therefore
never take effect, as on the hardware.

### Timeline

`timeline` is the ordered queue of remaining playback items:

- **`_Spoken`**: an utterance submitted to the backend, with marks and their actions: echoes, replies,
  `live` updates and index decrements.
- **`_Immediate`**: actions from a clause with nothing to say. They run once all preceding items finish.

Rules:

- **Clause start.** Each clause with effects receives an initial mark. Clause-stage actions (`@E` echoes,
  `@c?` and `@L` replies, settings) attach to it. They run when speech reaches the clause, immediately
  after the preceding clause finishes, matching the Apollo's sequential playback.
- **Merging.** Clauses received in the same read and using the same settings form **one message**.
  Speech is never systematically split into one message per word.
  - A silent clause between two texts becomes a mark at their junction.
  - At the end of a batch, it remains an `_Immediate` item executed at the actual end of speech (END).
- **Settings changes.** A volume change within a clause, or a settings change between clauses,
  starts a new message: SSIP applies settings per message.
- **Order.** An event for utterance N completes all preceding utterances: the engine speaks in order.
- **Cancellation.** A `cancel` event discards remaining actions for the utterance. Its echoes are lost,
  just like those of a clause erased by muting.

### `T` or `M` in the `@I?` reply

`talking` is true while a spoken utterance remains in the timeline or current batch.

With `--talking-rule rom`, it is also true while an incomplete clause is being received.
See [protocol.md](protocol.md) §2.4.

## Concurrency

Everything runs in one asyncio event loop on one thread:

- The transport calls `device.feed()` on each socket read.
- The backend calls `device.on_speech_event()` from its SSIP reader task.

The device is never called concurrently. Reentrant calls are supported, including a backend
reporting an event during `speak()`.

## Logging

- Logs use `logging`, on standard error, with four levels (`--log-level`).
- Unknown commands, rejected values and unsupported features are reported at `info` level.
- `debug` details every read and speech event.
- `--trace FILE` adds a line per serial read or write:
  `seconds RX|TX hex-bytes`, for example `   12.3456 RX 40 49 3f`.
  The file is opened in append mode. Each run first writes `# start YYYY-MM-DD hh:mm:ss`,
  the origin for subsequent relative timestamps. This format allows session replay or analysis.
