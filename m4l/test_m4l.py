"""Self-check des devices Max for Live. `python m4l/test_m4l.py`"""
import json
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
import soundfile as sf

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import build  # noqa: E402
import parity_check as pc  # noqa: E402

# 1. Le cerveau JS donne les mêmes conseils que le Python, sur un faux projet aux défauts connus
import test_m4l_fixture as fx  # noqa: E402

js, diffs = pc.compare(fx.entries())
assert not diffs, diffs
titles = {x["key"]: " | ".join(f["title"] for f in x["advice"]) for x in js["tracks"]}
assert "coupe-bas" in titles["Pad"] and "Grave en stéréo" in titles["Bass"], titles
assert any(c["keep"] == "Kick" and c["cut"] == "Bass" for c in js["conflicts"]), js["conflicts"]
assert js["mix"] and js["mix"]["findings"]

# 2. Les devices : en-tête Ableton, liaisons valides, page embarquée dans le script
out = build.build()
for mode, name in build.NAMES.items():
    raw = (out / name).read_bytes()
    assert raw[:24] == build.HEADER
    n = struct.unpack("<I", raw[28:32])[0]
    p = json.loads(raw[32:32 + n].rstrip(b"\x00"))["patcher"]
    ids = {b["box"]["id"] for b in p["boxes"]}
    for line in p["lines"]:
        assert line["patchline"]["source"][0] in ids and line["patchline"]["destination"][0] in ids, line
    texts = " ".join(b["box"].get("text", "") for b in p["boxes"])
    assert f"js mixcoach.js {mode}" in texts and "fffb~ 28" in texts and "plugout~" in texts
    assert ("jweb" in {b["box"]["maxclass"] for b in p["boxes"]}) == (mode == "master")
mjs = (out / "mixcoach.js").read_text(encoding="utf-8")
assert "MixCoachBrain" in mjs and '/*UI_HTML*/""' not in mjs
subprocess.run(["node", "--check", str(out / "mixcoach.js")], check=True)
subprocess.run(["node", str(HERE / "test_maxjs.js")], check=True)  # le script Max dans un faux Max

# La page charge brain.js puis son propre script dans le même espace global : pas de nom déclaré deux fois
import re  # noqa: E402
def decl(src):  # noms déclarés au niveau global : « const a = …, b = … », « function f »
    names = {n for m in re.finditer(r"^(?:const|let|var)\s+(.+?);", src, re.M) for n in re.findall(r"(?:^|,)\s*(\w+)\s*=", m[1])}
    return names | set(re.findall(r"^function\s+(\w+)", src, re.M))


ui_js = (HERE / "ui.html").read_text(encoding="utf-8").split("/*BRAIN*/")[1]
clash = decl((HERE / "brain.js").read_text(encoding="utf-8")) & decl(ui_js)
assert not clash, f"noms déclarés deux fois dans la page : {clash}"
print("OK — tous les checks passent")

# 3. MixCoach Auto (Remote Script) avec un faux Ableton
sys.path.insert(0, str(HERE / "MixCoachAuto"))
import importlib  # noqa: E402
auto_mod = importlib.import_module("__init__")


class Obj:
    def __init__(self, **kw):
        self.__dict__.update(kw)


sensor_item = Obj(name="MixCoach Sensor.amxd", is_loadable=True, children=[])
master_item = Obj(name="MixCoach.amxd", is_loadable=True, children=[])
browser = Obj(user_library=Obj(name="User Library", children=[Obj(name="Presets", children=[Obj(name="MixCoach", children=[sensor_item, master_item])])]))
kick = Obj(name="Kick", devices=[Obj(name="Simpler")], is_foldable=False)
grp = Obj(name="Drums", devices=[], is_foldable=True)
done = Obj(name="Pad", devices=[Obj(name="MixCoach Sensor")], is_foldable=False)
master = Obj(name="Main", devices=[])
view = Obj(selected_track=done, select_device=lambda d: None)
song = Obj(tracks=[kick, grp, done], return_tracks=[], master_track=master, view=view)


def load_item(item):
    view.selected_track.devices.append(Obj(name=auto_mod._base(item.name)))


browser.load_item = load_item
a = auto_mod.Auto(lambda: song, lambda: browser, lambda m: None)
for k in range(10):
    a.tick(now=100 + 3 * k)
assert [d.name for d in kick.devices] == ["Simpler", "MixCoach Sensor"], kick.devices  # en fin de chaîne
assert grp.devices == [] and [d.name for d in master.devices] == ["MixCoach"]
assert [d.name for d in done.devices] == ["MixCoach Sensor"]  # pas de doublon
assert view.selected_track is done  # sélection rendue à l'utilisateur
kick.devices.pop()  # l'utilisateur retire le capteur : on respecte
a.tick(now=200)
assert [d.name for d in kick.devices] == ["Simpler"]

print("OK — MixCoach Auto")
