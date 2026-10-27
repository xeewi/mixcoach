"""Construit les devices Max for Live de MixCoach.  `python m4l/build.py [--install]`

Produit dans m4l/dist/ :
  - constants.json        : constantes partagées Python → cerveau JS (zones de fréquences, courbe cible…)
  - mixcoach_ui.html      : la page du panneau Master (cerveau + rendu, tout en un fichier)
  - MixCoach Sensor.amxd  : capteur à poser sur chaque piste
  - MixCoach.amxd         : panneau à poser sur le Master
  - mixcoach.js           : script Max commun aux deux devices
"""
import json
import shutil
import struct
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import i18n  # noqa: E402
import mixcoach as mc  # noqa: E402

DIST = HERE / "dist"


def constants():
    return {
        "centers": [float(c) for c in mc.third_octave_bands()],
        "regions": [list(r[:6]) for r in mc.REGIONS],  # nom, Hz, ce que c'est, si trop, si pas assez
        "why": mc.WHY, "gain": mc.GAIN,
        # toutes les traductions sont embarquées : la page change de langue sans rien charger
        "langs": i18n.LANGS, "rtl": sorted(i18n.RTL),
        "i18n": {c: i18n.catalog(c) for c in i18n.LANGS if c != i18n.SOURCE and (i18n.DIR / f"{c}.json").exists()},
        "target_slope": mc.TARGET_SLOPE_DB_PER_OCT,
        "low_bump": mc.LOW_BUMP_DB,
        "tol_generic": mc.TOL_GENERIC_DB,
    }


def write_constants():
    (HERE / "constants.json").write_text(json.dumps(constants(), ensure_ascii=False, indent=1))


# ---------------------------------------------------------------- page et script

def ui_html(fixture=None):
    """La page du panneau Master : CSS de mixcoach.py + constantes + cerveau, en un seul fichier."""
    html = (HERE / "ui.html").read_text()
    html = html.replace("/*CSS*/", mc.CSS).replace("/*CONSTANTS*/null", json.dumps(constants(), ensure_ascii=False))
    html = html.replace("/*BRAIN*/", (HERE / "brain.js").read_text())
    if fixture is not None:  # aperçu hors de Max
        html = html.replace("<script>\nvar MIXCOACH_CONSTANTS", f"<script>window.MIXCOACH_FIXTURE = {json.dumps(fixture)};</script>\n<script>\nvar MIXCOACH_CONSTANTS", 1)
    return html


def max_js():
    """Le script Max, avec la page embarquée (un seul fichier à geler dans le device)."""
    return (HERE / "mixcoach.js").read_text().replace('/*UI_HTML*/""', json.dumps(ui_html()))


# ---------------------------------------------------------------- devices

TEMPLATE = Path("/Applications/Ableton Live 12 Suite.app/Contents/App-Resources/Misc/Max Devices/Max Audio Effect.amxd")


def read_amxd(path):
    raw = Path(path).read_bytes()
    assert raw[:4] == b"ampf" and raw[24:28] == b"ptch", "format .amxd inattendu"
    n = struct.unpack("<I", raw[28:32])[0]
    return raw[:24], json.loads(raw[32:32 + n].rstrip(b"\x00").decode("utf-8"))


def write_amxd(path, head, patch):
    body = json.dumps(patch, indent=1).encode("utf-8") + b"\n\x00"
    Path(path).write_bytes(head + b"ptch" + struct.pack("<I", len(body)) + body)


class Patch:
    def __init__(self):
        self.boxes, self.lines, self.n = [], [], 0

    def obj(self, text, ins, outs, outtype=None, cls="newobj", rect=None, **extra):
        self.n += 1
        bid = f"mc-{self.n}"
        rect = rect or [40.0 + (self.n % 6) * 150, 60.0 + (self.n // 6) * 40, 140.0, 22.0]
        box = {"id": bid, "maxclass": cls, "numinlets": ins, "numoutlets": outs, "patching_rect": rect, **extra}
        if text is not None:
            box["text"] = text
        if outtype is not None:
            box["outlettype"] = outtype
        self.boxes.append({"box": box})
        return bid

    def link(self, src, so, dst, di):
        self.lines.append({"patchline": {"source": [src, so], "destination": [dst, di]}})


def measurement(P, plugin):
    """Le patch qui mesure : banc de 28 filtres (tiers d'octave) + stéréo + crête, tout envoyé au js toutes les 100 ms."""
    nb = len(mc.third_octave_bands())
    add = P.obj("+~", 2, 1, ["signal"])
    half = P.obj("*~ 0.5", 2, 1, ["signal"])
    P.link(plugin, 0, add, 0); P.link(plugin, 1, add, 1); P.link(add, 0, half, 0)
    bank = P.obj(f"fffb~ {nb} 31.25 1.259921 4.32", 1, nb, ["signal"] * nb)
    P.link(half, 0, bank, 0)
    pack = P.obj(f"mc.pack~ {nb}", nb, 1, ["multichannelsignal"])
    # chaque bande passe dans un 2e filtre identique : pentes 2× plus raides, sinon une basse forte « fuit »
    # dans les bandes voisines (+8 dB mesurés à 31 Hz sur de vrais morceaux ; ~1 dB avec 2 filtres)
    for i, c in enumerate(mc.third_octave_bands()):
        f2 = P.obj(f"fffb~ 1 {c:.4f} 1 4.32", 1, 1, ["signal"])
        P.link(bank, i, f2, 0); P.link(f2, 0, pack, i)
    avg = P.obj("mc.average~ 4800 rms", 2, 1, ["multichannelsignal"])
    # mc.snapshot~ : sortie droite = « voice <n> », puis sortie gauche = valeur de ce canal
    snap = P.obj("mc.snapshot~ 100", 2, 2, ["", ""])
    pre_b = P.obj("prepend bval", 1, 1, [""])
    pre_bc = P.obj("prepend bch", 1, 1, [""])
    P.link(pack, 0, avg, 0); P.link(avg, 0, snap, 0); P.link(snap, 0, pre_b, 0); P.link(snap, 1, pre_bc, 0)
    # stéréo : L², R², LR, puis la même chose sous 120 Hz
    xl = P.obj("cross~ 120", 2, 2, ["signal", "signal"])
    xr = P.obj("cross~ 120", 2, 2, ["signal", "signal"])
    P.link(plugin, 0, xl, 0); P.link(plugin, 1, xr, 0)
    pack6 = P.obj("mc.pack~ 6", 6, 1, ["multichannelsignal"])
    for k, ((a, ao), (b, bo)) in enumerate([((plugin, 0), (plugin, 0)), ((plugin, 1), (plugin, 1)), ((plugin, 0), (plugin, 1)),
                                             ((xl, 0), (xl, 0)), ((xr, 0), (xr, 0)), ((xl, 0), (xr, 0))]):
        m = P.obj("*~", 2, 1, ["signal"])
        P.link(a, ao, m, 0); P.link(b, bo, m, 1); P.link(m, 0, pack6, k)
    avg6 = P.obj("mc.average~ 4800 bipolar", 2, 1, ["multichannelsignal"])
    snap6 = P.obj("mc.snapshot~ 100", 2, 2, ["", ""])
    pre_s = P.obj("prepend sval", 1, 1, [""])
    pre_sc = P.obj("prepend sch", 1, 1, [""])
    P.link(pack6, 0, avg6, 0); P.link(avg6, 0, snap6, 0); P.link(snap6, 0, pre_s, 0); P.link(snap6, 1, pre_sc, 0)
    pre_p = P.obj("prepend peak", 1, 1, [""])
    for ch in (0, 1):
        pk = P.obj("peakamp~ 100", 2, 1, ["float"])
        P.link(plugin, ch, pk, 0); P.link(pk, 0, pre_p, 0)
    return [pre_s, pre_sc, pre_b, pre_bc, pre_p]


def build_device(mode):
    head, patch = read_amxd(TEMPLATE)
    p = patch["patcher"]
    p["boxes"] = [b for b in p["boxes"] if b["box"].get("text") in ("plugin~", "plugout~")]  # le son passe sans modification
    plugin = next(b["box"]["id"] for b in p["boxes"] if b["box"]["text"] == "plugin~")
    P = Patch()
    feeds = measurement(P, plugin)
    js = P.obj(f"js mixcoach.js {mode}", 1, 2, ["", ""])
    for f in feeds:
        P.link(f, 0, js, 0)
    dev = P.obj("live.thisdevice", 1, 3, ["bang", "int", "int"])
    P.link(dev, 0, js, 0)
    font = {"fontname": "Ableton Sans Medium Regular", "fontsize": 11.0}
    P.obj("MixCoach", 1, 0, [], cls="comment", presentation=1, presentation_rect=[6.0, 4.0, 160.0, 18.0], **font)
    if mode == "sensor":
        txt = P.obj("Lance la lecture pour analyser", 1, 0, [], cls="comment", presentation=1, linecount=6,
                    presentation_rect=[6.0, 24.0, 168.0, 140.0], fontname="Ableton Sans Light Regular", fontsize=11.0)
        P.link(js, 0, txt, 0)
        p["devicewidth"] = 180.0
    else:
        web = P.obj(None, 1, 3, ["", "", ""], cls="jweb", rect=[40.0, 600.0, 640.0, 160.0],
                    presentation=1, presentation_rect=[0.0, 22.0, 640.0, 147.0], rendermode=0)
        P.link(js, 0, web, 0); P.link(web, 0, js, 0)
        # fenêtre flottante, même page en grand
        sub = {"fileversion": 1, "appversion": p["appversion"], "classnamespace": "box", "rect": [80.0, 80.0, 1000.0, 760.0],
               "toolbarvisible": 0, "statusbarvisible": 0, "boxes": [
                   {"box": {"id": "w-in0", "maxclass": "inlet", "numinlets": 0, "numoutlets": 1, "outlettype": [""], "patching_rect": [5.0, 5.0, 20.0, 20.0]}},
                   {"box": {"id": "w-in1", "maxclass": "inlet", "numinlets": 0, "numoutlets": 1, "outlettype": [""], "patching_rect": [40.0, 5.0, 20.0, 20.0]}},
                   {"box": {"id": "w-out", "maxclass": "outlet", "numinlets": 1, "numoutlets": 0, "patching_rect": [75.0, 5.0, 20.0, 20.0]}},
                   {"box": {"id": "w-web", "maxclass": "jweb", "numinlets": 1, "numoutlets": 3, "outlettype": ["", "", ""],
                            "patching_rect": [0.0, 0.0, 1000.0, 760.0], "rendermode": 0}}],
               "lines": [{"patchline": {"source": ["w-in1", 0], "destination": ["w-web", 0]}},
                         {"patchline": {"source": ["w-web", 0], "destination": ["w-out", 0]}}]}
        win = P.obj("p MixCoachFenetre", 2, 1, [""], patcher=sub)
        btn = P.obj("⤢", 1, 3, ["", "", "int"], cls="textbutton", presentation=1,
                    presentation_rect=[612.0, 2.0, 24.0, 18.0], fontsize=12.0)
        opn = P.obj("open", 2, 1, [""], cls="message")
        pc = P.obj("pcontrol", 1, 1, [""])
        P.link(btn, 0, opn, 0); P.link(opn, 0, pc, 0); P.link(pc, 0, win, 0)
        P.link(js, 0, win, 1); P.link(win, 0, js, 0)
        p["devicewidth"] = 640.0
    p["boxes"] += P.boxes
    p["lines"] += P.lines
    p["openinpresentation"] = 1
    return head, patch


NAMES = {"sensor": "MixCoach Sensor.amxd", "master": "MixCoach.amxd"}
USER_LIB = Path.home() / "Music/Ableton/User Library/Presets/Audio Effects/Max Audio Effect/MixCoach"


def build():
    write_constants()
    DIST.mkdir(exist_ok=True)
    (DIST / "mixcoach.js").write_text(max_js())
    if TEMPLATE.exists():  # les .amxd partent du modèle fourni avec Ableton Live (absent sur une machine sans Live, ex. CI)
        for mode, name in NAMES.items():
            write_amxd(DIST / name, *build_device(mode))
    return DIST


def install(tests=True):
    """Construit et copie dans la User Library d'Ableton — seulement si tous les tests passent."""
    if tests:
        import subprocess
        if subprocess.run([sys.executable, str(HERE.parent / "run_tests.py")]).returncode:
            sys.exit("\nInstallation annulée : un test échoue (voir ci-dessus). Forcer : --install --sans-tests")
    build()
    USER_LIB.mkdir(parents=True, exist_ok=True)
    for f in ["mixcoach.js", *NAMES.values()]:
        shutil.copy(DIST / f, USER_LIB / f)
    rs = Path.home() / "Music/Ableton/User Library/Remote Scripts/MixCoachAuto"
    rs.mkdir(parents=True, exist_ok=True)
    shutil.copy(HERE / "MixCoachAuto" / "__init__.py", rs / "__init__.py")
    print(f"Installé dans : {USER_LIB}\nRemote Script : {rs}")


if __name__ == "__main__":
    install("--sans-tests" not in sys.argv) if "--install" in sys.argv else print(f"Construit dans : {build()}")
