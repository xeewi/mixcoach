"""Self-check des traductions. `python test_i18n.py`"""
import json
import subprocess
import sys
from pathlib import Path

import i18n

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "m4l"))

# 1. Chaque langue : toutes les phrases, aucune en trop, mêmes {valeurs} ; 12 noms de notes
keys = i18n.extract()
for code in i18n.LANGS:
    if code == i18n.SOURCE:
        continue
    pb = i18n.check(code, keys)
    assert not pb, (code, pb[:5])
    assert len(i18n.catalog(code)[i18n.N_("Do Do# Ré Ré# Mi Fa Fa# Sol Sol# La La# Si")].split()) == 12, code

# 2. Détection de la langue du système
assert [i18n.match(x) for x in ("fr_FR.UTF-8", "pt_BR", "zh_Hant_TW", "zh-CN", "de-AT", "xx", "")] == \
       ["fr", "pt-BR", "zh-TW", "zh-CN", "de", "en", "en"]

# 3. Rapport traduit, et le device dit exactement la même chose que Python dans une autre langue
import parity_check as pc  # noqa: E402
import test_m4l_fixture as fx  # noqa: E402

for code in ("en", "ja", "ar"):
    js, diffs = pc.compare(fx.entries(), code)
    assert not diffs, (code, diffs)
    assert all(f["title"] for tk in js["tracks"] for f in tk["advice"])
i18n.set_lang("en")
import mixcoach as mc  # noqa: E402
f = mc.diagnose({"clipped": 3, "peak_db": 0.0, "true_peak_db": 0.5, "lufs": -9, "plr": 9.5, "dc": 0}, mc.third_octave_bands(),
                mc.third_octave_bands() * 0, None, "mix", "streaming", False)
assert f[0]["level"] == "problème" and "3" in f[0]["fact"] and f[0]["title"] == i18n.catalog("en")["Saturation numérique (clipping)"]
assert 'lang="en"' in mc.html_open("x") and 'dir="rtl"' not in mc.html_open("x")
i18n.set_lang("ar")
assert 'dir="rtl"' in mc.html_open("x")
i18n.set_lang("fr")
print(f"OK — {len(i18n.LANGS)} langues, {len(keys)} phrases chacune")
