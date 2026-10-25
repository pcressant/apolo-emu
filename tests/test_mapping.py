import unittest

from apolo_emu.mapping import Mapping
from apolo_emu.speech import VoiceParams


class MappingTests(unittest.TestCase):
    m = Mapping()

    def test_defaults_are_neutral(self):
        s = self.m.settings(VoiceParams())
        self.assertEqual((s["RATE"], s["PITCH"]), ("0", "0"))
        self.assertEqual(s["PUNCTUATION"], "none")
        self.assertEqual(s["VOICE_TYPE"], "MALE1")

    def test_rate_monotonic_and_bounded(self):
        rates = [self.m.rate(w) for w in range(1, 10)]
        self.assertEqual(rates, sorted(rates))
        self.assertEqual((rates[0], rates[2], rates[-1]), (-70, 0, 100))

    def test_pitch(self):
        self.assertEqual(self.m.pitch(0), -100)
        self.assertEqual(self.m.pitch(8), 0)
        self.assertEqual(self.m.pitch(15), 88)
        self.assertEqual(self.m.pitch(8, 16), 10)
        self.assertEqual(self.m.pitch(8, 0), -10)

    def test_volume(self):
        self.assertEqual(self.m.volume(0), -100)
        self.assertEqual(self.m.volume(15), 100)
        self.assertEqual(self.m.volume(6), -20)

    def test_offsets_clamped(self):
        m = Mapping(rate_offset=50, volume_offset=-200)
        self.assertEqual(m.rate(9), 100)
        self.assertEqual(m.volume(15), -100)

    def test_voice_types(self):
        self.assertEqual([self.m.voice_type(v, 0) for v in range(1, 7)],
                         ["MALE1", "MALE2", "MALE3", "FEMALE1", "FEMALE2", "FEMALE3"])

    def test_optional_settings(self):
        s = Mapping(use_volume=False, use_voice_type=False).settings(VoiceParams(punct=1, spell=1, language="fr"))
        self.assertNotIn("VOLUME", s)
        self.assertNotIn("VOICE_TYPE", s)
        self.assertEqual((s["PUNCTUATION"], s["SPELLING"], s["LANGUAGE"]), ("all", "on", "fr"))


if __name__ == "__main__":
    unittest.main()
