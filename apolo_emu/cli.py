"""Command-line interface.

  apolo-emu [options] [--listen PATH | --connect PATH]   standalone emulator
  apolo-emu run [options] -- qemu-system-i386 …          emulator + QEMU
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys

from . import __version__
from .app import Options, run_standalone
from .device import EXTENSIONS, DeviceConfig
from .mapping import Mapping


def _languages(value: str) -> dict[int, str]:
    """"fr" or "1=en,2=fr"."""
    out: dict[int, str] = {}
    for n, item in enumerate(value.split(","), start=1):
        slot, eq, lang = item.partition("=")
        if eq:
            out[int(slot)] = lang.strip()
        else:
            out[n] = slot.strip()
    if not out or any(not 1 <= k <= 7 for k in out):
        raise argparse.ArgumentTypeError("banks 1 through 7, for example 1=en,2=fr")
    return out


def _common(p: argparse.ArgumentParser) -> None:
    g = p.add_argument_group("device")
    g.add_argument("--languages", "--language", type=_languages, default={1: "en"}, metavar="LIST",
                   help="language of each ROM bank (@=n): fr or 1=en,2=fr (default: en)")
    g.add_argument("--codepage", default="cp437", help="code page of received text (default: cp437)")
    g.add_argument("--extension", action="append", default=[], choices=sorted(EXTENSIONS), metavar="NAME",
                   help="enable a non-authentic extension (repeatable; see --list-extensions)")
    g.add_argument("--talking-rule", choices=("doc", "rom"), default="doc",
                   help="meaning of T/M in the @I? reply (default: doc)")
    g.add_argument("--version-text", default=DeviceConfig.version_text, help="text spoken by @?")

    g = p.add_argument_group("speech")
    g.add_argument("--backend", choices=("ssip", "simulated", "null"), default="ssip",
                   help="ssip: Speech Dispatcher; simulated: silent, simulated duration; null: silent, immediate")
    g.add_argument("--speechd-address", help="SSIP address (default: $SPEECHD_ADDRESS or session socket)")
    g.add_argument("--module", help="Speech Dispatcher output module (e.g. espeak-ng)")
    g.add_argument("--voice", dest="synthesis_voice", help="engine voice (SYNTHESIS_VOICE); overrides @V")
    g.add_argument("--priority", default="message",
                   choices=("important", "message", "text", "notification", "progress"),
                   help="SSIP priority (default: message, sequential utterances without cancellation)")
    g.add_argument("--no-autospawn", dest="autospawn", action="store_false",
                   help="do not start Speech Dispatcher if absent")
    g.add_argument("--rate-offset", type=int, default=0, help="offset added to SSIP rate")
    g.add_argument("--pitch-offset", type=int, default=0, help="offset added to SSIP pitch")
    g.add_argument("--volume-offset", type=int, default=0, help="offset added to SSIP volume")
    g.add_argument("--no-volume", dest="use_volume", action="store_false", help="ignore @A")
    g.add_argument("--cps", type=float, default=15.0, help="characters per second for the simulated backend")

    g = p.add_argument_group("logging")
    g.add_argument("--log-level", default="info", choices=("debug", "info", "warning", "error"))
    g.add_argument("--trace", type=argparse.FileType("a", encoding="utf-8"), metavar="FILE",
                   help="timestamped log of received (RX) and transmitted (TX) bytes")


def _options(ns: argparse.Namespace) -> Options:
    return Options(
        listen=getattr(ns, "listen", None),
        connect=getattr(ns, "connect", None),
        backend=ns.backend,
        speechd_address=ns.speechd_address,
        module=ns.module,
        synthesis_voice=ns.synthesis_voice,
        priority=ns.priority,
        autospawn=ns.autospawn,
        mapping=Mapping(ns.rate_offset, ns.pitch_offset, ns.volume_offset, ns.use_volume),
        device=DeviceConfig(
            codepage=ns.codepage,
            languages=ns.languages,
            extensions=frozenset(ns.extension),
            talking_rule=ns.talking_rule,
            version_text=ns.version_text,
        ),
        cps=ns.cps,
        trace=ns.trace,
    )


def _setup_logging(level: str) -> None:
    logging.basicConfig(level=level.upper(), format="%(asctime)s apolo-emu %(levelname)s %(name)s: %(message)s",
                        datefmt="%H:%M:%S",
                        stream=sys.stderr)


def _check_codepage(name: str) -> None:
    import codecs

    try:
        codecs.lookup(name)
    except LookupError:
        raise SystemExit(f"apolo-emu: unknown code page: {name}")


def main_standalone(argv: list[str]) -> int:
    p = argparse.ArgumentParser(prog="apolo-emu", description="Apollo II speech synthesizer emulator.",
                                epilog="Launcher mode: apolo-emu run --help")
    where = p.add_mutually_exclusive_group()
    where.add_argument("--listen", "--socket", dest="listen", metavar="PATH",
                       help="listen on a Unix socket (QEMU: -chardev socket,path=PATH)")
    where.add_argument("--connect", metavar="PATH",
                       help="connect and reconnect to a QEMU server chardev socket (server=on)")
    p.add_argument("--list-extensions", action="store_true", help="list extensions and exit")
    p.add_argument("--version", action="version", version=f"apolo-emu {__version__}")
    _common(p)
    ns = p.parse_args(argv)
    if ns.list_extensions:
        for name, doc in sorted(EXTENSIONS.items()):
            print(f"{name:16} {doc}")
        return 0
    if not ns.listen and not ns.connect:
        p.error("specify --listen PATH or --connect PATH (or use apolo-emu run)")
    _check_codepage(ns.codepage)
    _setup_logging(ns.log_level)
    return asyncio.run(run_standalone(_options(ns)))


def main_run(argv: list[str]) -> int:
    from .launcher import run_launcher

    if "--" in argv:
        cut = argv.index("--")
        own, qemu = argv[:cut], argv[cut + 1 :]
    else:
        own, qemu = argv, []
    p = argparse.ArgumentParser(prog="apolo-emu run",
                                description="Start Apolo-emu and QEMU, connected to a guest COM port.",
                                usage="apolo-emu run [options] -- qemu-system-i386 [QEMU options]")
    p.add_argument("--com", type=int, default=1, choices=(1, 2, 3, 4), help="guest COM port (default: 1)")
    p.add_argument("--socket-dir", metavar="DIR",
                   help="parent directory for instances (default: $XDG_RUNTIME_DIR)")
    p.add_argument("--on-signal", choices=("forward", "wait"), default="forward",
                   help="forward: send SIGINT/SIGTERM/SIGHUP to QEMU; wait: wait for QEMU to exit")
    _common(p)
    ns = p.parse_args(own)
    if not qemu:
        p.error("missing QEMU command after --")
    _check_codepage(ns.codepage)
    _setup_logging(ns.log_level)
    return asyncio.run(run_launcher(qemu, _options(ns), ns.com, ns.socket_dir, ns.on_signal))


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    try:
        if argv and argv[0] == "run":
            return main_run(argv[1:])
        return main_standalone(argv)
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
