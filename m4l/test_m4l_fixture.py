"""Faux projet aux défauts connus (kick + basse en conflit, nappe avec grondement), partagé par les tests."""
import tempfile
from pathlib import Path

import numpy as np
import soundfile as sf

import parity_check as pc


def entries():
    SR, t = 44100, np.arange(44100 * 6) / 44100
    kick = 0.6 * np.sin(2 * np.pi * 55 * t) * (np.mod(t, 0.5) < 0.15)
    bass = np.stack([0.3 * np.sin(2 * np.pi * 55 * t), 0.3 * np.sin(2 * np.pi * 55 * t + 1.6)], 1)
    pad = sum(0.05 * np.sin(2 * np.pi * f * t) for f in (600, 800, 1000, 1200)) + 0.02 * np.sin(2 * np.pi * 40 * t)
    d = Path(tempfile.mkdtemp())
    sf.write(d / "P Kick.wav", np.stack([kick, kick], 1), SR)
    sf.write(d / "P Bass.wav", bass, SR)
    sf.write(d / "P Pad.wav", np.stack([pad, pad], 1), SR)
    return pc.entries_from_folder(d, seconds=6)
