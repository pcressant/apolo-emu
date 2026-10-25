"""Ligne de commande.

  apolo-emu [options] [--listen CHEMIN | --connect CHEMIN]   émulateur seul
  apolo-emu run [options] -- qemu-system-i386 …              émulateur + QEMU
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
    """« fr » ou « 1=en,2=fr »."""
    out: dict[int, str] = {}
    for n, item in enumerate(value.split(","), start=1):
        slot, eq, lang = item.partition("=")
        if eq:
            out[int(slot)] = lang.strip()
        else:
            out[n] = slot.strip()
    if not out or any(not 1 <= k <= 7 for k in out):
        raise argparse.ArgumentTypeError("emplacements 1 à 7, par exemple « 1=en,2=fr »")
    return out


def _common(p: argparse.ArgumentParser) -> None:
    g = p.add_argument_group("appareil")
    g.add_argument("--languages", "--language", type=_languages, default={1: "en"}, metavar="LISTE",
                   help="langue de chaque emplacement de ROM (@=n) : « fr » ou « 1=en,2=fr » (défaut : en)")
    g.add_argument("--codepage", default="cp437", help="page de codes du texte reçu (défaut : cp437)")
    g.add_argument("--extension", action="append", default=[], choices=sorted(EXTENSIONS), metavar="NOM",
                   help="active une extension non authentique (répétable ; voir --list-extensions)")
    g.add_argument("--talking-rule", choices=("doc", "rom"), default="doc",
                   help="sens de T/M dans la réponse à @I? (défaut : doc)")
    g.add_argument("--version-text", default=DeviceConfig.version_text, help="texte dit par @?")

    g = p.add_argument_group("parole")
    g.add_argument("--backend", choices=("ssip", "simulated", "null"), default="ssip",
                   help="ssip : Speech Dispatcher ; simulated : sans son, durée simulée ; null : sans son, immédiat")
    g.add_argument("--speechd-address", help="adresse SSIP (défaut : $SPEECHD_ADDRESS ou la socket de session)")
    g.add_argument("--module", help="module de sortie Speech Dispatcher (par exemple espeak-ng)")
    g.add_argument("--voice", dest="synthesis_voice", help="voix du moteur (SYNTHESIS_VOICE) ; remplace @V")
    g.add_argument("--priority", default="message",
                   choices=("important", "message", "text", "notification", "progress"),
                   help="priorité SSIP (défaut : message, les énoncés se suivent sans s'annuler)")
    g.add_argument("--no-autospawn", dest="autospawn", action="store_false",
                   help="ne pas démarrer Speech Dispatcher s'il est absent")
    g.add_argument("--rate-offset", type=int, default=0, help="décalage ajouté au débit SSIP")
    g.add_argument("--pitch-offset", type=int, default=0, help="décalage ajouté à la hauteur SSIP")
    g.add_argument("--volume-offset", type=int, default=0, help="décalage ajouté au volume SSIP")
    g.add_argument("--no-volume", dest="use_volume", action="store_false", help="ignorer @A")
    g.add_argument("--cps", type=float, default=15.0, help="caractères par seconde du backend simulé")

    g = p.add_argument_group("journal")
    g.add_argument("--log-level", default="info", choices=("debug", "info", "warning", "error"))
    g.add_argument("--trace", type=argparse.FileType("a", encoding="utf-8"), metavar="FICHIER",
                   help="journal horodaté des octets reçus (RX) et émis (TX)")


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
        raise SystemExit(f"apolo-emu: page de codes inconnue : {name}")


def main_standalone(argv: list[str]) -> int:
    p = argparse.ArgumentParser(prog="apolo-emu", description="Émulateur du synthétiseur vocal Apollo II.",
                                epilog="Mode lanceur : apolo-emu run --help")
    where = p.add_mutually_exclusive_group()
    where.add_argument("--listen", "--socket", dest="listen", metavar="CHEMIN",
                       help="écoute sur une socket Unix (QEMU : -chardev socket,path=CHEMIN)")
    where.add_argument("--connect", metavar="CHEMIN",
                       help="se connecte à la socket d'un chardev QEMU serveur (server=on) et s'y reconnecte")
    p.add_argument("--list-extensions", action="store_true", help="liste les extensions et quitte")
    p.add_argument("--version", action="version", version=f"apolo-emu {__version__}")
    _common(p)
    ns = p.parse_args(argv)
    if ns.list_extensions:
        for name, doc in sorted(EXTENSIONS.items()):
            print(f"{name:16} {doc}")
        return 0
    if not ns.listen and not ns.connect:
        p.error("indiquer --listen CHEMIN ou --connect CHEMIN (ou utiliser « apolo-emu run »)")
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
                                description="Démarre Apolo-emu puis QEMU, relié à un port COM de l'invité.",
                                usage="apolo-emu run [options] -- qemu-system-i386 [options QEMU]")
    p.add_argument("--com", type=int, default=1, choices=(1, 2, 3, 4), help="port COM de l'invité (défaut : 1)")
    p.add_argument("--socket-dir", metavar="DOSSIER",
                   help="dossier des répertoires d'instance (défaut : $XDG_RUNTIME_DIR)")
    p.add_argument("--on-signal", choices=("forward", "wait"), default="forward",
                   help="forward : transmettre SIGINT/SIGTERM/SIGHUP à QEMU ; wait : attendre que QEMU s'arrête")
    _common(p)
    ns = p.parse_args(own)
    if not qemu:
        p.error("commande QEMU absente après « -- »")
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
