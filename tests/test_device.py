import unittest

from apolo_emu.device import ApolloDevice, DeviceConfig
from apolo_emu.speech import Pause

from .fakes import FakeBackend


class DeviceTestCase(unittest.TestCase):
    config = DeviceConfig()

    def setUp(self):
        self.backend = FakeBackend()
        self.replies = bytearray()
        self.now = 0.0
        self.dev = ApolloDevice(self.backend, self.replies.extend, self.config, clock=lambda: self.now)

    def feed(self, data: bytes, chunk: int | None = None):
        if chunk is None:
            self.dev.feed(data)
        else:
            for i in range(0, len(data), chunk):
                self.dev.feed(data[i : i + chunk])

    def take_replies(self) -> bytes:
        out = bytes(self.replies)
        self.replies.clear()
        return out


class TextTests(DeviceTestCase):
    def test_text_needs_cr_or_punctuation(self):
        self.feed(b"hello world")
        self.assertEqual(self.backend.spoken, [])
        self.feed(b"\r")
        self.assertEqual(self.backend.texts, ["hello world "])

    def test_punctuation_ends_clause(self):
        self.feed(b"one, two")
        self.assertEqual(self.backend.texts, ["one, "])

    def test_fragmented_equals_whole(self):
        data = b"\x18@W4@A3@F9.  sonolect 7 poin onze b\rnext line\r"
        whole = FakeBackend()
        ApolloDevice(whole, None).feed(data)
        self.feed(data, chunk=1)
        self.assertEqual("".join(self.backend.texts), "".join(whole.texts))
        self.assertEqual([u.params for u in self.backend.spoken][-1], whole.spoken[-1].params)

    def test_clauses_of_one_read_are_one_message(self):
        self.feed(b"first sentence. second, third\r")
        self.assertEqual(self.backend.texts, ["first sentence.  second,  third "])

    def test_settings_apply_to_whole_clause(self):
        # TB25 §6.2: voice 5 applies to the entire clause in the example below.
        self.feed(b"An apple a day @V5 keeps the doctor away.")
        self.assertEqual(self.backend.spoken[0].params.voice, 5)

    def test_parameters_split_messages(self):
        self.feed(b"slow.@W7fast.")
        self.assertEqual([u.params.speed for u in self.backend.spoken], [3, 7])

    def test_rejected_speed_kept(self):
        self.feed(b"@W0@Wb x\r")
        self.assertEqual(self.backend.spoken[0].params.speed, 3)
        # @Wb is not a ROM command: stays in text, with @ silenced.
        self.assertIn("Wb", self.backend.texts[0])
        self.assertNotIn("@", self.backend.texts[0])

    def test_control_characters_become_spaces(self):
        self.feed(b"a\tb\x07c\r")
        self.assertEqual(self.backend.texts, ["a b c "])

    def test_codepage(self):
        self.feed(b"\x82t\x82\r")  # French 'été' in CP437/CP850 (encoding test data)
        self.assertEqual(self.backend.texts, ["été "])

    def test_punctuation_only_is_silent(self):
        self.feed(b"@W4@A3@F9.")
        self.assertEqual(self.backend.spoken, [])

    def test_voice_off_speaks_nothing_but_echoes(self):
        self.feed(b"@V0 hidden text@Ex\r")
        self.assertEqual(self.backend.spoken, [])
        self.assertEqual(self.take_replies(), b"x")


class MuteTests(DeviceTestCase):
    def test_ctrl_x_cancels(self):
        self.feed(b"long text\r")
        self.feed(b"\x18")
        self.assertEqual(self.backend.cancels, 1)
        self.assertEqual(self.backend.queue, [])

    def test_ctrl_a_mutes_too(self):
        self.feed(b"text\r")
        self.feed(b"\x01")
        self.assertEqual(self.backend.cancels, 1)

    def test_mute_in_same_read_sends_nothing(self):
        self.feed(b"text\r\x18")
        self.assertEqual(self.backend.spoken, [])

    def test_mute_discards_partial_clause(self):
        self.feed(b"lost words\x18kept\r")
        self.assertEqual(self.backend.texts, ["kept "])

    def test_mute_inside_command(self):
        # The prototype gateway swallowed Ctrl-X after @.
        self.feed(b"text\r")
        self.feed(b"@\x18")
        self.assertEqual(self.backend.cancels, 1)
        self.feed(b"W5 x\r")
        self.assertEqual(self.backend.texts[-1], "W5 x ")

    def test_srd2_silence_string(self):
        self.feed(b"text\r")
        self.feed(b"@\x01\x18")
        self.assertEqual(self.backend.cancels, 1)
        self.feed(b"after\r")
        self.assertEqual(self.backend.texts[-1], "after ")

    def test_mute_forgets_unspoken_settings(self):
        self.feed(b"first\r")
        self.feed(b"@W7 second\r")
        self.backend.begin()
        self.feed(b"\x18@W?")
        self.feed(b"\r")
        self.assertEqual(self.take_replies(), b"W30")

    def test_echo_lost_on_mute(self):
        self.feed(b"text\r@Ex\r")
        self.feed(b"\x18")
        self.backend.finish_all()
        self.assertEqual(self.take_replies(), b"")


class EchoTests(DeviceTestCase):
    def test_echo_alone_is_immediate(self):
        self.feed(b"@Ez\r")
        self.assertEqual(self.take_replies(), b"z")

    def test_documented_end_of_text_idiom(self):
        # APOLLO.TXT: text<CR>@Ex<CR> -> x returns after text finishes.
        self.feed(b"text to speak\r@Ex\r")
        self.assertEqual(self.take_replies(), b"")
        self.backend.begin()
        self.assertEqual(self.take_replies(), b"")
        self.backend.finish()
        self.assertEqual(self.take_replies(), b"x")

    def test_echo_at_clause_start(self):
        self.feed(b"first.\r")
        self.feed(b"second @E1 part.")
        utt = self.backend.spoken[1]
        self.assertEqual(self.take_replies(), b"")
        self.backend.finish()  # end of 'first'
        self.backend.begin()
        self.assertEqual(self.take_replies(), b"")
        self.backend.reach(0)  # clause-start mark
        self.assertEqual(self.take_replies(), b"1")
        self.assertEqual(self.backend.mark_positions(utt)[0][1], "")

    def test_srd2_word_echoes_are_per_clause(self):
        # Screen Reader/2: @e<TAB> before each word, then . and CR.
        self.feed(b"@e\t o @e\t a @e\thyphen @e\tworld. \r")
        self.assertEqual(self.backend.texts[0].split(), ["o", "a", "hyphen", "world."])
        self.assertEqual(len(self.backend.spoken), 1)
        self.backend.begin()
        self.backend.reach(0)
        self.assertEqual(self.take_replies(), b"\t\t\t\t")

    def test_echo_argument_raw(self):
        self.feed(b"@e.")
        self.assertEqual(self.take_replies(), b".")

    def test_echo_order_with_queries(self):
        self.feed(b"@E1@W?@E2.")
        self.assertEqual(self.take_replies(), b"1W302")

    def test_silent_clause_between_texts_is_a_junction_mark(self):
        self.feed(b"one\r@E1\rtwo\r")
        self.assertEqual(len(self.backend.spoken), 1)  # one fluent message
        utt = self.backend.spoken[0]
        self.assertEqual([t for _, t in self.backend.mark_positions(utt)], ["one "])
        self.backend.reach(0)
        self.assertEqual(self.take_replies(), b"1")

    def test_trailing_silent_clause_waits_for_end(self):
        self.feed(b"one, two\r@E2\r")
        self.assertEqual(self.backend.spoken[0].marks, [])
        self.backend.begin()
        self.assertEqual(self.take_replies(), b"")
        self.backend.finish()
        self.assertEqual(self.take_replies(), b"2")
        self.feed(b"@I?")
        self.assertEqual(self.take_replies(), b"I00M")

    def test_events_out_of_order_finish_previous(self):
        self.feed(b"one\r")
        self.feed(b"two @Eb\r")
        self.feed(b"@Ec\r")
        self.backend.queue.pop(0)  # 'one' finished without notification
        self.backend.finish()
        self.assertEqual(self.take_replies(), b"bc")


class IndexTests(DeviceTestCase):
    def test_query_idle(self):
        self.feed(b"@I?")
        self.assertEqual(self.take_replies(), b"I00M")

    def test_counting(self):
        self.feed(b"one @I+two @I+three @I+\r")
        self.feed(b"@I?")
        self.assertEqual(self.take_replies(), b"I30T")
        self.backend.begin()
        self.backend.reach(0)
        self.feed(b"@i?")
        self.assertEqual(self.take_replies(), b"I20T")
        self.backend.finish()
        self.feed(b"@I?")
        self.assertEqual(self.take_replies(), b"I00M")

    def test_query_is_immediate_and_leaves_no_text(self):
        self.feed(b"hello @I? world\r")
        self.assertEqual(self.take_replies(), b"I00M")
        self.assertEqual(self.backend.texts, ["hello  world "])

    def test_index_preserved_by_mute_then_reset(self):
        self.feed(b"a @I+b @I+c\r")
        self.feed(b"\x18@I?")
        self.assertEqual(self.take_replies(), b"I20M")
        self.feed(b"@I+d\r@I?")
        self.assertEqual(self.take_replies(), b"I10T")

    def test_marks_inside_one_message(self):
        self.feed(b"one @I+two @I+three\r")
        utt = self.backend.spoken[0]
        self.assertEqual([t for _, t in self.backend.mark_positions(utt)], ["one ", "one two "])

    def test_index_query_split_across_reads(self):
        self.feed(b"@")
        self.feed(b"I")
        self.assertEqual(self.take_replies(), b"")
        self.feed(b"?")
        self.assertEqual(self.take_replies(), b"I00M")

    def test_talking_rule_rom(self):
        dev = ApolloDevice(FakeBackend(), self.replies.extend, DeviceConfig(talking_rule="rom"))
        dev.feed(b"no punctuation yet@I?")
        self.assertEqual(self.take_replies(), b"I00T")
        self.dev.feed(b"no punctuation yet@I?")
        self.assertEqual(self.take_replies(), b"I00M")


class QueryTests(DeviceTestCase):
    def test_defaults(self):
        self.feed(b"@A?@W?@F?@D?@V?@M?@B?@K?@=?@$?")
        self.assertEqual(self.take_replies(), b"A60W30F80DB0V10M41B80K00=10$00")

    def test_unknown_letter_no_reply(self):
        self.feed(b"@E?@Y?")
        self.assertEqual(self.take_replies(), b"")

    def test_query_after_settings(self):
        self.feed(b"@W7@F+@P1@M2A@P?@M?@F?@W?")
        self.assertEqual(self.take_replies(), b"P10MA2F80W70")

    def test_star_pattern_swallows_next_cmd_char(self):
        # 'M**' accepts any character: '@Mz@' is recognized then rejected,
        # and the next @ is consumed (ROM behavior).
        self.feed(b"@Mz@M2A x.")
        self.assertEqual(self.backend.texts, ["M2A x. "])
        self.backend.finish_all()
        self.feed(b"@M?")
        self.assertEqual(self.take_replies(), b"M41")

    def test_pitch_plus_minus(self):
        self.feed(b"@F+ x.")
        self.assertEqual(self.backend.spoken[0].params.pitch_step, 0x10)
        self.feed(b"@F- y.@Fc z.")
        self.assertEqual([u.params.pitch_step for u in self.backend.spoken], [16, 0, 8])
        self.assertEqual(self.backend.spoken[-1].params.pitch, 12)

    def test_volume_query_follows_speech(self):
        self.feed(b"before @A2 after\r")
        self.feed(b"@A?\r")
        self.backend.begin()
        self.assertEqual(self.take_replies(), b"")
        self.backend.finish_all()
        self.assertEqual(self.take_replies(), b"A20")

    def test_languages(self):
        dev = ApolloDevice(FakeBackend(), self.replies.extend, DeviceConfig(languages={1: "en", 2: "fr"}))
        dev.feed(b"@L\r")
        out = self.take_replies()
        self.assertEqual(out[:5], b"L70E0")
        self.assertEqual(len(out), 5 + 7 * 14 + 1)
        self.assertEqual(out[5:19], b"00044002010404")
        self.assertEqual(out[19:24], b"00033")
        self.assertEqual(out[-1:], b"\r")

    def test_version_spoken_not_replied(self):
        self.feed(b"@?\r")
        self.assertEqual(self.take_replies(), b"")
        self.assertIn("Apollo", self.backend.texts[0])

    def test_soft_reset(self):
        self.feed(b"@W8@F2@V4@J@W?@F?@V?")
        self.assertEqual(self.take_replies(), b"W30F80V10")
        # @A is speech-synchronized: it takes effect after @J within the same clause.
        self.feed(b"@A2@J.@A?")
        self.assertEqual(self.take_replies(), b"A20")


class SyncTests(DeviceTestCase):
    def test_volume_change_splits_message(self):
        self.feed(b"loud @A3 quiet\r")
        self.assertEqual([(u.text, u.params.volume) for u in self.backend.spoken], [("loud ", 6), (" quiet ", 3)])

    def test_volume_at_start_no_empty_message(self):
        self.feed(b"@A3 quiet\r")
        self.assertEqual([u.params.volume for u in self.backend.spoken], [3])

    def test_sound_effect_is_a_pause(self):
        self.feed(b"error @T7 message\r")
        self.assertIn(Pause(500), self.backend.spoken[0].parts)

    def test_bank_selects_language(self):
        dev = ApolloDevice(self.backend, None, DeviceConfig(languages={1: "en", 2: "fr"}))
        dev.feed(b"@=2, bonjour\r@=5, still french\r")
        self.assertEqual([u.params.language for u in self.backend.spoken], ["fr"])
        self.assertEqual(self.backend.texts[0], " bonjour  still french ")


class BacklogTests(DeviceTestCase):
    def test_overflow_warning(self):
        with self.assertLogs("apolo_emu.device", "WARNING") as cm:
            self.feed(b"word " * 2000 + b"\r")
            self.assertIn("would have lost", cm.output[0])
        self.assertEqual(len(self.backend.spoken), 1)  # nothing is discarded


class ExtensionTests(DeviceTestCase):
    def test_epaulard_index_disabled_by_default(self):
        self.feed(b"\x18@IA.Paragraph one.\r")
        self.backend.finish_all()
        self.assertEqual(self.take_replies(), b"")
        self.assertIn("IA", self.backend.texts[0])

    def test_epaulard_index(self):
        backend = FakeBackend()
        dev = ApolloDevice(backend, self.replies.extend, DeviceConfig(extensions=frozenset({"epaulard-index"})))
        dev.feed(b"\x18@IA.Paragraph 001 : continuous reading test.\r")
        # : and . end clauses; one message, mark at the end.
        self.assertEqual(backend.texts, ["Paragraph 001 :  continuous reading test. "])
        backend.begin()
        self.assertEqual(self.take_replies(), b"")
        backend.finish()
        self.assertEqual(self.take_replies(), b"A")
        # Authentic commands retain their meanings.
        dev.feed(b"@I+x\r@I?")
        self.assertEqual(self.take_replies(), b"I10T")

    def test_epaulard_mark_not_returned_after_cancel(self):
        backend = FakeBackend()
        dev = ApolloDevice(backend, self.replies.extend, DeviceConfig(extensions=frozenset({"epaulard-index"})))
        dev.feed(b"@IB.texte\r\x18")
        self.assertEqual(self.take_replies(), b"")

    def test_word_echo(self):
        backend = FakeBackend()
        dev = ApolloDevice(backend, self.replies.extend, DeviceConfig(extensions=frozenset({"word-echo"})))
        dev.feed(b"@e1one @e2two.")
        utt = backend.spoken[0]
        self.assertEqual([t for _, t in backend.mark_positions(utt)], ["", "one "])
        backend.reach(0)
        self.assertEqual(self.take_replies(), b"1")
        backend.reach(1)
        self.assertEqual(self.take_replies(), b"2")

    def test_lenient_speed(self):
        backend = FakeBackend()
        dev = ApolloDevice(backend, None, DeviceConfig(extensions=frozenset({"lenient-speed"})))
        dev.feed(b"@wf x\r@w0 y\r")
        self.assertEqual([u.params.speed for u in backend.spoken], [9, 1])

    def test_burst_interrupt(self):
        backend = FakeBackend()
        dev = ApolloDevice(backend, None, DeviceConfig(extensions=frozenset({"burst-interrupt"})),
                           clock=lambda: self.now)
        dev.feed(b"d\r")
        self.now += 0.01
        dev.feed(b"i\r")  # same burst
        self.assertEqual(backend.cancels, 0)
        self.now += 0.5
        dev.feed(b"r\r")
        self.assertEqual(backend.cancels, 1)
        self.assertEqual(backend.texts[-1], "r ")

    def test_burst_interrupt_spares_awaited_echo(self):
        # Épaulard (read all): 'line\r@EA\r', then queue the next line ahead of time.
        backend = FakeBackend()
        replies = []
        dev = ApolloDevice(backend, replies.append,
                           DeviceConfig(extensions=frozenset({"burst-interrupt"})),
                           clock=lambda: self.now)
        dev.feed(b"ligne un\r@EA\r")
        backend.begin()
        self.now += 0.5
        dev.feed(b"ligne deux\r@EB\r")
        self.assertEqual(backend.cancels, 0)
        backend.finish()
        self.assertEqual(b"".join(replies), b"A")
        backend.begin()
        self.now += 0.5
        dev.feed(b"touche\r")  # echo B is still pending: do not interrupt
        self.assertEqual(backend.cancels, 0)
        backend.finish_all()
        self.assertEqual(b"".join(replies), b"AB")

    def test_unknown_extension_rejected(self):
        with self.assertRaises(ValueError):
            DeviceConfig(extensions=frozenset({"nope"}))


if __name__ == "__main__":
    unittest.main()
