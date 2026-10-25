"""Traduction des réglages Apollo II vers les réglages SSIP (Speech Dispatcher).

Aucune mesure de l'appareil réel n'est disponible : ces correspondances sont des
approximations choisies pour que les valeurs par défaut de l'Apollo donnent la
parole par défaut du moteur, et que les extrêmes donnent les extrêmes. Elles sont
documentées dans docs/backend-vocal.md et vérifiées par tests/test_mapping.py.
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
        """@W1-9, défaut 3 (environ 80 à 580 mots/min selon le manuel) vers RATE -100..100."""
        if speed <= 3:
            v = (speed - 3) * 35  # W1 = -70
        else:
            v = (speed - 3) * 100 / 6  # W9 = +100
        return clamp(v + self.rate_offset)

    def pitch(self, pitch: int, step: int = 8) -> int:
        """@F0-F, défaut 8, et @F+/@F- (léger décalage) vers PITCH -100..100."""
        v = (pitch - 8) * 12.5 + (step - 8) * 1.25  # F0 = -100, FF = +87 ; ±10 pour @F+/@F-
        return clamp(v + self.pitch_offset)

    def volume(self, volume: int) -> int:
        """@A0-F, proportion du volume du bouton, vers VOLUME -100..100 (A0 = -100, AF = +100)."""
        return clamp(volume * 200 / 15 - 100 + self.volume_offset)

    @staticmethod
    def voice_type(voice: int, speaker: int) -> str:
        """@V1-3 voix masculines, @V4-6 non masculines (manuel 1998)."""
        if 4 <= voice <= 6:
            return f"FEMALE{voice - 3}"
        if 1 <= voice <= 3:
            return f"MALE{voice}" if speaker == 0 else f"FEMALE{voice}"
        return "MALE1"

    def settings(self, p: VoiceParams) -> dict[str, str]:
        """Commandes « SET self … » correspondant à des réglages Apollo."""
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
