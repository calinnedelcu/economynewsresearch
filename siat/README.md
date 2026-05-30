# SIAT 2026 condensed version

This directory contains a condensed Romanian-audience version of the
paper, prepared for the **Concursul Joseph Schumpeter — Inovația și
Antreprenoriatul Tinerilor (SIAT) 2026** high-school economics
competition. It is **not** part of the canonical academic paper. See
the parent [`README.md`](../README.md) and [`paper/`](../paper/) for
the full work.

## Why a separate version

The SIAT regulation requires a short Word document with a 2,100-word
budget, A4 / Times New Roman 12 / 1.5 line spacing formatting, and
specific section headers (Abstract, Introducere, Conținut științific,
Concluzii, Referințe bibliografice). The canonical paper is ~38 pages
of LaTeX, so a compressed adaptation was needed.

The SIAT version covers the two headline questions (magnitude,
direction) plus three auxiliary findings (pre-event drift, cross-asset
disagreement, PhraseBank validation). The remaining hypotheses tested
in the main paper — H3, H4, H9, H11 and the C1–C7 robustness
extensions — are omitted for length, not because they are
uninformative.

## Files

| File | Purpose |
|---|---|
| `Nedelcu_Andrei-Calin_Unexpected_Online_Financial_News_Intraday_Market_Reactions.docx` | The canonical SIAT submission. **Source of truth** for the competition version. |
| `build_siat_docx.py` | Initial generator that produced the first draft of the .docx using only the Python standard library (no python-docx). The current `.docx` has been hand-edited beyond what this script produces and the script has not been kept in sync. |
| `apply_edits.py` | One-shot script (run once) that applied the final round of edits on top of the generator output: inline citations, identification assumption, magnitude-ratio formula, and table column widths. |
| `poster_brief_prompt.md` | Design brief for the accompanying poster (.pdf), used as a prompt for Canva/PowerPoint/AI design tools. |

If you need to regenerate the `.docx` from scratch, start from
`build_siat_docx.py` and re-apply the edits in `apply_edits.py`, or
treat the existing `.docx` as the source and edit it directly.

## Submission

Per the competition regulation:

- **Paper**: emailed as `.docx` to `cristina.vasile@lbi.ro` during the
  04 – 24 May 2026 submission window. Filename:
  `Nedelcu_Andrei-Calin_Unexpected_Online_Financial_News_Intraday_Market_Reactions.docx`.
- **Poster**: PDF brought on the day of presentation (29 May 2026),
  16:9 landscape, designed for screen / projector display.
- **Presentation**: 15-minute oral defense in front of the jury.
