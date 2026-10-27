"""Fake QEMU for launcher tests.

Connect to the -chardev socket,…,path=… socket, send FAKE_QEMU_SEND (hex),
write received bytes to FAKE_QEMU_OUT, then:
- FAKE_QEMU_MODE=exit: return FAKE_QEMU_RC after FAKE_QEMU_WAIT seconds;
- FAKE_QEMU_MODE=wait: wait for a signal; SIGTERM/SIGINT writes "signal N"
  and exits with code 0.
"""

import os
import signal
import socket
import sys
import time

args = sys.argv[1:]
path = None
for i, a in enumerate(args):
    if a == "-chardev" and args[i + 1].startswith("socket,"):
        for item in args[i + 1].split(","):
            if item.startswith("path="):
                path = item[5:]
out = os.environ.get("FAKE_QEMU_OUT")
with open(out + ".args", "w") as f:
    f.write("\n".join(args))

received = bytearray()


def stop(sig, frame):
    with open(out, "ab") as f:
        f.write(received)
    with open(out + ".signal", "w") as f:
        f.write(str(sig))
    sys.exit(0)


signal.signal(signal.SIGTERM, stop)
signal.signal(signal.SIGINT, stop)

s = socket.socket(socket.AF_UNIX)
s.connect(path)
s.sendall(bytes.fromhex(os.environ.get("FAKE_QEMU_SEND", "")))
s.settimeout(0.05)
deadline = time.monotonic() + float(os.environ.get("FAKE_QEMU_WAIT", "0.5"))
mode = os.environ.get("FAKE_QEMU_MODE", "exit")
while mode == "wait" or time.monotonic() < deadline:
    try:
        data = s.recv(4096)
        if not data:
            break
        received += data
    except socket.timeout:
        pass
with open(out, "ab") as f:
    f.write(received)
sys.exit(int(os.environ.get("FAKE_QEMU_RC", "0")))
