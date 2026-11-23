# Reports

| File | Submission | Covers |
|---|---|---|
| `Scope_Document.pdf`, `scope.tex` | Scope document | Problem statement, scope and deliverables |
| `stage2.tex` | Stage 2 (PDF) | Design approach, tools, implementation status, scope changes, pending tasks. Results: P0 (reference), steady calibration (P1-1 steady part), P1-3, P2-1 to P2-4 |
| `stage3.tex` | Stage 3 (PDF) | Transient calibration (P1-1 transient part, P1-2), P3-1 to P3-4, extended validation (EV), P4-1 to P4-3; verification approach, plan vs deviation, learnings, future scope |
| `stage4.tex` | Stage 4 (final report) | Summary of the whole project: models, results, validation on 500 (steady) and 100 (transient) generated floorplans, robustness, `ltp` tool, presentation feedback, how to run. |

The final presentation is in `../presentations/`.

Every file has an LLM disclosure section. Anything marked in red `[TODO: ...]` must be filled in
before submission: the exact LLM use, the presentation feedback, and the re-measured timings.

## Compiling

The figures are read from `../experiments/*/results/`, so compile from inside `reports/` in a
full checkout of the repository:

```
cd reports
pdflatex stage2.tex && pdflatex stage2.tex     # twice, for references / contents
```

On Overleaf, upload the repository (at least `reports/` and `experiments/`) and set the main file.
All reports use figures from `experiments/extended_validation/`, so include it too.
The stage 2 report also uses the `*_stage2.png` figures made by the `plot_stage2.py` scripts in
P1-1, P1-3 and P2-1.
