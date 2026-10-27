"""Traductions de MixCoach.

Le texte source est le français, écrit directement dans le code : t("Crête à {v} dBFS.", v="-1.0").
i18n/<langue>.json associe chaque phrase source à sa traduction ; une phrase absente reste en français.
N_("...") marque une phrase à traduire plus tard (données : zones, explications…) sans la traduire tout de suite.
`python i18n.py` liste toutes les phrases du projet dans i18n/_source.json (base pour les traducteurs).
"""
import json
import locale
import os
import re
from pathlib import Path

DIR = Path(__file__).resolve().parent / "i18n"
SOURCE = "fr"
LANGS = {  # code → nom dans sa propre langue (pour le menu)
    "en": "English", "fr": "Français", "es": "Español", "de": "Deutsch", "it": "Italiano", "pt-BR": "Português (Brasil)",
    "nl": "Nederlands", "pl": "Polski", "ru": "Русский", "uk": "Українська", "tr": "Türkçe", "ar": "العربية",
    "hi": "हिन्दी", "id": "Bahasa Indonesia", "ja": "日本語", "ko": "한국어", "zh-CN": "简体中文", "zh-TW": "繁體中文",
}
RTL = {"ar"}

lang, _cat = SOURCE, {}


def N_(s):
    return s


def t(s, **kw):
    out = _cat.get(s) or s
    return re.sub(r"\{(\w+)\}", lambda m: str(kw[m[1]]) if m[1] in kw else m[0], out) if kw else out


def match(code):
    """« fr_FR.UTF-8 » → fr, « pt_BR » → pt-BR, « zh_Hant_TW » → zh-TW ; inconnu → en."""
    c = (code or "").split(".")[0].replace("_", "-").lower()
    if c.startswith("zh"):
        return "zh-TW" if any(x in c for x in ("tw", "hk", "hant")) else "zh-CN"
    if c.startswith("pt"):
        return "pt-BR"
    return next((k for k in LANGS if k.lower() == c.split("-")[0]), "en")


def system_lang():
    env = os.environ.get("MIXCOACH_LANG") or os.environ.get("LC_ALL") or os.environ.get("LANG")
    return match(env or locale.getlocale()[0] or "")


def catalog(code):
    return {} if code == SOURCE else json.loads((DIR / f"{code}.json").read_text("utf-8"))


def set_lang(code):
    global lang, _cat
    lang = match(code) if code not in LANGS else code
    _cat = catalog(lang)


def placeholders(s):
    return sorted(set(re.findall(r"\{(\w+)\}", s)))


# ---------------------------------------------------------------- extraction des phrases

def extract():
    """Toutes les phrases à traduire : appels t("…") / N_("…") en Python (AST), t("…") / tr("…") en JS."""
    import ast
    root = DIR.parent
    keys = []
    for f in ["mixcoach.py", "tracks.py"]:
        for node in ast.walk(ast.parse((root / f).read_text("utf-8"))):
            if isinstance(node, ast.Call) and getattr(node.func, "id", None) in ("t", "N_") and node.args:
                a = node.args[0]  # t(variable) traduit une donnée déjà marquée par N_("…") : rien à extraire
                if isinstance(a, ast.Constant) and isinstance(a.value, str):
                    keys.append(a.value)
    for f in ["m4l/brain.js", "m4l/ui.html", "m4l/mixcoach.js"]:
        src = (root / f).read_text("utf-8")
        calls = re.findall(r"(?<![\w.])(?:t|tr)\(\s*(\"(?:[^\"\\]|\\.)*\")", src)
        bad = re.findall(r"(?<![\w.])(?:t|tr)\(\s*[`']", src)
        assert not bad, f"{f} : t() attend une chaîne entre guillemets doubles, sans ${{}}"
        keys += [json.loads(c) for c in calls]
    return list(dict.fromkeys(keys))


def check(code, keys=None):
    """Problèmes d'une traduction : phrases manquantes, en trop, ou dont les {valeurs} ne correspondent pas."""
    keys = keys or extract()
    cat = catalog(code)
    out = [f"manquante : {k!r}" for k in keys if not cat.get(k)]
    out += [f"en trop : {k!r}" for k in cat if k not in keys]
    out += [f"valeurs {placeholders(k)} ≠ {placeholders(v)} : {k!r}" for k, v in cat.items() if k in keys and placeholders(k) != placeholders(v)]
    return out


if __name__ == "__main__":
    import sys
    keys = extract()
    (DIR / "_source.json").write_text(json.dumps(keys, ensure_ascii=False, indent=1), "utf-8")
    print(f"{len(keys)} phrases → {DIR / '_source.json'}")
    bad = 0
    for code in LANGS:
        if code != SOURCE and (DIR / f"{code}.json").exists():
            pb = check(code, keys)
            bad += len(pb)
            print(f"  {code}: " + ("OK" if not pb else f"{len(pb)} problème(s)"))
            for x in pb[:5]:
                print("     ", x)
    sys.exit(1 if bad else 0)
