// Simule l'environnement Max pour tester m4l/mixcoach.js hors d'Ableton.  `node m4l/test_maxjs.js`
const fs = require("fs"), vm = require("vm"), assert = require("assert");
const dicts = {}, outs = [];
function load(mode, trackPath) {
  const ctx = {
    jsarguments: ["mixcoach.js", mode], post() {}, outlet: (...a) => outs.push(a),
    arrayfromargs: a => Array.prototype.slice.call(a),
    Task: function () { this.repeat = () => {}; this.cancel = () => {}; },
    File: function () { this.isopen = false; },
    Dict: function (name) { const d = dicts[name] = dicts[name] || {}; this.get = k => d[k]; this.set = (k, v) => { d[k] = v; }; this.remove = k => delete d[k]; this.stringify = () => JSON.stringify(d); this.getkeys = () => Object.keys(d); this.contains = k => k in d; },
    LiveAPI: function (path) {
      this.type = /canonical_parent$/.test(path) ? "Track" : "Device"; this.id = 7;
      this.unquotedpath = trackPath; this.path = trackPath;
      this.set = () => {}; this.get = p => ({ name: ["Loud", "Brass"], is_playing: [1], is_foldable: [0], mute: [0], value: [0] }[p] || [0]);
      this.call = (f, v) => f === "str_for_value" ? "0.0 dB" : null;
    },
    Math, JSON, Date, String, parseInt, parseFloat, isNaN,
  };
  vm.createContext(ctx);
  vm.runInContext(fs.readFileSync(__dirname + "/mixcoach.js", "utf8"), ctx);
  return ctx;
}

for (const base of [0, 1]) {  // mc.snapshot~ peut numéroter les canaux à partir de 0 ou de 1
  const js = load("sensor", "live_set tracks 3");
  js.everySecond();  // lit la piste, la lecture, le mixeur
  for (let f = 0; f < 20; f++) {
    for (let c = 0; c < 6; c++) { js.sch("voice", c + base); js.sval([0.1, 0.1, 0.09, 0.05, 0.05, 0.05][c]); }
    for (let c = 0; c < 28; c++) { js.bch("voice", c + base); js.bval(0.01 * (c + 1)); }
  }
  js.everySecond();  // publie dans le dict partagé
  const e = JSON.parse(dicts.mixcoach.T04);
  assert.strictEqual(e.name, "Loud Brass");
  assert.strictEqual(e.bands.length, 28);
  assert(e.bands.every(x => typeof x === "number" && x > 0), "bandes incomplètes : " + e.bands);
  assert(Math.abs(e.bands[27] / e.bands[0] - 28 * 28) < 1e-6, "mauvais ordre des canaux");
  assert(e.st.every(x => typeof x === "number"));
  delete dicts.mixcoach.T04;
}
// Clic ⚡ : la page envoie « fix <clé> <json encodé> », le script répond « fixResult <clé> <ok> <message encodé> »
{
  const js = load("master", "live_set tracks 3");
  dicts.mixcoach.T04 = JSON.stringify({ key: "T04", path: "live_set tracks 3", dev: "7" });
  outs.length = 0;
  js.fix("T04", encodeURIComponent(JSON.stringify({ kind: "pan_center", label: "Recentrer le panoramique" })));
  const r = outs.find(o => o[1] === "fixResult");
  assert(r && r[2] === "T04" && r[3] === 1, "pas de réponse ok : " + JSON.stringify(outs));
  assert.strictEqual(JSON.parse(decodeURIComponent(r[4])).msg, "Panoramique recentré");  // la page traduit cette clé
  outs.length = 0;
  js.fix("T04", encodeURIComponent(JSON.stringify({ kind: "inconnu" })));
  const e = JSON.parse(decodeURIComponent(outs.find(o => o[1] === "fixResult")[4]));
  assert(e.msg === "correction inconnue : {kind}" && e.vars.kind === "inconnu", JSON.stringify(e));
  assert(!/\s/.test(r[4]), "message non encodé (Max le découperait)");
}
console.log("OK — tous les checks passent");
