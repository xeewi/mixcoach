# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Beginner home-studio producers who make and finish tracks alone in Ableton Live 12. They have never learned mixing or music theory and can't read a spectrum analyzer. They open MixCoach while a track is playing, to find out why their mix sounds muddy, harsh or weak, and what to change.

## Product Purpose

MixCoach listens to every track of an Ableton Live project and says in plain words what to fix in the mix, how to do it in Ableton (real device and parameter names), and why it matters. A ⚡ action can apply the fix (pan, fader, EQ Eight, Utility), and Cmd/Ctrl+Z undoes it. It also writes a mastering report for an exported file (LUFS, true peak, PLR, tonal balance vs a target or a reference track) and covers basic music theory (key, scale, chords, Camelot code).

Success: a beginner understands what is wrong, applies the fix, and learns why, without needing to know any jargon first.

## Positioning

It compares tracks **with each other**, not only the master: "the Pad brings 60% of the mud between 250 and 500 Hz, cut it there." Analyzers show curves; MixCoach names the culprit track, explains it in everyday words, and gives the Ableton steps. Free, open source, offline: no account, no server, no AI service, just maths on the audio.

## Operating Context

- In Ableton Live: a *Sensor* device on each track, the *MixCoach* panel on the Master (Max for Live `jweb`, small inline view or a large ⤢ window). Used while the music is playing, in a studio setting, next to Live's own UI.
- From the command line: `mixcoach.py` / `tracks.py` on exported audio produce an HTML report that opens in the browser.
- Download page on GitHub Pages (`docs/index.html`), plus the README visuals on GitHub.

## Capabilities and Constraints

- Three web surfaces: download site, Ableton panel (`m4l/ui.html`), HTML report (from `mixcoach.py`). The panel and the report share one CSS string (`CSS` in `mixcoach.py`, injected into `ui.html` at `/*CSS*/`).
- The panel runs offline inside Max's `jweb` (Chromium): no network fonts or assets; everything is inlined in one file.
- 18 languages, including right-to-left Arabic, Hindi (Devanagari), Japanese, Korean and Chinese. Type has to cover these scripts or fall back cleanly.
- Ableton device and parameter names stay in English in every language.
- Python and Max for Live give the same advice (parity test); the UI renders the same findings in both.
- macOS and Windows.

## Brand Commitments

- Name: **MixCoach**. This is the only binding element of the current identity. The current logo, the ⚡ symbol and the purple/pink look are not binding.

## Evidence on Hand

- Real screenshots: `docs/assets/panel.png`, `docs/assets/card.png`, `docs/assets/report.png` (to be redone after the redesign).
- Real feature set and copy in `README.md` / `README.fr.md` and `i18n/`.
- No testimonials, user counts, press or download figures exist. Do not invent any.

## Product Principles

1. Plain words before numbers: every finding explains itself without jargon.
2. Always actionable: what to do in Ableton, step by step, and a one-click fix where possible.
3. Name the culprit: point at a specific track, not just a frequency band.
4. Honest and offline: no account, no tracking, nothing leaves the computer.
5. Teach while fixing: the "why" makes the user better at mixing over time.

## Accessibility & Inclusion

Must work in 18 languages including RTL (Arabic). Readable in a dim studio, inside a small Ableton device view.
