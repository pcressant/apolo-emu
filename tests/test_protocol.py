import unittest

from apolo_emu import protocol as P


class HexTests(unittest.TestCase):
    def test_hex_value_like_rom(self):
        self.assertEqual([P.hex_value(ord(c)) for c in "09AaFfZz"], [0, 9, 10, 10, 15, 15, 35, 35])
        # « : » à « @ » valent 35 ; les autres caractères donnent des valeurs hors plage.
        self.assertEqual(P.hex_value(ord(":")), 35)
        self.assertEqual(P.hex_value(ord("@")), 35)
        self.assertGreaterEqual(P.hex_value(ord("+")), 16)
        self.assertGreaterEqual(P.hex_value(ord(" ")), 16)

    def test_hex_reply_low_nibble_first(self):
        self.assertEqual(P.hex_reply(6), b"60")  # manuel : @A? -> A60
        self.assertEqual(P.hex_reply(0x1E), b"E1")
        self.assertEqual(P.hex_reply(0x100), b"00")


class ImmediateTests(unittest.TestCase):
    def test_states(self):
        self.assertEqual(P.immediate_state(b"I"), "partial")
        self.assertEqual(P.immediate_state(b"i"), "partial")
        self.assertEqual(P.immediate_state(b"I+"), "index_add")
        self.assertEqual(P.immediate_state(b"i?"), "index_query")
        self.assertIsNone(P.immediate_state(b"IA"))
        self.assertIsNone(P.immediate_state(b"e"))


class ScanTests(unittest.TestCase):
    table = P.DEFERRED_PATTERNS

    def scan(self, raw: bytes):
        return P.scan_clause(raw, P.DEFAULT_CMD_CHAR, self.table)

    def test_commands_removed_from_text(self):
        c = self.scan(b"@W4@A3@F9. ")
        self.assertEqual([(x.name, x.raw) for x in c.commands], [("speed", b"W4"), ("volume", b"A3"), ("pitch", b"F9")])
        self.assertEqual(c.text, b". ")

    def test_first_match_wins(self):
        self.assertEqual(self.scan(b"@A? ").commands[0].name, "query")
        self.assertEqual(self.scan(b"@? ").commands[0].name, "version")
        self.assertEqual(self.scan(b"@E? ").commands[0].name, "query")

    def test_unknown_command_stays_text(self):
        c = self.scan(b"@wb hello ")
        self.assertEqual(c.commands, [])
        self.assertEqual(c.text, b"@wb hello ")

    def test_positions(self):
        c = self.scan(b"one @I+ two@e\t three ")
        self.assertEqual([(x.name, x.position) for x in c.commands], [("index_mark", 4), ("echo", 8)])
        self.assertEqual(c.text, b"one  two three ")

    def test_multi_char_patterns(self):
        c = self.scan(b"@M1F @u212+ @RA3F x ")
        self.assertEqual([(x.name, x.raw) for x in c.commands],
                         [("mark_space", b"M1F"), ("formant", b"u212+"), ("prosody_param", b"RA3F")])

    def test_pattern_past_end_not_matched(self):
        self.assertEqual(self.scan(b"@M1").commands, [])


class AccumulatorTests(unittest.TestCase):
    def feed(self, data: bytes):
        acc = P.ClauseAccumulator()
        out = []
        for b in data:
            r = acc.push(b, P.DEFAULT_CMD_CHAR)
            if r:
                out.append(r)
        return out, acc

    def test_cr_and_punctuation_end_clauses(self):
        out, acc = self.feed(b"hello, world\rtext.no end")
        self.assertEqual(out, [(b"hello, ", False), (b" world ", True), (b"text. ", False)])
        self.assertEqual(acc.pending, 6)

    def test_lf_is_not_a_terminator(self):
        out, acc = self.feed(b"a\nb")
        self.assertEqual(out, [])

    def test_long_clause_breaks_at_space(self):
        out, _ = self.feed(b"x" * 218 + b"y z")
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0][0], b"x" * 218 + b"y  ")

    def test_long_clause_carries_cmd_char(self):
        out, acc = self.feed(b"x" * 219 + b"@W5 ")
        self.assertEqual(out[0][0], b"x" * 219 + b" ")
        r = None
        for b in b"\r":
            r = acc.push(b, P.DEFAULT_CMD_CHAR)
        self.assertEqual(r, (b"@W5  ", True))

    def test_hard_limit(self):
        out, _ = self.feed(b"x" * 300)
        self.assertEqual(len(out[0][0]), 250)


if __name__ == "__main__":
    unittest.main()
