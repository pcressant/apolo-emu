"""Intégration avec le vrai Speech Dispatcher et eSpeak NG.

Produit du son (volume très bas, priorité « notification » pour ne pas couper les autres
clients) : à lancer explicitement avec APOLO_EMU_SPEECHD=1.
"""

import asyncio
import os
import time
import unittest

from apolo_emu.device import ApolloDevice, DeviceConfig
from apolo_emu.mapping import Mapping
from apolo_emu.ssip import SSIPBackend

from .test_ssip import until


@unittest.skipUnless(os.environ.get("APOLO_EMU_SPEECHD"), "APOLO_EMU_SPEECHD=1 pour activer")
class SpeechdTests(unittest.IsolatedAsyncioTestCase):
    async def test_echo_and_index_follow_real_speech(self):
        backend = SSIPBackend(priority="notification", mapping=Mapping(volume_offset=-90),
                              client_name="apolo-emu-test", module=os.environ.get("APOLO_EMU_MODULE"))
        replies = []
        t0 = time.monotonic()
        dev = ApolloDevice(backend, lambda b: replies.append((time.monotonic() - t0, b)),
                           DeviceConfig(languages={1: "fr"}))
        await backend.start()
        try:
            dev.feed(b"@E1un deux trois quatre, @I+cinq six sept huit.\r@E2\r")
            dev.feed(b"@I?")
            await until(lambda: any(b == b"2" for _, b in replies), timeout=15)
            # @I? répond tout de suite ; « 1 » attend que la parole atteigne la proposition.
            self.assertEqual([b for _, b in replies], [b"I10T", b"1", b"2"])
            t1, t2 = replies[1][0], replies[2][0]
            self.assertGreater(t2 - t1, 0.5, "l'écho final doit suivre la parole réelle")
            replies.clear()
            dev.feed(b"@I?")
            self.assertEqual(replies[0][1], b"I00M")
        finally:
            await backend.close()


if __name__ == "__main__":
    unittest.main()
