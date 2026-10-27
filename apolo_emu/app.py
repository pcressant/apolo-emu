"""Assembly: device + speech backend + serial transport, configured from options."""

from __future__ import annotations

import asyncio
import logging
import signal
from dataclasses import dataclass, field
from typing import IO

from .device import ApolloDevice, DeviceConfig
from .mapping import Mapping
from .speech import NullBackend, SimulatedBackend
from .ssip import SSIPBackend
from .transport import SerialLink, Trace

log = logging.getLogger(__name__)


@dataclass
class Options:
    listen: str | None = None
    connect: str | None = None
    backend: str = "ssip"  # ssip, simulated, null
    speechd_address: str | None = None
    module: str | None = None
    synthesis_voice: str | None = None
    priority: str = "message"
    autospawn: bool = True
    client_name: str = "apolo-emu"
    mapping: Mapping = field(default_factory=Mapping)
    device: DeviceConfig = field(default_factory=DeviceConfig)
    cps: float = 15.0
    trace: IO[str] | None = None


class Emulator:
    """A complete virtual Apollo II, ready to connect to a socket."""

    def __init__(self, opts: Options) -> None:
        self.opts = opts
        if opts.backend == "ssip":
            self.backend = SSIPBackend(
                address=opts.speechd_address,
                client_name=opts.client_name,
                module=opts.module,
                synthesis_voice=opts.synthesis_voice,
                priority=opts.priority,
                mapping=opts.mapping,
                autospawn=opts.autospawn,
            )
        elif opts.backend == "simulated":
            self.backend = SimulatedBackend(opts.cps)
        elif opts.backend == "null":
            self.backend = NullBackend()
        else:
            raise ValueError(f"unknown backend: {opts.backend}")
        self.device = ApolloDevice(self.backend, None, opts.device)
        self.link = SerialLink(self.device, Trace(opts.trace) if opts.trace else None)
        self._connect_task: asyncio.Task | None = None

    async def start(self) -> None:
        await self.backend.start()
        if self.opts.listen:
            await self.link.listen(self.opts.listen)
        elif self.opts.connect:
            self._connect_task = asyncio.create_task(self.link.connect_forever(self.opts.connect))

    async def close(self) -> None:
        if self._connect_task:
            self._connect_task.cancel()
            await asyncio.gather(self._connect_task, return_exceptions=True)
        await self.link.close()
        await self.backend.close()


async def run_standalone(opts: Options) -> int:
    emu = Emulator(opts)
    await emu.start()
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
        loop.add_signal_handler(sig, stop.set)
    try:
        await stop.wait()
        log.info("shutdown requested")
    finally:
        for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
            loop.remove_signal_handler(sig)
        await emu.close()
    return 0
