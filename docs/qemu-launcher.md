English | [Français](lanceur-qemu-fr.md)

# QEMU launcher

```bash
apolo-emu run [Apolo-emu options] -- qemu-system-i386 [QEMU options]
```

## Lifecycle

1. **Instance directory.**
   - Created under `$XDG_RUNTIME_DIR` or `--socket-dir`: `apolo-emu-XXXXXXXX/`, mode 0700,
     containing a `pid` file and the `com.sock` socket.
   - Before creating it, the launcher removes **abandoned** `apolo-emu-*` directories owned by
     the current user whose process has gone and which contain only `pid` and `com.sock`.
   - It touches nothing else.
2. **The emulator starts listening.** If this fails, QEMU is not started (exit code 2).
3. **The QEMU command is extended.** User options are unchanged; the launcher appends:
   ```text
   -chardev socket,id=apolo-emu-<pid>,path=<directory>/com.sock
   -device isa-serial,chardev=apolo-emu-<pid>,index=<N-1>
   ```
   `--com N` (1–4, default 1) selects the port; `index` selects COMN's standard address and IRQ.
4. **QEMU starts** in the same process group. It keeps the terminal: console, monitor and Ctrl-C
   behave normally.
5. **When QEMU exits**, the launcher closes the emulator and SSIP connection, removes the socket
   and directory, and returns QEMU's exit code.

## Port conflicts

The launcher inspects the QEMU command and refuses to start (code 2) if the requested port is already defined.

**Verified with QEMU 10.2.4:** QEMU allows two UARTs at the same address. With `-serial null` and
`-device isa-serial,index=0`, both occupy 0x3F8. The launcher therefore checks this itself.

| Command option | Effect |
|---|---|
| `-serial X` | occupies the next port: first `-serial` is COM1, second is COM2, etc. |
| `-serial none` | consumes a number **without** creating a port (verified: `-serial none -serial null` places `null` on COM2) |
| `-device isa-serial,index=K` | occupies COM(K+1) |
| `-device isa-serial` without `index` | QEMU chooses; the launcher warns |
| `-chardev …,id=apolo-emu-<pid>` | rejected: identifier already in use |
| `-readconfig` | not parsed; the launcher warns |
| `-nographic` without `-serial` | warning: adding `-device isa-serial` prevents QEMU's default COM1 serial console; add `-serial mon:stdio` and use `--com 2` |

## Signals and shutdown

| Event | Behavior |
|---|---|
| Terminal Ctrl-C | QEMU receives it directly in the same process group and exits normally; the launcher waits and cleans up |
| SIGTERM, SIGHUP, SIGINT or SIGQUIT sent to the launcher | forwarded to QEMU with `--on-signal forward` (default) |
| Same, with `--on-signal wait` | not forwarded: the launcher logs a request to shut down the guest cleanly, then waits for QEMU to exit |
| Emulator error during execution | logged; **the VM keeps running** without speech and is never stopped by the launcher |

The launcher never sends SIGKILL and only acts on the QEMU process it started.

Systems of this era (DOS, Windows 3.11, OS/2 Warp 4) do not support ACPI shutdown.
`--on-signal wait` prevents an accidental signal from stopping a VM during a disk write.

## Exit codes

| Code | Meaning |
|---|---|
| QEMU's exit code | normal completion |
| 128 + n | QEMU killed by signal n |
| 2 | usage error, port conflict or emulator startup failure |
| 126 / 127 | QEMU not executable / not found |

## Multiple instances

Each launch has its own directory, socket and chardev identifier. Multiple VMs can run simultaneously,
each with its virtual Apollo II (verified by `tests/test_launcher.py`). They share Speech Dispatcher
and therefore the audio output.

## Integration with an existing QEMU command

### Without the launcher: Apolo-emu listening

```bash
apolo-emu --listen "$XDG_RUNTIME_DIR/apollo.sock" --language fr &
qemu-system-i386 … \
  -chardev socket,id=apollo,path="$XDG_RUNTIME_DIR/apollo.sock",reconnect-ms=1000 \
  -serial chardev:apollo
```

- With `reconnect-ms`, QEMU starts even if the emulator is not ready and reconnects after emulator restarts.
- `-serial chardev:apollo` takes the next number among `-serial` options: COM1 if first.
  To select a specific port, use `-device isa-serial,chardev=apollo,index=0`.
- Verified with QEMU 10.2.4: without `reconnect-ms`, a missing socket causes exit code 1;
  with it, QEMU starts and waits.

### QEMU already configured as a server

The `pc486` and `os2` projects use this configuration; their scripts start Apolo-emu
(`scripts/pc486 gateway start`, `scripts/gateway`):

```text
-chardev socket,id=com1,path=$RUN/com1.sock,server=on,wait=off -serial chardev:com1
```

Connect Apolo-emu:

```bash
apolo-emu --connect /path/to/run/com1.sock --language fr --codepage cp850 --extension burst-interrupt
```

- A QEMU server chardev accepts one client: one Apolo-emu or other client per VM.
- With `wait=off`, guest bytes sent while no client is connected are lost.
- Apolo-emu reconnects every second: it can start before the VM and survive VM restarts.

### Complete examples

```bash
# DOS + Sonolect, COM1, French speech
apolo-emu run --language fr --codepage cp850 --extension burst-interrupt -- \
  qemu-system-i386 -machine pc -m 16 -hda dos.img

# OS/2 + Screen Reader/2: monitor serial console on COM1, Apollo on COM2
apolo-emu run --com 2 --language en --extension lenient-speed -- \
  qemu-system-i386 -m 64 -hda os2.img -serial mon:stdio
```

For the second example, configure Screen Reader/2 for COM2. The `os2` project's QEMU patch is still
needed for COM.SYS to detect CTS and DSR (see [serial-transport.md](serial-transport.md)).
