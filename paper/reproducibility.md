# Reproducibility Statement

All numerical results in this paper can be reproduced from the public
project repository using the commands and the seed reported below.

## Code, data, and environment

The repository is organised around eight pipeline scripts plus
auxiliary tools. Production runs use Python 3.13 in an isolated virtual
environment with the dependencies pinned in `requirements.txt`. The
event-study core uses `pandas`, `numpy`, `scipy`, `statsmodels`, and
`matplotlib`; the LLM sentiment step uses the `openai` Python client
against a DeepSeek API endpoint; and the dictionary baseline uses
`pysentiment2` [@pysentiment2], which bundles the Loughran-McDonald
master dictionary [@loughran2011liability].

Raw price data are downloaded via `dukascopy-python` (one-minute
OHLCV bars for EUR/USD and the `E_NQ-100` CFD). Raw news data are
exported via DiscordChatExporter from the publicly accessible
FinancialJuice newsfeed channel and stored as a single JSON archive
under `data/`. Neither input file is committed to the repository; both
are reproducible from the underlying public sources.

## Random seeds

All stochastic procedures (matched baseline sampling, bootstrap
resampling, train/test splits used in robustness checks) are seeded
with `SEED = 42` in `event_study.py`. Re-running the pipeline with the
same code, same input data, and the same seed reproduces every
numerical value reported in Section 5 to the full precision of the
output CSVs.

## End-to-end reproduction

The full pipeline is reproduced by the following sequence of
commands. Steps 1-3 download or generate the inputs; steps 4-6 produce
the analysis outputs.

```bash
# 1. Parse the Discord export into the gold event list.
python parse_fj_discord.py "data/FinancialJuice ... .json" \
    -o outputs/events.csv --summary

# 2. Download or refresh the 1-minute price panels.
python download_prices.py --start 2025-03-24 --merge-existing

# 3. Classify each gold event with the LLM (cached in SQLite).
python sentiment.py outputs/events.csv \
    -o outputs/events_sentiment.csv --workers 15

# 4. Run the event-study pipeline (H1-H14, C1-C7).
python event_study.py

# 5. Validate methodology-sensitive outputs.
python validate_outputs.py
# Expected output: "OK: outputs passed methodology sanity checks"

# 6. Generate the HTML report.
python make_report.py --also-copy docs/report.html

# 7. Run the Loughran-McDonald dictionary baseline.
python sentiment_baseline.py outputs/events_sentiment.csv \
    -o outputs/events_sentiment_baseline.csv

# 8. Run the FinBERT-tone neural baseline (first run downloads the
#    yiyanghkust/finbert-tone model, ~440 MB, into HuggingFace cache).
python sentiment_finbert.py outputs/events_sentiment.csv \
    -o outputs/events_sentiment_finbert.csv

# 9. Three-way comparison: LLM vs LM vs FinBERT.
python sentiment_baseline_compare.py
```

The manual-validation subsample for the sentiment audit is generated
by `prepare_manual_validation.py` and scored, once the two-annotator
labels are filled in, by `score_manual_validation.py`.

## Validation harness

`validate_outputs.py` runs deterministic sanity checks on the
generated outputs: it verifies that the event/baseline magnitude ratio
in `h1_results.csv` is between 1.0 and 5.0; that the H2 hit-rate
column is in $[0, 1]$; that `methodology_summary.csv` reports the
expected target conventions; and that the cluster-level outputs are
non-empty. A pipeline run with code changes that breaks any of these
invariants will fail this check before any results are reported.

## Pre-specification

The fourteen pre-specified hypotheses H1-H14 are defined in
`event_study.py` and were fixed before any cleanup of the result
tables. The extensions C1-C7 were added during methodological
revision, as documented in `STATUS.md`; C8 was added as an exploratory
analysis and is reported in Limitations rather than as a main result.
Robust standard errors, cluster-robust standard errors, and the
Benjamini-Hochberg false discovery rate adjustment
[@benjamini1995controlling] are applied uniformly to every test
output and are not chosen post hoc per hypothesis.

## Repository

The complete source for the analysis and this paper draft is
maintained as a git repository. Each subsection in Section 5
corresponds to a CSV file in `outputs/`; readers seeking to audit a
specific number reported in the text can locate the underlying row by
the variable name conventions described in `validate_outputs.py`.
