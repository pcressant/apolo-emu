import asyncio
import os
import signal
import subprocess
import sys
import tempfile
import time
import unittest

from apolo_emu.app import Options
from apolo_emu.launcher import (
    DIR_PREFIX, LaunchError, build_qemu_args, clean_stale_dirs, run_launcher, serial_usage,
)

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
FAKE_QEMU = [sys.executable, os.path.join(HERE, "fake_qemu.py")]


class ArgsTests(unittest.TestCase):
    def test_adds_chardev_and_device(self):
        argv = build_qemu_args(["qemu-system-i386", "-m", "64"], "/run/x/com.sock", 1, "apolo")
        self.assertEqual(argv[-4:], ["-chardev", "socket,id=apolo,path=/run/x/com.sock",
                                     "-device", "isa-serial,chardev=apolo,index=0"])
        self.assertEqual(argv[:3], ["qemu-system-i386", "-m", "64"])

    def test_conflicts(self):
        with self.assertRaises(LaunchError):
            build_qemu_args(["q", "-serial", "stdio"], "/s", 1, "a")
        self.assertIn("index=1", build_qemu_args(["q", "-serial", "stdio"], "/s", 2, "a")[-1])
        with self.assertRaises(LaunchError):
            build_qemu_args(["q", "-device", "isa-serial,chardev=c,index=1"], "/s", 2, "a")
        with self.assertRaises(LaunchError):
            build_qemu_args(["q", "-chardev", "null,id=a"], "/s", 1, "a")
        with self.assertRaises(LaunchError):
            build_qemu_args(["q"], "/s", 5, "a")

    def test_serial_none_consumes_an_index(self):
        # Vérifié sur QEMU 10.2 : « -serial none -serial null » place null sur COM2.
        self.assertEqual(serial_usage(["-serial", "none", "-serial", "null"]).occupied, {1})
        build_qemu_args(["q", "-serial", "none", "-serial", "null"], "/s", 1, "a")

    def test_option_forms(self):
        self.assertEqual(serial_usage(["--serial", "stdio", "-serial=null"]).occupied, {0, 1})
        u = serial_usage(["-device", "driver=isa-serial,index=3", "-device", "isa-serial", "-nographic"])
        self.assertEqual((u.occupied, u.auto), ({3}, 1))
        self.assertFalse(serial_usage(["-nographic", "-hda", "-serial"]).occupied)  # « -serial » comme valeur

    def test_nographic_warning(self):
        self.assertTrue(serial_usage(["-nographic"]).warnings)
        self.assertFalse(serial_usage(["-nographic", "-serial", "mon:stdio"]).warnings)


class StaleDirTests(unittest.TestCase):
    def test_only_dead_and_ours(self):
        with tempfile.TemporaryDirectory() as base:
            dead = subprocess.Popen([sys.executable, "-c", "pass"])
            dead.wait()

            def make(name, pid, extra=None):
                d = os.path.join(base, DIR_PREFIX + name)
                os.mkdir(d)
                with open(os.path.join(d, "pid"), "w") as f:
                    f.write(str(pid))
                open(os.path.join(d, "com.sock"), "w").close()
                if extra:
                    open(os.path.join(d, extra), "w").close()
                return d

            stale = make("stale", dead.pid)
            alive = make("alive", os.getpid())
            foreign = make("foreign", dead.pid, extra="disk.img")
            other = os.path.join(base, "unrelated")
            os.mkdir(other)
            removed = clean_stale_dirs(base)
            self.assertEqual(removed, [stale])
            for d in (alive, foreign, other):
                self.assertTrue(os.path.isdir(d))


def fake_env(tmp: str, **kw) -> str:
    out = os.path.join(tmp, "out.bin")
    os.environ["FAKE_QEMU_OUT"] = out
    for k, v in kw.items():
        os.environ[f"FAKE_QEMU_{k}"] = str(v)
    return out


class RunTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = os.path.join(self.tmp.name, "run")
        os.mkdir(self.base)
        self.saved_env = dict(os.environ)

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self.saved_env)
        self.tmp.cleanup()

    async def test_roundtrip_exit_code_and_cleanup(self):
        out = fake_env(self.tmp.name, SEND=b"@I?".hex(), RC=3, WAIT=0.5)
        rc = await run_launcher(FAKE_QEMU, Options(backend="null"), base_dir=self.base)
        self.assertEqual(rc, 3)
        with open(out, "rb") as f:
            self.assertEqual(f.read(), b"I00M")
        self.assertEqual(os.listdir(self.base), [])  # socket et répertoire supprimés

    async def test_missing_qemu(self):
        rc = await run_launcher(["/nonexistent/qemu-system-i386"], Options(backend="null"), base_dir=self.base)
        self.assertEqual(rc, 127)
        self.assertEqual(os.listdir(self.base), [])

    async def test_conflict_does_not_start_qemu(self):
        out = fake_env(self.tmp.name)
        rc = await run_launcher(FAKE_QEMU + ["-serial", "stdio"], Options(backend="null"), base_dir=self.base)
        self.assertEqual(rc, 2)
        self.assertFalse(os.path.exists(out + ".args"))
        self.assertEqual(os.listdir(self.base), [])

    async def test_parallel_instances(self):
        outs = []
        tasks = []
        for i in range(3):
            d = os.path.join(self.tmp.name, f"i{i}")
            os.mkdir(d)
            outs.append(os.path.join(d, "out.bin"))
        # Chaque faux QEMU écrit dans son propre fichier : l'environnement est figé au lancement.
        for out in outs:
            os.environ.update(FAKE_QEMU_OUT=out, FAKE_QEMU_SEND=b"@Ex\r".hex(), FAKE_QEMU_WAIT="0.6",
                              FAKE_QEMU_RC="0")
            tasks.append(asyncio.create_task(run_launcher(FAKE_QEMU, Options(backend="null"), base_dir=self.base)))
            await asyncio.sleep(0.15)
        self.assertEqual(len(os.listdir(self.base)), 3)  # trois instances simultanées
        self.assertEqual(await asyncio.gather(*tasks), [0, 0, 0])
        for out in outs:
            with open(out, "rb") as f:
                self.assertEqual(f.read(), b"x")
        sockets = set()
        for out in outs:
            with open(out + ".args") as f:
                sockets.add([a for a in f.read().split("\n") if a.startswith("socket,")][0])
        self.assertEqual(len(sockets), 3)
        self.assertEqual(os.listdir(self.base), [])


class SignalTests(unittest.TestCase):
    def run_cli(self, tmp, base, extra=()):
        env = dict(os.environ, FAKE_QEMU_OUT=os.path.join(tmp, "out.bin"), FAKE_QEMU_MODE="wait",
                   PYTHONPATH=ROOT)
        return subprocess.Popen(
            [sys.executable, "-m", "apolo_emu", "run", "--backend", "null", "--socket-dir", base, *extra,
             "--", *FAKE_QEMU],
            env=env, stderr=subprocess.PIPE, start_new_session=True,
        )

    def wait_started(self, tmp):
        for _ in range(100):
            if os.path.exists(os.path.join(tmp, "out.bin.args")):
                time.sleep(0.2)
                return
            time.sleep(0.05)
        self.fail("faux QEMU non démarré")

    def test_sigterm_forwarded_and_cleanup(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = os.path.join(tmp, "run")
            os.mkdir(base)
            p = self.run_cli(tmp, base)
            self.wait_started(tmp)
            p.send_signal(signal.SIGTERM)
            _, err = p.communicate(timeout=10)
            self.assertEqual(p.returncode, 0, err.decode())
            with open(os.path.join(tmp, "out.bin.signal")) as f:
                self.assertEqual(f.read(), str(int(signal.SIGTERM)))
            self.assertEqual(os.listdir(base), [])

    def test_wait_policy_does_not_signal_qemu(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = os.path.join(tmp, "run")
            os.mkdir(base)
            p = self.run_cli(tmp, base, ("--on-signal", "wait"))
            self.wait_started(tmp)
            p.send_signal(signal.SIGTERM)  # au lanceur seul
            time.sleep(0.5)
            self.assertIsNone(p.poll())
            self.assertFalse(os.path.exists(os.path.join(tmp, "out.bin.signal")))
            os.killpg(p.pid, signal.SIGINT)  # comme un Ctrl-C au terminal : QEMU le reçoit lui-même
            _, err = p.communicate(timeout=10)
            self.assertEqual(p.returncode, 0, err.decode())
            self.assertEqual(os.listdir(base), [])


if __name__ == "__main__":
    unittest.main()
