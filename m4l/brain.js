// MixCoach — le « cerveau » : compare les pistes entre elles et au mix, et produit les conseils.
// Port JavaScript de tracks.coach (Python) pour tourner dans Ableton sans rien installer.
// Les constantes (zones de fréquences, explications, traductions, courbe cible) viennent de Python via constants.json (build.py).
// Les phrases sont les mêmes qu'en Python, mot pour mot : elles servent de clés de traduction (i18n/<langue>.json).
// Entrée : les mesures brutes envoyées par chaque capteur (voir mixcoach.js → entry()).
"use strict";

const C = typeof MIXCOACH_CONSTANTS !== "undefined" ? MIXCOACH_CONSTANTS : require("./constants.json");
const CENTERS = C.centers;
const LOW_NAME = /kick|bass|sub|808/i;  // pistes qu'on ne coupe jamais dans le grave
const LOW_SHARE = 0.10;  // = tracks.LOW_SHARE
const isLow = tk => LOW_NAME.test(tk.name) || tk.f50 < 120 || tk.low_frac >= LOW_SHARE;  // = tracks.is_low
const ORDER = { "problème": 0, "attention": 1, "info": 2, "ok": 3 };
const ROLES = [[120, "grave (kick / basse)"], [500, "bas-médium (corps)"], [2500, "médium (lead, voix, synthés)"], [1e9, "aigu (hats, cymbales, brillance)"]];

// ------------------------------------------------------------ traduction

let LANG = "fr", CAT = {};
function setLang(code) { LANG = C.langs && C.langs[code] ? code : "en"; CAT = (C.i18n && C.i18n[LANG]) || {}; return LANG; }
function t(s, v) {
  const out = CAT[s] || s;
  return v ? out.replace(/\{(\w+)\}/g, (m, k) => (k in v ? String(v[k]) : m)) : out;
}
const why = key => { const [a, b] = C.why[key]; return [a ? t(a) : "", b ? t(b) : ""]; };

const log10 = Math.log10, log2 = Math.log2;
const pdb = x => 10 * log10(Math.max(x, 1e-20));
const db = x => 20 * log10(Math.max(x, 1e-12));
const sum = a => a.reduce((s, x) => s + x, 0);
const clip = (x, lo, hi) => Math.min(Math.max(x, lo), hi);
const median = a => { const s = [...a].sort((x, y) => x - y), n = s.length; return n % 2 ? s[(n - 1) / 2] : (s[n / 2 - 1] + s[n / 2]) / 2; };
const pct = x => x < 0.01 ? "<1%" : `${Math.round(x * 100)}%`;
const fmtHz = f => f < 1000 ? `${f.toFixed(0)} Hz` : `${(f / 1000).toFixed(1)} kHz`;
const role = f50 => t(ROLES.find(([lim]) => f50 < lim)[1]);
const panLabel = p => Math.abs(p) < 1.5 ? t("centre") : (p > 0 ? t("droite ({v} dB)") : t("gauche ({v} dB)")).replace("{v}", Math.abs(p).toFixed(0));
const finding = (level, title, fact, w, action, fix = null) => {
  const [expl, gain] = Array.isArray(w) ? w : [w, ""];
  return { level, title, fact, why: expl, gain, action, fix };
};

// ------------------------------------------------------------ mesures brutes → caractéristiques

function stereoStats(LL, RR, LR) {
  const corr = LL > 0 && RR > 0 ? LR / Math.sqrt(LL * RR) : 1;
  const mid = (LL + RR + 2 * LR) / 4, side = Math.max((LL + RR - 2 * LR) / 4, 0);
  return { corr, width_db: pdb(side) - pdb(mid) };
}

function features(e) {
  // e.bands : puissance moyenne par tiers d'octave ; e.st : moyennes [L², R², LR, Lb², Rb², LbRb] (b = sous 120 Hz)
  const power = e.bands.map(x => Math.max(x, 1e-20)), tot = sum(power);
  let cum = 0, i50 = power.length - 1;
  for (let i = 0; i < power.length; i++) { cum += power[i] / tot; if (cum >= 0.5) { i50 = i; break; } }
  const below = lim => sum(power.filter((_, i) => CENTERS[i] < lim)) / tot;
  const [LL, RR, LR, lLL, lRR, lLR] = e.st;
  const full = stereoStats(LL, RR, LR), low = stereoStats(lLL, lRR, lLR);
  return {
    key: e.key, name: e.name, power,
    peak: e.peak, f50: CENTERS[i50], low_frac: below(100), low120_frac: below(120),
    stereo: { corr: full.corr, width_db: full.width_db, corr_low: low.corr, low_width_db: low.width_db },
    pan_db: LL > 0 && RR > 0 ? pdb(RR) - pdb(LL) : 0,
    punch_db: e.punch || 0,
  };
}

function tonalDeviation(bandsDb) {
  const dev = bandsDb.map((b, i) => b - C.target[i]);
  const m = median(dev.filter((_, i) => CENTERS[i] >= 100 && CENTERS[i] <= 10000));
  return dev.map(d => d - m);
}

function whoKeepsLow(a, b) {
  // le kick (nom) d'abord : un kick « clicky » peut avoir son centre au-dessus de 120 Hz
  const ka = /kick/i.test(a.name), kb = /kick/i.test(b.name);
  if (ka !== kb) return ka ? [a, b] : [b, a];
  const ga = isLow(a), gb = isLow(b);
  if (ga !== gb) return ga ? [a, b] : [b, a];
  return a.punch_db > b.punch_db ? [a, b] : [b, a];
}

const lowcutStep = hp => t("Bande 1 : choisis le filtre « Low Cut » doux (12 dB/oct, pas la version 48) — la courbe qui descend à gauche — et règle-le vers {f} Hz.", { f: hp });

// ------------------------------------------------------------ comparaison des pistes (= tracks.coach)

function coach(tracks, mixPower) {
  const nB = CENTERS.length;
  const P = tracks.map(tk => tk.power);
  const total = CENTERS.map((_, b) => sum(P.map(r => r[b])) + 1e-20);
  const share = P.map(r => r.map((x, b) => x / total[b]));
  const own = P.map(r => { const mx = Math.max(...r); return r.map(x => 10 * log10(x / (mx + 1e-20) + 1e-20)); });
  const grand = sum(P.map(sum));
  const energyShare = P.map(r => sum(r) / grand);
  const advice = Object.fromEntries(tracks.map(tk => [tk.key, []]));

  // a) Coupables des déséquilibres du mix
  const dev = tonalDeviation(mixPower.map(pdb));
  for (const [z, [zone, lo, hi, what, tooMuch, tooLittle]] of C.regions.entries()) {
    const tol = C.tol_generic[z];
    const idx = CENTERS.map((c, i) => c >= lo && c < hi ? i : -1).filter(i => i >= 0);
    const d = sum(idx.map(i => dev[i])) / idx.length;
    if (Math.abs(d) <= tol) continue;
    const reg = P.map(r => sum(idx.map(i => r[i])));
    const regTot = sum(reg);
    const rs = reg.map(x => x / regTot);
    const top = rs.map((x, i) => [x, i]).sort((a, b) => b[0] - a[0]).slice(0, 2);
    const fc = Math.floor(Math.sqrt(lo * hi));
    const intro = t("Cette zone, c'est {what}.", { what: t(what) });
    for (const [x, i] of top) {
      if (x < 0.25) break;
      const tk = tracks[i], pc = `${Math.round(x * 100)}%`;
      if (d > 0) {
        const w = why("region_more");
        advice[tk.key].push(finding("attention", t("Principale source de l'excès {zone}", { zone: t(zone) }),
          t("Le mix a +{d} dB de trop entre {lo} et {hi} Hz, et cette piste en fournit {pc}.", { d: d.toFixed(1), lo, hi, pc }),
          [intro + " " + t(tooMuch) + " " + w[0], w[1]],
          [t("Ajoute un EQ Eight sur la piste (Navigateur → Audio Effects → EQ Eight)."),
           t("Choisis une bande, mets-la en cloche (Bell), fréquence ~{f} Hz.", { f: fc }),
           t("Baisse son gain de -2 à -4 dB, largeur (Q) ≈ 1."),
           t("Réécoute dans le mix (pas en solo) : ça doit sonner plus clair, sans que la piste disparaisse."),
           t("Variante plus simple : baisse le fader de la piste de 1 à 2 dB.")],
          { kind: "eq", shape: "bell", freq: fc, gain: -3, q: 1, label: t("Ajouter EQ Eight : cloche -3 dB à {f} Hz", { f: fc }) }));
      } else {
        let steps, auto = null;
        if (-d < 8) {
          steps = [t("Monte le fader de la piste de 1 à 2 dB et réécoute."), t("Si ça ne suffit pas : EQ Eight, cloche à ~{f} Hz, +2 dB, Q ≈ 1.", { f: fc })];
          auto = { kind: "volume", delta: 1.5, label: t("Monter le fader de 1,5 dB") };
        } else {
          steps = [t("Il manque {d} dB : un EQ ne suffira pas, ce son n'a presque rien dans cette zone.", { d: (-d).toFixed(0) })].concat(
            hi <= 60 ? [t("Prends un kick plus profond (avec plus de sub) ;"),
                        t("ou ajoute une couche de sub : piste MIDI avec Operator, onde sinus, qui joue les mêmes notes que la basse, entre 30 et 60 Hz.")]
            : hi <= 250 ? [t("Ajoute un Saturator sur la basse (Drive 3 à 6 dB) : il crée des harmoniques qui remplissent cette zone ;"),
                           t("ou choisis un son de basse plus plein (onde en dent de scie ou carrée, filtrée).")]
            : [t("Choisis un son plus riche dans cette zone, ou superpose un deuxième son qui la remplit.")]);
        }
        advice[tk.key].push(finding("info", t("Peut combler le manque {zone}", { zone: t(zone) }),
          t("Le mix manque de {d} dB entre {lo} et {hi} Hz ; cette piste est celle qui en apporte le plus ({pc}).", { d: (-d).toFixed(1), lo, hi, pc }),
          [intro + " " + t(tooLittle), why("region_less")[1]], steps, auto));
      }
    }
  }

  // b) Conflits (masquage)
  const usable = CENTERS.map(c => c >= 30 && c <= 8000);
  const maxUsable = Math.max(...total.filter((_, b) => usable[b]));
  const found = [];
  for (let i = 0; i < tracks.length; i++) for (let j = i + 1; j < tracks.length; j++) {
    let best = -1, bs = 0;
    for (let b = 0; b < nB; b++) {
      const both = usable[b] && own[i][b] > -6 && own[j][b] > -6 && share[i][b] > 0.2 && share[j][b] > 0.2;
      const s = both ? Math.min(share[i][b], share[j][b]) * total[b] / maxUsable : 0;
      if (s > bs) { bs = s; best = b; }
    }
    if (best < 0 || bs < 0.02) continue;
    found.push([bs, i, j, CENTERS[best]]);
  }
  found.sort((x, y) => y[0] - x[0]);
  const conflicts = [];
  for (const [, i, j, f] of found.slice(0, 6)) {
    const a = tracks[i], b = tracks[j];
    const [keep, cut] = f < 150 ? whoKeepsLow(a, b)
      : (Math.abs(log2(a.f50 / f)) < Math.abs(log2(b.f50 / f)) ? [a, b] : [b, a]);
    const fr = fmtHz(f), k = keep.name, c = cut.name;
    let act, auto;
    if (f < 150 && !isLow(cut)) {
      const hp = clip(Math.round(f * 1.5 / 10) * 10, 60, 150);
      act = [t("Sur « {cut} » : ajoute un EQ Eight.", { cut: c }), lowcutStep(hp),
             t("Ce grave ne sert pas le morceau et vient brouiller « {keep} ». Écoute « {keep} » : il doit devenir plus net.", { keep: k })];
      auto = { kind: "eq", shape: "lowcut12", freq: hp, label: t("Ajouter EQ Eight : coupe-bas doux à {f} Hz", { f: hp }) };
    } else if (f < 150) {
      act = [t("Sur « {cut} » : ajoute un Compressor.", { cut: c }),
             t("Déplie le panneau Sidechain (petit triangle en haut à gauche du device), active-le."),
             t("Audio From : choisis « {keep} ».", { keep: k }),
             t("Ratio 4:1, Attack 1 ms, Release 50-100 ms, puis baisse Threshold jusqu'à 3-6 dB de réduction à chaque coup."),
             t("Résultat : « {cut} » s'efface une fraction de seconde à chaque coup de « {keep} ».", { cut: c, keep: k }),
             t("Alternative (automatisable) : EQ Eight sur « {cut} », cloche -3 dB à {f}, Q ≈ 2.", { cut: c, f: fr })];
      auto = { kind: "eq", shape: "bell", freq: Math.round(f), gain: -3, q: 2, label: t("Ajouter EQ Eight : cloche -3 dB à {f}", { f: fr }) };
    } else {
      act = [t("Sur « {cut} » : ajoute un EQ Eight.", { cut: c }),
             t("Une bande en cloche (Bell) à {f}, gain -3 dB, Q ≈ 2 (assez étroit).", { f: fr }),
             t("Réécoute avec « {keep} » : les deux doivent devenir plus distincts.", { keep: k }),
             t("Autre option : si aucun des deux n'est un élément central, panoramique l'un un peu à gauche, l'autre un peu à droite.")];
      auto = { kind: "eq", shape: "bell", freq: Math.round(f), gain: -3, q: 2, label: t("Ajouter EQ Eight : cloche -3 dB à {f}", { f: fr }) };
    }
    const fnd = finding("attention", t("Conflit avec « {keep} » vers {f}", { keep: k, f: fr }),
      t("« {a} » et « {b} » sont tous les deux forts autour de {f}.", { a: a.name, b: b.name, f: fr }), why("conflict"), act, auto);
    advice[cut.key].push(fnd);
    conflicts.push({ a: a.name, b: b.name, freq: f, cut: c, keep: k });
  }

  // c) Règles propres à chaque piste
  tracks.forEach((tk, n) => {
    const adv = advice[tk.key], st = tk.stereo;
    if (tk.peak >= 0.999)  // info : dans Live (virgule flottante) une piste au-dessus de 0 dB ne sature pas
      adv.push(finding("info", t("Piste très forte (au-dessus de 0 dB)"), t("Crête à {v} dBFS.", { v: db(tk.peak).toFixed(1) }), why("track_hot"),
        [t("Baisse le fader de la piste, ou la sortie de l'effet qui pousse le plus (saturateur, EQ avec gros boost) ;"),
         t("ou ajoute un Utility en fin de chaîne et baisse son Gain jusqu'à ce que le vumètre de la piste ne passe plus au rouge.")],
        { kind: "utility_gain", db: -3, label: t("Ajouter Utility : gain -3 dB") }));
    if (tk.f50 > 400 && tk.low_frac > 0.02 && !isLow(tk)) {
      const hp = clip(Math.round(tk.f50 / 8 / 10) * 10, 40, 150);
      adv.push(finding("attention", t("Grave inutile : mets un coupe-bas"),
        t("Le contenu principal de la piste est vers {f} Hz, mais {pc} de son énergie est sous 100 Hz.", { f: tk.f50.toFixed(0), pc: `${(tk.low_frac * 100).toFixed(1)}%` }),
        why("lowcut"),
        [t("Ajoute un EQ Eight sur la piste."), lowcutStep(hp),
         t("Astuce d'oreille : monte la fréquence jusqu'à entendre la piste s'amincir, puis redescends un peu.")],
        { kind: "eq", shape: "lowcut12", freq: hp, label: t("Ajouter EQ Eight : coupe-bas doux à {f} Hz", { f: hp }) }));
    }
    if (tk.low120_frac > 0.1 && (st.low_width_db > -12 || st.corr_low < 0.7))
      adv.push(finding("attention", t("Grave en stéréo"),
        t("Largeur sous 120 Hz : {w} dB (corrélation {c}).", { w: st.low_width_db.toFixed(0), c: st.corr_low.toFixed(2) }), why("track_bass_stereo"),
        [t("Ajoute un Utility sur la piste."), t("Active « Bass Mono » et règle sa fréquence sur 120 Hz."),
         t("Tout ce qui est sous 120 Hz devient mono ; le reste garde sa largeur.")],
        { kind: "bassmono", freq: 120, label: t("Ajouter Utility : Bass Mono à 120 Hz") }));
    if (st.corr < -0.1)
      adv.push(finding("problème", t("Phase inversée / trop large"), t("Corrélation L/R = {v}.", { v: st.corr.toFixed(2) }), why("track_phase"),
        [t("Ajoute un Utility, mets Width à 0 % : si la piste s'affaiblit beaucoup, elle a bien un problème de phase."),
         t("Désactive un par un les effets stéréo de la piste (Chorus-Ensemble, élargisseurs, Utility Width > 100 %) pour trouver le coupable."),
         t("Réduis son réglage de largeur, ou remplace-le. (Pas de correction automatique : il faut trouver la cause.)")]));
    if (tk.f50 < 120 && Math.abs(tk.pan_db) > 3)
      adv.push(finding("attention", t("Grave décentré"), t("Panoramique : {p}.", { p: panLabel(tk.pan_db) }), why("track_bass_pan"),
        [t("Dans le mixeur, remets le panoramique de la piste au centre (double-clic sur le bouton Pan, ou tape « C »).")],
        { kind: "pan_center", label: t("Recentrer le panoramique") }));
    if (!adv.length)
      adv.push(finding("ok", t("Rien à signaler"), t("Piste {role}, {pc} de l'énergie du mix.", { role: role(tk.f50), pc: pct(energyShare[n]) }),
        why("nothing"), []));
    adv.sort((x, y) => ORDER[x.level] - ORDER[y.level]);
  });
  return { advice, conflicts, energyShare };
}

// ------------------------------------------------------------ le mix global (sous-ensemble de mixcoach.diagnose mesurable en direct)

function mixFindings(m) {
  const out = [], peakDb = db(m.peak), st = m.stereo, v = { v: peakDb.toFixed(1) };
  if (m.peak >= 1)  // le Master est le seul vrai plafond dans Live
    out.push(finding("problème", t("Le Master sature"), t("Crête à {v} dBFS.", v), why("clipping"),
      [t("Baisse les faders des pistes jusqu'à ce que le vumètre du Master ne passe jamais au rouge."),
       t("Si c'est un master : mets un Limiter en toute dernière position sur le Master.")]));
  else if (peakDb > -3)
    out.push(finding("attention", t("Pas assez de marge (headroom) pour le mastering"), t("Crête à {v} dBFS.", v), why("headroom"),
      [t("Sélectionne toutes les pistes et baisse leurs faders ensemble de quelques dB."), t("Enlève tout limiteur du Master pendant le mix.")]));
  else
    out.push(finding("ok", t("Bonne marge pour le mastering"), t("Crête à {v} dBFS.", v), why("headroom_ok"), []));
  if (st.corr < -0.1)
    out.push(finding("problème", t("Problème de phase"), t("Corrélation L/R = {v} (négative).", { v: st.corr.toFixed(2) }), why("phase"),
      [t("Mets un Utility sur le Master, Width 0 % (tu écoutes en mono)."), t("Mute les pistes une par une pour trouver celle qui disparaît."),
       t("Sur cette piste, cherche un élargisseur stéréo, un chorus ou une phase inversée.")]));
  if (st.low_width_db > -12 || st.corr_low < 0.7)
    out.push(finding("attention", t("Basses pas assez mono"),
      t("Largeur stéréo sous 120 Hz : {w} dB (corrélation {c}).", { w: st.low_width_db.toFixed(0), c: st.corr_low.toFixed(2) }), why("bass_mono"),
      [t("Regarde quelles pistes ont « Grave en stéréo » ci-dessus et corrige-les en priorité."), t("Sinon : Utility sur le Master, « Bass Mono » à 120 Hz.")]));
  if (st.width_db < -25)
    out.push(finding("info", t("Mix quasi mono"), t("Largeur stéréo : {w} dB.", { w: st.width_db.toFixed(0) }), why("mono_mix"),
      [t("Panoramique les éléments secondaires (hats, percus, doublures) à gauche et à droite."), t("Garde kick, basse et voix au centre.")]));
  return out.sort((x, y) => ORDER[x.level] - ORDER[y.level]);
}

// ------------------------------------------------------------ point d'entrée

function analyze(entries) {
  const master = entries.find(e => e.kind === "master");
  const audible = e => sum(e.bands) > 1e-10;  // piste muette pendant la mesure : rien à analyser
  const tracks = entries.filter(e => e.kind === "track" && audible(e)).map(features);
  if (!tracks.length) return null;
  const mixPower = master ? master.bands : CENTERS.map((_, b) => sum(tracks.map(tk => tk.power[b])));
  const { advice, conflicts, energyShare } = coach(tracks, mixPower);
  const mix = master ? features(master) : null;
  return {
    tracks: tracks.map((tk, k) => ({ key: tk.key, name: tk.name, role: role(tk.f50), share: energyShare[k], pan: panLabel(tk.pan_db), advice: advice[tk.key] })),
    conflicts,
    mix: mix ? { peak_db: db(mix.peak), findings: mixFindings(mix) } : null,
  };
}

// Résumé d'une ligne pour le petit panneau du capteur de chaque piste.
function summary(tk) {
  const todo = tk.advice.filter(f => f.level === "problème" || f.level === "attention");
  if (!todo.length) return t("✓ Rien à signaler");
  return t("{n} à corriger : {title}", { n: todo.length, title: todo[0].title });
}

const api = { analyze, summary, features, coach, tonalDeviation, pct, fmtHz, CENTERS, t, setLang, get lang() { return LANG; } };
if (typeof module !== "undefined") module.exports = api;
else window.MixCoachBrain = api;
