# Presentations

Beamer slides for the final presentation of TapSense (Lightweight Temperature Predictor).
Spell the name "TapSense" in slide text (footer included), never "TapaSense".
The current deck is `presentation.tex` (about 25 slides, a 10-12 minute talk).

## Sources: only the reports

- Every topic on a slide must be one the reports explain. If a topic is not explained in a
  report, it does not go on a slide, even if an experiment for it exists in `experiments/`.
- Sources:
  1. `reports/stage2.tex`: data, reference checks, S0, S1, S2 (low rank), calibration-free
     methods, hot spots (S1-hot-max).
  2. `reports/stage3_v5.tex` (the final Stage 3 report): T1, T2 ARX, T3, trade-offs, the 52
     generated floorplans, robustness, leakage.
  3. Stage 4: only the `ltp` tool. Every other topic must come from Stage 2 or Stage 3.
- Where Stage 3 v5 and older versions differ, follow v5 (for example: no task migration,
  default leakage only, ARX not described as unstable).
- Out of scope (only in the Stage 4 working copy): proactive DTM, forecasting, T4 (reduced
  HotSpot network), S2 with k nearest cores, candidate cells / "one fixed hottest cell",
  calibration-time target.
- Proactive DTM is explicitly excluded. DTM may appear only as the motivation (why fast
  temperatures are needed).
- Copy numbers exactly from the reports. Do not compute new numbers or draw new conclusions.
  If a slide needs a number the reports do not give, ask the user.
- Figures from `experiments/*/results/` are fine even if no report uses them, as long as they
  show a topic the reports explain.

## Professor's format (strict)

- 10 minutes + 5 minutes Q&A. No conceptual background unless needed.
- At most 7 minutes on what we did and the results.
- Last 3 minutes: novelty, lines of code, each member's contribution, verification approach and
  number of test cases, key learnings, major challenges, limitations.

## Story

1. Main part 1 (about 7 min): problem, HotSpot is linear, two stages, models we
   tried, S1 ("is calibration needed" is a backup slide, `b-calib`, linked from S1), S1 against HotSpot, hot spots (S1-hot-max), step responses,
   T3 with a T1/T2/T3 table, unseen floorplans, `ltp` with demo output, results against targets.
   Main ideas only; details go to backup.
2. Main part 2 (about 3 min, 3 slides): "Contributions and team" (contributions + lines of
   code per member), "Verification", "Learnings, challenges and limitations" (three blocks plus
   the heavy-AI-usage note). Then "Thank you".
3. Backup slides after "Thank you" (`\appendix`, numbered separately): an index slide with links,
   then one slide per model or study (S0, S2, hot spots, leakage, T1, T2, T3, choosing M, test
   trace, robustness). Main slides link to them with small "more" buttons (`\backup{label}{text}`).
- Lines of code: keep it minimal. Count only code lines (no blanks, comments or docstrings) of
  the main experiments and the tool; no plot scripts, demos, tests, setup or out-of-scope
  experiments. The slide shows only Ethan and Kaivalya with their counts: no "Both" block, no
  total, no explanatory note. Split by topic: steady state is Ethan, transient is Kaivalya.
  Ethan (~1,350): src/sim hotspot, parallel, stepper, gridmap, floorplans, powergen, datasets,
  tagen, experiments/common.py, added lines of setup/ltp.patch, P0-2, P1-3, P2-1, P2-3, P4-2,
  P4-3. Kaivalya (~1,300): flpgen + P0-5d, P1-1, P1-2, P3-1, P3-3, extended_validation/run.py,
  P4-1, src/ltp.
- Unseen-floorplan results live on the Verification slide (table: floorplans and power vectors
  per floorplan, steady and transient); there is no separate "chips we never saw" slide.
  The slide is only that table plus a crop of P0-5d examples.png (generated floorplans). Rows:
  Steady S1 24 given (302) and 500 generated (15, from extended_validation_s1/results_500, an
  approved exception to the reports-only rule); Transient T3 24 given and 52 generated (2,000).
  No calibration-free, S1-hot-max, T3 results or other text.
- The `ltp` slide holds only "Demo of the ltp package" and a link to the user's Google Drive
  video (no image, no embedded video). Stills from it
  (`figures/ltp_demo_*.png`, black bars cropped) are on four backup slides (label `b-demo`) in
  case the video does not play.
- Limitations slide ends with an "AI usage" block, worded from the reports' LLM disclosure.
- Transient time/size targets reuse the Stage 2 targets (20 us, 5 kB).
- T2 backup: no "long trace" wording; results are "on a test trace".
- No "128x128" in captions: call it the HotSpot grid. Main slides show the formula of each
  kept model (S1 as G_ij, S1-hot-max, T3). Keep formulas simple: no complex ones (the S0
  kernel formula was removed on request).
- Wording the user asked for: "one HotSpot run per core" (never "8 runs"); "T2: fitted to one
  trace" (not "ARX" in main slides); HotSpot introduced as a chip thermal simulator; no
  "response time(s)" phrasing; tau_m are "time constants".
- Challenge slide: HotSpot precision patch, and caching HotSpot's matrix factorisation (29x
  faster, Stage 3 v4 learnings). No 60 s trace / 4 h story.
- Edits are crisp: short lines, no extra wording.

Keep the slides consistent with each other: the same model names (S0, S1, T1, T2, T3), units and
numbers everywhere.

## Style

- Standard Beamer: `\usetheme{Madrid}`, orange structure colour `#E8710A`, alerts `#C2570C`,
  16:9, 14 pt. Use standard elements only (blocks, booktabs tables, itemize, figures). No custom
  "big number" macros or other homemade layouts.
- Minimal: one figure or table per slide plus 2-4 short lines. Big fonts, nothing crowded. Use only
  what is needed to explain the point.
- Plain wording. No em dashes (`---`). Use `--` only for number ranges (`0.06--0.09\,K`).
  Avoid wording that sounds machine-written.
- Mark the chosen model in tables with bold.
- Logo (`figures/`): `tapasense_lockup.png` (icon + "तापSense") on the title and thank-you
  slides; `tapasense_icon_white.png` in the top-right of every frame title bar. Backgrounds are
  transparent, cut from the originals `tapasense_logo_original.png` and
  `tapasense_logo_sheet_original.png`. `tapasense_icon.png` (colour) and
  `tapasense_icon_mono.png` (dark) are spares.

## Building and checking

- MiKTeX's `pdflatex.exe` on this machine is a 0-byte file and does not run. Use LuaLaTeX:
  `/c/Users/ethan/AppData/Local/Programs/MiKTeX/miktex/bin/x64/lualatex.exe -interaction=nonstopmode presentation.tex`
  Run it twice (for the outline). Run it from this folder: figures are found through
  `\graphicspath{{../experiments/}}`.
- After every change, check `presentation.log` for `^!` errors and `Overfull` boxes, and render the
  pages (`pdftoppm -r 80 -png presentation.pdf <scratch dir>/p`) to look at them. Text running off a
  slide or into the footer must be fixed.
- Edit the `.tex` with exact-string edits. Python heredoc replacements failed here on
  backslash-heavy LaTeX strings.
- Do not touch `reports/`; other people edit it. The older 15-minute deck `reports/archive/slides.tex`
  is kept as it is.
- Do not commit unless the user asks.
