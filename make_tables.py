#!/usr/bin/env python3
"""Generate publication-quality LaTeX tables from analysis CSVs.

Reads CSV outputs under outputs/ and writes booktabs-formatted .tex
inserts under paper/tables/. Each table mirrors a result reported in
Section 5 of the paper, with consistent formatting:

  * three-line booktabs rule structure (\\toprule, \\midrule, \\bottomrule)
  * t/q-values typeset with significance stars
  * sample sizes formatted with thousand separators
  * caption above, tablenotes below in threeparttable

Run:
    python make_tables.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

OUTPUTS = Path("outputs")
TABLES = Path("paper/tables")
TABLES.mkdir(parents=True, exist_ok=True)

PRIMARY_WINDOWS = [5, 15, 60]
ALL_WINDOWS = [1, 5, 15, 60, 240]


def fmt_num(x, digits=4):
    if pd.isna(x) or not np.isfinite(x):
        return "--"
    return f"{x:.{digits}f}"


def fmt_int(x):
    if pd.isna(x):
        return "--"
    return f"{int(x):,}"


def fmt_pval(p):
    """Format a p-value with scientific notation for very small values."""
    if pd.isna(p) or not np.isfinite(p):
        return "--"
    if p < 1e-15:
        return r"${<}10^{-15}$"
    if p < 1e-4:
        exp = int(np.floor(np.log10(p)))
        mantissa = p / 10 ** exp
        return f"${mantissa:.1f}\\!\\times\\!10^{{{exp}}}$"
    if p < 0.001:
        return f"{p:.4f}"
    return f"{p:.3f}"


def sig_stars(p):
    if pd.isna(p):
        return ""
    if p < 0.01:
        return r"$^{***}$"
    if p < 0.05:
        return r"$^{**}$"
    if p < 0.10:
        return r"$^{*}$"
    return ""


def write_table(name: str, content: str):
    out = TABLES / f"{name}.tex"
    out.write_text(content, encoding="utf-8")
    print(f"  wrote {out} ({len(content)} chars)")


# ---------------------------------------------------------------------------
# T2: Variable definitions (hand-coded, not from CSV)
# ---------------------------------------------------------------------------


def table_2_variable_definitions():
    body = r"""
\begin{table}[!htbp]
\centering
\caption{Variable definitions.}
\label{tab:var-defs}
\begin{threeparttable}
\small
\begin{tabularx}{\textwidth}{lXl}
\toprule
\textbf{Variable} & \textbf{Definition} & \textbf{Unit} \\
\midrule
$r^{\text{price}}_{i,a,W}$ & Close-to-close percentage return of asset $a$ over the $W$-minute post-event window starting at $\lceil t_i \rceil_{1\text{m}}$. & \% \\[2pt]
$r^{\text{target}}_{i,a,W}$ & Target-aligned return. Equal to $r^{\text{price}}$ for NDX; equal to $-r^{\text{price}}$ for EUR/USD (USD proxy convention). & \% \\[2pt]
$\text{range}_{i,a,W}$ & Intra-window high minus low, expressed as a percentage of the open price. & \% \\[2pt]
$\text{maxabs}_{i,a,W}$ & Maximum of the absolute upward and downward intra-window excursions, as a percentage of open. & \% \\[2pt]
$z_{i,a,W}$ & Standardised abnormal score: outcome minus matched-baseline mean, divided by matched-baseline standard deviation. & dimensionless \\[2pt]
\texttt{sentiment\_usd} & LLM-derived discrete USD sentiment $\in$ \{bull, bear, neutral\}. & categorical \\[2pt]
\texttt{sentiment\_ndx} & LLM-derived discrete NDX sentiment. Independent of \texttt{sentiment\_usd}. & categorical \\[2pt]
\texttt{sentiment\_lm} & Loughran-McDonald dictionary sentiment thresholded at $|\text{polarity}| \geq 0.1$. & categorical \\[2pt]
\texttt{sentiment\_finbert} & FinBERT-tone argmax label remapped to \{bull, bear, neutral\}. & categorical \\[2pt]
\texttt{category} & Hand-coded event category from \{macro\_release, central\_bank, geopolitical, politics, energy, corporate, other\}. & categorical \\[2pt]
\texttt{event\_cluster\_id} & Integer identifier grouping events separated by no more than 15 minutes. & integer \\[2pt]
\texttt{event\_cluster\_size} & Number of headlines in the cluster containing event $i$. & integer \\[2pt]
\texttt{is\_in\_closed\_period} & Boolean: event timestamp falls within a market-closed gap. Diverts to H4 instead of intraday windows. & boolean \\[2pt]
$\mu^{\text{base}}_{a,W,h,d}$ & Matched-baseline mean for asset $a$, window $W$, hour-of-day $h$, day-of-week $d$, sampled from non-event windows with $\pm 60$-minute event exclusion buffer. & varies \\[2pt]
$q$-value & Benjamini-Hochberg false discovery rate adjustment applied across the union of all reported $p$-values. & probability \\
\bottomrule
\end{tabularx}
\begin{tablenotes}
\footnotesize
\item \textit{Notes.} Variable conventions used throughout
Sections~\ref{sec:methodology} and~\ref{sec:results}. All
timestamps are UTC. Window lengths $W$ are in minutes; primary
windows are $W \in \{5, 15, 60\}$.
\end{tablenotes}
\end{threeparttable}
\end{table}
""".strip() + "\n"
    write_table("table_2_variable_definitions", body)


# ---------------------------------------------------------------------------
# T3: Descriptive statistics for key variables
# ---------------------------------------------------------------------------


def table_3_descriptive_stats():
    events = pd.read_csv(OUTPUTS / "events_sentiment.csv")
    windows = pd.read_csv(OUTPUTS / "event_study_windows.csv")

    # Numeric LLM features per event
    rows = []

    def stats(series, label, unit=""):
        s = pd.to_numeric(series, errors="coerce").dropna()
        if len(s) == 0:
            return None
        return {
            "label": label,
            "unit": unit,
            "n": len(s),
            "mean": s.mean(),
            "sd": s.std(),
            "min": s.min(),
            "p25": s.quantile(0.25),
            "median": s.median(),
            "p75": s.quantile(0.75),
            "max": s.max(),
        }

    rows.append(stats(events["directional_strength_usd"], r"\texttt{directional\_strength\_usd}", "[-1, +1]"))
    rows.append(stats(events["directional_strength_ndx"], r"\texttt{directional\_strength\_ndx}", "[-1, +1]"))
    rows.append(stats(events["confidence"], r"\texttt{confidence}", "[0, 1]"))
    rows.append(stats(events["event_cluster_size"] if "event_cluster_size" in events.columns else pd.Series(dtype=float), r"\texttt{event\_cluster\_size}", "count"))

    # Window-level outcomes for the 5/15/60 primary windows, both assets
    for asset in ["eurusd", "ndx"]:
        for w in PRIMARY_WINDOWS:
            sub = windows[(windows["asset"] == asset) & (windows["window_min"] == w)]
            rows.append(stats(sub["delta_pct"].abs(), f"$|r|$ {asset} +{w}m", r"\%"))
            rows.append(stats(sub["range_pct"], f"range {asset} +{w}m", r"\%"))

    rows = [r for r in rows if r is not None]

    header = (
        r"\begin{table}[!htbp]" + "\n"
        r"\centering" + "\n"
        r"\caption{Descriptive statistics for key variables.}" + "\n"
        r"\label{tab:desc-stats}" + "\n"
        r"\begin{threeparttable}" + "\n"
        r"\small" + "\n"
        r"\begin{tabular}{lcrrrrrrr}" + "\n"
        r"\toprule" + "\n"
        r"\textbf{Variable} & \textbf{Unit} & \textbf{$N$} & \textbf{Mean} & \textbf{SD} & \textbf{Min} & \textbf{p25} & \textbf{Median} & \textbf{p75} \\" + "\n"
        r"\midrule" + "\n"
    )
    lines = []
    for r in rows:
        lines.append(
            f"{r['label']} & {r['unit']} & {fmt_int(r['n'])} & "
            f"{fmt_num(r['mean'])} & {fmt_num(r['sd'])} & "
            f"{fmt_num(r['min'])} & {fmt_num(r['p25'])} & "
            f"{fmt_num(r['median'])} & {fmt_num(r['p75'])} \\\\"
        )

    footer = (
        r"\bottomrule" + "\n"
        r"\end{tabular}" + "\n"
        r"\begin{tablenotes}" + "\n"
        r"\footnotesize" + "\n"
        r"\item \textit{Notes.} Descriptive statistics for the LLM-derived" + "\n"
        r"event-level features (top rows) and for the event-window" + "\n"
        r"absolute return and intra-window range at the primary 5/15/60-minute" + "\n"
        r"horizons (lower rows). $N$ counts non-missing observations." + "\n"
        r"\end{tablenotes}" + "\n"
        r"\end{threeparttable}" + "\n"
        r"\end{table}" + "\n"
    )
    write_table("table_3_descriptive_stats", header + "\n".join(lines) + "\n" + footer)


# ---------------------------------------------------------------------------
# T4: Sentiment distribution + pairwise agreement
# ---------------------------------------------------------------------------


def table_4_sentiment_distribution():
    llm = pd.read_csv(OUTPUTS / "events_sentiment.csv")
    lm_path = OUTPUTS / "events_sentiment_baseline.csv"
    fb_path = OUTPUTS / "events_sentiment_finbert.csv"
    n = len(llm)

    def dist(s):
        v = s.value_counts()
        return {
            "bull": int(v.get("bull", 0)),
            "bear": int(v.get("bear", 0)),
            "neutral": int(v.get("neutral", 0)),
        }

    rows = []
    rows.append(("LLM (USD)", dist(llm["sentiment_usd"])))
    rows.append(("LLM (NDX)", dist(llm["sentiment_ndx"])))

    if lm_path.exists():
        lm = pd.read_csv(lm_path)
        rows.append(("Loughran-McDonald", dist(lm["sentiment_usd_lm"])))
    if fb_path.exists():
        fb = pd.read_csv(fb_path)
        rows.append(("FinBERT-tone", dist(fb["sentiment_usd_finbert"])))

    # Pairwise agreement matrix on USD label
    agree_pairs = []
    base = llm[["id", "sentiment_usd", "sentiment_ndx"]].rename(
        columns={"sentiment_usd": "llm_usd", "sentiment_ndx": "llm_ndx"})
    if lm_path.exists():
        lm = pd.read_csv(lm_path)[["id", "sentiment_usd_lm"]]
        m = base.merge(lm, on="id")
        agree_pairs.append(("LLM USD vs LM", (m["llm_usd"] == m["sentiment_usd_lm"]).mean()))
    if fb_path.exists():
        fb = pd.read_csv(fb_path)[["id", "sentiment_usd_finbert"]]
        m = base.merge(fb, on="id")
        agree_pairs.append(("LLM USD vs FinBERT", (m["llm_usd"] == m["sentiment_usd_finbert"]).mean()))
    if lm_path.exists() and fb_path.exists():
        m = base.merge(lm, on="id").merge(fb, on="id")
        agree_pairs.append(("LM vs FinBERT", (m["sentiment_usd_lm"] == m["sentiment_usd_finbert"]).mean()))

    cross_disagree_llm = (llm["sentiment_usd"] != llm["sentiment_ndx"]).mean()

    body = []
    body.append(r"\begin{table}[!htbp]")
    body.append(r"\centering")
    body.append(r"\caption{Sentiment label distribution and pairwise classifier agreement.}")
    body.append(r"\label{tab:sentiment-dist}")
    body.append(r"\begin{threeparttable}")
    body.append(r"\small")
    body.append(r"\begin{tabular}{lrrrr}")
    body.append(r"\toprule")
    body.append(r"\textbf{Classifier} & \textbf{Bull} & \textbf{Bear} & \textbf{Neutral} & \textbf{Total} \\")
    body.append(r"\midrule")
    for label, d in rows:
        total = d["bull"] + d["bear"] + d["neutral"]
        body.append(
            f"{label} & {d['bull']:,} ({d['bull']/total*100:.1f}\\%) & "
            f"{d['bear']:,} ({d['bear']/total*100:.1f}\\%) & "
            f"{d['neutral']:,} ({d['neutral']/total*100:.1f}\\%) & {total:,} \\\\"
        )
    body.append(r"\midrule")
    body.append(r"\multicolumn{5}{l}{\textit{Pairwise label agreement on USD sentiment ($N$=" + f"{n:,}" + r")}} \\")
    for pair_label, pct in agree_pairs:
        body.append(f"\\quad {pair_label} & \\multicolumn{{4}}{{l}}{{{pct*100:.1f}\\%}} \\\\")
    body.append(r"\midrule")
    body.append(r"\multicolumn{5}{l}{\textit{Cross-asset disagreement (\texttt{sentiment\_usd} $\neq$ \texttt{sentiment\_ndx})}} \\")
    body.append(f"\\quad LLM & \\multicolumn{{4}}{{l}}{{{cross_disagree_llm*100:.1f}\\%}} \\\\")
    body.append(r"\quad LM, FinBERT & \multicolumn{4}{l}{$0\%$ by construction (single-polarity classifiers)} \\")
    body.append(r"\bottomrule")
    body.append(r"\end{tabular}")
    body.append(r"\begin{tablenotes}")
    body.append(r"\footnotesize")
    body.append(r"\item \textit{Notes.} Distribution of discrete sentiment labels")
    body.append(r"across the full event sample for each classifier, with column")
    body.append(r"percentages in parentheses. LM and FinBERT produce a single")
    body.append(r"polarity per event and therefore cannot disagree across")
    body.append(r"assets. Pairwise agreement reports the share of events on")
    body.append(r"which the two classifiers assign the same USD label.")
    body.append(r"\end{tablenotes}")
    body.append(r"\end{threeparttable}")
    body.append(r"\end{table}")
    write_table("table_4_sentiment_distribution", "\n".join(body) + "\n")


# ---------------------------------------------------------------------------
# T5: H1 main results
# ---------------------------------------------------------------------------


def table_5_h1_main():
    h1 = pd.read_csv(OUTPUTS / "h1_results.csv")
    rng = pd.read_csv(OUTPUTS / "range_outcomes_results.csv")

    body = []
    body.append(r"\begin{table}[!htbp]")
    body.append(r"\centering")
    body.append(r"\caption{Event-window magnitude versus matched baseline (H1 and C2).}")
    body.append(r"\label{tab:h1-main}")
    body.append(r"\begin{threeparttable}")
    body.append(r"\small")
    body.append(r"\begin{tabular}{lcccccc}")
    body.append(r"\toprule")
    body.append(r" & \multicolumn{3}{c}{EUR/USD (USD proxy)} & \multicolumn{3}{c}{Nasdaq-100} \\")
    body.append(r"\cmidrule(lr){2-4} \cmidrule(lr){5-7}")
    body.append(r"Window & 5m & 15m & 60m & 5m & 15m & 60m \\")
    body.append(r"\midrule")

    def row(label, metric_key, source_df):
        cells = []
        for asset in ["eurusd", "ndx"]:
            for w in PRIMARY_WINDOWS:
                if "metric" in source_df.columns:
                    r = source_df[(source_df["asset"] == asset) &
                                  (source_df["window_min"] == w) &
                                  (source_df["metric"] == metric_key)]
                else:
                    r = source_df[(source_df["asset"] == asset) & (source_df["window_min"] == w)]
                if r.empty:
                    cells.append("--")
                else:
                    cells.append(label["fn"](r.iloc[0]))
        return label["row"] + " & " + " & ".join(cells) + r" \\"

    # H1: abs_delta_pct
    body.append(row(
        {"row": r"Mean $|r|$, event ($\%$)", "fn": lambda r: fmt_num(r["mean_abs_event"])},
        None, h1))
    body.append(row(
        {"row": r"Mean $|r|$, baseline ($\%$)", "fn": lambda r: fmt_num(r["mean_abs_baseline"])},
        None, h1))
    body.append(row(
        {"row": r"Ratio (event/baseline)", "fn": lambda r: fmt_num(r["ratio"], 2) + r"$\times$"},
        None, h1))
    body.append(row(
        {"row": r"$q$-value (MWU one-sided)", "fn": lambda r: fmt_pval(r["q_mwu_greater"])},
        None, h1))

    body.append(r"\addlinespace")
    body.append(r"\multicolumn{7}{l}{\textit{C2: intra-window range and maximum absolute move}} \\")
    body.append(row(
        {"row": r"Range, event ($\%$)", "fn": lambda r: fmt_num(r["mean_event"])},
        "range_pct", rng))
    body.append(row(
        {"row": r"Range, baseline ($\%$)", "fn": lambda r: fmt_num(r["mean_baseline"])},
        "range_pct", rng))
    body.append(row(
        {"row": r"Ratio range", "fn": lambda r: fmt_num(r["ratio"], 2) + r"$\times$"},
        "range_pct", rng))
    body.append(row(
        {"row": r"Max abs move, event ($\%$)", "fn": lambda r: fmt_num(r["mean_event"])},
        "max_abs_move_pct", rng))
    body.append(row(
        {"row": r"Ratio max abs move", "fn": lambda r: fmt_num(r["ratio"], 2) + r"$\times$"},
        "max_abs_move_pct", rng))

    body.append(r"\addlinespace")
    body.append(row(
        {"row": r"$N$ clusters (event)", "fn": lambda r: fmt_int(r["n_clusters"])},
        None, h1))

    body.append(r"\bottomrule")
    body.append(r"\end{tabular}")
    body.append(r"\begin{tablenotes}")
    body.append(r"\footnotesize")
    body.append(r"\item \textit{Notes.} Event-window absolute return $|r|$, intra-window")
    body.append(r"high-low range, and maximum absolute intra-window move, all in percentage")
    body.append(r"points. Baselines are drawn from non-event windows matched on asset,")
    body.append(r"window length, hour-of-day, and day-of-week, with 30 draws per event.")
    body.append(r"The $q$-value comes from a one-sided Mann-Whitney $U$ test against")
    body.append(r"the baseline distribution, with Benjamini-Hochberg FDR adjustment")
    body.append(r"applied across the full hypothesis battery. Cluster identifier groups")
    body.append(r"events at a 15-minute gap. Welch $t$-test alternative reported in")
    body.append(r"the Online Appendix.")
    body.append(r"\end{tablenotes}")
    body.append(r"\end{threeparttable}")
    body.append(r"\end{table}")
    write_table("table_5_h1_main", "\n".join(body) + "\n")


# ---------------------------------------------------------------------------
# T6: Three-way direction hit rate comparison
# ---------------------------------------------------------------------------


def table_6_baseline_compare():
    cmp = pd.read_csv(OUTPUTS / "sentiment_baseline_compare.csv")

    body = []
    body.append(r"\begin{table}[!htbp]")
    body.append(r"\centering")
    body.append(r"\caption{Direction hit rate: LLM versus baselines.}")
    body.append(r"\label{tab:baseline-compare}")
    body.append(r"\begin{threeparttable}")
    body.append(r"\small")
    body.append(r"\begin{tabular}{llcccc}")
    body.append(r"\toprule")
    body.append(r"\textbf{Asset} & \textbf{Source} & \textbf{Window} & \textbf{$N$} & \textbf{Hit rate} & \textbf{$q$-value} \\")
    body.append(r"\midrule")

    for asset in ["eurusd", "ndx"]:
        asset_label = "EUR/USD" if asset == "eurusd" else "NDX"
        first_in_asset = True
        for w in PRIMARY_WINDOWS:
            for src_key, src_label in [("LLM", "LLM"), ("LM", "LM (dict.)"), ("FINBERT", "FinBERT")]:
                row = cmp[(cmp["asset"] == asset) & (cmp["window_min"] == w) & (cmp["source"] == src_key)]
                if row.empty:
                    continue
                r = row.iloc[0]
                hit = f"{r['hit_rate']*100:.1f}\\%"
                ci = f"[{r['ci95_low']:.3f}, {r['ci95_high']:.3f}]"
                stars = sig_stars(r["p_binom_greater"])
                asset_cell = asset_label if first_in_asset else ""
                first_in_asset = False
                body.append(
                    f"{asset_cell} & {src_label} & +{w}m & {fmt_int(r['n'])} & "
                    f"{hit}{stars} & {fmt_pval(r['q_binom_greater'])} \\\\"
                )
            body.append(r"\addlinespace[2pt]")
        body.append(r"\midrule")

    body.append(r"\bottomrule")
    body.append(r"\end{tabular}")
    body.append(r"\begin{tablenotes}")
    body.append(r"\footnotesize")
    body.append(r"\item \textit{Notes.} Direction hit rate against the realised target")
    body.append(r"direction (positive vs negative target return). $N$ counts directional")
    body.append(r"events (excludes events the classifier labels neutral). Each row")
    body.append(r"reports a one-sided binomial test against the null $p_0 = 0.5$;")
    body.append(r"$q$-values from Benjamini-Hochberg FDR adjustment.")
    body.append(r"$^{*}p<0.10$, $^{**}p<0.05$, $^{***}p<0.01$ on raw $p$-values.")
    body.append(r"\end{tablenotes}")
    body.append(r"\end{threeparttable}")
    body.append(r"\end{table}")
    write_table("table_6_baseline_compare", "\n".join(body) + "\n")


# ---------------------------------------------------------------------------
# T7: Multivariate regression (one representative cell + appendix list)
# ---------------------------------------------------------------------------


def table_7_multivariate():
    mv = pd.read_csv(OUTPUTS / "multivariate_results.csv")
    # Show EUR/USD 5m abs_return_z as the representative cell, and NDX 15m for comparison
    cells = [
        ("eurusd", 5, "abs_return_z"),
        ("eurusd", 60, "abs_return_z"),
        ("ndx", 5, "abs_return_z"),
        ("ndx", 60, "abs_return_z"),
    ]

    body = []
    body.append(r"\begin{table}[!htbp]")
    body.append(r"\centering")
    body.append(r"\caption{Multivariate regression of standardised abnormal magnitude.}")
    body.append(r"\label{tab:multivariate}")
    body.append(r"\begin{threeparttable}")
    body.append(r"\small")
    body.append(r"\begin{tabular}{lcccc}")
    body.append(r"\toprule")
    body.append(r" & \multicolumn{2}{c}{EUR/USD ($|z|$)} & \multicolumn{2}{c}{NDX ($|z|$)} \\")
    body.append(r"\cmidrule(lr){2-3} \cmidrule(lr){4-5}")
    body.append(r"Term & +5m & +60m & +5m & +60m \\")
    body.append(r"\midrule")

    # Pick a stable set of terms to report
    terms = [
        ("log_n_headlines", r"$\log(\text{cluster size})$"),
        ("pre_abs_target_delta_15", r"Pre-event $|r|_{15}$"),
        ("cluster_surprise_score_max", r"Surprise level"),
        ("cluster_magnitude_score_max", r"Expected magnitude"),
        ("cluster_confidence_mean", r"LLM confidence"),
        ("headline_length_mean", r"Headline length"),
        ("cat_central_bank", r"Cat: central bank"),
        ("cat_geopolitical", r"Cat: geopolitical"),
        ("cat_corporate", r"Cat: corporate"),
        ("cat_energy", r"Cat: energy"),
    ]

    for term_key, term_label in terms:
        coef_cells, se_cells = [], []
        for asset, w, outcome in cells:
            r = mv[(mv["asset"] == asset) & (mv["window_min"] == w) &
                   (mv["outcome"] == outcome) & (mv["term"] == term_key)]
            if r.empty:
                coef_cells.append("--"); se_cells.append("")
                continue
            row = r.iloc[0]
            stars = sig_stars(row["p_value"])
            coef_cells.append(f"${fmt_num(row['coef'], 3)}${stars}")
            se_cells.append(f"$({fmt_num(row['se'], 3)})$")
        body.append(term_label + " & " + " & ".join(coef_cells) + r" \\")
        body.append(" & " + " & ".join(se_cells) + r" \\")
        body.append(r"\addlinespace[2pt]")

    # R^2 footer
    r2_cells = []
    n_cells = []
    for asset, w, outcome in cells:
        r = mv[(mv["asset"] == asset) & (mv["window_min"] == w) & (mv["outcome"] == outcome)]
        if r.empty:
            r2_cells.append("--")
            n_cells.append("--")
        else:
            r2_cells.append(fmt_num(r.iloc[0]["r2"], 3))
            n_cells.append(fmt_int(r.iloc[0]["n_clusters"]))
    body.append(r"\midrule")
    body.append("$R^2$ & " + " & ".join(r2_cells) + r" \\")
    body.append("$N$ clusters & " + " & ".join(n_cells) + r" \\")

    body.append(r"\bottomrule")
    body.append(r"\end{tabular}")
    body.append(r"\begin{tablenotes}")
    body.append(r"\footnotesize")
    body.append(r"\item \textit{Notes.} OLS of the standardised abnormal $|z|$ on the")
    body.append(r"listed regressors. Coefficient on top, robust standard error in")
    body.append(r"parentheses below; cluster-robust covariance with the 15-minute")
    body.append(r"news-cluster identifier as the grouping variable.")
    body.append(r"$^{*}p<0.10$, $^{**}p<0.05$, $^{***}p<0.01$ on raw $p$-values;")
    body.append(r"$q$-values reported in the Online Appendix. Category baseline:")
    body.append(r"\texttt{politics}.")
    body.append(r"\end{tablenotes}")
    body.append(r"\end{threeparttable}")
    body.append(r"\end{table}")
    write_table("table_7_multivariate", "\n".join(body) + "\n")


# ---------------------------------------------------------------------------
# T8: Pre/post knowledge-cutoff stability
# ---------------------------------------------------------------------------


def table_8_pre_post_cutoff():
    pp = pd.read_csv(OUTPUTS / "pre_post_stability_results.csv")

    body = []
    body.append(r"\begin{table}[!htbp]")
    body.append(r"\centering")
    body.append(r"\caption{Stability across LLM knowledge-cutoff split (15 January 2026).}")
    body.append(r"\label{tab:pre-post}")
    body.append(r"\begin{threeparttable}")
    body.append(r"\small")
    body.append(r"\begin{tabular}{lcccccc}")
    body.append(r"\toprule")
    body.append(r" & \multicolumn{3}{c}{EUR/USD} & \multicolumn{3}{c}{NDX} \\")
    body.append(r"\cmidrule(lr){2-4} \cmidrule(lr){5-7}")
    body.append(r"Period & 5m & 15m & 60m & 5m & 15m & 60m \\")
    body.append(r"\midrule")

    for period_key, period_label in [("pre_cutoff", "Pre-cutoff: mean $|z|_{\\,|r|}$"),
                                       ("post_cutoff", "Post-cutoff: mean $|z|_{\\,|r|}$")]:
        cells = []
        for asset in ["eurusd", "ndx"]:
            for w in PRIMARY_WINDOWS:
                r = pp[(pp["sample_period"] == period_key) & (pp["asset"] == asset) &
                       (pp["window_min"] == w)]
                if r.empty:
                    cells.append("--")
                else:
                    cells.append(fmt_num(r.iloc[0]["mean_abs_return_z"], 3))
        body.append(period_label + " & " + " & ".join(cells) + r" \\")

    for period_key, period_label in [("pre_cutoff", "Pre-cutoff: $q$"),
                                       ("post_cutoff", "Post-cutoff: $q$")]:
        cells = []
        for asset in ["eurusd", "ndx"]:
            for w in PRIMARY_WINDOWS:
                r = pp[(pp["sample_period"] == period_key) & (pp["asset"] == asset) &
                       (pp["window_min"] == w)]
                if r.empty:
                    cells.append("--")
                else:
                    cells.append(fmt_pval(r.iloc[0]["q_abs_return_z_ttest_gt0"]))
        body.append(period_label + " & " + " & ".join(cells) + r" \\")

    # Cluster counts for pre
    cells = []
    for asset in ["eurusd", "ndx"]:
        for w in PRIMARY_WINDOWS:
            r = pp[(pp["sample_period"] == "pre_cutoff") & (pp["asset"] == asset) &
                   (pp["window_min"] == w)]
            if r.empty:
                cells.append("--")
            else:
                cells.append(fmt_int(r.iloc[0]["n_clusters"]))
    body.append(r"\addlinespace")
    body.append("Pre-cutoff $N$ clusters & " + " & ".join(cells) + r" \\")

    body.append(r"\bottomrule")
    body.append(r"\end{tabular}")
    body.append(r"\begin{tablenotes}")
    body.append(r"\footnotesize")
    body.append(r"\item \textit{Notes.} Standardised abnormal absolute return $|z|$")
    body.append(r"in the pre-cutoff and post-cutoff halves, with the split at the LLM's")
    body.append(r"reported training data cutoff of 15 January 2026. $q$-values from")
    body.append(r"one-sided $t$-test against zero with BH-FDR adjustment.")
    body.append(r"\end{tablenotes}")
    body.append(r"\end{threeparttable}")
    body.append(r"\end{table}")
    write_table("table_8_pre_post_cutoff", "\n".join(body) + "\n")


# ---------------------------------------------------------------------------
# T10: Backtest results with and without costs
# ---------------------------------------------------------------------------


def table_10_backtest():
    cost_path = OUTPUTS / "trader_backtest_summary.csv"
    nocost_path = OUTPUTS / "trader_backtest_summary_nocost.csv"
    if not cost_path.exists() or not nocost_path.exists():
        print("  skipping table 10: backtest CSVs not found")
        return

    cost = pd.read_csv(cost_path)
    nocost = pd.read_csv(nocost_path)

    # Pick top 6 strategies by total return (with costs)
    # Use strategy + asset as key
    cost["key"] = cost["strategy"] + "/" + cost["asset"]
    nocost["key"] = nocost["strategy"] + "/" + nocost["asset"]
    merged = cost.merge(nocost, on="key", suffixes=("_cost", "_nocost"))

    body = []
    body.append(r"\begin{table}[!htbp]")
    body.append(r"\centering")
    body.append(r"\caption{Naive sentiment-following strategy backtest with and without transaction costs.}")
    body.append(r"\label{tab:backtest}")
    body.append(r"\begin{threeparttable}")
    body.append(r"\footnotesize")
    body.append(r"\begin{tabular}{lcrcccc}")
    body.append(r"\toprule")
    body.append(r"\textbf{Strategy} & \textbf{Asset} & \textbf{$N$ trades} & \textbf{Win \%} & \textbf{Tot.\,ret.\,(\%)} & \textbf{Profit factor} & \textbf{Max DD (\%)} \\")
    body.append(r"\midrule")
    body.append(r"\multicolumn{7}{l}{\textit{With realistic spread + slippage}} \\")
    for _, r in merged.iterrows():
        body.append(
            f"{r['strategy_cost'].replace('_', r'\_')} & {r['asset_cost']} & "
            f"{fmt_int(r['n_trades_cost'])} & "
            f"{r['win_rate_cost']*100:.1f}\\% & "
            f"{fmt_num(r['total_return_pct_sum_cost'], 2)} & "
            f"{fmt_num(r['profit_factor_cost'], 2)} & "
            f"{fmt_num(r['max_drawdown_pct_sum_cost'], 2)} \\\\"
        )
    body.append(r"\addlinespace")
    body.append(r"\multicolumn{7}{l}{\textit{Without transaction costs (frictionless)}} \\")
    for _, r in merged.iterrows():
        body.append(
            f"{r['strategy_nocost'].replace('_', r'\_')} & {r['asset_nocost']} & "
            f"{fmt_int(r['n_trades_nocost'])} & "
            f"{r['win_rate_nocost']*100:.1f}\\% & "
            f"{fmt_num(r['total_return_pct_sum_nocost'], 2)} & "
            f"{fmt_num(r['profit_factor_nocost'], 2)} & "
            f"{fmt_num(r['max_drawdown_pct_sum_nocost'], 2)} \\\\"
        )
    body.append(r"\bottomrule")
    body.append(r"\end{tabular}")
    body.append(r"\begin{tablenotes}")
    body.append(r"\footnotesize")
    body.append(r"\item \textit{Notes.} Seven naive sentiment-following strategies")
    body.append(r"applied to each event, traded with EUR/USD spot or NDX CFD prices.")
    body.append(r"Costs include venue-typical spread and slippage. Total return is")
    body.append(r"the simple sum across trades, in percentage points. Profit factor")
    body.append(r"is gross profit divided by gross loss; values below 1.0 indicate")
    body.append(r"a losing strategy.")
    body.append(r"\end{tablenotes}")
    body.append(r"\end{threeparttable}")
    body.append(r"\end{table}")
    write_table("table_10_backtest", "\n".join(body) + "\n")


# ---------------------------------------------------------------------------
# T11: Winsorisation robustness
# ---------------------------------------------------------------------------


def table_11_winsorisation():
    ws = pd.read_csv(OUTPUTS / "outlier_robustness_results.csv")

    body = []
    body.append(r"\begin{table}[!htbp]")
    body.append(r"\centering")
    body.append(r"\caption{Robustness to winsorisation at 1\% tails.}")
    body.append(r"\label{tab:winsor}")
    body.append(r"\begin{threeparttable}")
    body.append(r"\small")
    body.append(r"\begin{tabular}{lccccccc}")
    body.append(r"\toprule")
    body.append(r" & & \multicolumn{2}{c}{Mean $|z|$} & \multicolumn{2}{c}{$q$-value ($t$-test)} \\")
    body.append(r"\cmidrule(lr){3-4} \cmidrule(lr){5-6}")
    body.append(r"Asset & Window & Raw & Winsor 1\% & Raw & Winsor 1\% & $N$ \\")
    body.append(r"\midrule")
    for asset in ["eurusd", "ndx"]:
        asset_label = "EUR/USD" if asset == "eurusd" else "NDX"
        for w in PRIMARY_WINDOWS:
            r = ws[(ws["asset"] == asset) & (ws["window_min"] == w) & (ws["metric"] == "abs_return_z")]
            if r.empty:
                continue
            row = r.iloc[0]
            body.append(
                f"{asset_label} & +{w}m & {fmt_num(row['mean_raw'], 3)} & {fmt_num(row['mean_winsor_1pct'], 3)} & "
                f"{fmt_pval(row['q_raw_ttest_gt0'])} & {fmt_pval(row['q_winsor_ttest_gt0'])} & {fmt_int(row['n_clusters'])} \\\\"
            )
    body.append(r"\bottomrule")
    body.append(r"\end{tabular}")
    body.append(r"\begin{tablenotes}")
    body.append(r"\footnotesize")
    body.append(r"\item \textit{Notes.} Mean of $|z|$ (standardised abnormal absolute")
    body.append(r"return) in the raw and 1\%-winsorised samples, with corresponding")
    body.append(r"$q$-values from a one-sided $t$-test against zero. Winsorisation")
    body.append(r"is applied separately within each (asset, window) cell.")
    body.append(r"\end{tablenotes}")
    body.append(r"\end{threeparttable}")
    body.append(r"\end{table}")
    write_table("table_11_winsorisation", "\n".join(body) + "\n")


def main():
    print(f"Writing tables to {TABLES}/ ...")
    table_2_variable_definitions()
    table_3_descriptive_stats()
    table_4_sentiment_distribution()
    table_5_h1_main()
    table_6_baseline_compare()
    table_7_multivariate()
    table_8_pre_post_cutoff()
    table_10_backtest()
    table_11_winsorisation()
    print("Done.")


if __name__ == "__main__":
    main()
