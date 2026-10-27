English | [Français](README-fr.md)

# Apolo-emu

Apolo-emu emulates a **Dolphin Apollo II** hardware speech synthesizer connected to a serial port.
It lets DOS, Windows and OS/2 screen readers from the 1990s speak inside QEMU: Sonolect, Épaulard,
IBM Screen Reader/2 and others. Speech comes from eSpeak NG through Speech Dispatcher.

The goal is **protocol fidelity**, rather than reproducing the original voice. This includes:

- `@` commands and their parameter ranges;
- splitting text into clauses;
- the timing of each command;
- `@E` echoes and `@I+` / `@I?` indexes synchronized with actual speech;
- `@c?` and `@L` queries;
- muting (Ctrl-X).

Unknown behavior, approximations and unsupported features are explicitly documented.

This is an independent project, with no affiliation to Dolphin or IBM. The project's own code and
documentation are available under the [MIT license](LICENSE); see the [provenance notice](NOTICE.md).
No ROM or proprietary guest software is included.

```text
DOS / Windows / OS/2 VM → Apollo II driver → COM1 → QEMU UART → Unix socket
  → Apolo-emu (transport → Apollo II device → speech backend) → Speech Dispatcher → eSpeak NG
```

## Installation

Linux and Python 3.10 or later are required. There are no additional Python runtime dependencies.
Speech output requires Speech Dispatcher and eSpeak NG; the launcher requires QEMU.

```bash
# Run from the repository without installing
python3 -m apolo_emu --help

# Install for the current user (creates the apolo-emu command)
pip install --user .
```

Debian or Ubuntu: `apt install speech-dispatcher espeak-ng qemu-system-x86`.

NixOS: these packages and `python3` are sufficient. Apolo-emu runs without root privileges.

### Arch Linux

From the complete project directory:

```bash
sudo pacman -S --needed base-devel
makepkg -si
# For speech output (optional package dependencies):
sudo pacman -S --needed speech-dispatcher espeak-ng
```

The [PKGBUILD](PKGBUILD) builds the current local checkout, including uncommitted changes;
it does not download sources and cannot be used on its own or as an AUR submission.
`makepkg -s` installs build/check dependencies, including `qemu-system-x86` for the independent
test VM. Tests produce no speech and do not use your existing VMs. QEMU is optional at runtime
when connecting to an already configured serial socket. Both documentation languages are
installed under `/usr/share/doc/apolo-emu/`.

## Usage

### Launcher mode: Apolo-emu and QEMU together

```bash
apolo-emu run --language fr -- qemu-system-i386 -m 64 -hda dos.img
```

The launcher:

1. Creates a socket for the instance.
2. Starts the emulator.
3. Adds COM1 to the QEMU command.
4. Starts QEMU and cleans up when it exits.

Other QEMU options are preserved. Select another port with `--com 2`. The launcher refuses to start
if the selected port is already defined. See [docs/qemu-launcher.md](docs/qemu-launcher.md).

### Standalone mode: the emulator alone

```bash
apolo-emu --listen /run/user/$UID/apollo.sock
qemu-system-i386 … -chardev socket,id=apollo,path=/run/user/$UID/apollo.sock,reconnect-ms=1000 \
                   -serial chardev:apollo
```

If QEMU is already configured as a server (`server=on`), connect in the opposite direction:

```bash
apolo-emu --connect /path/to/com1.sock
```

### Settings for each guest application

| Guest | Suggested options |
|---|---|
| Sonolect 7.11 (DOS) | `--language fr --codepage cp850 --extension burst-interrupt` (interrupt speech when typing) |
| Épaulard (Windows 3.11) | `--language fr --codepage cp850` with a version using the authentic `@E` echo; see below |
| IBM Screen Reader/2 (OS/2) | `--language en --extension lenient-speed` (the IBM profile sends `@wb` and `@wf`); see [launcher integration](docs/qemu-launcher.md) |
| Speakup (Linux) | none |

Extensions are disabled by default. They are described in [docs/extensions.md](docs/extensions.md)
and listed by `apolo-emu --list-extensions`.

The Épaulard trial described in the development report used a version modified to send
`text<CR>@E<c><CR>`. Versions using the old `@I<c>` need the `epaulard-index` extension;
read [its description](docs/extensions.md) before enabling it.

### Useful options

| Option | Purpose |
|---|---|
| `--backend simulated` | Silent output with simulated speech duration, for trials without Speech Dispatcher |
| `--backend null` | Silent output; each utterance finishes immediately |
| `--module espeak-ng`, `--voice NAME` | Select the Speech Dispatcher output module and voice |
| `--rate-offset`, `--pitch-offset`, `--volume-offset`, `--no-volume` | Adjust parameter mapping |
| `--trace FILE` | Timestamped log of every received (RX) and transmitted (TX) byte |
| `--log-level debug` | Detailed parsing and speech events |

## Documentation

Each document links to its French version.

| Document | Contents |
|---|---|
| [docs/protocol.md](docs/protocol.md) | Apollo II protocol, with sources and confidence levels |
| [docs/compatibility.md](docs/compatibility.md) | Command compatibility matrix |
| [docs/architecture.md](docs/architecture.md) | Modules, interfaces and synchronization model |
| [docs/serial-transport.md](docs/serial-transport.md) | QEMU, socket and Apollo responsibilities; flow control |
| [docs/speech-backend.md](docs/speech-backend.md) | Parameter mapping, SSML marks and Speech Dispatcher |
| [docs/qemu-launcher.md](docs/qemu-launcher.md) | Launcher and integration with existing QEMU commands |
| [docs/extensions.md](docs/extensions.md) | Non-authentic extensions, disabled by default |
| [docs/limitations.md](docs/limitations.md) | Known limitations |
| [docs/references.md](docs/references.md) | Sources consulted |
| [docs/publication.md](docs/publication.md) | Provenance and history checks before publication |
| [docs/development-report.md](docs/development-report.md) | Development report |
| [docs/requirements.md](docs/requirements.md) | Original project requirements |

## Tests

```bash
python3 -m unittest discover -s tests -t .                       # full suite, including QEMU if available
APOLO_EMU_SKIP_QEMU=1 python3 -m unittest discover -s tests -t .  # without QEMU
APOLO_EMU_SPEECHD=1 python3 -m unittest tests.test_speechd_integration   # actual speech, very low volume
```

The suite requires neither OS/2 nor Windows:

- A fake speech backend controls speech progress.
- A fake QEMU tests the launcher.
- A 512-byte boot sector, assembled by the tests, provides a test VM under real QEMU.
