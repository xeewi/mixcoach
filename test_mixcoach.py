"""Self-check : signaux synthétiques aux propriétés connues. `python test_mixcoach.py`"""
import tempfile
from pathlib import Path

import numpy as np
import soundfile as sf

import mixcoach as mc

SR = 44100


def tone(midi, dur, amp=0.1):
    t = np.arange(int(SR * dur)) / SR
    f = 440 * 2 ** ((midi - 69) / 12)
    return sum(amp / h * np.sin(2 * np.pi * f * h * t) for h in range(1, 5))


def chord(notes, dur):
    return sum(tone(n, dur) for n in notes)


def write(x, name):
    p = Path(tempfile.mkdtemp()) / name
    sf.write(p, x, SR)
    return p


def titles(findings):
    return " | ".join(f["title"] for f in findings)


# Progression Am – Dm – E – Am (+ basse) → La mineur
prog = [[57, 60, 64, 45], [57, 62, 65, 50], [56, 59, 64, 52], [57, 60, 64, 45]] * 2
music = np.concatenate([chord(c, 1.5) for c in prog])
music = music / np.max(np.abs(music)) * 0.5
stereo = np.stack([music, music], axis=1)

L, st, key, *_ , findings = mc.analyze(write(stereo, "am.wav"))
assert (mc.NOTES[key["tonic"]], key["mode"]) == ("A", "mineur"), key
assert mc.camelot(9, "mineur") == "8A" and mc.camelot(0, "majeur") == "8B" and mc.camelot(7, "majeur") == "9B"
assert abs(L["peak_db"] - mc.db(0.5)) < 0.1
assert st["corr"] > 0.99
assert "clipping" not in titles(findings)

# Sinus 1 kHz pleine échelle → clipping, true peak ≥ 0, LUFS ≈ -3 (mono 1 kHz full scale ≈ -3.01 LUFS)
t = np.arange(SR * 5) / SR
sine = np.sin(2 * np.pi * 1000 * t)
L, st, key, *_, findings = mc.analyze(write(sine, "sine.wav"), stage="master")
assert abs(L["lufs"] - (-3.01)) < 0.3, L["lufs"]
assert "clipping" in titles(findings) and "True peak" in titles(findings), titles(findings)
assert st is None

# Basse en opposition de phase L/R → problème de phase + basses pas mono
bass = 0.3 * np.sin(2 * np.pi * 55 * t)
anti = np.stack([bass, -bass], axis=1)
*_, findings = mc.analyze(write(anti, "phase.wav"))
assert "phase" in titles(findings) and "Basses pas assez mono" in titles(findings), titles(findings)

# Le rapport HTML se génère
L, st, key, c, dev, findings = mc.analyze(write(stereo, "am2.wav"))
html_out = mc.render_html("x.wav", "mix", "streaming", L, st, key, c, dev, findings, False)
assert "La mineur" in html_out
assert "A mineur" in html_out and "Dm" in html_out

# Revue théorie : le conseil suit le sens du déséquilibre, et un master club fort n'est pas « écrasé »
c = mc.third_octave_bands()
L0 = {"clipped": 0, "peak_db": -1.0, "true_peak_db": -1.0, "lufs": -7.0, "plr": 6.0, "dc": 0.0}
dev = np.where(c >= 6000, -8.0, 0.0)  # manque d'aigus
f = {x["title"]: x for x in mc.diagnose(L0, c, dev, None, "master", "club", False)}
assert "Dynamique très écrasée" not in f and "Loudness dans la cible" in f, list(f)
assert "+1 à +2 dB" in " ".join(f["Manque d'aigus / air (6000-20000 Hz)"]["action"])
f = {x["title"]: x for x in mc.diagnose(L0, c, -dev, None, "master", "streaming", False)}
assert "-2 dB" in " ".join(f["Trop d'aigus / air (6000-20000 Hz)"]["action"]) and "Dynamique très écrasée" in f
assert all(x["why"] for x in f.values()) and "<b>Ce que ça t" in mc.why_html(f["Problème de phase"] if "Problème de phase" in f else mc.finding("x", "", "", mc.why("phase"), []))

print("OK — tous les checks passent")
