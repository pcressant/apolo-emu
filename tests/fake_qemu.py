"""Faux QEMU pour les tests du lanceur.

Se connecte à la socket de « -chardev socket,…,path=… », envoie FAKE_QEMU_SEND (hex),
écrit les octets reçus dans FAKE_QEMU_OUT, puis :
- FAKE_QEMU_MODE=exit : se termine avec le code FAKE_QEMU_RC après FAKE_QEMU_WAIT secondes ;
- FAKE_QEMU_MODE=wait : attend un signal ; SIGTERM ou SIGINT -> écrit « signal N » et sort (code 0).
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
