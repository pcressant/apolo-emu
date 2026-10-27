"""Serial transport: connect the device to a Unix socket (QEMU socket chardev).

Sockets carry bytes only, not RTS, CTS, DTR or DSR. QEMU's emulated UART
sees CTS, DSR and DCD permanently asserted (docs/serial-transport.md).
No flow control is emulated here.
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
    """Remove a stale socket; reject a path in use or a non-socket path."""
    try:
        st = os.lstat(path)
    except FileNotFoundError:
        return
    if not stat.S_ISSOCK(st.st_mode):
        raise SocketInUse(f"{path} exists and is not a socket: refusing to replace it")
    probe = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        probe.settimeout(1.0)
        probe.connect(path)
    except (ConnectionRefusedError, FileNotFoundError):
        log.info("removed stale socket: %s", path)
        os.unlink(path)
        return
    except OSError as e:
        raise SocketInUse(f"{path} : {e}") from e
    finally:
        probe.close()
    raise SocketInUse(f"{path} is already in use by another process")


class Trace:
    """Timestamped byte log (format documented in docs/architecture.md)."""

    def __init__(self, stream: IO[str]) -> None:
        self.stream = stream
        self.t0 = time.monotonic()
        stream.write(f"# start {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        stream.flush()

    def record(self, direction: str, data: bytes) -> None:
        self.stream.write(f"{time.monotonic() - self.t0:10.4f} {direction} {data.hex(' ')}\n")
        self.stream.flush()


class SerialLink:
    """One connection at a time, like a serial cable."""

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
            log.warning("reply lost, serial port disconnected: %s", data.hex(" "))
            return
        self._writer.write(data)

    async def _session(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        if self._writer is not None and not self._writer.is_closing():
            log.warning("second connection rejected: serial port already connected")
            writer.close()
            try:
                await writer.wait_closed()
            except OSError:
                pass
            return
        self._writer = writer
        self.connected.set()
        log.info("serial port connected")
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
            log.warning("serial port: %s", e)
        finally:
            if self._writer is writer:
                self._writer = None
                self.connected.clear()
            writer.close()
            log.info("serial port disconnected")

    async def listen(self, path: str) -> None:
        prepare_listen_path(path)
        old = os.umask(0o077)
        try:
            self._server = await asyncio.start_unix_server(self._session, path=path)
        finally:
            os.umask(old)
        self._path = path
        log.info("listening on %s", path)

    async def connect_forever(self, path: str, retry: float = 1.0) -> None:
        """Client for a QEMU server chardev (server=on); reconnect indefinitely."""
        announced = False
        while True:
            try:
                reader, writer = await asyncio.open_unix_connection(path)
            except (FileNotFoundError, ConnectionRefusedError) as e:
                if not announced:
                    log.info("waiting for %s (%s)", path, e.__class__.__name__)
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
