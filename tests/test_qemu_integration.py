"""Integration with real QEMU and an independent test VM (tests/guest.py boot sector).

Skipped if qemu-system-i386 is missing or APOLO_EMU_SKIP_QEMU is set.
"""

import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unittest

from .guest import disk_image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
QEMU = shutil.which("qemu-system-i386")


@unittest.skipIf(QEMU is None or os.environ.get("APOLO_EMU_SKIP_QEMU"), "QEMU unavailable or disabled")
class QemuTests(unittest.TestCase):
    def run_vm(self, message: bytes, expected_len: int, extra=(), qemu_extra=(), timeout=30, port=0x3F8):
        with tempfile.TemporaryDirectory() as tmp:
            img = os.path.join(tmp, "boot.img")
            with open(img, "wb") as f:
                f.write(disk_image(message, port))
            out = os.path.join(tmp, "debugcon.bin")
            base = os.path.join(tmp, "run")
            os.mkdir(base)
            cmd = [
                sys.executable, "-m", "apolo_emu", "run", "--backend", "simulated", "--cps", "50",
                "--socket-dir", base, *extra, "--",
                QEMU, "-machine", "pc", "-accel", "tcg", "-m", "16", "-display", "none", "-nodefaults",
                "-drive", f"file={img},format=raw,if=ide", "-debugcon", f"file:{out}", "-no-reboot", *qemu_extra,
            ]
            p = subprocess.Popen(cmd, env=dict(os.environ, PYTHONPATH=ROOT), stderr=subprocess.PIPE,
                                 start_new_session=True)
            data = b""
            deadline = time.monotonic() + timeout
            try:
                while time.monotonic() < deadline:
                    if os.path.exists(out):
                        with open(out, "rb") as f:
                            data = f.read()
                    if len(data) >= expected_len or p.poll() is not None:
                        break
                    time.sleep(0.1)
            finally:
                if p.poll() is None:
                    p.send_signal(signal.SIGTERM)  # forwarded to QEMU by the launcher
                _, err = p.communicate(timeout=15)
            leftovers = os.listdir(base)
            return data, p.returncode, err.decode(errors="replace"), leftovers

    def test_echo_and_index_through_qemu_uart(self):
        data, rc, err, leftovers = self.run_vm(b"hello world @I+\r@E1\r@I?", 1 + 4 + 1)
        self.assertGreaterEqual(len(data), 6, err)
        msr = data[0]
        print(f"Guest-visible MSR: {msr:#04x}", file=sys.stderr)
        # Socket: QEMU UART exposes CTS, DSR, DCD permanently asserted (docs/serial-transport.md).
        self.assertEqual(msr & 0xB0, 0xB0, f"MSR = {msr:#04x}")
        # @I? is handled on reception: speech active, one unspoken mark.
        self.assertEqual(data[1:5], b"I10T")
        # @E1 follows the end of 'hello world'.
        self.assertEqual(data[5:6], b"1")
        self.assertEqual(rc, 0, err)
        self.assertEqual(leftovers, [])

    def test_com2_beside_existing_com1(self):
        data, rc, err, leftovers = self.run_vm(b"@W?", 4, extra=("--com", "2"),
                                              qemu_extra=("-serial", "null"), port=0x2F8)
        self.assertEqual(data[1:4], b"W30", err)
        self.assertEqual(leftovers, [])


if __name__ == "__main__":
    unittest.main()
