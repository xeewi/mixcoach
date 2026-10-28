"""MixCoach — analyse un mix exporté d'Ableton et explique quoi corriger, et pourquoi.

Usage:
    python mixcoach.py mon_mix.wav                       # pre-master (avant mastering)
    python mixcoach.py mon_master.wav --stage master     # master final, cible streaming
    python mixcoach.py mon_master.wav --stage master --target club
    python mixcoach.py mon_mix.wav --reference morceau_pro.wav
"""
import argparse
import html
import re
import sys
import webbrowser
from pathlib import Path

import numpy as np
import pyloudnorm
import soundfile as sf
from scipy import signal

import i18n
from i18n import N_, t

# ---------------------------------------------------------------- constantes

NOTES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

# Profils de Krumhansl-Kessler : "à quel point chaque note sonne stable" dans une tonalité.
KK_MAJOR = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
KK_MINOR = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])

SCALES = {  # intervalles (demi-tons) + qualité des accords construits sur chaque degré
    "majeur": ([0, 2, 4, 5, 7, 9, 11], ["", "m", "m", "", "", "m", "dim"], ["I", "ii", "iii", "IV", "V", "vi", "vii°"]),
    "mineur": ([0, 2, 3, 5, 7, 8, 10], ["m", "dim", "", "m", "m", "", ""], ["i", "ii°", "III", "iv", "v", "VI", "VII"]),
}

MODES = (N_("majeur"), N_("mineur"))  # clés de SCALES, affichées traduites
LEVELS = (N_("problème"), N_("attention"), N_("info"), N_("ok"))
NOTES_LOCAL = N_("Do Do# Ré Ré# Mi Fa Fa# Sol Sol# La La# Si")  # noms des notes dans la langue choisie (solfège, ou C D E… / H en allemand)
GAIN = N_("Ce que ça t'apporte :")  # chaque explication finit par le bénéfice concret (affiché en gras)

TARGETS = {  # loudness intégrée (LUFS), true peak max (dBTP), écart crête/volume minimal (PLR) pour un master
    "streaming": {"lufs": -14.0, "tol": 1.5, "tp": -1.0, "plr_min": 7.0,
                  "why": (N_("Spotify, YouTube et Deezer remettent tous les morceaux au même volume, autour de -14 LUFS "
                             "(Apple Music autour de -16). Si ton morceau est plus fort, ils le baissent tout seuls. "
                             "Masteriser très fort ne te rend donc pas plus fort que les autres : tu perds juste du punch. "
                             "(Beaucoup de morceaux électro sortent quand même vers -9 à -7 LUFS : c'est un choix de style, pas une faute.)"),
                          N_("un morceau qui garde ses coups et sa respiration en streaming."))},
    "club": {"lufs": -8.0, "tol": 2.0, "tp": -1.0, "plr_min": 5.0,  # à -8 LUFS et -1 dBTP, le PLR ne peut pas dépasser 7
             "why": (N_("En club, personne ne remet les morceaux au même volume : le DJ enchaîne ton morceau avec d'autres très forts. "
                        "Les morceaux électro pour le club sont donc masterisés fort (entre -9 et -6 LUFS)."),
                     N_("ton morceau ne paraît pas plus faible que les autres dans un set."))},
}

# Zones du spectre : ce qu'on y entend, ce que ça fait quand il y en a trop / pas assez, et comment corriger dans chaque cas.
# (« de <zone> » pour les titres, Hz bas, Hz haut, ce que c'est, symptôme si trop, si pas assez, étapes si trop, si pas assez)
REGIONS = [
    (N_("de sub"), 20, 60, N_("le sub : la vibration très grave qu'on sent dans le ventre plus qu'on ne l'entend (le « boum » du kick, le bas de la basse)"),
     N_("Quand il y en a trop, le morceau devient brouillon, les enceintes « pompent » et en club ça sature."),
     N_("Quand il en manque, le morceau n'a pas de poids : sur une grosse sono, rien ne fait bouger le corps."),
     [N_("Baisse un peu le fader de la basse ou du kick (1 à 2 dB) et réécoute."),
      N_("Sur chaque piste qui n'est ni le kick ni la basse : EQ Eight, bande 1 en « Low Cut » vers 80-100 Hz, pour qu'elle n'ajoute pas de sub.")],
     [N_("Monte le kick et la basse de 1 à 2 dB."),
      N_("Si ça ne suffit pas, c'est le son lui-même qui manque de sub : prends un kick plus profond, "
         "ou ajoute une couche de sub (Operator, onde sinus, qui joue les mêmes notes que la basse, entre 30 et 60 Hz).")]),
    (N_("de basses"), 60, 250, N_("les basses : le corps et la chaleur du kick et de la basse"),
     N_("Trop : le son devient lourd et flou, comme écouté à travers un mur."),
     N_("Pas assez : le son est maigre, il n'a pas d'assise."),
     [N_("Sidechain : Compressor sur la basse, entrée Sidechain = la piste du kick, Ratio 4:1, Attack rapide. La basse se pousse à chaque coup de kick."),
      N_("Sinon : EQ Eight sur la basse, une cloche vers 120 Hz, -2 à -3 dB.")],
     [N_("Monte le fader de la basse de 1 à 2 dB."),
      N_("Ou ajoute un Saturator léger sur la basse (Drive 3 à 6 dB) : il crée des harmoniques qui rendent la basse plus présente, même sur de petites enceintes.")]),
    (N_("de bas-médiums"), 250, 500, N_("les bas-médiums : la zone où presque tous les instruments ont de l'énergie, donc où tout s'empile"),
     N_("Trop : le son est étouffé, « en carton », rien n'est net. C'est le défaut n°1 des débutants."),
     N_("Pas assez : le son devient froid et creux, il manque de corps."),
     [N_("Sur les nappes, synthés, guitares, voix (pas sur le master) : EQ Eight, une cloche vers 300 Hz, -2 à -4 dB, Q ≈ 1."),
      N_("Commence par la piste la plus chargée dans cette zone (voir l'analyse piste par piste).")],
     [N_("Sur les nappes ou les synthés principaux : EQ Eight, une cloche vers 300 Hz, +1 à +2 dB, Q ≈ 1."),
      N_("Vérifie aussi que tes coupe-bas ne sont pas réglés trop haut : au-dessus de 200 Hz, ils enlèvent ce corps.")]),
    (N_("de médiums"), 500, 2000, N_("les médiums : le cœur des instruments et de la voix, la seule chose qu'un téléphone ou une petite enceinte arrive vraiment à jouer"),
     N_("Trop : le son devient nasal, comme dans un vieux téléphone."),
     N_("Pas assez : le son est creux, et sur un téléphone ton lead ou ta voix disparaît."),
     [N_("Trouve l'élément principal le plus fort (lead, voix) : EQ Eight, une cloche vers 1 kHz, -2 dB, Q ≈ 1.")],
     [N_("Sur le lead ou la voix : EQ Eight, une cloche vers 1 kHz, +2 dB, Q ≈ 1."), N_("Ou monte simplement son fader de 1 dB.")]),
    (N_("de haut-médiums"), 2000, 6000, N_("les haut-médiums : l'attaque et la présence des sons ; l'oreille humaine y est très sensible"),
     N_("Trop : le son agresse et fatigue l'oreille au bout de quelques minutes."),
     N_("Pas assez : le son est terne, comme joué derrière une couverture."),
     [N_("Trouve l'élément agressif (souvent le lead, les hats ou la snare)."),
      N_("EQ Eight : une cloche étroite (Q ≈ 3), monte-la à +6 dB et déplace-la jusqu'à trouver la fréquence qui pique."),
      N_("Puis passe ce gain à -2 à -4 dB.")],
     [N_("Sur les éléments qui doivent ressortir (lead, voix, snare) : EQ Eight, une cloche large vers 3 kHz, +1 à +2 dB.")]),
    (N_("d'aigus / air"), 6000, 20000, N_("les aigus : la brillance, les cymbales, le souffle, « l'air »"),
     N_("Trop : ça siffle, les cymbales piquent les oreilles."),
     N_("Pas assez : le mix est sourd, comme étouffé."),
     [N_("Sur les hats et cymbales : EQ Eight, bande « High Shelf » vers 8 kHz, -2 dB."),
      N_("Si c'est une voix qui siffle sur les « s » : ajoute un de-esser.")],
     [N_("Sur le master ou le bus : EQ Eight, bande « High Shelf » à 10 kHz, +1 à +2 dB maximum."), N_("Ou monte un peu les hats.")]),
]

# Les explications « Pourquoi ? » : (ce qui se passe, ce que ça t'apporte). Partagées avec le device (build.py → constants.json).
# Règle : des mots de tous les jours, une image si possible, et toujours le bénéfice concret.
WHY = {
    "clipping": (N_("Le son numérique a un plafond : 0 dB. Tout ce qui essaie de passer au-dessus est coupé net, comme une vague qu'on raboterait. "
                    "Ça fait un grésillement dur, impossible à enlever après coup."),
                 N_("un son propre, sans craquements, sur toutes les enceintes.")),
    "headroom": (N_("Un mix qu'on va masteriser doit garder de la place sous le plafond, comme un verre qu'on ne remplit pas à ras bord : "
                    "on vise des pics entre -6 et -3 dB. C'est le mastering qui monte le volume final. Si le mix est déjà au maximum, "
                    "on est obligé d'écraser le son pour le faire rentrer."),
                 N_("un mastering qui peut rendre ton morceau fort sans l'abîmer.")),
    "headroom_ok": (N_("Tes pics restent sous -3 dB : il reste assez de place pour le mastering."), ""),
    "lufs": (N_("Le LUFS mesure le volume tel que ton oreille le ressent, pas seulement les pics."), ""),
    "true_peak": (N_("Même si chaque point du fichier reste sous 0 dB, la vraie onde qui sort des enceintes peut passer au-dessus entre deux points. "
                     "Quand Spotify ou YouTube convertissent ton morceau (MP3, AAC), ces dépassements deviennent des grésillements."),
                  N_("pas de distorsion surprise une fois ton morceau en ligne.")),
    "plr_low": (N_("Le PLR, c'est l'écart entre les coups les plus forts et le volume moyen. Plus il est petit, plus le son est « écrasé » : "
                   "tout est au même niveau, les kicks ne tapent plus, l'oreille fatigue vite."),
                N_("des kicks qui frappent et un morceau qu'on écoute longtemps sans fatigue.")),
    "plr_high": (N_("Ton morceau a beaucoup d'écart entre ses moments forts et faibles. C'est naturel, mais en électro ça peut sonner moins dense, "
                    "moins « gros » que les autres morceaux."),
                 N_("(avec un peu de compression) un son plus soudé et plus plein, sans l'écraser.")),
    "phase": (N_("La gauche et la droite jouent « à l'envers » l'une de l'autre. Quand on les additionne (téléphone, enceinte Bluetooth, sono de club "
                 "souvent en mono), elles s'annulent et des sons disparaissent."),
              N_("un morceau qui sonne pareil partout, même sur une seule enceinte.")),
    "bass_mono": (N_("Les sons graves doivent être au centre. En club, le caisson de basses est souvent en mono ; une basse étalée à gauche et à droite "
                     "perd de la force et devient floue."),
                  N_("un grave solide et puissant, sur toutes les sonos.")),
    "mono_mix": (N_("Un mix où tout est au centre sonne petit et serré. La largeur vient du panoramique (gauche / droite) et des effets comme la reverb "
                    "ou le delay."),
                 N_("de l'espace : chaque son trouve sa place.")),
    "dc": (N_("Ton signal est décalé vers le haut ou le bas au lieu d'être centré sur zéro. Ça ne s'entend pas, mais ça gaspille de la place sous "
              "le plafond et ça peut créer des petits clics."),
           N_("de la marge récupérée gratuitement.")),
    "region_more": (N_("Corriger la piste qui en apporte le plus est plus propre que corriger tout le mix d'un coup : tu ne touches que ce qui pose problème."),
                    N_("un mix plus clair, sans perdre ce qui fait le son de la piste.")),
    "region_less": ("", N_("un mix plus complet, qui sonne bien sur tous les systèmes.")),
    "conflict": (N_("Quand deux sons jouent dans les mêmes fréquences, l'oreille n'arrive plus à les séparer : ils se cachent l'un l'autre, comme deux "
                    "personnes qui parlent en même temps. On a alors envie de monter les deux, ce qui empire tout. On laisse donc la place à l'un des deux. "
                    "(L'analyse regarde le son en moyenne : si ces deux sons ne jouent jamais en même temps, ignore ce conseil.)"),
                 N_("on entend chaque son clairement, sans monter le volume.")),
    "track_hot": (N_("Dans Ableton, une piste peut dépasser 0 dB sans abîmer le son : le calcul interne n'a pas de plafond. Le seul vrai plafond, "
                     "c'est la sortie du Master (et l'export). Mais des pistes trop fortes poussent le Master vers la saturation et rendent le mixage "
                     "plus difficile."),
                  N_("des niveaux bien rangés, faciles à mixer, et un Master qui ne sature pas.")),
    "lowcut": (N_("Cette piste contient des graves qu'on n'entend presque pas quand elle joue seule. Mais dans le mix, ces petits graves s'additionnent "
                  "à ceux des autres pistes et brouillent le kick et la basse. Un coupe-bas doux les enlève. Attention à ne pas le régler trop haut : "
                  "la piste deviendrait maigre."),
               N_("un kick et une basse plus nets, un grave plus propre.")),
    "track_bass_stereo": (N_("Les sons graves doivent être au centre : étalés à gauche et à droite, ils perdent de la force, et sur une sono en mono "
                             "(souvent en club) une partie disparaît."),
                          N_("un grave plus puissant, qui tient sur toutes les sonos.")),
    "track_phase": (N_("La gauche et la droite de cette piste s'annulent : écoutée sur une seule enceinte, elle va presque disparaître. "
                       "C'est souvent la faute d'un effet qui élargit le son."),
                    N_("une piste qui reste présente sur téléphone et en club.")),
    "track_bass_pan": (N_("Le kick et la basse portent l'énergie du morceau. Décalés d'un côté, c'est tout le morceau qui penche, et au casque c'est gênant."),
                       N_("un morceau équilibré, avec un grave bien ancré au centre.")),
    "nothing": (N_("Pas de conflit marqué ni de défaut détecté."), ""),
}


def why(key):
    """Explication traduite : (ce qui se passe, ce que ça t'apporte)."""
    a, b = WHY[key]
    return (t(a) if a else "", t(b) if b else "")


# Courbe "tonale" typique d'un morceau électro masterisé, par bande de tiers d'octave (heuristique),
# calibrée sur des tracks pros : pente ~-3 dB/oct + bosse de grave (~+8 dB sous 100 Hz, nulle à 400 Hz), chute sous 45 Hz.
# ponytail: courbe générique calibrée sur 2 tracks ; --reference (même style) est bien plus fiable.
TARGET_SLOPE_DB_PER_OCT = -3.0
LOW_BUMP_DB = 8.0
TOL_GENERIC_DB, TOL_REF_DB = 5.0, 3.0  # les tracks pros eux-mêmes varient de ±5 dB autour de la courbe générique


def db(x):
    return 20 * np.log10(np.maximum(x, 1e-12))


def pdb(x):  # puissance → dB
    return 10 * np.log10(np.maximum(x, 1e-20))


# ---------------------------------------------------------------- analyse

def load(path):
    data, sr = sf.read(str(path), always_2d=True, dtype="float64")
    return data, sr


def loudness(data, sr):
    peak = float(np.max(np.abs(data)))
    up = signal.resample_poly(data, 4, 1, axis=0)  # sur-échantillonnage x4 pour estimer les "inter-sample peaks"
    true_peak = float(np.max(np.abs(up)))
    lufs = float(pyloudnorm.Meter(sr).integrated_loudness(data))
    clipped = int(np.sum(np.abs(data) >= 0.999))
    return {
        "peak_db": db(peak), "true_peak_db": db(true_peak), "lufs": lufs,
        "plr": db(true_peak) - lufs,  # Peak-to-Loudness Ratio : mesure de dynamique
        "clipped": clipped, "dc": float(np.max(np.abs(data.mean(axis=0)))),
    }


def third_octave_bands():
    centers = 1000 * 2 ** (np.arange(-16, 14) / 3)  # ~25 Hz → ~16 kHz
    return centers[(centers >= 25) & (centers <= 16500)]


def spectrum(data, sr):
    mono = data.mean(axis=1)
    f, p = signal.welch(mono, sr, nperseg=8192)
    centers = third_octave_bands()
    bands = []
    for c in centers:
        m = (f >= c / 2 ** (1 / 6)) & (f < c * 2 ** (1 / 6))
        bands.append(pdb(p[m].sum()) if m.any() else -200)
    return centers, np.array(bands)


def tonal_deviation(centers, bands, ref_bands=None):
    """Écart (dB) de chaque bande par rapport à la cible, recalé sur la zone 100 Hz–10 kHz."""
    if ref_bands is None:
        bump = LOW_BUMP_DB * np.clip(np.log2(400 / centers) / 2, 0, 1)
        rolloff = -12 * np.clip(np.log2(45 / centers), 0, None)  # même les pros perdent du grave sous ~45 Hz
        target = TARGET_SLOPE_DB_PER_OCT * np.log2(centers / 1000) + bump + rolloff
    else:
        target = ref_bands
    dev = bands - target
    mid = (centers >= 100) & (centers <= 10000)
    return dev - np.median(dev[mid])


def stereo(data, sr):
    if data.shape[1] < 2:
        return None
    L, R = data[:, 0], data[:, 1]

    def corr(a, b):
        d = np.sqrt(np.sum(a * a) * np.sum(b * b))
        return float(np.sum(a * b) / d) if d > 0 else 1.0

    sos = signal.butter(4, 120, "lowpass", fs=sr, output="sos")
    lL, lR = signal.sosfilt(sos, L), signal.sosfilt(sos, R)
    mid, side = (L + R) / 2, (L - R) / 2
    lmid, lside = (lL + lR) / 2, (lL - lR) / 2
    rms = lambda x: np.sqrt(np.mean(x * x)) + 1e-12
    return {
        "corr": corr(L, R),
        "corr_low": corr(lL, lR),
        "width_db": db(rms(side) / rms(mid)),       # < -20 dB ≈ quasi mono ; > -3 dB ≈ très large
        "low_width_db": db(rms(lside) / rms(lmid)),
    }


def detect_key(data, sr):
    mono = data.mean(axis=1)
    if sr > 22050:
        mono = signal.resample_poly(mono, 1, int(sr // 22050))
        sr = sr / int(sr // 22050)
    f, _, Z = signal.stft(mono, sr, nperseg=8192)
    A = np.abs(Z)
    mag = np.log1p(100 * A / (A.max() + 1e-20)).sum(axis=1)  # log sur une échelle normalisée : la basse forte n'écrase pas les notes
    keep = (f >= 55) & (f <= 2000)
    pcs = np.round(12 * np.log2(f[keep] / 440) + 69).astype(int) % 12
    chroma = np.bincount(pcs, weights=mag[keep], minlength=12)
    scores = []
    for tonic in range(12):
        for mode, prof in (("majeur", KK_MAJOR), ("mineur", KK_MINOR)):
            scores.append((float(np.corrcoef(chroma, np.roll(prof, tonic))[0, 1]), tonic, mode))
    scores.sort(reverse=True)
    (best, tonic, mode), second = scores[0], scores[1]
    return {"tonic": tonic, "mode": mode, "confidence": best - second[0], "runner_up": second}


def camelot(tonic, mode):
    major_pc = tonic if mode == "majeur" else (tonic + 3) % 12
    return f"{((7 * major_pc) % 12 + 7) % 12 + 1}{'B' if mode == 'majeur' else 'A'}"


def key_theory(tonic, mode):
    intervals, quals, romans = SCALES[mode]
    notes = [(tonic + i) % 12 for i in intervals]
    chords = [f"{r} = {NOTES[n]}{q}" for r, n, q in zip(romans, notes, quals)]
    rel = (tonic + 9) % 12 if mode == "majeur" else (tonic + 3) % 12
    rel_mode = "mineur" if mode == "majeur" else "majeur"
    return notes, chords, (rel, rel_mode)


# ---------------------------------------------------------------- diagnostic

def finding(level, title, fact, why, action, fix=None):
    """why : texte, ou (explication, bénéfice) ; action : liste d'étapes ; fix : correction du bouton ⚡ (device Max for Live, voir m4l/)."""
    expl, gain = why if isinstance(why, tuple) else (why, "")
    return {"level": level, "title": title, "fact": fact, "why": expl, "gain": gain, "action": action, "fix": fix}


def diagnose(L, centers, dev, st, stage, target, has_ref):
    out = []
    tg = TARGETS[target]
    F = finding
    ceiling = f"{tg['tp']:.0f}"
    # 1. Clipping / saturation numérique (le fichier exporté, donc la sortie du Master)
    if L["clipped"] > 0:
        out.append(F("problème", t("Saturation numérique (clipping)"), t("{n} échantillons touchent 0 dBFS.", n=L["clipped"]), why("clipping"),
            [t("Baisse les faders des pistes jusqu'à ce que le vumètre du Master ne passe jamais au rouge."),
             t("Si c'est un master : mets un Limiter en toute dernière position sur le Master.")]))

    # 2. Niveau selon l'étape
    peak = f"{L['peak_db']:.1f}"
    if stage == "mix":
        if L["peak_db"] > -3:
            out.append(F("attention", t("Pas assez de marge (headroom) pour le mastering"), t("Crête à {v} dBFS.", v=peak), why("headroom"),
                [t("Sélectionne toutes les pistes et baisse leurs faders ensemble de quelques dB (ou mets un Utility en tête du Master avec un Gain négatif)."),
                 t("Enlève tout limiteur du Master pendant le mix.")]))
        else:
            out.append(F("ok", t("Bonne marge pour le mastering"), t("Crête à {v} dBFS.", v=peak), why("headroom_ok"), []))
    else:
        diff = L["lufs"] - tg["lufs"]
        lufs, goal = f"{L['lufs']:.1f}", f"{tg['lufs']:.0f}"
        twhy = (t(WHY["lufs"][0]) + " " + t(tg["why"][0]), t(tg["why"][1]))
        if abs(diff) <= tg["tol"]:
            out.append(F("ok", t("Loudness dans la cible"), t("{v} LUFS (cible {target} : {goal}).", v=lufs, target=target, goal=goal), twhy, []))
        elif diff < 0:
            out.append(F("attention", t("Master trop faible"),
                t("{v} LUFS, la cible {target} est ~{goal} LUFS ({d} dB en dessous).", v=lufs, target=target, goal=goal, d=f"{-diff:.1f}"), twhy,
                [t("Sur le Master : Glue Compressor (Ratio 2:1, 1 à 2 dB de réduction maximum)."),
                 t("Puis un Limiter en dernier, Ceiling {c} dB.", c=ceiling),
                 t("Monte le Gain du Limiter d'environ {d} dB en regardant un loudness meter (Youlean Loudness Meter, gratuit : Ableton n'affiche pas les LUFS).",
                   d=f"{-diff:.0f}")]))
        else:
            out.append(F("attention", t("Master trop fort"),
                t("{v} LUFS, la cible {target} est ~{goal} LUFS ({d} dB au-dessus).", v=lufs, target=target, goal=goal, d=f"{diff:.1f}"), twhy,
                [t("Baisse le Gain du Limiter d'environ {d} dB.", d=f"{diff:.0f}"),
                 t("Ton morceau sonnera aussi fort une fois en ligne, mais avec plus de punch.")]))
        if L["true_peak_db"] > tg["tp"]:
            out.append(F("problème", t("True peak trop haut"),
                t("True peak à {v} dBTP (max conseillé {c}).", v=f"{L['true_peak_db']:.1f}", c=ceiling), why("true_peak"),
                [t("Limiter en toute fin de chaîne du Master, Ceiling à {c} dB.", c=ceiling), t("Active son option « True Peak » (Live 12).")]))

    # 3. Dynamique (seuil propre à la cible : un master club fort a forcément un PLR plus bas)
    if L["plr"] < tg["plr_min"]:
        out.append(F("attention", t("Dynamique très écrasée"),
            t("Écart crête/volume (PLR) = {v} dB : sous {min} dB, c'est très écrasé pour cette cible.", v=f"{L['plr']:.1f}", min=f"{tg['plr_min']:.0f}"),
            why("plr_low"),
            [t("Baisse le Gain du Limiter ou la compression du Master."),
             t("Si des pistes ont des compresseurs qui réduisent de plus de 6 dB, allège-les.")]))
    elif stage == "master" and L["plr"] > 16:
        out.append(F("info", t("Beaucoup de dynamique"), t("PLR = {v} dB.", v=f"{L['plr']:.1f}"), why("plr_high"),
            [t("Un peu de compression de bus : Glue Compressor 2:1, Attack 10 ms, Release Auto, 1 à 2 dB de réduction.")]))

    # 4. Équilibre tonal : le conseil dépend du sens (trop ou pas assez)
    tol = TOL_REF_DB if has_ref else TOL_GENERIC_DB
    ref_txt = t("par rapport à ta référence") if has_ref else \
        t("par rapport à la courbe moyenne d'un mix moderne (approximatif — fournis une référence pour plus de précision)")
    for zone, lo, hi, what, too_much, too_little, fix_more, fix_less in REGIONS:
        m = (centers >= lo) & (centers < hi)
        d = float(np.mean(dev[m]))
        intro = t("Cette zone, c'est {what}.", what=t(what))
        if d > tol:
            out.append(F("attention", t("Trop {zone} ({lo}-{hi} Hz)", zone=t(zone), lo=lo, hi=hi),
                t("+{d} dB {ref}.", d=f"{d:.1f}", ref=ref_txt), intro + " " + t(too_much), [t(x) for x in fix_more]))
        elif d < -tol:
            out.append(F("attention", t("Manque {zone} ({lo}-{hi} Hz)", zone=t(zone), lo=lo, hi=hi),
                t("{d} dB {ref}.", d=f"{d:.1f}", ref=ref_txt), intro + " " + t(too_little), [t(x) for x in fix_less]))

    # 5. Stéréo
    if st:
        if st["corr"] < -0.1:
            out.append(F("problème", t("Problème de phase"), t("Corrélation L/R = {v} (négative).", v=f"{st['corr']:.2f}"), why("phase"),
                [t("Mets un Utility sur le Master, Width 0 % (tu écoutes en mono)."), t("Mute les pistes une par une pour trouver celle qui disparaît."),
                 t("Sur cette piste, cherche un élargisseur stéréo, un chorus ou une phase inversée.")]))
        if st["low_width_db"] > -12 or st["corr_low"] < 0.7:
            out.append(F("attention", t("Basses pas assez mono"),
                t("Largeur stéréo sous 120 Hz : {w} dB (corrélation {c}).", w=f"{st['low_width_db']:.0f}", c=f"{st['corr_low']:.2f}"), why("bass_mono"),
                [t("Sur le Master (ou le bus des basses) : Utility, active « Bass Mono », fréquence 120 Hz.")]))
        if st["width_db"] < -25:
            out.append(F("info", t("Mix quasi mono"), t("Largeur stéréo : {w} dB.", w=f"{st['width_db']:.0f}"), why("mono_mix"),
                [t("Panoramique les éléments secondaires (hats, percus, doublures) à gauche et à droite."), t("Garde kick, basse et voix au centre.")]))

    if L["dc"] > 0.01:
        out.append(F("attention", t("Décalage DC"), t("Offset de {v}.", v=f"{L['dc']:.3f}"), why("dc"),
            [t("Utility sur la piste fautive : active le bouton « DC ».")]))

    order = {"problème": 0, "attention": 1, "info": 2, "ok": 3}
    return sorted(out, key=lambda x: order[x["level"]])


# ---------------------------------------------------------------- rapport

CSS = """
:root{--bg:#DCDEE1;--fg:#0E0E0F;--mut:#3E4249;--card:#ECEDEF;--line:#8E9298;--rule:#0E0E0F;
--sub:#2343B0;--bass:#2FA35F;--lowmid:#F4C300;--mid:#E8471C;--himid:#D9468E;--air:#8EC3EA}
@media (prefers-color-scheme:dark){:root{--bg:#151617;--fg:#EDEEF0;--mut:#A4A8AF;--card:#1E1F21;--line:#3A3C40;--rule:#EDEEF0}}
:root.dark{--bg:#151617;--fg:#EDEEF0;--mut:#A4A8AF;--card:#1E1F21;--line:#3A3C40;--rule:#EDEEF0}
::selection{background:var(--fg);color:var(--bg)} :focus-visible{outline:2px solid var(--fg);outline-offset:2px}
body{background:var(--bg);color:var(--fg);font:16px/1.55 "Helvetica Neue",Helvetica,Arial,system-ui,sans-serif;margin:0;padding:24px 16px;-webkit-font-smoothing:antialiased}
main{max-width:820px;margin:auto}
h1{margin:0 0 4px;font-weight:700;letter-spacing:-.02em} h2{margin-top:32px;padding-bottom:6px;border-bottom:1px solid var(--rule);font-weight:600;letter-spacing:-.01em}
.sub{color:var(--mut);margin:0 0 24px}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));border-top:1px solid var(--rule);border-bottom:1px solid var(--rule);margin-bottom:24px}
.stats div{padding:12px 12px 12px 0}
.stats b{display:block;font-size:1.5em;font-weight:500;letter-spacing:-.02em;font-variant-numeric:tabular-nums} .stats span{color:var(--mut);font-size:.85em}
.card{background:var(--card);border:1px solid var(--line);padding:0 16px 14px;margin:10px 0}
.head{display:flex;align-items:stretch;margin:0 -16px;border-bottom:1px solid var(--line);font-size:.7em;font-weight:700;text-transform:uppercase;letter-spacing:.14em;line-height:1}
.head>span{padding:7px 9px}
.head .num{font-variant-numeric:tabular-nums;border-inline-end:1px solid var(--line)}
.tag{color:var(--mut)} .card.problème .tag,.card.attention .tag{background:var(--fg);color:var(--bg)}
.zone{margin-inline-start:auto;color:#0E0E0F;letter-spacing:.06em;text-transform:none}
.zone.z-sub{background:var(--sub);color:#fff} .zone.z-bass{background:var(--bass)} .zone.z-lowmid{background:var(--lowmid)}
.zone.z-mid{background:var(--mid)} .zone.z-himid{background:var(--himid)} .zone.z-air{background:var(--air)}
.card h3{margin:12px 0 6px;font-size:1.05em;font-weight:600}
.fact{margin:0 0 6px} summary{cursor:pointer;color:var(--fg);text-decoration:underline;text-underline-offset:.2em;text-decoration-thickness:1px}
.action{border-top:1px solid var(--line);padding:8px 0 0;margin:10px 0 0} .action ol{margin:6px 0 4px;padding-inline-start:22px}
.autofix{display:inline-flex;align-items:center;gap:8px;font:inherit;font-size:.92em;font-weight:600;margin:8px 0 2px;padding:7px 12px;border:1px solid var(--fg);background:var(--fg);color:var(--bg);cursor:pointer}
@media (hover:hover){.autofix:hover{background:var(--bg);color:var(--fg)}}
.autofix:active{transform:translateY(1px)}
.autofix:disabled,.autofix:disabled:hover{background:transparent;color:var(--mut);border-color:var(--line);transform:none;cursor:default} .fixstatus{margin-inline-start:10px;color:var(--mut);font-size:.9em}
.bolt{width:1em;height:1em;flex:none;vertical-align:-.12em}
svg{width:100%;height:auto;background:var(--card);border:1px solid var(--line)}
.axis{stroke:var(--fg)} .grid{stroke:var(--line)} .band{fill:var(--fg);opacity:.1}
.lbl{fill:var(--mut);font-size:11px;text-anchor:middle} .lbl.start{text-anchor:start} code{background:var(--card);padding:1px 5px}
.z-sub{fill:var(--sub)} .z-bass{fill:var(--bass)} .z-lowmid{fill:var(--lowmid)} .z-mid{fill:var(--mid)} .z-himid{fill:var(--himid)} .z-air{fill:var(--air)}
"""


def why_html(f):
    """L'explication, puis le bénéfice en gras sur sa propre ligne."""
    e = html.escape
    out = f"<p>{e(f['why'])}</p>"
    return out + (f"<p><b>{e(t(GAIN))}</b> {e(f['gain'])}</p>" if f.get("gain") else "")


def card_html(f, n=None):
    """Un conseil. n = son numéro dans la liste (01, 02…), affiché comme un numéro de catalogue."""
    e = html.escape
    z = finding_zone(f)
    head = (f'<span class="num">{n:02d}</span>' if n else "") + f'<span class="tag">{e(t(f["level"]))}</span>' \
        + (f'<span class="zone z-{z[0]}">{z[1]} Hz</span>' if z else "")
    out = (f'<article class="card {e(f["level"])}"><header class="head">{head}</header><h3>{e(f["title"])}</h3>'
           f'<p class="fact">{e(f["fact"])}</p>'
           f'<details><summary>{e(t("Pourquoi ?"))}</summary>{why_html(f)}</details>')
    if f["action"]:
        out += (f'<div class="action"><b>{e(t("Comment corriger dans Ableton"))}</b><ol>'
                + "".join(f"<li>{e(x)}</li>" for x in f["action"]) + "</ol></div>")
    return out + "</article>"


def html_open(title):
    """Début de page commun aux rapports : langue et sens d'écriture (arabe : de droite à gauche)."""
    rtl = ' dir="rtl"' if i18n.lang in i18n.RTL else ""
    return (f'<!doctype html><html lang="{i18n.lang}"{rtl}><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(title)}</title>')


ZONES = [(60, "sub", "20–60"), (250, "bass", "60–250"), (500, "lowmid", "250–500"),
         (2000, "mid", "500–2k"), (6000, "himid", "2k–6k"), (float("inf"), "air", "6k–20k")]


def zone_of(hz):
    """La zone de fréquence (sub … air) d'une fréquence en Hz."""
    return next(z for top, z, _ in ZONES if hz <= top)


def finding_zone(f):
    """La zone dont parle un conseil, d'après la première fréquence citée (« 39 Hz », « 1,3 kHz », « 60-250 Hz »). None si aucune."""
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*(k?)Hz", f["title"] + " " + f["fact"])
    if not m:
        return None
    hz = float(m.group(1).replace(",", ".")) * (1000 if m.group(2) else 1)
    return next((z, r) for top, z, r in ZONES if hz <= top)


def svg_spectrum(centers, dev, tol):
    W, H, pad = 700, 220, 30
    x = lambda f: pad + (np.log10(f) - np.log10(20)) / (np.log10(20000) - np.log10(20)) * (W - 2 * pad)
    y = lambda d: H / 2 - np.clip(d, -12, 12) / 12 * (H / 2 - pad)
    parts = [f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="{html.escape(t("Écart spectral"))}" dir="ltr">',
             f'<rect x="{x(20):.0f}" y="{y(tol):.0f}" width="{x(20000) - x(20):.0f}" height="{y(-tol) - y(tol):.0f}" class="band"/>']
    for f, lab in [(30, "30"), (60, "60"), (250, "250"), (500, "500"), (2000, "2k"), (6000, "6k"), (16000, "16k")]:
        parts.append(f'<line x1="{x(f):.1f}" x2="{x(f):.1f}" y1="{pad}" y2="{H - pad}" class="grid"/>'
                     f'<text x="{x(f):.1f}" y="{H - 8}" class="lbl">{lab} Hz</text>')
    for f, d in zip(centers, dev):  # une barre par bande, de la ligne 0 jusqu'à l'écart, couleur de sa zone
        x0, x1 = x(f / 2 ** (1 / 6)), x(f * 2 ** (1 / 6))
        top, bot = sorted((y(d), H / 2))
        parts.append(f'<rect x="{x0 + 1:.1f}" y="{top:.1f}" width="{max(x1 - x0 - 2, 1):.1f}" height="{max(bot - top, 1):.1f}" class="z-{zone_of(f)}"/>')
    parts += [f'<line x1="{pad}" x2="{W - pad}" y1="{H / 2}" y2="{H / 2}" class="axis"/>',
              f'<text x="4" y="{y(12) + 4:.0f}" class="lbl start">+12 dB</text>',
              f'<text x="4" y="{y(-12):.0f}" class="lbl start">-12 dB</text></svg>']
    return "".join(parts)


def render_html(name, stage, target, L, st, key, centers, dev, findings, has_ref):
    e = html.escape
    tonic, mode = key["tonic"], key["mode"]
    notes, chords, (rel, rel_mode) = key_theory(tonic, mode)
    local = t(NOTES_LOCAL).split()
    tol = TOL_REF_DB if has_ref else TOL_GENERIC_DB
    cards = [card_html(f, i) for i, f in enumerate(findings, 1)]
    stereo_row = (f"<div><b>{st['corr']:.2f}</b><span>{e(t('corrélation L/R'))}</span></div>"
                  f"<div><b>{st['width_db']:.0f} dB</b><span>{e(t('largeur stéréo'))}</span></div>") if st else \
        f"<div><b>mono</b><span>{e(t('fichier'))}</span></div>"
    key_conf = t("fiable") if key["confidence"] > 0.05 else t("incertaine (morceau ambigu ou très percussif)")
    key_txt = f"{NOTES[tonic]} {t(mode)}"
    stage_txt = t("pre-master (mix)") if stage == "mix" else t("master · cible {target}", target=target)
    ref = t("par rapport à ta référence") if has_ref else t("par rapport à un mix moderne moyen")
    return f"""{html_open("MixCoach — " + name)}<style>{CSS}</style></head><body><main>
<h1>MixCoach</h1><p class="sub">{e(name)} · {e(t("étape :"))} <b>{e(stage_txt)}</b></p>
<section class="stats">
<div><b>{L['lufs']:.1f}</b><span>{e(t("LUFS intégrés (volume perçu)"))}</span></div>
<div><b>{L['true_peak_db']:.1f}</b><span>{e(t("dBTP true peak"))}</span></div>
<div><b>{L['plr']:.1f} dB</b><span>{e(t("dynamique (PLR)"))}</span></div>{stereo_row}
<div><b>{e(key_txt)}</b><span>{e(t("tonalité"))} · {camelot(tonic, mode)}</span></div></section>
<h2>{e(t("Diagnostic"))}</h2>{"".join(cards)}
<h2>{e(t("Équilibre tonal"))}</h2>
<p>{e(t("Écart de ton mix {ref}. La bande grise = ±{tol} dB, zone correcte. Au-dessus : trop d'énergie, en dessous : pas assez.", ref=ref, tol=f"{tol:.0f}"))}</p>
{svg_spectrum(centers, dev, tol)}
<h2>{e(t("Théorie : ta tonalité"))}</h2>
<p>{e(t("Tonalité détectée : {key} ({local}) — détection {conf}.", key=key_txt, local=f"{local[tonic]} {t(mode)}", conf=key_conf))}
{e(t("Code Camelot {code} (pour mixer en DJ : compatible avec ±1 et la lettre opposée).", code=camelot(tonic, mode)))}</p>
<p><b>{e(t("Notes de la gamme"))}</b> {e(t("(celles qui « sonnent juste » dans ton morceau) :"))} {e(", ".join(f"{NOTES[n]} ({local[n]})" for n in notes))}.</p>
<p><b>{e(t("Accords de la gamme"))}</b> : {e(" · ".join(chords))}.</p>
<p>{e(t("Astuce Ableton : dans un clip MIDI, active Scale (Live 12) et choisis {scale} — le piano roll surligne ces notes.",
         scale=f"{NOTES[tonic]} {'Major' if mode == 'majeur' else 'Minor'}"))}
{e(t("Tonalité relative : {key} (mêmes notes, autre centre).", key=f"{NOTES[rel]} {t(rel_mode)}"))}</p>
</main></body></html>"""


# ---------------------------------------------------------------- main

def analyze(path, stage="mix", target="streaming", reference=None):
    data, sr = load(path)
    L = loudness(data, sr)
    centers, bands = spectrum(data, sr)
    ref_bands = spectrum(*load(reference))[1] if reference else None
    dev = tonal_deviation(centers, bands, ref_bands)
    st = stereo(data, sr)
    key = detect_key(data, sr)
    findings = diagnose(L, centers, dev, st, stage, target, reference is not None)
    return L, st, key, centers, dev, findings


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("file")
    ap.add_argument("--stage", choices=["mix", "master"], default="mix")
    ap.add_argument("--target", choices=list(TARGETS), default="streaming")
    ap.add_argument("--reference", help="morceau pro du même style, pour comparer l'équilibre tonal")
    ap.add_argument("--lang", choices=list(i18n.LANGS), help="langue du rapport (par défaut : celle du système)")
    ap.add_argument("--no-open", action="store_true")
    a = ap.parse_args()
    i18n.set_lang(a.lang or i18n.system_lang())
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")  # console Windows : un symbole inconnu ne fait pas planter

    L, st, key, centers, dev, findings = analyze(a.file, a.stage, a.target, a.reference)
    out = Path(a.file).with_suffix(".mixcoach.html")
    out.write_text(render_html(Path(a.file).name, a.stage, a.target, L, st, key, centers, dev, findings, bool(a.reference)), encoding="utf-8")

    print(f"{L['lufs']:.1f} LUFS | true peak {L['true_peak_db']:.1f} dBTP | PLR {L['plr']:.1f} dB | "
          f"{t('tonalité')} {NOTES[key['tonic']]} {t(key['mode'])} ({camelot(key['tonic'], key['mode'])})")
    for f in findings:
        print(f"  [{t(f['level']):^9}] {f['title']} — {f['fact']}")
    print(f"\n{t('Rapport :')} {out}")
    if not a.no_open:
        webbrowser.open(out.resolve().as_uri())


if __name__ == "__main__":
    sys.exit(main())
