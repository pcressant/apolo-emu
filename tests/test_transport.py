import asyncio
import io
import os
import socket
import tempfile
import unittest

from apolo_emu.device import ApolloDevice
from apolo_emu.speech import NullBackend
from apolo_emu.transport import SerialLink, SocketInUse, Trace, prepare_listen_path

from .test_ssip import until


class StaleSocketTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmp.name, "com.sock")

    def tearDown(self):
        self.tmp.cleanup()

    def test_missing_is_fine(self):
        prepare_listen_path(self.path)

    def test_stale_socket_removed(self):
        s = socket.socket(socket.AF_UNIX)
        s.bind(self.path)
        s.close()  # the file remains, but nobody is listening
        prepare_listen_path(self.path)
        self.assertFalse(os.path.exists(self.path))

    def test_live_socket_refused(self):
        s = socket.socket(socket.AF_UNIX)
        s.bind(self.path)
        s.listen()
        try:
            with self.assertRaises(SocketInUse):
                prepare_listen_path(self.path)
            self.assertTrue(os.path.exists(self.path))
        finally:
            s.close()

    def test_regular_file_refused(self):
        with open(self.path, "w") as f:
            f.write("x")
        with self.assertRaises(SocketInUse):
            prepare_listen_path(self.path)
        self.assertTrue(os.path.exists(self.path))


class LinkTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmp.name, "com.sock")
        self.trace = io.StringIO()
        self.device = ApolloDevice(NullBackend())
        self.link = SerialLink(self.device, Trace(self.trace))
        await self.link.listen(self.path)

    async def asyncTearDown(self):
        await self.link.close()
        self.tmp.cleanup()

    async def roundtrip(self, writer, reader, data: bytes, n: int) -> bytes:
        writer.write(data)
        await writer.drain()
        return await asyncio.wait_for(reader.readexactly(n), 2)

    async def test_query_over_socket(self):
        reader, writer = await asyncio.open_unix_connection(self.path)
        self.assertEqual(await self.roundtrip(writer, reader, b"@I?", 4), b"I00M")
        writer.close()
        self.assertIn("RX 40 49 3f", self.trace.getvalue())
        self.assertIn("TX 49 30 30 4d", self.trace.getvalue())

    async def test_fragments(self):
        reader, writer = await asyncio.open_unix_connection(self.path)
        for b in b"hello @Ex\r":
            writer.write(bytes((b,)))
            await writer.drain()
            await asyncio.sleep(0.001)
        self.assertEqual(await asyncio.wait_for(reader.readexactly(1), 2), b"x")
        writer.close()

    async def test_socket_permissions(self):
        self.assertEqual(os.stat(self.path).st_mode & 0o077, 0)  # owner access only

    async def test_second_connection_refused_then_reconnect(self):
        r1, w1 = await asyncio.open_unix_connection(self.path)
        await until(self.link.connected.is_set)
        r2, w2 = await asyncio.open_unix_connection(self.path)
        self.assertEqual(await asyncio.wait_for(r2.read(), 2), b"")  # closed immediately
        w2.close()
        self.assertEqual(await self.roundtrip(w1, r1, b"text @I+more\r\x18", 0), b"")
        w1.close()
        await until(lambda: not self.link.connected.is_set())
        # Device state persists across connections (index counter retained).
        r3, w3 = await asyncio.open_unix_connection(self.path)
        self.assertEqual(await self.roundtrip(w3, r3, b"@I?", 4), b"I10M")
        w3.close()

    async def test_reply_while_disconnected_is_dropped(self):
        self.device.feed(b"@Ez\r")
        self.assertEqual(self.link.dropped_replies, 1)

    async def test_close_removes_socket(self):
        await self.link.close()
        self.assertFalse(os.path.exists(self.path))


class ConnectModeTests(unittest.IsolatedAsyncioTestCase):
    async def test_connects_and_reconnects(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "qemu.sock")
            sessions = asyncio.Queue()

            async def qemu(reader, writer):  # QEMU with server=on
                await sessions.put((reader, writer))

            device = ApolloDevice(NullBackend())
            link = SerialLink(device)
            task = asyncio.create_task(link.connect_forever(path, retry=0.05))
            await asyncio.sleep(0.1)  # QEMU not ready yet: emulator waits
            server = await asyncio.start_unix_server(qemu, path=path)
            reader, writer = await asyncio.wait_for(sessions.get(), 2)
            writer.write(b"@I?")
            self.assertEqual(await asyncio.wait_for(reader.readexactly(4), 2), b"I00M")
            writer.close()
            reader, writer = await asyncio.wait_for(sessions.get(), 2)  # reconnection
            writer.write(b"@W?")
            writer.write(b"\r")
            self.assertEqual(await asyncio.wait_for(reader.readexactly(3), 2), b"W30")
            writer.close()
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            server.close()
            await link.close()


if __name__ == "__main__":
    unittest.main()
