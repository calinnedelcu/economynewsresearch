# Paper sources

Canonical LaTeX sources, figures, tables, and compiled PDFs for:

> Nedelcu, A. C., and Cheroiu, A. (2026). *Unexpected Online Financial
> News and Intraday Market Reactions: An Event-Study of EUR/USD and
> Nasdaq-100 Prices.*

For the repository overview, reproduction instructions, and key
findings, see the top-level [`README.md`](../README.md).

## Contents

- `main.tex` — main paper master file
- `main.pdf` — compiled main paper
- `online_appendix.tex` / `online_appendix.pdf` — online appendix
- `references.bib` — BibTeX bibliography
- `sections/` — per-section sources included by `main.tex`
- `tables/` — auto-generated `.tex` tables (output of `make_tables.py`)
- `figures/` — `.png` and `.pdf` figures (output of `make_figures.py`)
- `main.aux`, `main.bbl`, `main.log`, `main.out` — LaTeX build artefacts

## Sections

| File | Section |
|---|---|
| `sections/abstract.tex` | Abstract |
| `sections/section_1_introduction.tex` | Introduction |
| `sections/section_2_literature_review.tex` | Literature review |
| `sections/section_2b_hypothesis_development.tex` | Hypothesis development |
| `sections/section_3_data.tex` | Data |
| `sections/section_4_methodology.tex` | Methodology |
| `sections/section_5_results.tex` | Results |
| `sections/section_6_discussion.tex` | Discussion |
| `sections/section_7_limitations.tex` | Limitations |
| `sections/section_8_conclusion.tex` | Conclusion |
| `sections/online_appendix.tex` | Appendix master |
| `sections/acknowledgments.tex` | Acknowledgments |
| `sections/data_availability.tex` | Data availability statement |
| `sections/reproducibility.tex` | Reproducibility statement |

## Tables

All tables are generated from `outputs/` by [`make_tables.py`](../make_tables.py).
Re-run when underlying results change:

```bash
.venv/Scripts/python.exe make_tables.py
```

## Figures

All figures are generated from `outputs/` by [`make_figures.py`](../make_figures.py).
Both `.png` (for `\includegraphics` in screen rendering) and `.pdf`
(for print) variants are produced.

```bash
.venv/Scripts/python.exe make_figures.py
```

## Compiling

The paper uses standard `pdflatex` + `bibtex`. From this directory:

```bash
pdflatex main.tex
bibtex main
pdflatex main.tex
pdflatex main.tex
```

Or use the top-level `make all-paper` target.
