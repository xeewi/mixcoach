// MixCoach — script Max (JavaScript ES5) commun aux deux devices.
//   [js mixcoach.js sensor] : sur chaque piste. Accumule les mesures envoyées par le patch (bandes, stéréo, crête),
//                             les publie dans le dict partagé « mixcoach », et affiche le résumé de sa piste.
//   [js mixcoach.js master] : sur le Master. Même mesure (= le mix) + affiche la page (jweb) et applique les corrections ⚡.
// Les devices d'un même Live partagent les dicts nommés : c'est ainsi que le Master voit toutes les pistes.
autowatch = 1;
inlets = 1;
outlets = 2;  // 0 : vers jweb (master) ou commentaire (sensor) ; 1 : non utilisé

var MODE = jsarguments.length > 1 ? jsarguments[1] : "sensor";
var UI_HTML = /*UI_HTML*/"";
var SELF = this;      // l'objet js (pour retrouver le fichier du device)
var DEBUG = false;   // true : journal /tmp/mixcoach_dbg_<clé>.json chaque seconde (diagnostic sans ouvrir Max ; Mac/Linux)

var DECAY = Math.exp(-0.1 / 60);  // mesures toutes les 100 ms, mémoire ~1 minute
var NB = 28;
var acc = null, accSt = null, w = 0, peaks = [], frames = [], lastSt = null;
var gains = { l: 1, r: 1 }, playing = false, info = null, lastReset = 0;
var clock = new Task(everySecond, this);
// Références permanentes : un dict nommé sans aucune référence est libéré par Max, puis recréé vide.
var SHARED = new Dict("mixcoach"), SUMMARY = new Dict("mixcoach_summary"), RESETS = new Dict("mixcoach_reset");

function reset() {
    acc = []; for (var i = 0; i < NB; i++) acc.push(0);
    accSt = [0, 0, 0, 0, 0, 0];
    w = 0; peaks = []; frames = [];
}
reset();

function bang() { uiLoaded = false; }  // live.thisdevice : device (re)chargé → recharger la page
var received = [];  // derniers messages reçus de la page (diagnostic)
function note(msg) { received.push(msg.slice(0, 160)); if (received.length > 6) received.shift(); }
function anything() { note(messagename + " " + arrayfromargs(arguments).join(" ")); }  // « url », « title »… du jweb

// L'horloge démarre dès le chargement du script : après un rechargement à chaud (autowatch), Max ne renvoie pas
// le bang de live.thisdevice. Tant que la Live API n'est pas prête, tick() échoue et on réessaie la seconde suivante.
var uiLoaded = false;
clock.interval = 1000;
clock.repeat();

function loadUI() {
    // Où écrire la page du panneau :
    //  - macOS : /tmp. Le navigateur intégré de Max n'a pas le droit de lire ~/Music ni ~/Documents (protection
    //    de la vie privée de macOS : la page s'affichait vide) ;
    //  - Windows : pas de /tmp → à côté du device (.amxd), dans Documents\Ableton\User Library.
    var here = String((SELF.patcher && SELF.patcher.filepath) || ""), dirs = [];
    var deviceDir = here.lastIndexOf("/") > 0 ? [here.slice(0, here.lastIndexOf("/"))] : [];
    dirs = typeof max !== "undefined" && max.os === "windows" ? deviceDir.concat(["/tmp"]) : ["/tmp"].concat(deviceDir);
    for (var i = 0; i < dirs.length; i++) {
        var file = dirs[i] + "/mixcoach_ui.html";
        if (writeText(file, UI_HTML)) { outlet(0, "url", fileUrl(file)); uiLoaded = true; return; }
    }
    throw "impossible d'écrire la page du panneau (" + dirs.join(", ") + ")";
}

function fileUrl(maxPath) {
    // Chemin Max → URL : « Macintosh HD:/Users/moi/a b.html » → file:///Users/moi/a%20b.html ;
    // « C:/Users/moi/a.html » → file:///C:/Users/moi/a.html
    // ponytail: un disque Mac autre que celui du système donnerait /chemin au lieu de /Volumes/Disque/chemin.
    var m = maxPath.match(/^([^:\/]+):(\/.*)$/), path = maxPath;
    if (m) path = m[1].length === 1 ? m[1] + ":" + m[2] : m[2];
    return "file://" + (path.charAt(0) === "/" ? "" : "/") + encodeURI(path);
}

function writeText(path, s) {  // par morceaux : writestring est limité en taille
    var f = new File(path, "write", "TEXT");
    if (!f.isopen) return false;
    f.eof = 0;
    for (var i = 0; i < s.length; i += 8000) f.writestring(s.substr(i, 8000));
    f.eof = f.position;
    f.close();
    return true;
}

function notifydeleted() {
    clock.cancel();
    if (info) SHARED.remove(info.key);
}

// ------------------------------------------------------------ piste et table de mixage

function findTrack() {
    var path = "this_device";
    for (var i = 0; i < 8; i++) {
        path += " canonical_parent";
        var api = new LiveAPI(path);
        if (api.type === "Track") return api;
        if (!api.id || api.id == 0) return null;
    }
    return null;
}

function trackInfo() {
    var t = findTrack();
    if (!t) return null;
    // Live 12 nomme automatiquement les pistes d'après leurs effets (« A-Reverb | MixCoach Sensor ») : on retire le nôtre.
    var p = t.unquotedpath, name = String(t.get("name").join(" ")).replace(/\s*\|\s*MixCoach( Sensor)?/g, ""), kind = "track", key;
    if (p.indexOf("master_track") >= 0) { kind = "master"; key = "Master"; }
    else {
        var m = p.match(/return_tracks (\d+)/), n = p.match(/tracks (\d+)/);
        // clé sans espace (les dicts Max n'aiment pas les espaces) ; le nom affiché reste dans « name »
        key = m ? "R" + m[1] : "T" + (n && parseInt(n[1], 10) < 9 ? "0" : "") + (n ? parseInt(n[1], 10) + 1 : 0);
        if (m) name = "Retour " + name;
        try { if (t.get("is_foldable")[0] == 1) kind = "group"; } catch (e) {}
    }
    return { api: t, path: p, key: key, name: name, kind: kind, dev: String(new LiveAPI("this_device").id) };
}

function num(str) {  // "130 Hz" → 130, "1.30 kHz" → 1300, "-6.0 dB" → -6, "-inf dB" → -1000
    var s = String(str);
    if (/-inf/i.test(s)) return -1000;
    var m = s.match(/(-?\d+(?:\.\d+)?)\s*(k?)/i);
    return m ? parseFloat(m[1]) * (m[2] ? 1000 : 1) : NaN;
}

function display(p, v) { return String(p.call("str_for_value", v)); }

function readMixer() {
    // Le patch entend le son AVANT le fader : on applique fader / panoramique / mute de la piste.
    try {
        var vol = new LiveAPI(info.path + " mixer_device volume");
        var g = Math.pow(10, Math.max(num(display(vol, vol.get("value")[0])), -120) / 20);
        var pan = info.kind === "master" ? 0 : new LiveAPI(info.path + " mixer_device panning").get("value")[0];
        var muted = info.kind !== "master" && info.api.get("mute")[0] == 1;
        gains = muted ? { l: 0, r: 0 } : { l: g * Math.min(1, 1 - pan), r: g * Math.min(1, 1 + pan) };
    } catch (e) {}
}

function everySecond() {
    try { tick(); debug(""); } catch (err) { debug(String(err)); }
}

function debug(err) {  // journal par device : /tmp/mixcoach_dbg_<clé>.json (diagnostic sans ouvrir Max)
    if (!DEBUG) return;
    var k = info ? info.key : "inconnu_" + MODE;
    writeText("/tmp/mixcoach_dbg_" + k + ".json", JSON.stringify({ mode: MODE, key: k, w: w, playing: playing,
        lastSt: lastSt, frames: frames.length, ch: ch, base: base, err: err, ts: new Date().getTime() / 1000,
        seen: [].concat(SHARED.getkeys() || []), mine: info ? SHARED.contains(info.key) : null,
        summary: info && SUMMARY.contains(info.key) ? String(SUMMARY.get(info.key)) : null, received: received }));
}

function tick() {
    info = trackInfo();
    if (!info) return;
    if (MODE === "master" && !uiLoaded) loadUI();
    playing = new LiveAPI("live_set").get("is_playing")[0] == 1;
    readMixer();
    var r = RESETS.get(info.key);
    if (r && r !== lastReset) { lastReset = r; reset(); }
    if (w > 0) SHARED.set(info.key, JSON.stringify(entry()));
    if (DEBUG && MODE === "master") writeText("/tmp/mixcoach_state.json", SHARED.stringify());  // état complet, pour diagnostiquer
    if (MODE === "sensor") {
        var s = SUMMARY.get(info.key);
        // textes d'attente traduits par la page (clés _busy / _idle), français par défaut
        outlet(0, "set", s ? String(s) : String(SUMMARY.get(w > 0 ? "_busy" : "_idle") || (w > 0 ? "Analyse en cours…" : "Lance la lecture pour analyser")));
    }
}

function entry() {
    var bands = [], st = [], i;
    for (i = 0; i < NB; i++) bands.push(acc[i] / w);
    for (i = 0; i < 6; i++) st.push(accSt[i] / w);
    var pk = 0;
    for (i = 0; i < peaks.length; i++) pk = Math.max(pk, peaks[i]);
    return { key: info.key, name: info.name, kind: info.kind, path: info.path, dev: info.dev,
             bands: bands, st: st, peak: pk, punch: punch(), ts: new Date().getTime() / 1000 };
}

function punch() {  // écart entre trames fortes et faibles (100 ms) : élevé = son percussif
    var f = [], mx = -1e9, i;
    for (i = 0; i < frames.length; i++) mx = Math.max(mx, frames[i]);
    for (i = 0; i < frames.length; i++) if (frames[i] > mx - 40) f.push(frames[i]);
    if (f.length < 10) return 0;
    f.sort(function (a, b) { return a - b; });
    return f[Math.floor(0.9 * (f.length - 1))] - f[Math.floor(0.1 * (f.length - 1))];
}

// ------------------------------------------------------------ mesures venant du patch (toutes les 100 ms)

// mc.snapshot~ envoie chaque canal séparément : d'abord « voice <n> » (sortie droite), puis la valeur (sortie gauche).
var frame = { b: [], s: [] }, ch = { b: 0, s: 0 }, base = { b: 1, s: 1 };
function chan(which, args) {
    var n = args[args.length - 1];
    if (n === 0) base[which] = 0;  // numérotation à partir de 0 ou de 1 : on s'adapte
    ch[which] = n - base[which];
}
function bch() { chan("b", arrayfromargs(arguments)); }
function sch() { chan("s", arrayfromargs(arguments)); }
function bval(v) {
    frame.b[ch.b] = v;
    if (ch.b === NB - 1) bands.apply(this, frame.b);
}
function sval(v) {
    frame.s[ch.s] = v;
    if (ch.s === 5) st.apply(this, frame.s);
}

function bands() {  // 28 valeurs RMS du banc de filtres (mid)
    if (!playing || !lastSt || arguments.length < NB) return;
    for (var j = 0; j < NB; j++) if (typeof arguments[j] !== "number" || isNaN(arguments[j])) return;
    // puissance du mid après fader/pan : (gL²·L² + gR²·R² + 2·gL·gR·LR) / (L² + R² + 2·LR)
    var den = lastSt[0] + lastSt[1] + 2 * lastSt[2];
    var k = den > 1e-20 ? (gains.l * gains.l * lastSt[0] + gains.r * gains.r * lastSt[1] + 2 * gains.l * gains.r * lastSt[2]) / den
                        : (gains.l * gains.l + gains.r * gains.r) / 2;
    var tot = 0;
    for (var i = 0; i < NB; i++) {
        var p = arguments[i] * arguments[i] * k;
        acc[i] = acc[i] * DECAY + p;
        tot += p;
    }
    for (i = 0; i < 6; i++) accSt[i] *= DECAY;
    var gl = gains.l, gr = gains.r, g = [gl * gl, gr * gr, gl * gr, gl * gl, gr * gr, gl * gr];
    for (i = 0; i < 6; i++) accSt[i] += lastSt[i] * g[i];
    w = w * DECAY + 1;
    frames.push(10 * Math.log(Math.max(tot, 1e-20)) / Math.LN10);
    if (frames.length > 600) frames.shift();
}

function st() {
    var a = arrayfromargs(arguments);
    if (a.length === 6) lastSt = a;
}  // moyennes [L², R², LR, Lb², Rb², LbRb]

function peak(v) {
    if (!playing) return;
    peaks.push(v * Math.max(gains.l, gains.r));
    if (peaks.length > 1200) peaks.shift();  // 2 capteurs de crête × 10/s × 60 s
}

// ------------------------------------------------------------ corrections ⚡ (device Master uniquement)

// Message en français + valeurs : la page le traduit (même clé que dans i18n/<langue>.json).
function tr(msg, vars) { return { msg: msg, vars: vars || {} }; }


function setByDisplay(p, target) {
    // On cherche la valeur interne dont l'affichage (Hz, dB…) vaut la cible : marche quelle que soit l'échelle.
    var lo = p.get("min")[0], hi = p.get("max")[0];
    for (var i = 0; i < 30; i++) {
        var mid = (lo + hi) / 2;
        if (num(display(p, mid)) < target) lo = mid; else hi = mid;
    }
    p.set("value", (lo + hi) / 2);
    return display(p, (lo + hi) / 2);
}

function setChoice(p, test) {
    var lo = p.get("min")[0], hi = p.get("max")[0], seen = [];
    for (var v = lo; v <= hi; v++) {
        var label = display(p, v);
        seen.push(label);
        if (test(label.toLowerCase().replace(/\s/g, ""))) { p.set("value", v); return label; }
    }
    throw tr("choix introuvable parmi : {list}", { list: seen.join(", ") });
}

function ids(list) {
    var out = [];
    for (var i = 0; i < list.length; i++) if (list[i] === "id") out.push(String(list[i + 1]));
    return out;
}

function param(dev, re) {
    var ps = ids(dev.get("parameters")), names = [];
    for (var i = 0; i < ps.length; i++) {
        var p = new LiveAPI("id " + ps[i]);
        var n = String(p.get("name").join(" "));
        if (re.test(n)) return p;
        names.push(n);
    }
    throw tr("paramètre {name} introuvable ({list})", { name: String(re), list: names.slice(0, 20).join(", ") });
}

function insertBefore(track, sensorId, deviceName) {
    // Juste avant le capteur de la piste, pour que l'analyse entende le résultat.
    var before = ids(track.get("devices")), idx = before.indexOf(sensorId), moved = false;
    try { track.call("insert_device", deviceName, idx >= 0 ? idx : before.length); } catch (e) {}
    var after = ids(track.get("devices"));
    if (after.length === before.length && idx >= 0) {  // ex. capteur placé avant l'instrument
        try { track.call("insert_device", deviceName); } catch (e) {}
        after = ids(track.get("devices"));
        moved = true;
    }
    if (after.length === before.length)
        throw tr("impossible d'ajouter {device} : il faut Live 12.3 ou plus récent (mise à jour gratuite)", { device: deviceName });
    for (var i = 0; i < after.length; i++)
        if (before.indexOf(after[i]) < 0) return { dev: new LiveAPI("id " + after[i]), moved: moved };
}

function applyFix(e, fx) {
    var track = new LiveAPI(e.path);
    if (fx.kind === "volume") {
        var vol = new LiveAPI(e.path + " mixer_device volume");
        var cur = num(display(vol, vol.get("value")[0]));
        return tr("Fader : {from} → {to}", { from: cur.toFixed(1), to: setByDisplay(vol, cur + fx.delta) });
    }
    if (fx.kind === "pan_center") {
        new LiveAPI(e.path + " mixer_device panning").set("value", 0);
        return tr("Panoramique recentré");
    }
    if (fx.kind === "eq") {
        var r = insertBefore(track, e.dev, "EQ Eight"), eq = r.dev, band = fx.shape === "bell" ? 4 : 1;
        param(eq, new RegExp("^" + band + " Filter On A$")).set("value", 1);
        var type = param(eq, new RegExp("^" + band + " Filter Type A$"));
        if (fx.shape === "lowcut12") setChoice(type, function (l) { return /(lowcut|highpass|^hp)/.test(l) && !/48/.test(l); });  // le coupe-bas doux, pas le 48 dB
        else setChoice(type, function (l) { return /(bell|peak)/.test(l); });
        var freq = setByDisplay(param(eq, new RegExp("^" + band + " Frequency A$")), fx.freq), res;
        if (fx.shape === "bell") {
            res = tr("EQ Eight ajouté : bande {band} à {freq}, {gain}", { band: band, freq: freq,
                     gain: setByDisplay(param(eq, new RegExp("^" + band + " Gain A$")), fx.gain) });
            setByDisplay(param(eq, new RegExp("^" + band + " Resonance A$")), fx.q);
        } else res = tr("EQ Eight ajouté : bande {band} à {freq}", { band: band, freq: freq });
        res.moved = r.moved;
        return res;
    }
    if (fx.kind === "bassmono") {
        var u = insertBefore(track, e.dev, "Utility");
        setChoice(param(u.dev, /^bass\s*mono$/i), function (l) { return l === "on" || l === "1"; });
        var bm = tr("Utility ajouté : Bass Mono à {freq}", { freq: setByDisplay(param(u.dev, /bass.*(freq|hz)|mono.*freq/i), fx.freq) });
        bm.moved = u.moved;
        return bm;
    }
    if (fx.kind === "utility_gain") {
        var g = insertBefore(track, e.dev, "Utility");
        var ug = tr("Utility ajouté : gain {gain}", { gain: setByDisplay(param(g.dev, /^gain$/i), fx.db) });
        ug.moved = g.moved;
        return ug;
    }
    throw tr("correction inconnue : {kind}", { kind: fx.kind });
}

function fix(key, fxEnc) {  // envoyé par la page : « fix <clé piste> <json encodé URI, sans espaces> »
    var ok = 1, res;
    note("fix " + key + " " + fxEnc);
    try {
        var raw = SHARED.get(String(key));
        if (!raw) throw tr("piste introuvable (capteur supprimé ?)");
        res = applyFix(JSON.parse(String(raw)), JSON.parse(decodeURIComponent(String(fxEnc))));
        RESETS.set(String(key), new Date().getTime());  // la piste repart de zéro pour juger le nouveau son
    } catch (err) { ok = 0; res = err && err.msg ? err : { msg: String(err) }; }  // erreur Live brute : affichée telle quelle
    note("résultat " + ok + " " + JSON.stringify(res));
    outlet(0, "fixResult", String(key), ok, encodeURIComponent(JSON.stringify(res)));  // encodé : un seul mot pour Max
}
