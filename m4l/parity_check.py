"""Vérifie que le cerveau JS (m4l/brain.js) donne les mêmes conseils que le Python (tracks.coach).

    python m4l/parity_check.py dossier_de_pistes/     # ex. ~/Music/Exports/002

1. On imite en Python ce que mesurera Max : banc de 28 filtres passe-bande (comme fffb~), moyennes L²/R²/LR,
   grave sous 120 Hz (cross~), crête, « punch » sur trames de 100 ms.
2. Ces mesures passent dans brain.js (node) ET dans tracks.coach : les conseils doivent être identiques.
"""
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
from scipy import signal

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import i18n  # noqa: E402
import mixcoach as mc  # noqa: E402
import tracks as tr  # noqa: E402
import build  # noqa: E402

CENTERS = mc.third_octave_bands()
Q = 4.32  # tiers d'octave


def entry(key, name, data, sr, kind="track"):
    """Ce que le capteur Max enverra : moyennes de puissance, pas d'audio."""
    data = data.astype(np.float64)
    mid = data.mean(axis=1)
    bands = []
    for c in CENTERS:  # fffb~ = filtres résonants 2 pôles ; iirpeak a la même forme, gain 1 au centre
        b, a = signal.iirpeak(c, Q, fs=sr)
        bands.append(float(np.mean(signal.lfilter(b, a, signal.lfilter(b, a, mid)) ** 2)))  # 2 filtres en série, comme le device
    L, R = data[:, 0], data[:, 1]
    sos = signal.butter(3, 120, "lowpass", fs=sr, output="sos")  # cross~ : 3e ordre
    lL, lR = signal.sosfilt(sos, L), signal.sosfilt(sos, R)
    st = [float(np.mean(x * y)) for x, y in ((L, L), (R, R), (L, R), (lL, lL), (lR, lR), (lL, lR))]
    hop = sr // 10
    fr = mc.pdb(np.mean(mid[: len(mid) // hop * hop].reshape(-1, hop) ** 2, axis=1))
    fr = fr[fr > fr.max() - 40]
    punch = float(np.percentile(fr, 90) - np.percentile(fr, 10))
    return {"key": key, "name": name, "kind": kind, "bands": bands, "st": st, "peak": float(np.max(np.abs(data))), "punch": punch}


def py_features(e):
    """Mêmes caractéristiques que brain.features, pour nourrir tracks.coach."""
    power = np.maximum(np.array(e["bands"]), 1e-20)
    cum = np.cumsum(power) / power.sum()
    LL, RR, LR, lLL, lRR, lLR = e["st"]

    def ss(a, b, c):
        mid, side = (a + b + 2 * c) / 4, max((a + b - 2 * c) / 4, 0)
        return (c / np.sqrt(a * b) if a > 0 and b > 0 else 1.0), float(mc.pdb(side) - mc.pdb(mid))

    corr, width = ss(LL, RR, LR)
    corr_low, low_width = ss(lLL, lRR, lLR)
    return {"name": e["key"], "centers": CENTERS, "power": power, "peak": e["peak"],
            "f50": float(CENTERS[np.searchsorted(cum, 0.5)]),
            "low_frac": float(power[CENTERS < 100].sum() / power.sum()),
            "low120_frac": float(power[CENTERS < 120].sum() / power.sum()),
            "stereo": {"corr": corr, "corr_low": corr_low, "width_db": width, "low_width_db": low_width},
            "pan_db": float(mc.pdb(RR) - mc.pdb(LL)), "punch_db": e["punch"]}


def entries_from_folder(folder, seconds=60):
    stems, mix, sr, groups = tr.load_folder(folder)  # réutilise le chargement (master, groupes, préfixe)
    files = {p.stem: p for p in Path(folder).iterdir()}
    out = []
    for t in stems:
        p = next(p for s, p in files.items() if s.endswith(t["name"]))
        data, _ = tr.read(p)
        mid = len(data) // 2
        out.append(entry(t["name"], t["name"], data[max(0, mid - seconds * sr // 2): mid + seconds * sr // 2], sr))
    mid = len(mix) // 2
    out.append(entry("Master", "Master", mix[max(0, mid - seconds * sr // 2): mid + seconds * sr // 2], sr, "master"))
    return out


def compare(entries, lang="fr"):
    """Mêmes conseils (titres + corrections) côté JS et Python, dans la langue demandée."""
    build.write_constants()
    i18n.set_lang(lang)
    js = subprocess.run(["node", "-e", "const b=require(process.argv[1]);b.setLang(process.argv[2]);const r=b.analyze(JSON.parse(require('fs').readFileSync(0)));"
                         "console.log(JSON.stringify(r))", str(HERE / "brain.js"), lang],
                        input=json.dumps(entries), capture_output=True, text=True, check=True)
    js = json.loads(js.stdout)
    tracks = [py_features(e) for e in entries if e["kind"] == "track" and sum(e["bands"]) > 1e-10]
    master = next(e for e in entries if e["kind"] == "master")
    advice, conflicts, share = tr.coach(tracks, mc.pdb(np.array(master["bands"])))
    diffs = []
    for t in js["tracks"]:
        a = [(f["title"], json.dumps(f["fix"], sort_keys=True)) for f in t["advice"]]
        b = [(f["title"], json.dumps(f.get("fix"), sort_keys=True)) for f in advice[t["key"]]]
        if a != b:
            diffs.append((t["key"], a, b))
    return js, diffs


if __name__ == "__main__":
    js, diffs = compare(entries_from_folder(sys.argv[1]))
    for t in js["tracks"]:
        print(f"■ {t['name']}: " + " | ".join(f["title"] for f in t["advice"]))
    print("\nMix:", " | ".join(f["title"] for f in js["mix"]["findings"]))
    print("\nIDENTIQUE au Python ✓" if not diffs else f"\n{len(diffs)} DIFFÉRENCE(S) :")
    for d in diffs:
        print(" ", d)
    sys.exit(1 if diffs else 0)
