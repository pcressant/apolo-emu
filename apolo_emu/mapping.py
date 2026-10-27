"""Map Apollo II settings to SSIP (Speech Dispatcher) settings.

No hardware measurements are available. These approximations map Apollo
defaults to engine defaults and extreme values to engine extremes.
Documented in docs/speech-backend.md and checked by tests/test_mapping.py.
"""

from __future__ import annotations

from dataclasses import dataclass

from .speech import VoiceParams


def clamp(v: float, lo: int = -100, hi: int = 100) -> int:
    return int(max(lo, min(hi, round(v))))


@dataclass(frozen=True)
class Mapping:
    rate_offset: int = 0
    pitch_offset: int = 0
    volume_offset: int = 0
    use_volume: bool = True
    use_voice_type: bool = True

    def rate(self, speed: int) -> int:
        """@W1-9, default 3 (about 80-580 words/min in the manual) to RATE -100..100."""
        if speed <= 3:
            v = (speed - 3) * 35  # W1 = -70
        else:
            v = (speed - 3) * 100 / 6  # W9 = +100
        return clamp(v + self.rate_offset)

    def pitch(self, pitch: int, step: int = 8) -> int:
        """@F0-F, default 8, and @F+/@F- (small offset) to PITCH -100..100."""
        v = (pitch - 8) * 12.5 + (step - 8) * 1.25  # F0 = -100, FF = +87; ±10 for @F+/@F-
        return clamp(v + self.pitch_offset)

    def volume(self, volume: int) -> int:
        """@A0-F, relative to the volume knob, to VOLUME -100..100 (A0 = -100, AF = +100)."""
        return clamp(volume * 200 / 15 - 100 + self.volume_offset)

    @staticmethod
    def voice_type(voice: int, speaker: int) -> str:
        """@V1-3 male voices, @V4-6 non-male (1998 manual)."""
        if 4 <= voice <= 6:
            return f"FEMALE{voice - 3}"
        if 1 <= voice <= 3:
            return f"MALE{voice}" if speaker == 0 else f"FEMALE{voice}"
        return "MALE1"

    def settings(self, p: VoiceParams) -> dict[str, str]:
        """SET self commands corresponding to Apollo settings."""
        out = {
            "RATE": str(self.rate(p.speed)),
            "PITCH": str(self.pitch(p.pitch, p.pitch_step)),
            "PUNCTUATION": "all" if p.punct else "none",
            "SPELLING": "on" if p.spell else "off",
            "LANGUAGE": p.language,
        }
        if self.use_volume:
            out["VOLUME"] = str(self.volume(p.volume))
        if self.use_voice_type:
            out["VOICE_TYPE"] = self.voice_type(p.voice, p.speaker)
        return out
