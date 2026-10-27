"""Test boot sector assembled here (16-bit real mode, no dependencies).

The program:
1. configures the UART (COM1 by default) for 9600 baud 8N1, asserting DTR/RTS/OUT2;
2. writes the guest-visible modem-status register (MSR) to QEMU debugcon port 0xE9;
3. sends MESSAGE to Apollo byte by byte, waiting for THRE;
4. copies each received Apollo byte to port 0xE9 indefinitely.
"""

from __future__ import annotations

import struct

COM1 = 0x3F8
DEBUGCON = 0xE9


class Asm:
    def __init__(self, origin: int) -> None:
        self.origin = origin
        self.code = bytearray()
        self.labels: dict[str, int] = {}
        self.fixups: list[tuple[int, str]] = []

    def label(self, name: str) -> None:
        self.labels[name] = len(self.code)

    def emit(self, *b: int) -> None:
        self.code += bytes(b)

    def mov_dx(self, v: int) -> None:
        self.emit(0xBA, *struct.pack("<H", v))

    def mov_al(self, v: int) -> None:
        self.emit(0xB0, v)

    def out(self, port: int, value: int) -> None:
        self.mov_dx(port)
        self.mov_al(value)
        self.emit(0xEE)  # out dx, al

    def jcc(self, opcode: int, target: str) -> None:
        self.emit(opcode, 0)
        self.fixups.append((len(self.code) - 1, target))

    def address(self, name: str) -> int:
        return self.origin + self.labels[name]

    def assemble(self) -> bytes:
        for pos, target in self.fixups:
            rel = self.labels[target] - (pos + 1)
            assert -128 <= rel < 128, target
            self.code[pos] = rel & 0xFF
        return bytes(self.code)


def boot_sector(message: bytes, port: int = COM1) -> bytes:
    a = Asm(0x7C00)
    a.emit(0xFA, 0x31, 0xC0, 0x8E, 0xD8, 0xFC)  # cli ; xor ax,ax ; mov ds,ax ; cld
    a.out(port + 3, 0x80)  # LCR : DLAB
    a.out(port + 0, 12)  # divisor 12 = 9600 baud
    a.out(port + 1, 0)
    a.out(port + 3, 0x03)  # 8N1
    a.out(port + 4, 0x0B)  # MCR : DTR, RTS, OUT2
    a.mov_dx(port + 6)
    a.emit(0xEC)  # in al, dx (MSR)
    a.mov_dx(DEBUGCON)
    a.emit(0xEE)
    a.emit(0xBE, 0, 0)  # mov si, message (patched below)
    si_fix = len(a.code) - 2
    a.label("send")
    a.emit(0xAC)  # lodsb
    a.emit(0x08, 0xC0)  # or al, al
    a.jcc(0x74, "recv")  # jz recv
    a.emit(0x88, 0xC4)  # mov ah, al
    a.label("thre")
    a.mov_dx(port + 5)
    a.emit(0xEC, 0xA8, 0x20)  # in al, dx ; test al, 0x20
    a.jcc(0x74, "thre")
    a.emit(0x88, 0xE0)  # mov al, ah
    a.mov_dx(port)
    a.emit(0xEE)
    a.jcc(0xEB, "send")
    a.label("recv")
    a.mov_dx(port + 5)
    a.emit(0xEC, 0xA8, 0x01)  # in al, dx ; test al, 1 (data ready)
    a.jcc(0x74, "recv")
    a.mov_dx(port)
    a.emit(0xEC)
    a.mov_dx(DEBUGCON)
    a.emit(0xEE)
    a.jcc(0xEB, "recv")
    a.label("message")
    a.code += message + b"\0"
    code = a.assemble()
    code = code[:si_fix] + struct.pack("<H", a.address("message")) + code[si_fix + 2 :]
    if len(code) > 510:
        raise ValueError("message too long for a boot sector")
    return code.ljust(510, b"\0") + b"\x55\xaa"


def disk_image(message: bytes, port: int = COM1) -> bytes:
    return boot_sector(message, port).ljust(64 * 1024, b"\0")
