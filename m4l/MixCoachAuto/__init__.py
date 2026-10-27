"""MixCoach Auto — Remote Script Ableton : pose « MixCoach Sensor » sur chaque piste et « MixCoach » sur le Master.

Installation : ce dossier dans « User Library/Remote Scripts/ », puis
Réglages → Link, Tempo & MIDI → Surface de contrôle → « MixCoachAuto ».

Toutes les 2 s : chaque piste (hors groupes) et chaque retour sans capteur en reçoit un, en fin de chaîne.
Si tu retires un capteur toi-même, il n'est pas remis pendant la session.
"""
import time

SENSOR, MASTER = "MixCoach Sensor", "MixCoach"
CHECK_EVERY_S = 2.0
LOAD_TIMEOUT_S = 10.0  # le chargement d'un device Max prend un moment : on n'en relance pas un 2e entre-temps


def _base(name):
    return name[:-5] if name.lower().endswith(".amxd") else name


class Auto(object):
    """La logique, sans dépendance à Ableton (testable avec de faux objets)."""

    def __init__(self, song, browser, log):
        self.song, self.browser, self.log = song, browser, log
        self.items = {}
        self.handled = set()   # pistes déjà équipées une fois (si l'utilisateur retire le capteur, on respecte)
        self.pending = {}      # piste → heure de la demande de chargement
        self.tries = {}        # piste → nombre d'essais (abandon après 2 : on ne harcèle pas Ableton)
        self.last = 0.0

    def find_item(self, name):
        if name in self.items:
            return self.items[name]
        stack = [(self.browser().user_library, 0)]
        while stack:
            item, depth = stack.pop()
            if getattr(item, "is_loadable", False) and _base(item.name) == name:
                self.items[name] = item
                return item
            if depth < 6:
                stack.extend((c, depth + 1) for c in getattr(item, "children", []))
        return None

    def wanted(self, track, is_master):
        """Le nom du device à ajouter sur cette piste, ou None."""
        if not is_master and getattr(track, "is_foldable", False):
            return None  # groupe : son déjà mesuré par ses pistes
        want = MASTER if is_master else SENSOR
        if any(d.name == want for d in track.devices):
            return None
        return want

    def tick(self, now=None):
        now = time.time() if now is None else now
        if now - self.last < CHECK_EVERY_S:
            return
        self.last = now
        s = self.song()
        targets = [(t, False) for t in list(s.tracks) + list(s.return_tracks)] + [(s.master_track, True)]
        for track, is_master in targets:
            key = id(track) if not hasattr(track, "_live_ptr") else track._live_ptr
            want = self.wanted(track, is_master)
            if want is None:
                self.handled.add(key)
                self.pending.pop(key, None)
                continue
            if key in self.handled or now - self.pending.get(key, 0) < LOAD_TIMEOUT_S:
                continue
            if self.tries.get(key, 0) >= 2:
                self.handled.add(key)
                self.log("MixCoachAuto : impossible d'ajouter le capteur sur « %s »" % track.name)
                continue
            item = self.find_item(want)
            if item is None:
                self.log("MixCoachAuto : « %s » introuvable dans la User Library" % want)
                return
            self.load(track, item)
            self.pending[key] = now
            self.tries[key] = self.tries.get(key, 0) + 1
            return  # un device à la fois

    def load(self, track, item):
        view = self.song().view
        before = view.selected_track
        view.selected_track = track
        if len(track.devices):
            view.select_device(track.devices[-1])  # le browser insère après le device sélectionné → fin de chaîne
        self.browser().load_item(item)
        view.selected_track = before
        self.log("MixCoachAuto : ajouté sur « %s »" % track.name)


def create_instance(c_instance):
    from _Framework.ControlSurface import ControlSurface  # disponible seulement dans Ableton

    class MixCoachAuto(ControlSurface):
        def __init__(self, c_instance):
            ControlSurface.__init__(self, c_instance)
            self.auto = Auto(self.song, lambda: self.application().browser, self.log_message)
            self.show_message("MixCoach Auto ✓")  # sans phrase : compris dans toutes les langues

        def update_display(self):  # appelé ~10 fois par seconde par Ableton
            ControlSurface.update_display(self)
            try:
                self.auto.tick()
            except Exception as e:  # ne jamais faire planter Ableton
                self.log_message("MixCoachAuto erreur : %r" % (e,))

    return MixCoachAuto(c_instance)
