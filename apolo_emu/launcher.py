"""Lanceur : démarre Apolo-emu puis QEMU, relie un port COM à l'émulateur, nettoie à la fin.

Principes (docs/lanceur-qemu.md) :
- l'émulateur écoute d'abord, sur une socket propre à l'instance ; QEMU s'y connecte ;
- le port est ajouté par « -device isa-serial,index=N », sans toucher aux options de
  l'utilisateur, et refusé s'il est déjà occupé ;
- les signaux reçus sont transmis à QEMU, seul juge de son arrêt ; le lanceur ne tue
  jamais QEMU de force et n'agit sur aucun autre processus ;
- le code de retour de QEMU est rendu tel quel.
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import signal
import stat
import tempfile
from dataclasses import dataclass

from .app import Emulator, Options

log = logging.getLogger(__name__)

DIR_PREFIX = "apolo-emu-"
SOCKET_NAME = "com.sock"
PID_NAME = "pid"
EXIT_USAGE = 2
EXIT_NOT_EXECUTABLE = 126
EXIT_NOT_FOUND = 127


class LaunchError(Exception):
    pass


@dataclass
class SerialUsage:
    occupied: set[int]
    auto: int = 0  # isa-serial sans index, placés par QEMU
    warnings: list[str] | None = None


def _option(arg: str) -> str | None:
    """« -serial », « --serial » -> « serial » ; None pour un argument qui n'est pas une option."""
    if arg.startswith("--") and len(arg) > 2:
        return arg[2:]
    if arg.startswith("-") and len(arg) > 1:
        return arg[1:]
    return None


def _props(value: str) -> tuple[str, dict[str, str]]:
    """« isa-serial,index=1 » ou « driver=isa-serial,index=1 » -> pilote et propriétés."""
    items = value.split(",")
    props = {}
    driver = ""
    for n, item in enumerate(items):
        k, eq, v = item.partition("=")
        if n == 0 and not eq:
            driver = k
        else:
            props[k] = v
    return props.pop("driver", driver), props


VALUE_OPTIONS = {"serial", "device", "chardev", "readconfig"}


def serial_usage(args: list[str]) -> SerialUsage:
    """Ports COM déjà utilisés par une ligne de commande QEMU."""
    usage = SerialUsage(set(), 0, [])
    next_serial = 0
    nographic = False
    any_serial = False
    i = 0
    while i < len(args):
        opt = _option(args[i])
        value = None
        if opt is not None and "=" in opt:
            opt, _, value = opt.partition("=")
        elif opt in VALUE_OPTIONS and i + 1 < len(args):
            value = args[i + 1]
            i += 1
        i += 1
        if opt == "serial" and value is not None:
            any_serial = True
            if value != "none":  # « none » consomme un numéro sans créer de port (vérifié sur QEMU 10.2)
                usage.occupied.add(next_serial)
            next_serial += 1
        elif opt == "device" and value is not None:
            driver, props = _props(value)
            if driver == "isa-serial":
                any_serial = True
                if "index" in props:
                    try:
                        usage.occupied.add(int(props["index"], 0))
                    except ValueError:
                        usage.warnings.append(f"index illisible : {value}")
                else:
                    usage.auto += 1
        elif opt == "nographic":
            nographic = True
        elif opt == "readconfig":
            usage.warnings.append("-readconfig : les ports série qu'il définit ne sont pas vérifiés")
    if nographic and not any_serial:
        usage.warnings.append(
            "-nographic sans -serial : la console série que QEMU aurait placée sur COM1 ne sera pas créée "
            "(ajouter par exemple « -serial mon:stdio » et choisir --com 2)"
        )
    return usage


def build_qemu_args(argv: list[str], socket_path: str, com: int, chardev_id: str) -> list[str]:
    if not argv:
        raise LaunchError("commande QEMU absente : apolo-emu run [options] -- qemu-system-i386 …")
    if not 1 <= com <= 4:
        raise LaunchError("--com doit valoir 1, 2, 3 ou 4")
    usage = serial_usage(argv[1:])
    for w in usage.warnings or []:
        log.warning("%s", w)
    index = com - 1
    if index in usage.occupied:
        raise LaunchError(
            f"COM{com} est déjà défini dans la commande QEMU (ports occupés : "
            f"{', '.join(f'COM{i + 1}' for i in sorted(usage.occupied))}) ; choisir un autre port avec --com"
        )
    if usage.auto:
        log.warning("%d isa-serial sans index : QEMU leur choisira un port ; conflit possible avec COM%d",
                    usage.auto, com)
    for i, arg in enumerate(argv):
        if _option(arg) == "chardev" and i + 1 < len(argv) and f"id={chardev_id}" in argv[i + 1].split(","):
            raise LaunchError(f"identifiant de chardev déjà utilisé : {chardev_id}")
    return [
        *argv,
        "-chardev", f"socket,id={chardev_id},path={socket_path}",
        "-device", f"isa-serial,chardev={chardev_id},index={index}",
    ]


def runtime_dir() -> str:
    d = os.environ.get("XDG_RUNTIME_DIR")
    if d and os.path.isdir(d) and os.access(d, os.W_OK):
        return d
    return tempfile.gettempdir()


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def clean_stale_dirs(base: str) -> list[str]:
    """Supprime les répertoires d'instances abandonnées (processus disparu), et seulement eux."""
    removed = []
    try:
        entries = os.listdir(base)
    except OSError:
        return removed
    uid = os.getuid()
    for name in entries:
        if not name.startswith(DIR_PREFIX):
            continue
        path = os.path.join(base, name)
        try:
            st = os.lstat(path)
            if not stat.S_ISDIR(st.st_mode) or st.st_uid != uid:
                continue
            content = set(os.listdir(path))
            if not content <= {SOCKET_NAME, PID_NAME}:
                continue  # contenu inattendu : on n'y touche pas
            with open(os.path.join(path, PID_NAME)) as f:
                pid = int(f.read().strip())
        except (OSError, ValueError):
            continue
        if _pid_alive(pid):
            continue
        for item in content:
            os.unlink(os.path.join(path, item))
        os.rmdir(path)
        removed.append(path)
        log.info("répertoire d'instance abandonné supprimé : %s", path)
    return removed


class InstanceDir:
    def __init__(self, base: str | None = None) -> None:
        base = base or runtime_dir()
        clean_stale_dirs(base)
        self.path = tempfile.mkdtemp(prefix=DIR_PREFIX, dir=base)
        with open(os.path.join(self.path, PID_NAME), "w") as f:
            f.write(f"{os.getpid()}\n")
        self.socket = os.path.join(self.path, SOCKET_NAME)
        if len(self.socket.encode()) > 107:
            self.remove()
            raise LaunchError(f"chemin de socket trop long : {self.socket}")

    def remove(self) -> None:
        for name in (SOCKET_NAME, PID_NAME):
            try:
                os.unlink(os.path.join(self.path, name))
            except FileNotFoundError:
                pass
        try:
            os.rmdir(self.path)
        except OSError as e:
            log.warning("répertoire non supprimé %s : %s", self.path, e)


FORWARDED = (signal.SIGINT, signal.SIGTERM, signal.SIGHUP, signal.SIGQUIT)


async def run_launcher(qemu_argv: list[str], opts: Options, com: int = 1, base_dir: str | None = None,
                       on_signal: str = "forward") -> int:
    if not qemu_argv:
        log.error("commande QEMU absente : apolo-emu run [options] -- qemu-system-i386 …")
        return EXIT_USAGE
    if shutil.which(qemu_argv[0]) is None and not os.path.exists(qemu_argv[0]):
        log.error("programme introuvable : %s", qemu_argv[0])
        return EXIT_NOT_FOUND
    try:
        inst = InstanceDir(base_dir)
    except (OSError, LaunchError) as e:
        log.error("%s", e)
        return EXIT_USAGE
    emu = None
    loop = asyncio.get_running_loop()
    try:
        try:
            argv = build_qemu_args(qemu_argv, inst.socket, com, f"apolo-emu-{os.getpid()}")
        except LaunchError as e:
            log.error("%s", e)
            return EXIT_USAGE
        opts.listen, opts.connect = inst.socket, None
        emu = Emulator(opts)
        try:
            await emu.start()
        except Exception as e:
            log.error("l'émulateur n'a pas pu démarrer : %s", e)
            return EXIT_USAGE
        log.info("lancement : %s", " ".join(argv))
        try:
            proc = await asyncio.create_subprocess_exec(*argv)
        except FileNotFoundError:
            log.error("programme introuvable : %s", argv[0])
            return EXIT_NOT_FOUND
        except PermissionError:
            log.error("programme non exécutable : %s", argv[0])
            return EXIT_NOT_EXECUTABLE

        def forward(sig: signal.Signals) -> None:
            if proc.returncode is not None:
                return
            if on_signal == "forward":
                log.info("%s transmis à QEMU (pid %d)", sig.name, proc.pid)
                try:
                    proc.send_signal(sig)
                except ProcessLookupError:
                    pass
            else:
                log.warning("%s reçu : arrêtez le système invité, puis fermez QEMU", sig.name)

        for sig in FORWARDED:
            loop.add_signal_handler(sig, forward, sig)
        try:
            rc = await proc.wait()
        finally:
            for sig in FORWARDED:
                loop.remove_signal_handler(sig)
        if rc < 0:
            log.info("QEMU arrêté par le signal %d", -rc)
            return 128 - rc
        log.info("QEMU terminé (code %d)", rc)
        return rc
    finally:
        if emu is not None:
            try:
                await emu.close()
            except Exception:
                log.exception("erreur à la fermeture de l'émulateur")
        inst.remove()
