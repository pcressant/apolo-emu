"""Transport série : relie l'appareil à une socket Unix (côté QEMU : chardev socket).

Une socket ne transporte que des octets : RTS, CTS, DTR et DSR ne la traversent
pas, et l'UART émulée par QEMU voit CTS, DSR et DCD actifs en permanence
(docs/transport-serie.md). Aucun contrôle de flux n'est donc émulé ici.
"""

from __future__ import annotations

import asyncio
import logging
import os
import socket
import stat
import time
from typing import IO

from .device import ApolloDevice

log = logging.getLogger(__name__)

READ_SIZE = 4096


class SocketInUse(Exception):
    pass


def prepare_listen_path(path: str) -> None:
    """Supprime une socket obsolète ; refuse un chemin utilisé ou qui n'est pas une socket."""
    try:
        st = os.lstat(path)
    except FileNotFoundError:
        return
    if not stat.S_ISSOCK(st.st_mode):
        raise SocketInUse(f"{path} existe et n'est pas une socket : refus de le remplacer")
    probe = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        probe.settimeout(1.0)
        probe.connect(path)
    except (ConnectionRefusedError, FileNotFoundError):
        log.info("socket obsolète supprimée : %s", path)
        os.unlink(path)
        return
    except OSError as e:
        raise SocketInUse(f"{path} : {e}") from e
    finally:
        probe.close()
    raise SocketInUse(f"{path} est déjà utilisée par un autre processus")


class Trace:
    """Journal horodaté des octets échangés (format décrit dans docs/architecture.md)."""

    def __init__(self, stream: IO[str]) -> None:
        self.stream = stream
        self.t0 = time.monotonic()
        stream.write(f"# début {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        stream.flush()

    def record(self, direction: str, data: bytes) -> None:
        self.stream.write(f"{time.monotonic() - self.t0:10.4f} {direction} {data.hex(' ')}\n")
        self.stream.flush()


class SerialLink:
    """Une seule connexion à la fois, comme un câble série."""

    def __init__(self, device: ApolloDevice, trace: Trace | None = None) -> None:
        self.device = device
        self.trace = trace
        self._writer: asyncio.StreamWriter | None = None
        self._server: asyncio.base_events.Server | None = None
        self._path: str | None = None
        self.connected = asyncio.Event()
        self.dropped_replies = 0
        device.reply_sink = self.write

    def write(self, data: bytes) -> None:
        if self.trace:
            self.trace.record("TX", data)
        if self._writer is None or self._writer.is_closing():
            self.dropped_replies += len(data)
            log.warning("réponse perdue, port série non connecté : %s", data.hex(" "))
            return
        self._writer.write(data)

    async def _session(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        if self._writer is not None and not self._writer.is_closing():
            log.warning("seconde connexion refusée : le port série est déjà relié")
            writer.close()
            try:
                await writer.wait_closed()
            except OSError:
                pass
            return
        self._writer = writer
        self.connected.set()
        log.info("port série relié")
        try:
            while True:
                data = await reader.read(READ_SIZE)
                if not data:
                    break
                if self.trace:
                    self.trace.record("RX", data)
                log.debug("RX %s", data.hex(" "))
                self.device.feed(data)
        except (ConnectionError, OSError) as e:
            log.warning("port série : %s", e)
        finally:
            if self._writer is writer:
                self._writer = None
                self.connected.clear()
            writer.close()
            log.info("port série débranché")

    async def listen(self, path: str) -> None:
        prepare_listen_path(path)
        old = os.umask(0o077)
        try:
            self._server = await asyncio.start_unix_server(self._session, path=path)
        finally:
            os.umask(old)
        self._path = path
        log.info("en écoute sur %s", path)

    async def connect_forever(self, path: str, retry: float = 1.0) -> None:
        """Client d'un chardev QEMU serveur (server=on) ; se reconnecte indéfiniment."""
        announced = False
        while True:
            try:
                reader, writer = await asyncio.open_unix_connection(path)
            except (FileNotFoundError, ConnectionRefusedError) as e:
                if not announced:
                    log.info("attente de %s (%s)", path, e.__class__.__name__)
                    announced = True
                await asyncio.sleep(retry)
                continue
            announced = False
            await self._session(reader, writer)
            await asyncio.sleep(retry)

    async def close(self) -> None:
        if self._writer is not None:
            self._writer.close()
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None
        if self._path is not None:
            try:
                if stat.S_ISSOCK(os.lstat(self._path).st_mode):
                    os.unlink(self._path)
            except FileNotFoundError:
                pass
            self._path = None
