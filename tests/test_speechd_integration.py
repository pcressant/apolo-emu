"""Integration with real Speech Dispatcher and eSpeak NG.

Produces sound at very low volume with notification priority to avoid interrupting
other clients. Run explicitly with APOLO_EMU_SPEECHD=1.
"""

import asyncio
import os
import time
import unittest

from apolo_emu.device import ApolloDevice, DeviceConfig
from apolo_emu.mapping import Mapping
from apolo_emu.ssip import SSIPBackend

from .test_ssip import until


@unittest.skipUnless(os.environ.get("APOLO_EMU_SPEECHD"), "set APOLO_EMU_SPEECHD=1 to enable")
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
            # @I? replies immediately; 1 waits for speech to reach the clause.
            self.assertEqual([b for _, b in replies], [b"I10T", b"1", b"2"])
            t1, t2 = replies[1][0], replies[2][0]
            self.assertGreater(t2 - t1, 0.5, "the final echo must follow actual speech")
            replies.clear()
            dev.feed(b"@I?")
            self.assertEqual(replies[0][1], b"I00M")
        finally:
            await backend.close()


if __name__ == "__main__":
    unittest.main()
