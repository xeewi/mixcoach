---
name: MixCoach
description: The mix read as a coded record sleeve; six frequency zones, six flat colours, every finding a catalogue number.
colors:
  silver: "#C8CBD0"
  silver-deep: "#B9BDC3"
  ink: "#0E0E0F"
  ink-soft: "#34373D"
  paper: "#E4E6E9"
  white: "#FFFFFF"
  report-ground: "#DCDEE1"
  report-card: "#ECEDEF"
  report-muted: "#3E4249"
  report-line: "#8E9298"
  graphite: "#151617"
  graphite-card: "#1E1F21"
  graphite-ink: "#EDEEF0"
  graphite-muted: "#A4A8AF"
  graphite-line: "#3A3C40"
  zone-sub: "#2343B0"
  zone-bass: "#2FA35F"
  zone-lowmid: "#F4C300"
  zone-mid: "#E8471C"
  zone-himid: "#D9468E"
  zone-air: "#8EC3EA"
typography:
  display:
    fontFamily: "Archivo, Helvetica Neue, Helvetica, Arial, system-ui, sans-serif"
    fontSize: "clamp(40px, 5.4vw, 76px)"
    fontWeight: 500
    lineHeight: 1
    letterSpacing: "-0.035em"
  headline:
    fontFamily: "Archivo, Helvetica Neue, Helvetica, Arial, system-ui, sans-serif"
    fontSize: "clamp(32px, 3.6vw, 48px)"
    fontWeight: 500
    lineHeight: 1.05
    letterSpacing: "-0.03em"
  title:
    fontFamily: "Archivo, Helvetica Neue, Helvetica, Arial, system-ui, sans-serif"
    fontSize: "28px"
    fontWeight: 600
    lineHeight: 1.15
    letterSpacing: "-0.02em"
  lead:
    fontFamily: "Archivo, Helvetica Neue, Helvetica, Arial, system-ui, sans-serif"
    fontSize: "20px"
    fontWeight: 400
    lineHeight: 1.5
  body:
    fontFamily: "Archivo, Helvetica Neue, Helvetica, Arial, system-ui, sans-serif"
    fontSize: "17px"
    fontWeight: 400
    lineHeight: 1.55
  label:
    fontFamily: "Archivo, Helvetica Neue, Helvetica, Arial, system-ui, sans-serif"
    fontSize: "12px"
    fontWeight: 600
    letterSpacing: "0.16em"
    fontVariation: "\"wdth\" 125"
  app-body:
    fontFamily: "Helvetica Neue, Helvetica, Arial, system-ui, sans-serif"
    fontSize: "16px"
    fontWeight: 400
    lineHeight: 1.55
  app-title:
    fontFamily: "Helvetica Neue, Helvetica, Arial, system-ui, sans-serif"
    fontSize: "1.05em"
    fontWeight: 600
  app-label:
    fontFamily: "Helvetica Neue, Helvetica, Arial, system-ui, sans-serif"
    fontSize: "0.7em"
    fontWeight: 700
    lineHeight: 1
    letterSpacing: "0.14em"
rounded:
  none: "0px"
spacing:
  xs: "6px"
  sm: "12px"
  md: "16px"
  lg: "28px"
  xl: "56px"
  section: "88px"
components:
  button-download:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.white}"
    rounded: "{rounded.none}"
    padding: "20px 28px"
  button-download-hover:
    backgroundColor: "{colors.white}"
    textColor: "{colors.ink}"
  button-fix:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.white}"
    rounded: "{rounded.none}"
    padding: "12px 18px"
  button-fix-hover:
    backgroundColor: "{colors.white}"
    textColor: "{colors.ink}"
  segmented-option:
    backgroundColor: "transparent"
    textColor: "{colors.ink}"
    typography: "{typography.label}"
    padding: "8px 18px"
  segmented-option-selected:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.white}"
  severity-label-strong:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.white}"
    typography: "{typography.label}"
    padding: "10px 14px"
  zone-chip-sub:
    backgroundColor: "{colors.zone-sub}"
    textColor: "{colors.white}"
    typography: "{typography.app-label}"
    padding: "7px 9px"
  zone-chip-lowmid:
    backgroundColor: "{colors.zone-lowmid}"
    textColor: "{colors.ink}"
    typography: "{typography.app-label}"
    padding: "7px 9px"
  finding-card:
    backgroundColor: "{colors.report-card}"
    textColor: "{colors.ink}"
    rounded: "{rounded.none}"
    padding: "0 16px 14px"
  finding-card-dark:
    backgroundColor: "{colors.graphite-card}"
    textColor: "{colors.graphite-ink}"
    rounded: "{rounded.none}"
    padding: "0 16px 14px"
  button-autofix:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.report-ground}"
    rounded: "{rounded.none}"
    padding: "7px 12px"
---

# Design System: MixCoach

## Overview

**Creative North Star: "The Coded Sleeve"**

MixCoach reads a mix the way a Factory Records sleeve reads a record: a silver-grey ground, black ink, and a colour code that has to be learned once and then means one thing everywhere. Six flat fields stand for the six frequency zones (sub, bass, low mids, mids, high mids, air). Each finding the product gives is filed like a catalogue entry: a two-digit number, a severity word in ink, and the zone it concerns as a coloured chip with its Hz range.

The system spans three surfaces with one grammar. The download site (Persuade) uses the full sleeve: big tight Archivo headlines, the stacked six-band sleeve that changes the headline when a band is picked, hairline-ruled sections. The HTML report and the Ableton panel (Operate) share one stylesheet and say the same thing more quietly: system neo-grotesk, a lighter silver ground for the report and dark graphite for the panel, which lives inside Ableton. The cipher, the catalogue numbers and the ink severity labels are the same across all three.

Everything is flat. No gradients, no glow, no rounded cards, no drop shadows. Depth comes from flat fields sitting next to each other and from 1px ink rules. The visual this rejects is the dark plugin-vendor page with a glowing screenshot and a grid of icon cards.

**Key Characteristics:**
- Silver ground, black ink, square corners, 1px hairline rules.
- Six flat cipher colours, used for frequency-zone data only.
- Every finding is a catalogue entry: number, severity word, zone chip.
- Severity is shown by ink weight and words, never by colour.
- Neo-grotesk: large and tight for findings, small, wide and tracked for labels.
- State changes invert ink and ground; they never add colour.

## Colors

A neutral silver-and-ink sleeve carrying one six-colour data cipher; nothing else in the system is coloured.

### Primary
- **Sleeve Ink** (ink): text, rules, the solid download block, the strong severity label, focus outlines, selection. The one voice of the system.

### Secondary: the zone cipher (data only)
- **Sub Ultramarine** (zone-sub): 20–60 Hz. The only zone dark enough to need white text.
- **Bass Green** (zone-bass): 60–250 Hz.
- **Low-Mid Yellow** (zone-lowmid): 250–500 Hz, the "mud" zone, the default selected band on the site.
- **Mids Vermilion** (zone-mid): 500 Hz–2 kHz.
- **High-Mid Magenta** (zone-himid): 2–6 kHz.
- **Air Sky** (zone-air): 6–20 kHz.

The cipher keeps the same values in light and dark themes. Text on a zone field is ink, except on Sub Ultramarine where it is white.

### Neutral
- **Sleeve Silver** (silver): the site ground and the `theme-color`.
- **Deep Silver** (silver-deep): secondary text on the inverted ink closing band.
- **Soft Ink** (ink-soft): secondary copy, leads, captions on silver.
- **Sleeve Paper** (paper): the lighter field behind the example entry and inline `code`.
- **White** (white): text on ink, and the inverted hover state of ink blocks.
- **Report Silver / Report Card / Report Muted / Report Line** (report-ground, report-card, report-muted, report-line): the light theme of the shared report/panel stylesheet. The line grey is for card borders and table rules; section rules stay ink.
- **Graphite family** (graphite, graphite-card, graphite-ink, graphite-muted, graphite-line): the dark theme, forced on in the Ableton panel and used by the report under `prefers-color-scheme: dark`. In it, "ink" becomes graphite-ink and inversions flip accordingly.

### Named Rules
**The Cipher Is Data Rule.** The six zone colours mark frequency zones and nothing else: zone bands, zone swatches, zone chips, the bars of the tonal-balance spectrum. Hover, focus, selection, links and buttons are ink or inverse. The one exception is the logo, whose six bands are the cipher used as identity.

**The Ink Severity Rule.** Severity is never a colour. "Problem" and "warning" (FR "problème", "attention") are a solid ink label with ground-coloured text; "info" and "ok" are muted text with no fill. Use the product's translated level words, not invented codes.

## Typography

**Display Font (site):** Archivo, self-hosted variable woff2 (weights 100–900, widths 62–125%), with Helvetica Neue, Helvetica, Arial, system-ui fallback
**App Font (panel and report):** Helvetica Neue, Helvetica, Arial, system-ui, sans-serif
**Mono:** ui-monospace, SF Mono, Menlo, Consolas (paths and parameters in `code`)

**Character:** One neo-grotesk voice in two settings. Findings are set large, medium weight and tightly tracked so they read like a sleeve's title; labels are set small, uppercase, widened (Archivo at 125% width) and spread out like catalogue code. Archivo is only for the site. The panel runs offline in Max's jweb and has to cover 18 scripts, so it uses the system stack.

### Hierarchy
- **Display** (500, clamp 40–76px, 1.0, −0.035em): the hero finding headline only, balanced wrap.
- **Headline** (500, clamp 32–48px, 1.05, −0.03em): section titles, max ~18em.
- **Title** (600, 28px, 1.15, −0.02em): the title of an example entry; zone names in the key are 600 at 20px.
- **Lead** (400, 20px, 1.5): the one-line explainer under the display line; section subs are 19px, max ~38em.
- **Body** (400, 17px, 1.55): site running text.
- **Label** (600, 12px, 0.16em, uppercase, 125% width): nav, catalogue numbers, Hz ranges, severity, zone chips, list keys (A1, B2), sub-headings like "How to fix it in Ableton".
- **App body / title / label** (system stack; 16px report, 14px panel; card titles 600 at 1.05em; card-head labels 700 at 0.7em, 0.14em, uppercase): the shared report/panel stylesheet. The zone chip inside a card head drops the uppercase and uses 0.06em tracking so "250–500 Hz" stays readable.

### Named Rules
**The Tabular Code Rule.** Every number that is part of the code (catalogue numbers, Hz ranges, LUFS, dB, percentages in tables) uses tabular figures.

**The Label Names Things Rule.** Tracked labels name, number or classify what they sit on or beside (a band, an entry, a list row, a nav target). A label never floats above a headline as a decorative eyebrow.

## Layout

Site: a 1240px max container with 32px side padding (16px under 620px). The hero is a 5:6 two-column grid with a 56px gap: copy on the left (display line, lead, download block, meta), the square sleeve on the right. Sections are separated by a 1px ink top rule and padded 88px (64px on mobile). Two-column compositions (example entry + notes, Side A / Side B) use a 7:5 or 1:1 grid with a 56px gap and collapse to one column under 980px. The six-zone key is a 6-column ruled grid that goes to 3 columns under 980px and 2 under 620px. Lists are ruled rows: a fixed key column (52–92px, 44px on mobile) and the content.

Report: a single 820px column. Stats are an auto-fit grid (min 130px) between two ink rules. Panel: full-width, 12–14px padding, track cards in an auto-fill grid with a 320px minimum.

Rhythm runs on 6 / 12 / 16 / 28 / 56 / 88px steps. All grids are RTL-safe (logical `inline-start` borders and padding).

## Elevation & Depth

None. The system is flat: no drop shadows, no gradients, no blur, no glow. Depth comes from flat fields next to each other (zone bands, the paper entry on silver, the ink closing band) and from 1px rules. The only `box-shadow` used is inset, as a thick outline: the selected sleeve band carries a 6px inset ink frame (7px in the banner), and its focus state adds a 3px white inner ring.

### Named Rules
**The Flat Sleeve Rule.** Nothing floats above the page. A selected thing gets an ink frame or an inversion; it is never lifted.

## Shapes

Square corners everywhere (0px), including native controls (`border-radius:0` on the panel's language select). Borders are 1px ink hairlines; a 3px ink rule is used only under the Side A / Side B headings. Colour fields run flush to their container's edges: the sleeve bands fill the square with no gaps, and key swatches bleed to the column rules. Content inside those fields is inset (22px in bands, 16px in key columns). The sleeve is a 1:1 square split into horizontal bands whose heights scale with the example mix's energy per zone.

## Components

### Buttons
Solid ink blocks that turn inside out on hover.
- **Shape:** square (0px).
- **Download block:** ink, white bold title (22px, 700) over a small line with the platforms and release tag, and a 30px square-cap download arrow; padding 20px 28px. On the ink closing band it starts white with ink text.
- **Fix button (site) / autofix (panel, report):** ink with ground-coloured text, weight 600, an inline SVG bolt (stroke 2, miter joins) before the label. Hover inverts to ground with ink text and a 1px ink edge. Disabled turns soft ink (site) or 50% opacity (app) and shows the undo hint.
- **Ghost (nav language toggle):** transparent, 1px ink border, label type, padding 5px 10px; hover fills with ink.
- **Focus:** a 3px ink outline offset by 3px on the site (white on the ink band); 2px offset 2px in the app.

### Segmented control
- **Style:** a 1px ink-bordered strip of label-type options (macOS / Windows), padding 8px 18px.
- **State:** the selected option is solid ink with white text; the others are transparent.

### Catalogue head (signature)
The header strip of every finding, all on one line and joined by 1px rules: catalogue number (`01`, continuous across the whole panel or report) | severity word | zone chip with the Hz range (taken from the first frequency the finding cites). The chip sits at the inline end. If a finding cites no frequency it gets no chip.

### Cards / Containers
- **Corner Style:** square (0px).
- **Background:** report-card / graphite-card in the app; paper on the site's example entry.
- **Shadow Strategy:** none (see Elevation & Depth).
- **Border:** 1px line grey (app) or 1px ink (site), with a rule under the catalogue head.
- **Internal Padding:** 0 16px 14px in the app; 24px 28px 28px for the site entry body.
- **Inside:** title, fact, a "Why?" disclosure (underlined summary), then a ruled "How to fix it in Ableton" block with numbered steps and the autofix button.

### Zone sleeve (signature)
Six full-bleed buttons stacked as horizontal bands, air at the top and sub at the bottom, each holding a label (zone name + Hz range) and the culprit track, which shows on hover or when selected. Picking a band frames it in ink and swaps the hero headline for that zone's finding (a 0.28s fade-and-rise on `cubic-bezier(.2,.7,0,1)`; band heights ease over 0.4s). All motion is removed under `prefers-reduced-motion`.

### Tonal-balance spectrum
An SVG on the card background with a 1px line border, log-frequency axis with hairline grid lines at 30 / 60 / 250 / 500 / 2k / 6k / 16k Hz, a 10%-ink tolerance band, and one bar per sixth-octave band from the 0 dB axis, filled with the colour of its zone.

### Navigation
A single row above a 1px ink rule: logo mark (28px) + "MixCoach" in 700 at 19px + the catalogue mark `MXC 001` after a hairline divider, then label-type links (underlined on hover) and the language toggle. Under 620px the secondary links and the catalogue mark are hidden.

### Tables (panel, report)
Full width, card background, 1px line border and row rules, tabular figures, muted 500-weight headers, start-aligned cells.

## Do's and Don'ts

### Do:
- **Do** keep the ground silver (site), report silver (report) or graphite (panel), with ink text and 1px ink rules.
- **Do** use the six zone colours only for frequency-zone data, with ink text on them (white on Sub Ultramarine).
- **Do** give every finding a catalogue head: two-digit number continuous across the surface, the translated severity word, and the Hz zone chip.
- **Do** show "problem" and "warning" as solid ink labels and "info" / "ok" as muted unfilled text.
- **Do** show hover, focus and selection as ink/ground inversions or ink frames (6px inset on bands, 3px outline on the site).
- **Do** use Archivo on the site only, and the system Helvetica Neue stack in the panel and report.
- **Do** use logical properties so every layout mirrors for Arabic.

### Don't:
- **Don't** use a zone colour for a button, link, hover, focus ring or severity.
- **Don't** add gradients, glow, blur, drop shadows or rounded corners.
- **Don't** build a grid of icon cards or a glowing dark product screenshot hero.
- **Don't** load network fonts or assets in the panel; it runs offline inside Max's jweb.
- **Don't** put a tracked label above a headline as an eyebrow; labels name or number the thing they belong to.
