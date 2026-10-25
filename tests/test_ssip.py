import asyncio
import os
import tempfile
import unittest

from apolo_emu.speech import Mark, Pause, Utterance, VoiceParams
from apolo_emu.ssip import SSIPBackend, escape_data, to_ssml


class FakeSpeechd:
    """Serveur SSIP minimal : enregistre les commandes, émet les événements à la demande."""

    def __init__(self, path: str, refuse_speak: bool = False) -> None:
        self.path = path
        self.commands: list[str] = []
        self.bodies: list[str] = []
        self.writer: asyncio.StreamWriter | None = None
        self.refuse_speak = refuse_speak
        self.next_id = 100
        self.connections = 0
        self.server = None

    async def start(self):
        self.server = await asyncio.start_unix_server(self._client, path=self.path)

    async def stop(self):
        if self.writer:
            self.writer.close()
        self.server.close()
        await self.server.wait_closed()

    async def _client(self, reader, writer):
        self.connections += 1
        self.writer = writer
        try:
            while True:
                line = await reader.readline()
                if not line:
                    return
                cmd = line.decode().rstrip("\r\n")
                self.commands.append(cmd)
                if cmd == "SPEAK":
                    if self.refuse_speak:
                        writer.write(b"401 ERR MESSAGE REFUSED\r\n")
                        continue
                    writer.write(b"230 OK RECEIVING DATA\r\n")
                    body = []
                    while True:
                        l = (await reader.readline()).decode().rstrip("\r\n")
                        if l == ".":
                            break
                        body.append(l)
                    self.bodies.append("\n".join(body))
                    self.next_id += 1
                    writer.write(f"225-{self.next_id}\r\n225 OK MESSAGE QUEUED\r\n".encode())
                elif cmd == "QUIT":
                    writer.write(b"231 HAPPY HACKING\r\n")
                elif cmd.startswith("CANCEL"):
                    writer.write(b"210 OK CANCELED\r\n")
                else:
                    writer.write(b"200 OK\r\n")
        except ConnectionError:
            pass

    def event(self, code: int, msg_id: int, text: str, extra: str | None = None):
        lines = [f"{code}-{msg_id}", f"{code}-1"]
        if extra is not None:
            lines.append(f"{code}-{extra}")
        lines.append(f"{code} {text}")
        self.writer.write(("\r\n".join(lines) + "\r\n").encode())


async def until(cond, timeout=2.0):
    loop = asyncio.get_running_loop()
    end = loop.time() + timeout
    while not cond():
        if loop.time() > end:
            raise AssertionError("délai dépassé")
        await asyncio.sleep(0.005)


class RenderTests(unittest.TestCase):
    def test_ssml(self):
        utt = Utterance(1, VoiceParams(), [Mark("m1"), "a < b & c", Pause(100), Mark("m2")])
        self.assertEqual(to_ssml(utt), '<speak><mark name="m1"/>a &lt; b &amp; c<break time="100ms"/><mark name="m2"/></speak>')

    def test_dot_escaping(self):
        self.assertEqual(escape_data(".\n..x\ny"), "..\r\n...x\r\ny")


class SSIPTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmp.name, "speechd.sock")
        self.server = FakeSpeechd(self.path)
        await self.server.start()
        self.events = []
        self.be = SSIPBackend(address=f"unix_socket:{self.path}", autospawn=False)
        self.be.set_event_sink(self.events.append)
        await self.be.start()

    async def asyncTearDown(self):
        await self.be.close()
        await self.server.stop()
        self.tmp.cleanup()

    async def test_setup_and_speak(self):
        self.assertIn("SET self SSML_MODE on", self.server.commands)
        self.assertIn("SET self NOTIFICATION all on", self.server.commands)
        self.assertIn("SET self PRIORITY message", self.server.commands)
        self.be.speak(Utterance(7, VoiceParams(speed=5), [Mark("m1"), "bonjour"]))
        await until(lambda: self.server.bodies)
        self.assertEqual(self.server.bodies[0], '<speak><mark name="m1"/>bonjour</speak>')
        self.assertIn("SET self RATE 33", self.server.commands)

    async def test_settings_sent_only_when_changed(self):
        self.be.speak(Utterance(1, VoiceParams(), ["a"]))
        self.be.speak(Utterance(2, VoiceParams(), ["b"]))
        self.be.speak(Utterance(3, VoiceParams(pitch=12), ["c"]))
        await until(lambda: len(self.server.bodies) == 3)
        self.assertEqual(sum(c.startswith("SET self RATE") for c in self.server.commands), 1)
        self.assertEqual(sum(c.startswith("SET self PITCH") for c in self.server.commands), 2)

    async def test_events(self):
        self.be.speak(Utterance(5, VoiceParams(), [Mark("m1"), "x", Mark("m2")]))
        await until(lambda: self.server.bodies)
        msg = self.server.next_id
        self.server.event(701, msg, "BEGIN")
        self.server.event(700, msg, "INDEX MARK", "m2")
        self.server.event(702, msg, "END")
        await until(lambda: len(self.events) == 3)
        self.assertEqual([(e.uid, e.kind, e.mark) for e in self.events],
                         [(5, "begin", None), (5, "mark", "m2"), (5, "end", None)])

    async def test_cancel(self):
        self.be.speak(Utterance(1, VoiceParams(), ["a"]))
        await until(lambda: self.server.bodies)
        self.be.speak(Utterance(2, VoiceParams(), ["b"]))
        self.be.cancel()
        await until(lambda: "CANCEL self" in self.server.commands)
        self.assertEqual(len(self.server.bodies), 1)  # le second n'a jamais été transmis

    async def test_disconnect_releases_sent_utterances(self):
        self.be.speak(Utterance(9, VoiceParams(), ["a"]))
        await until(lambda: self.server.bodies)
        self.server.writer.close()
        await until(lambda: any(e.uid == 9 and e.kind == "end" for e in self.events))
        # Reconnexion automatique au prochain énoncé, réglages renvoyés.
        self.be.speak(Utterance(10, VoiceParams(), ["b"]))
        await until(lambda: len(self.server.bodies) == 2)
        self.assertEqual(self.server.connections, 2)
        self.assertEqual(sum(c.startswith("SET self RATE") for c in self.server.commands), 2)


class SSIPFailureTests(unittest.IsolatedAsyncioTestCase):
    async def test_unreachable_does_not_block(self):
        events = []
        be = SSIPBackend(address="unix_socket:/nonexistent/apolo-emu-test.sock", autospawn=False, connect_timeout=0.2)
        be.set_event_sink(events.append)
        await be.start()
        be.speak(Utterance(3, VoiceParams(), ["a"]))
        await until(lambda: events)
        self.assertEqual((events[0].uid, events[0].kind), (3, "end"))
        await be.close()

    async def test_refused_speak(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "s.sock")
            server = FakeSpeechd(path, refuse_speak=True)
            await server.start()
            events = []
            be = SSIPBackend(address=f"unix_socket:{path}", autospawn=False)
            be.set_event_sink(events.append)
            await be.start()
            be.speak(Utterance(4, VoiceParams(), ["a"]))
            await until(lambda: events)
            self.assertEqual((events[0].uid, events[0].kind), (4, "end"))
            await be.close()
            await server.stop()


if __name__ == "__main__":
    unittest.main()
