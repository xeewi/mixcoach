"""Lance tous les tests de MixCoach.  `.venv/bin/python run_tests.py`

Chaque test est un script indépendant (des `assert`, aucun framework) ; on les lance tous, même si l'un échoue,
puis on affiche un résumé. Code de sortie 1 si au moins un test échoue (utilisé par `m4l/build.py --install`).
Si tes exports Ableton sont là, on vérifie en plus le device sur un vrai morceau (~/Music/Exports/002).
"""
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TESTS = [
    ("Analyse globale (LUFS, crêtes, tonalité, conseils)", ["test_mixcoach.py"]),
    ("Analyse piste par piste (conflits, coupe-bas, groupes)", ["test_tracks.py"]),
    ("Device Max for Live (cerveau JS = Python, .amxd, script Max, MixCoach Auto)", ["m4l/test_m4l.py"]),
    ("Traductions (18 langues complètes, mêmes conseils partout)", ["test_i18n.py"]),
]
REAL = Path.home() / "Music/Exports/002"  # vrai projet exporté : facultatif
if REAL.is_dir() and "--rapide" not in sys.argv:  # --rapide : saute ce test (~35 s), ex. avant chaque commit
    TESTS.append(("Device sur un vrai morceau (même conseils que Python)", ["m4l/parity_check.py", str(REAL)]))


def main():
    failed = []
    for label, cmd in TESTS:
        t0 = time.time()
        r = subprocess.run([sys.executable, *cmd], cwd=ROOT, capture_output=True, text=True)
        ok = r.returncode == 0
        print(f"{'✓' if ok else '✗'} {label}  ({time.time() - t0:.1f} s)")
        if not ok:
            failed.append(label)
            print("    " + (r.stdout + r.stderr).strip()[-1500:].replace("\n", "\n    "))
    print(f"\n{len(TESTS) - len(failed)}/{len(TESTS)} OK" + (f" — en échec : {', '.join(failed)}" if failed else ""))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
