English | [Français](transport-serie-fr.md)

# Serial transport and flow control

Three distinct layers are involved:

| Layer | Implementation | Responsibility |
|---|---|---|
| Guest-visible 16550 UART | QEMU (`hw/char/serial.c`) | registers, FIFO, interrupts and modem lines (MCR, MSR) |
| Link between QEMU and emulator | QEMU `socket` chardev and Unix socket | a byte stream in each direction, **nothing else** |
| Device | Apolo-emu | the Apollo II protocol |

## What a socket does not carry

- **Guest to emulator:** RTS and DTR, set by the guest in MCR, never leave QEMU:
  the socket chardev has no modem-line interface.
- **Emulator to guest:** the emulator cannot change CTS, DSR, DCD or RI. QEMU queries the chardev
  (`CHR_IOCTL_SERIAL_GET_TIOCM`); a socket cannot answer, so the UART retains its reset MSR value,
  with **DCD, DSR and CTS permanently asserted**.
  - **Measured:** the test boot sector reads **MSR = 0xB0** on COM1 under QEMU 10.2.4 with
    `-chardev socket` (`tests/test_qemu_integration.py`).
- **No pacing:** QEMU does not apply the guest's baud rate to outgoing bytes. It reads the socket
  only while space remains in the receive FIFO.

## Consequences for emulation

Apollo II uses alternating RTS/CTS handshaking (TB25 §5.1; 1998 manual, appendix 6):

- The device deasserts CTS while processing each byte.
- The PC deasserts RTS to read.
- The device replies with NAK if it has nothing to send.

**None of this is emulated, and a socket cannot provide it:**

- The guest sees CTS asserted and sends without waiting. This satisfies OS/2's COM driver,
  which requires CTS and DSR.
- Apolo-emu accepts every byte and cannot throttle the guest.
  - A real Apollo II would lose data if input outpaced speech consumption: it has no “buffer full” signal.
  - Apolo-emu logs this condition (about 6 KB pending, the ROM 2.01 input ring size), but drops nothing.
- Replies (echoes, indexes, queries) are written as soon as they are produced. They enter the guest's
  receive FIFO regardless of RTS.
- Empty-read NAK requires knowledge of RTS and is not emulated.
- Speakup pulses RTS when its tty is full. That pulse has no effect here and is unnecessary.

## The `os2` project's QEMU patch

`../os2/tools/qemu-serial-loopback-msr.patch` fixes an **emulated UART** defect independent of the device:

- QEMU did not set MSR delta bits (DCTS, DDSR, DDCD, TERI) when entering or leaving loopback mode (MCR.LOOP).
- It also failed to raise the corresponding modem-status interrupt.
- OS/2's COM.SYS detects CTS and DSR this way; without the patch, Screen Reader/2 reports
  “The synthesizer did not respond”.

This behavior belongs **entirely to QEMU**. Apolo-emu cannot cause or fix it and does not modify QEMU.
With an unpatched QEMU, the problem is the same regardless of the program connected to the socket.

## Connection modes

| Mode | Apolo-emu | QEMU |
|---|---|---|
| Listening (launcher default) | `--listen PATH` | `-chardev socket,id=X,path=PATH[,reconnect-ms=1000]` (client) |
| Connecting | `--connect PATH` | `-chardev socket,id=X,path=PATH,server=on,wait=off` (server) |

- One connection at a time, like a cable. In listening mode, a second connection is rejected.
- The device preserves state across connections: unplugging a cable does not power off an Apollo.
- Replies produced while disconnected are lost and logged.
- **Stale socket (listening mode):** if no process listens on the socket path, it is removed.
  Paths used by another process or paths that are not sockets are rejected.
- Socket permissions restrict access to the current user.
- **Reconnection:** in connecting mode, Apolo-emu retries every second; in listening mode,
  QEMU reconnects when configured with `reconnect-ms`.
