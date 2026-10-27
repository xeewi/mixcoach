"""MixCoach piste par piste — dit, pour chaque piste, quoi faire par rapport au reste du mix.

Dans Ableton : Fichier → Exporter audio/vidéo → Piste rendue : « Toutes les pistes individuelles »
(WAV, Normaliser désactivé). Puis :

    python tracks.py dossier_des_pistes/
    python tracks.py dossier_des_pistes/ --reference morceau_pro.wav

Un fichier dont le nom contient « master » est utilisé comme mix ; sinon le mix = somme des pistes.
"""
import argparse
import html
import os
import re
import sys
import webbrowser
from itertools import combinations
from pathlib import Path

import numpy as np
import soundfile as sf

import i18n
import mixcoach as mc
from i18n import N_, t

AUDIO_EXT = {".wav", ".aif", ".aiff", ".flac", ".mp3"}
ROLES = [(120, N_("grave (kick / basse)")), (500, N_("bas-médium (corps)")), (2500, N_("médium (lead, voix, synthés)")), (1e9, N_("aigu (hats, cymbales, brillance)"))]


# ---------------------------------------------------------------- 1. mesures d'une piste
# ponytail: ce dict est le contrat avec le futur capteur Max for Live — il enverra les mêmes champs.

def features(name, data, sr):
    centers, bands = mc.spectrum(data, sr)
    power = 10 ** (bands / 10)
    cum = np.cumsum(power) / power.sum()
    st = mc.stereo(data, sr)
    pan_db = 0.0
    if data.shape[1] > 1:
        pl, pr = np.mean(data[:, 0] ** 2), np.mean(data[:, 1] ** 2)
        pan_db = float(mc.pdb(pr) - mc.pdb(pl)) if pl > 0 and pr > 0 else 0.0
    return {
        "name": name,
        "centers": centers, "power": power,
        "rms_db": float(mc.pdb(np.mean(data ** 2))),
        "peak": float(np.max(np.abs(data))),
        "punch_db": punch_db(data, sr),
        "f50": float(centers[np.searchsorted(cum, 0.5)]),         # fréquence "centrale" de la piste
        "low_frac": float(power[centers < 100].sum() / power.sum()),  # part d'énergie sous 100 Hz
        "low120_frac": float(power[centers < 120].sum() / power.sum()),
        "stereo": st, "pan_db": pan_db,
    }


def punch_db(data, sr):
    """Écart entre les moments forts et faibles de l'enveloppe (trames de 10 ms) pendant que la piste joue :
    élevé = son percussif (kick), faible = son tenu (basse, nappe)."""
    x = data.mean(axis=1, dtype=np.float64)
    frame = int(sr / 100)
    n = len(x) // frame * frame
    fr = mc.db(np.sqrt(np.mean(x[:n].reshape(-1, frame) ** 2, axis=1)))
    fr = fr[fr > fr.max() - 40]
    return float(np.percentile(fr, 90) - np.percentile(fr, 10))


LOW_NAME = re.compile(r"kick|bass|sub|808", re.I)  # pistes qu'on ne coupe jamais dans le grave


def who_keeps_low(a, b):
    """Dans le grave : le kick (d'après son nom) passe devant ; sinon l'élément grave ; sinon le plus percussif.
    Le nom d'abord : un kick très « clicky » peut avoir son centre au-dessus de 120 Hz, il reste un kick."""
    ka, kb = "kick" in a["name"].lower(), "kick" in b["name"].lower()
    if ka != kb:
        return (a, b) if ka else (b, a)
    ga, gb = a["f50"] < 120, b["f50"] < 120
    if ga != gb:
        return (a, b) if ga else (b, a)
    return (a, b) if a["punch_db"] > b["punch_db"] else (b, a)


def lowcut_step(hp):
    return t("Bande 1 : choisis le filtre « Low Cut » doux (12 dB/oct, pas la version 48) — la courbe qui descend à gauche — et règle-le vers {f} Hz.", f=hp)


def pct(x):
    return "<1%" if x < 0.01 else f"{x:.0%}"


def role(f50):
    return t(next(r for lim, r in ROLES if f50 < lim))


def pan_label(p):
    if abs(p) < 1.5:
        return t("centre")
    return (t("droite ({v} dB)") if p > 0 else t("gauche ({v} dB)")).replace("{v}", f"{abs(p):.0f}")


# ---------------------------------------------------------------- 2. le cerveau : comparer les pistes

def coach(tracks, mix_bands, ref_bands=None):
    """tracks : liste de features. Retourne (conseils par piste, conflits, parts d'énergie)."""
    centers = tracks[0]["centers"]
    P = np.array([tk["power"] for tk in tracks])         # pistes × bandes
    total = P.sum(axis=0) + 1e-20
    share = P / total                                   # qui occupe quelle bande
    own = 10 * np.log10(P / (P.max(axis=1, keepdims=True) + 1e-20) + 1e-20)  # dB sous le max de la piste
    energy_share = P.sum(axis=1) / P.sum()
    advice = {tk["name"]: [] for tk in tracks}
    F = mc.finding

    # a) Coupables des déséquilibres du mix
    has_ref = ref_bands is not None
    tol = mc.TOL_REF_DB if has_ref else mc.TOL_GENERIC_DB
    dev = mc.tonal_deviation(centers, mix_bands, ref_bands)
    for zone, lo, hi, what, too_much, too_little, *_ in mc.REGIONS:
        m = (centers >= lo) & (centers < hi)
        d = float(np.mean(dev[m]))
        if abs(d) <= tol:
            continue
        region_share = P[:, m].sum(axis=1) / P[:, m].sum()
        intro = t("Cette zone, c'est {what}.", what=t(what))
        for i in sorted(range(len(tracks)), key=lambda i: (-region_share[i], i))[:2]:  # ex æquo : la première piste
            if region_share[i] < 0.25:
                break
            tk = tracks[i]
            fc = int(np.sqrt(lo * hi))
            pc = f"{region_share[i]:.0%}"
            if d > 0:
                w = mc.why("region_more")
                advice[tk["name"]].append(F("attention", t("Principale source de l'excès {zone}", zone=t(zone)),
                    t("Le mix a +{d} dB de trop entre {lo} et {hi} Hz, et cette piste en fournit {pc}.", d=f"{d:.1f}", lo=lo, hi=hi, pc=pc),
                    (intro + " " + t(too_much) + " " + w[0], w[1]),
                    [t("Ajoute un EQ Eight sur la piste (Navigateur → Audio Effects → EQ Eight)."),
                     t("Choisis une bande, mets-la en cloche (Bell), fréquence ~{f} Hz.", f=fc),
                     t("Baisse son gain de -2 à -4 dB, largeur (Q) ≈ 1."),
                     t("Réécoute dans le mix (pas en solo) : ça doit sonner plus clair, sans que la piste disparaisse."),
                     t("Variante plus simple : baisse le fader de la piste de 1 à 2 dB.")],
                    fix={"kind": "eq", "shape": "bell", "freq": fc, "gain": -3, "q": 1,
                         "label": t("Ajouter EQ Eight : cloche -3 dB à {f} Hz", f=fc)}))
            else:
                if -d < 8:
                    steps = [t("Monte le fader de la piste de 1 à 2 dB et réécoute."),
                             t("Si ça ne suffit pas : EQ Eight, cloche à ~{f} Hz, +2 dB, Q ≈ 1.", f=fc)]
                    auto = {"kind": "volume", "delta": 1.5, "label": t("Monter le fader de 1,5 dB")}
                else:
                    steps = [t("Il manque {d} dB : un EQ ne suffira pas, ce son n'a presque rien dans cette zone.", d=f"{-d:.0f}")]
                    if hi <= 60:
                        steps += [t("Prends un kick plus profond (avec plus de sub) ;"),
                                  t("ou ajoute une couche de sub : piste MIDI avec Operator, onde sinus, qui joue les mêmes notes que la basse, entre 30 et 60 Hz.")]
                    elif hi <= 250:
                        steps += [t("Ajoute un Saturator sur la basse (Drive 3 à 6 dB) : il crée des harmoniques qui remplissent cette zone ;"),
                                  t("ou choisis un son de basse plus plein (onde en dent de scie ou carrée, filtrée).")]
                    else:
                        steps += [t("Choisis un son plus riche dans cette zone, ou superpose un deuxième son qui la remplit.")]
                    auto = None
                advice[tk["name"]].append(F("info", t("Peut combler le manque {zone}", zone=t(zone)),
                    t("Le mix manque de {d} dB entre {lo} et {hi} Hz ; cette piste est celle qui en apporte le plus ({pc}).", d=f"{-d:.1f}", lo=lo, hi=hi, pc=pc),
                    (intro + " " + t(too_little), mc.why("region_less")[1]), steps, fix=auto))

    # b) Conflits (masquage) : deux pistes fortes dans la même bande
    conflicts = []
    usable = (centers >= 30) & (centers <= 8000)
    for i, j in combinations(range(len(tracks)), 2):
        both = usable & (own[i] > -6) & (own[j] > -6) & (share[i] > 0.2) & (share[j] > 0.2)
        if not both.any():
            continue
        score = np.where(both, np.minimum(share[i], share[j]) * total / total[usable].max(), 0)
        b = int(np.argmax(score))
        if score[b] < 0.02:  # bande négligeable dans le mix
            continue
        conflicts.append((float(score[b]), i, j, float(centers[b])))
    conflicts.sort(reverse=True)
    conflict_list = []
    for _s, i, j, f in conflicts[:6]:
        a, b = tracks[i], tracks[j]
        if f < 150:  # dans le grave, le kick passe devant la basse
            keep, cut = who_keeps_low(a, b)
        else:  # ailleurs, on creuse la piste pour qui cette fréquence est la moins "centrale"
            keep, cut = (a, b) if abs(np.log2(a["f50"] / f)) < abs(np.log2(b["f50"] / f)) else (b, a)
        fr = f"{f:.0f} Hz" if f < 1000 else f"{f / 1000:.1f} kHz"
        k, c = keep["name"], cut["name"]
        if f < 150 and cut["f50"] >= 120 and not LOW_NAME.search(c):  # pas un élément grave : rien à faire là
            hp = int(np.clip(round(f * 1.5, -1), 60, 150))
            act = [t("Sur « {cut} » : ajoute un EQ Eight.", cut=c), lowcut_step(hp),
                   t("Ce grave ne sert pas le morceau et vient brouiller « {keep} ». Écoute « {keep} » : il doit devenir plus net.", keep=k)]
            auto = {"kind": "eq", "shape": "lowcut12", "freq": hp, "label": t("Ajouter EQ Eight : coupe-bas doux à {f} Hz", f=hp)}
        elif f < 150:
            act = [t("Sur « {cut} » : ajoute un Compressor.", cut=c),
                   t("Déplie le panneau Sidechain (petit triangle en haut à gauche du device), active-le."),
                   t("Audio From : choisis « {keep} ».", keep=k),
                   t("Ratio 4:1, Attack 1 ms, Release 50-100 ms, puis baisse Threshold jusqu'à 3-6 dB de réduction à chaque coup."),
                   t("Résultat : « {cut} » s'efface une fraction de seconde à chaque coup de « {keep} ».", cut=c, keep=k),
                   t("Alternative (automatisable) : EQ Eight sur « {cut} », cloche -3 dB à {f}, Q ≈ 2.", cut=c, f=fr)]
            auto = {"kind": "eq", "shape": "bell", "freq": round(f), "gain": -3, "q": 2, "label": t("Ajouter EQ Eight : cloche -3 dB à {f}", f=fr)}
        else:
            act = [t("Sur « {cut} » : ajoute un EQ Eight.", cut=c),
                   t("Une bande en cloche (Bell) à {f}, gain -3 dB, Q ≈ 2 (assez étroit).", f=fr),
                   t("Réécoute avec « {keep} » : les deux doivent devenir plus distincts.", keep=k),
                   t("Autre option : si aucun des deux n'est un élément central, panoramique l'un un peu à gauche, l'autre un peu à droite.")]
            auto = {"kind": "eq", "shape": "bell", "freq": round(f), "gain": -3, "q": 2, "label": t("Ajouter EQ Eight : cloche -3 dB à {f}", f=fr)}
        fnd = F("attention", t("Conflit avec « {keep} » vers {f}", keep=k, f=fr),
                t("« {a} » et « {b} » sont tous les deux forts autour de {f}.", a=a["name"], b=b["name"], f=fr), mc.why("conflict"), act, fix=auto)
        advice[c].append(fnd)
        conflict_list.append({"a": a["name"], "b": b["name"], "freq": f, "cut": c, "keep": k, "finding": fnd})

    # c) Règles propres à chaque piste
    for n, tk in enumerate(tracks):
        adv = advice[tk["name"]]
        if tk["peak"] >= 0.999:  # info : dans Live (calcul en virgule flottante) une piste au-dessus de 0 dB ne sature pas
            adv.append(F("info", t("Piste très forte (au-dessus de 0 dB)"), t("Crête à {v} dBFS.", v=f"{mc.db(tk['peak']):.1f}"), mc.why("track_hot"),
                [t("Baisse le fader de la piste, ou la sortie de l'effet qui pousse le plus (saturateur, EQ avec gros boost) ;"),
                 t("ou ajoute un Utility en fin de chaîne et baisse son Gain jusqu'à ce que le vumètre de la piste ne passe plus au rouge.")],
                fix={"kind": "utility_gain", "db": -3, "label": t("Ajouter Utility : gain -3 dB")}))
        if tk["f50"] > 400 and tk["low_frac"] > 0.02 and not LOW_NAME.search(tk["name"]):
            hp = int(np.clip(round(tk["f50"] / 8, -1), 40, 150))
            adv.append(F("attention", t("Grave inutile : mets un coupe-bas"),
                t("Le contenu principal de la piste est vers {f} Hz, mais {pc} de son énergie est sous 100 Hz.", f=f"{tk['f50']:.0f}", pc=f"{tk['low_frac']:.1%}"),
                mc.why("lowcut"),
                [t("Ajoute un EQ Eight sur la piste."), lowcut_step(hp),
                 t("Astuce d'oreille : monte la fréquence jusqu'à entendre la piste s'amincir, puis redescends un peu.")],
                fix={"kind": "eq", "shape": "lowcut12", "freq": hp, "label": t("Ajouter EQ Eight : coupe-bas doux à {f} Hz", f=hp)}))
        st = tk["stereo"]
        if st and tk["low120_frac"] > 0.1 and (st["low_width_db"] > -12 or st["corr_low"] < 0.7):
            adv.append(F("attention", t("Grave en stéréo"),
                t("Largeur sous 120 Hz : {w} dB (corrélation {c}).", w=f"{st['low_width_db']:.0f}", c=f"{st['corr_low']:.2f}"), mc.why("track_bass_stereo"),
                [t("Ajoute un Utility sur la piste."), t("Active « Bass Mono » et règle sa fréquence sur 120 Hz."),
                 t("Tout ce qui est sous 120 Hz devient mono ; le reste garde sa largeur.")],
                fix={"kind": "bassmono", "freq": 120, "label": t("Ajouter Utility : Bass Mono à 120 Hz")}))
        if st and st["corr"] < -0.1:  # ~0 = simplement décorrélé (stéréo large), pas un problème
            adv.append(F("problème", t("Phase inversée / trop large"), t("Corrélation L/R = {v}.", v=f"{st['corr']:.2f}"), mc.why("track_phase"),
                [t("Ajoute un Utility, mets Width à 0 % : si la piste s'affaiblit beaucoup, elle a bien un problème de phase."),
                 t("Désactive un par un les effets stéréo de la piste (Chorus-Ensemble, élargisseurs, Utility Width > 100 %) pour trouver le coupable."),
                 t("Réduis son réglage de largeur, ou remplace-le. (Pas de correction automatique : il faut trouver la cause.)")]))
        if tk["f50"] < 120 and abs(tk["pan_db"]) > 3:
            adv.append(F("attention", t("Grave décentré"), t("Panoramique : {p}.", p=pan_label(tk["pan_db"])), mc.why("track_bass_pan"),
                [t("Dans le mixeur, remets le panoramique de la piste au centre (double-clic sur le bouton Pan, ou tape « C »).")],
                fix={"kind": "pan_center", "label": t("Recentrer le panoramique")}))
        if not adv:
            adv.append(F("ok", t("Rien à signaler"), t("Piste {role}, {pc} de l'énergie du mix.", role=role(tk["f50"]), pc=pct(energy_share[n])),
                mc.why("nothing"), []))
    order = {"problème": 0, "attention": 1, "info": 2, "ok": 3}
    for v in advice.values():
        v.sort(key=lambda x: order[x["level"]])
    return advice, conflict_list, energy_share


# ---------------------------------------------------------------- chargement / rapport

def read(p):
    data, sr = sf.read(str(p), always_2d=True, dtype="float32")  # float32 : 15 pistes de 5 min tiennent en mémoire
    return (np.repeat(data, 2, axis=1) if data.shape[1] == 1 else data[:, :2]), sr


def find_master(files):
    """« ... Master.wav », ou le fichier dont le nom préfixe tous les autres (Ableton : « 002.wav » + « 002 Kick.wav »)."""
    for p in files:
        if "master" in p.stem.lower() or (len(files) > 2 and all(q == p or q.stem.startswith(p.stem + " ") for q in files)):
            return p
    return None


def snippet(data, sr):
    """Extrait mono léger (60 s au milieu, 1 échantillon sur 16) pour comparer les pistes entre elles."""
    mid, half = len(data) // 2, 30 * sr
    return data[max(0, mid - half):mid + half].mean(axis=1)[::16].astype(np.float64)


def detect_groups(snips):
    """Une piste groupe = somme (pondérée, positive) de plusieurs autres pistes. On l'écarte pour ne pas compter le son deux fois."""
    names = list(snips)
    n = min(len(v) for v in snips.values())
    X = np.array([snips[k][:n] for k in names])
    groups = []
    for g in range(len(names)):
        others = np.delete(X, g, axis=0)
        coef, *_ = np.linalg.lstsq(others.T, X[g], rcond=None)
        r2 = 1 - np.sum((X[g] - coef @ others) ** 2) / (np.sum(X[g] ** 2) + 1e-20)
        # ponytail: r2 > 0.9 tolère un compresseur de bus ; un groupe très traité (saturation forte) peut passer à travers.
        if r2 > 0.9 and coef.min() > -0.1 and (coef > 0.3).sum() >= 2:
            groups.append(names[g])
    return groups


def load_folder(folder):
    files = sorted(p for p in Path(folder).iterdir() if p.suffix.lower() in AUDIO_EXT)
    master = find_master(files)
    files = [p for p in files if p != master]
    prefix = (master.stem + " ") if master else os.path.commonprefix([q.stem for q in files])
    prefix = prefix[:prefix.rfind(" ") + 1] if len(files) > 1 else ""  # « Proj Kick » → « Kick »
    feats, snips, sr, mix = [], {}, None, None
    for p in files:
        data, s = read(p)
        if sr and s != sr:
            raise SystemExit(t("{file} : fréquence d'échantillonnage différente ({a} vs {b}).", file=p.name, a=s, b=sr))
        sr = s
        if mc.pdb(np.mean(data.astype(np.float64) ** 2)) < -70:  # piste vide / silencieuse
            continue
        name = p.stem[len(prefix):] if prefix and p.stem.startswith(prefix) else p.stem
        feats.append((p, features(name, data, sr)))
        snips[name] = snippet(data, sr)
        if not master:
            mix = data.copy() if mix is None else _add(mix, data)
    if not feats:
        raise SystemExit(t("Aucune piste audio trouvée dans ce dossier."))
    groups = detect_groups(snips) if len(snips) > 2 else []
    if master:
        mix = read(master)[0]
    else:
        for p, f in feats:
            if f["name"] in groups:
                mix = _add(mix, -read(p)[0])
    return [f for _, f in feats if f["name"] not in groups], mix, sr, groups


def _add(a, b):
    if len(b) > len(a):
        a, b = b.copy(), a
    a[:len(b)] += b
    return a


def render(folder, tracks, advice, conflicts, energy_share, mix_L, mix_findings):
    e = html.escape
    rows = "".join(
        f"<tr><td>{e(tk['name'])}</td><td>{e(role(tk['f50']))}</td><td>{pct(energy_share[k])}</td><td>{e(pan_label(tk['pan_db']))}</td>"
        f"<td>{sum(f['level'] in ('problème', 'attention') for f in advice[tk['name']])}</td></tr>"
        for k, tk in enumerate(tracks))
    conf = "".join("<li>" + e(t("« {a} » ↔ « {b} » vers {f} → creuser « {cut} »", a=c["a"], b=c["b"], f=f"{c['freq']:.0f} Hz", cut=c["cut"])) + "</li>"
                   for c in conflicts) or "<li>" + e(t("Aucun conflit marqué.")) + "</li>"
    per_track = "".join(
        f"<section class='track'><h3 class='tname'>{e(tk['name'])} <small>· {e(role(tk['f50']))}</small></h3>"
        + "".join(mc.card_html(f) for f in advice[tk["name"]]) + "</section>"
        for tk in tracks)
    head = [t("Piste"), t("Rôle"), t("Énergie"), t("Panoramique"), t("À corriger")]
    return f"""{mc.html_open(t("MixCoach pistes — {name}", name=Path(folder).name))}<style>{mc.CSS}
table{{width:100%;border-collapse:collapse;background:var(--card);border:1px solid var(--line);border-radius:10px;overflow:hidden;font-size:.92em}}
td,th{{padding:8px 10px;border-bottom:1px solid var(--line);text-align:start}} th{{color:var(--mut);font-weight:500}}
.track{{margin-top:22px}} .tname{{margin:0;font-size:1.15em}} .tname small{{color:var(--mut);font-weight:400}}
.wrap{{overflow-x:auto}}</style></head><body><main>
<h1>{e(t("MixCoach · piste par piste"))}</h1><p class="sub">{e(Path(folder).name)} · {e(t("{n} pistes", n=len(tracks)))}</p>
<section class="stats"><div><b>{mix_L['lufs']:.1f}</b><span>{e(t("LUFS du mix"))}</span></div>
<div><b>{mix_L['peak_db']:.1f}</b><span>{e(t("dBFS crête du mix"))}</span></div><div><b>{len(conflicts)}</b><span>{e(t("conflits entre pistes"))}</span></div></section>
<h2>{e(t("Vue d'ensemble"))}</h2><p>{e(t("« Énergie » = part de la puissance totale du mix apportée par la piste (le grave pèse naturellement lourd)."))}</p>
<div class="wrap"><table><tr>{"".join(f"<th>{e(h)}</th>" for h in head)}</tr>{rows}</table></div>
<h2>{e(t("Conflits entre pistes"))}</h2><ul>{conf}</ul>
<h2>{e(t("Piste par piste"))}</h2>{per_track}
<h2>{e(t("Le mix global"))}</h2>{"".join(mc.card_html(f) for f in mix_findings)}
</main></body></html>"""


def analyze_folder(folder, reference=None):
    return analyze(*load_folder(folder), reference=reference)


def analyze(tracks, mix, sr, groups=(), reference=None):
    centers, mix_bands = mc.spectrum(mix, sr)
    ref_bands = mc.spectrum(*mc.load(reference))[1] if reference else None
    advice, conflicts, energy_share = coach(tracks, mix_bands, ref_bands)
    mix_L = mc.loudness(mix, sr)
    dev = mc.tonal_deviation(centers, mix_bands, ref_bands)
    # le spectre du mix est déjà détaillé par piste : on garde ici les points globaux (niveau, stéréo…)
    mix_findings = [f for f in mc.diagnose(mix_L, centers, dev, mc.stereo(mix, sr), "mix", "streaming", reference is not None)
                    if not f["title"].endswith(" Hz)")]
    if groups:
        mix_findings.append(mc.finding("info", t("Pistes groupe ignorées"), ", ".join(groups),
            t("Ableton exporte aussi les groupes, qui contiennent le son de leurs pistes : les analyser compterait ce son deux fois."), []))
    return tracks, advice, conflicts, energy_share, mix_L, mix_findings


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("folder")
    ap.add_argument("--reference")
    ap.add_argument("--lang", choices=list(i18n.LANGS), help="langue du rapport (par défaut : celle du système)")
    ap.add_argument("--no-open", action="store_true")
    a = ap.parse_args()
    i18n.set_lang(a.lang or i18n.system_lang())
    tracks, advice, conflicts, share, mix_L, mix_findings = analyze_folder(a.folder, a.reference)
    for k, tk in enumerate(tracks):
        print(f"\n■ {tk['name']} — {role(tk['f50'])}, {pct(share[k])}, {pan_label(tk['pan_db'])}")
        for f in advice[tk["name"]]:
            print(f"   [{t(f['level'])}] {f['title']} — {f['fact']}")
    out = Path(a.folder) / "mixcoach-pistes.html"
    out.write_text(render(a.folder, tracks, advice, conflicts, share, mix_L, mix_findings), encoding="utf-8")
    print(f"\n{t('Rapport :')} {out}")
    if not a.no_open:
        webbrowser.open(out.resolve().as_uri())


if __name__ == "__main__":
    sys.exit(main())
