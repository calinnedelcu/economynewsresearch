# Unexpected Online Financial News and Intraday Market Reactions

An event-study of EUR/USD and Nasdaq-100 prices using LLM-labelled
FinancialJuice headlines.

**Authors:** Andrei Calin Nedelcu, Andrei Cheroiu

**Paper:** [`paper/main.pdf`](paper/main.pdf) · **Online Appendix:** [`paper/online_appendix.pdf`](paper/online_appendix.pdf)

---

## Abstract

We study the intraday response of EUR/USD and the Nasdaq-100 index to
**2,449 unscheduled news events** from a public real-time newsfeed
over a thirteen-month sample (24 March 2025 – 5 May 2026). Each event
is independently labelled by a large language model and benchmarked
against the Loughran-McDonald dictionary and FinBERT-tone. Using a
matched, hour-of-day and day-of-week stratified baseline with
cluster-robust standard errors and uniform Benjamini-Hochberg false
discovery rate adjustment, we find that news events are associated
with intraday magnitude **1.3× to 1.9×** the baseline level on every
asset-window cell. The directional content of LLM sentiment is modest
(**49–54% hit rate**) and likely too small to overcome typical
intraday transaction costs, but the LLM outperforms the dictionary
baseline by about 1–6 percentage points, is competitive with FinBERT
across primary windows, and produces asset-specific sentiment on
**73.5% of events**. On the Financial PhraseBank external benchmark,
the LLM attains **84.6% accuracy and Cohen's κ = 0.72** against gold
human labels, outperforming FinBERT by 5.4 percentage points. The
pre-event absolute return matches the post-event return in magnitude,
indicating that the public headline timestamp is not the informational
event time.

## Key findings

1. **Magnitude is robust.** Event-window absolute returns are 1.4×–1.8×
   the matched non-event baseline on both assets across 5, 15, and 60
   minute windows. Range and maximum-move measures fall in the same
   band. All ratios survive Benjamini-Hochberg FDR correction.
2. **Direction is modest.** The LLM achieves 49%–54% directional hit
   rates, beating the Loughran-McDonald dictionary by 1–6 pp and
   competitive with FinBERT-tone, but not large enough for a
   standalone trading rule.
3. **Pre-event drift is the central methodological finding.** The
   fifteen minutes *before* the public Discord timestamp already
   contain abnormal movement of the same order as the post-event
   window, consistent with feed latency between primary sources and
   the public repost. Online-news event studies should report
   pre-event drift as a diagnostic.
4. **External validation.** On Financial PhraseBank (4,840 sentences
   labelled by 16 finance professionals), the LLM achieves 84.6%
   accuracy and Cohen's κ = 0.72, materially above FinBERT (79.2%, κ =
   0.60) and Loughran-McDonald (57.4%, κ = 0.22).

## Repository structure

```text
paper/                        canonical LaTeX sources, compiled PDFs, figures, tables
  main.tex / main.pdf         main paper
  online_appendix.tex/pdf     online appendix
  sections/                   per-section .tex files
  tables/                     auto-generated .tex tables
  figures/                    .png / .pdf figures used in paper

event_study.py                event-study core: H1–H14, cluster tests, z-scores, FDR q-values
sentiment.py                  DeepSeek-compatible LLM classifier with SQLite cache
sentiment_baseline.py         Loughran-McDonald dictionary baseline
sentiment_finbert.py          FinBERT-tone neural baseline
sentiment_external_benchmark.py  Financial PhraseBank validation
sentiment_baseline_compare.py    LLM vs baselines on event sample
sentiment_subsample_analysis.py  pre/post training-cutoff stability
parse_fj_discord.py           DiscordChatExporter JSON → outputs/events.csv
download_prices.py            Dukascopy EUR/USD + Nasdaq-100 1m → outputs/prices_*.csv
cluster_gap_robustness.py     varying cluster gap threshold
make_figures.py               regenerate paper figures from outputs/
make_tables.py                regenerate paper tables from outputs/
validate_outputs.py           sanity checks for methodology-sensitive outputs
Makefile                      convenience targets

outputs/                      generated CSVs, figures, cache (gitignored)
data/                         raw JSON exports (gitignored)
docs/history/                 process notes from earlier development phases
siat/                         condensed version for SIAT 2026 competition (see below)
```

## Reproduction

Setup:

```bash
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt
```

Sentiment classification requires a DeepSeek-compatible API key in `.env`:

```text
DEEPSEEK_API_KEY=sk-...
```

Run the pipeline end to end:

```bash
# 1. Parse Discord export → events
.venv/Scripts/python.exe parse_fj_discord.py "data/FinancialJuice ... .json" -o outputs/events.csv --summary

# 2. Download intraday prices
.venv/Scripts/python.exe download_prices.py --start 2025-03-24 --merge-existing

# 3. LLM sentiment with SQLite cache
.venv/Scripts/python.exe sentiment.py outputs/events.csv -o outputs/events_sentiment.csv --workers 15

# 4. Event-study core
.venv/Scripts/python.exe event_study.py

# 5. Validate methodology-sensitive outputs
.venv/Scripts/python.exe validate_outputs.py
```

Shortcuts (if `make` is available):

```bash
make validate
make all-paper
```

Expected validator output:

```text
OK: outputs passed methodology sanity checks
```

## Pipeline outputs

Main per-hypothesis result files in [`outputs/`](outputs/):

| File | Content |
|---|---|
| `events.csv` | parsed messages |
| `events_sentiment.csv` | gold events with LLM sentiment |
| `event_study_windows.csv` | event × asset × window panel |
| `cluster_event_study_windows.csv` | cluster × asset × window panel |
| `h1_results.csv` … `h14_results.csv` | per-hypothesis test results |
| `cluster_sentiment_results.csv` | direction on cluster-aggregated sentiment |
| `range_outcomes_results.csv` | range and max-move vs baseline |
| `abnormal_z_results.csv` | standardised abnormal z-scores |
| `targeted_category_results.csv` | category-targeted hypotheses |
| `pre_post_stability_results.csv` | stability before/after `2026-01-15` |
| `multivariate_results.csv` | multivariate regressions with controls |
| `outlier_robustness_results.csv` | 1% winsorisation robustness |
| `h4_periods.csv` | closed-period definitions used for H4 |
| `methodology_summary.csv` | effective methodology settings |

## Pipeline diagnostics

Status per main hypothesis after the methodology corrections (see
[`docs/history/STATUS.md`](docs/history/STATUS.md) for the audit
trail):

| H | Verdict | Short interpretation |
|---|---|---|
| H1 | robust | Events have above-baseline absolute moves on both assets, all windows. |
| H2 | modest / mixed | Small directional edge; after FDR only a restricted subset remains. |
| H3 | partial | Sentiment × trend interaction relevant mainly on NDX +5m / +15m. |
| H4 | partial | NDX closed-period gap has signal; EUR/USD marginal. |
| H5 | weak / partial | `expected_magnitude` helps narrowly, mostly NDX +1m. |
| H6 | weak | `confidence` is overconfident; not a calibrated probability. |
| H7 | partial | Categories matter modestly for EUR/USD, less clear for NDX. |
| H8 | robust, with caveat | Pre-event drift > baseline; may reflect feed lag rather than front-running. |
| H9 | robust | Sign tends to persist between +15m and +4h. |
| H10 | proxy evidence | Proxy/tick volume rises around events; not consolidated volume. |
| H11 | partial | Time-of-day matters for EUR/USD; weaker on NDX after clustering. |
| H12 | weak | Bear vs bull asymmetry small. |
| H13 | weak / partial | `surprise_level` helps mainly on NDX short windows. |
| H14 | robust, careful framing | EUR/USD vs NDX is negative; USD proxy vs NDX is positive by sign convention. |

Robustness extensions reported in the paper:

| Extension | Verdict | Note |
|---|---|---|
| Cluster sentiment | partial | Cluster aggregation slightly improves NDX +5m/+15m direction. |
| Range / max-move | very robust | Strongest new result alongside H1. |
| Abnormal z-scores | robust | Standardised abnormal movement positive on close-to-close, range, max-move. |
| Targeted categories | reportable | Central bank, geopolitical, politics, energy, corporate report separately. |
| Pre/post training cutoff | robust | Max-move effect remains positive after `2026-01-15`. |
| Multivariate controls | important | Signal survives category, surprise, length, cluster-size controls. |
| Outlier robustness | robust | 1% winsorisation does not remove the main signal. |

## Citation

See [`CITATION.cff`](CITATION.cff). Brief form:

> Nedelcu, A. C., and Cheroiu, A. (2026). Unexpected Online Financial
> News and Intraday Market Reactions: An Event-Study of EUR/USD and
> Nasdaq-100 Prices.

## Other artifacts

A condensed Romanian-audience version of the paper was prepared for
the **SIAT 2026 high-school economics competition** (Joseph Schumpeter
— Innovation and Youth Entrepreneurship). It lives in
[`siat/`](siat/) and is not part of the canonical academic paper —
see [`siat/README.md`](siat/README.md) for context.

Historical planning and audit notes from earlier development phases
are archived under [`docs/history/`](docs/history/) and are not
canonical paper sources.
