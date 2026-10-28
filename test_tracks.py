"""Self-check piste par piste : faux projet aux défauts connus. `python test_tracks.py`"""
import tempfile
from pathlib import Path

import numpy as np
import soundfile as sf

import tracks as tr

SR, DUR = 44100, 6
t = np.arange(SR * DUR) / SR
rng = np.random.default_rng(0)

# Kick : sinus 55 Hz par impulsions ; Basse : 55 Hz continu (même zone → conflit), en stéréo décalée (pas mono)
env = (np.mod(t, 0.5) < 0.15) * np.exp(-np.mod(t, 0.5) * 20)
kick = 0.6 * np.sin(2 * np.pi * 55 * t) * env
bass_l = 0.3 * np.sin(2 * np.pi * 55 * t)
bass_r = 0.3 * np.sin(2 * np.pi * 55 * t + 1.6)
# Pad : contenu vers 600-1200 Hz + grondement à 40 Hz (→ coupe-bas)
pad = sum(0.05 * np.sin(2 * np.pi * f * t) for f in (600, 800, 1000, 1200)) + 0.02 * np.sin(2 * np.pi * 40 * t)
# Hats : bruit filtré aigu, propre
from scipy import signal
hats = 0.05 * signal.sosfilt(signal.butter(4, 6000, "highpass", fs=SR, output="sos"), rng.standard_normal(len(t)))

d = Path(tempfile.mkdtemp())
sf.write(d / "1-Kick.wav", np.stack([kick, kick], 1), SR)
sf.write(d / "2-Bass.wav", np.stack([bass_l, bass_r], 1), SR)
sf.write(d / "3-Pad.wav", np.stack([pad, pad], 1), SR)
sf.write(d / "4-Hats.wav", np.stack([hats, hats], 1), SR)
sf.write(d / "5-Vide.wav", np.zeros((len(t), 2)), SR)  # piste silencieuse : ignorée
sf.write(d / "6-Drums.wav", np.stack([kick + hats, kick + hats], 1) * 0.8, SR)  # groupe = kick + hats : ignoré

tracks, advice, conflicts, share, mix_L, mix_findings = tr.analyze_folder(d)
names = [x["name"] for x in tracks]
titles = {k: " | ".join(f["title"] for f in v) for k, v in advice.items()}

assert "5-Vide" not in names and "6-Drums" not in names, names
assert any("6-Drums" in f["fact"] for f in mix_findings)
assert any(c["keep"] == "1-Kick" and c["cut"] == "2-Bass" for c in conflicts), conflicts  # la basse s'efface devant le kick
assert "coupe-bas" in titles["3-Pad"], titles["3-Pad"]
assert "Grave en stéréo" in titles["2-Bass"], titles["2-Bass"]
assert "coupe-bas" not in titles["1-Kick"] and "coupe-bas" not in titles["4-Hats"]
assert tr.role(tracks[names.index("4-Hats")]["f50"]).startswith("aigu")
assert abs(sum(share) - 1) < 1e-6

html_out = tr.render(d, tracks, advice, conflicts, share, mix_L, mix_findings)
assert "1-Kick" in html_out and "Conflits" in html_out
print("OK — tous les checks passent")
for k, v in titles.items():
    print(f"  {k}: {v}")

# Nommage Ableton : « 002.wav » (master) + « 002 Kick.wav »…
P = Path
assert tr.find_master([P("002 Bass.wav"), P("002 Kick.wav"), P("002.wav")]) == P("002.wav")
assert tr.find_master([P("a.wav"), P("b.wav"), P("c.wav")]) is None
assert tr.find_master([P("Kick.wav"), P("Master.wav")]) == P("Master.wav")

# Revue théorie : un kick « clicky » (centre au-dessus de 120 Hz) garde son grave face à la basse
ck = {"name": "Kick Clicky", "f50": 160.0, "punch_db": 20.0}
bs = {"name": "Sub Bass", "f50": 60.0, "punch_db": 3.0}
assert tr.who_keeps_low(ck, bs) == (ck, bs) and tr.LOW_NAME.search("808 Bass") and not tr.LOW_NAME.search("Pad")
loud = dict(tracks[names.index("3-Pad")], name="Loud", peak=1.2)
adv, *_ = tr.coach([loud], tracks[0]["power"])
assert [f["level"] for f in adv["Loud"] if "0 dB" in f["title"]] == ["info"]  # pas « problème » : Live ne sature pas en interne
print("OK — revue théorie")

# Vrai cas (Octobeats #15) : la basse garde le nom du plugin et ses harmoniques mettent son centre vers 200 Hz.
# Elle a beaucoup d'énergie sous 100 Hz : c'est une basse, on la sidechaine, on ne lui coupe pas le grave.
synth_bass = sum(a * np.sin(2 * np.pi * 55 * h * t) for h, a in ((1, 0.25), (2, 0.15), (3, 0.25), (4, 0.25), (5, 0.2)))
d2 = Path(tempfile.mkdtemp())
sf.write(d2 / "1-Kick.wav", np.stack([kick, kick], 1), SR)
sf.write(d2 / "2-Analog Lab V.wav", np.stack([synth_bass, synth_bass], 1), SR)
tracks2, advice2, conflicts2, *_ = tr.analyze_folder(d2)
lab = next(x for x in tracks2 if x["name"] == "2-Analog Lab V")
assert lab["f50"] >= 120 and tr.is_low(lab), (lab["f50"], lab["low_frac"])
acts = " ".join(" ".join(f["action"]) for f in advice2["2-Analog Lab V"])
assert any(c["cut"] == "2-Analog Lab V" for c in conflicts2), conflicts2  # le kick garde le grave
assert "Sidechain" in acts and "Low Cut" not in acts and "Grave inutile" not in " ".join(f["title"] for f in advice2["2-Analog Lab V"]), acts
print("OK — basse au nom de plugin")
