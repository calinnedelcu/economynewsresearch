# 4. Methodology

Our approach follows the standard event-study tradition
[@mackinlay1997event] adapted to a high-frequency intraday setting. The
core idea is to compare price behaviour in a short window around each
news event to a matched baseline drawn from non-event periods of the same
asset. We pay particular attention to three design decisions that are
often glossed over in shorter-horizon studies: event-time alignment with
respect to the minute bar that contains the event timestamp, the
appropriate proxy for USD strength when only EUR/USD is observed, and
the dependency structure induced by news clusters.

## 4.1 Event-Time Alignment

Each event arrives with a UTC timestamp recorded by Discord at message
publication. To avoid contamination of the post-event window by the
fractional bar that contains the event itself, we use ceil/floor
alignment on the one-minute bar grid. For an event with timestamp
$t_i$:

$$
\text{post-event start}(t_i) = \lceil t_i \rceil_{1\text{m}},
\qquad
\text{pre-event end}(t_i) = \lfloor t_i \rfloor_{1\text{m}} - 1\,\text{minute}.
$$

A forward window of $W$ minutes uses the bars
$\lceil t_i \rceil_{1\text{m}}, \ldots, \lceil t_i \rceil_{1\text{m}} + (W-1)\,\text{min}$,
all of which are completely post-event. A pre-event window of $W$ minutes
ends at $\lfloor t_i \rfloor_{1\text{m}} - 1\,\text{min}$. Events whose
window cannot be completely populated (missing bars, weekend boundary,
market closure) are flagged as `is_in_closed_period` and diverted to a
separate gap-test pipeline rather than being silently dropped.

This alignment is more conservative than the common practice of using
$\lfloor t_i \rfloor_{1\text{m}}$ as the base bar, which mixes the bar
containing the event into both the pre-event and post-event windows and
biases short-window estimates toward zero.

## 4.2 Return Definitions and the USD Proxy

For each event $i$, asset $a \in \{\text{EUR/USD}, \text{NDX}\}$, and
window length $W \in \{1, 5, 15, 60, 240\}$ minutes, we define the
close-to-close percentage return

$$
r^{\text{price}}_{i,a,W} = \frac{P^{\text{close}}_{\text{end}} - P^{\text{open}}_{\text{start}}}{P^{\text{open}}_{\text{start}}} \times 100,
$$

together with two intra-window magnitude measures:

$$
\text{range}_{i,a,W} = \frac{\max_t H_t - \min_t L_t}{P^{\text{open}}_{\text{start}}} \times 100,
\qquad
\text{maxabs}_{i,a,W} = \max\bigl(|\text{max\_up}|, |\text{max\_down}|\bigr),
$$

where $H_t, L_t$ are the high and low of bar $t$ within the window. The
range and maximum-absolute-move statistics capture intra-window
volatility that close-to-close returns can miss, particularly on news
where the price overshoots and partially reverses.

Because the sentiment labels are constructed with respect to USD
strength rather than EUR weakness, the EUR/USD price return must be
sign-flipped before being compared against `sentiment_usd`:

$$
r^{\text{target}}_{i,\text{EURUSD},W} = -\,r^{\text{price}}_{i,\text{EURUSD},W},
\qquad
r^{\text{target}}_{i,\text{NDX},W} = r^{\text{price}}_{i,\text{NDX},W}.
$$

This convention is preserved across H2, H3, H4, and H14. Treating
EUR/USD as a direct USD target produces the wrong sign on every
directional test and is, in our view, one of the most easily missed
sources of error in this kind of analysis.

## 4.3 Event Clustering

News events do not arrive independently. Central bank decisions are
typically followed by press conferences; geopolitical escalations
provoke a cascade of related headlines. A naive treatment that
considers each headline as an independent observation will overstate
the number of effective trials and inflate t-statistics through
within-cluster correlation. We address this in two complementary ways.

First, we assign cluster identities by gap rule: two consecutive events
belong to the same cluster if and only if they are separated by no more
than 15 minutes. At the 24,490-row event-window panel this collapses to
14,050 cluster-window rows. Non-regression tests (H1, H2, C1, etc.)
use the first event per cluster as the independent unit, which yields
a more conservative effective sample size than the raw event count.

Second, regression-based tests (H3, H4, C6) employ cluster-robust
standard errors with the cluster identifier as the grouping variable
[@white1980heteroskedasticity], or HC3 standard errors when the cluster
count is insufficient. The two devices together ensure that within-burst
correlation does not contaminate the reported $p$-values.

A separate cluster-level panel
(`cluster_event_study_windows.csv`) aggregates event-level features
within each cluster: the modal sentiment, the maximum surprise level,
the dominant category, the count of headlines, and the mean headline
length. This permits cluster-level direction tests (C1) that ask
whether the consensus sentiment of the cluster predicts the realised
target direction.

## 4.4 Matched Baseline

To contextualise event-window returns, we draw a baseline pool of
non-event windows of the same length for each asset. The pool excludes
all bar-start timestamps falling within $\pm 60$ minutes of any event,
which removes the obvious correlation between the baseline and the
events it is meant to control for. From this pool we sample 30 matched
baseline returns per event, drawing where possible from the same
hour-of-day and day-of-week bucket. When a bucket contains fewer than
ten observations, the sampler falls back to the hour-of-day bucket, then
to the unconditional pool. This stratification absorbs known
weekly and intraday volatility seasonality (e.g., the New York open,
the Asia-Europe handover) without removing the event signal.

For each event-window outcome (close-to-close return, absolute return,
range, max-absolute-move) we report

$$
z_{i,a,W} = \frac{x_{i,a,W} - \mu^{\text{base}}_{a,W,h,d}}{\sigma^{\text{base}}_{a,W,h,d}},
$$

where $(h, d)$ are the hour and day-of-week of the event. Standardising
by the matched baseline second moment makes the EUR/USD and NDX
event-window panels directly comparable on a common dimensionless
scale.

## 4.5 Hypothesis Tests

The pipeline runs fourteen pre-specified hypotheses (H1-H14) and eight
extensions (C1-C8). For reasons of space we report the main results in
Section 5 only for those tests that produced non-trivial findings; the
full set is reproduced in Appendix [N] for auditability. Each test is
summarised below; pre-specified $p$-value definitions are documented in
`event_study.py` and are not adjusted post hoc.

**Main results (Section 5)**:

- **H1 (volatility)**: absolute event-window return versus matched
  baseline, tested by Mann-Whitney $U$ one-sided. Welch's
  $t$-test [@welch1947generalization] is reported as a robustness
  check in the Appendix.
- **H2 (direction)**: hit rate of LLM sentiment against realised target
  direction, tested by one-sided binomial against $p_0 = 0.5$, with
  Wilson 95 percent confidence intervals.
- **H3 (sentiment × prior trend)**: cluster-robust OLS of absolute
  return on sentiment, prior 60-minute trend, and their interaction.
- **H4 (closed-period gap)**: aggregated target sentiment regressed on
  the opening-bar gap across each closed period (weekend, holiday),
  with HC3 robust standard errors.
- **H8 (pre-event drift)**: absolute pre-event return versus matched
  baseline; interpreted as evidence on the timing of information
  arrival, with explicit caveat that the Discord timestamp is not the
  primary-source timestamp.
- **H9 (persistence)**: sign agreement between the $+15$-minute and
  $+4$-hour returns.
- **H11 (time-of-day)**: hour-of-day and day-of-week effects on the
  event/baseline ratio.
- **H14 (cross-asset)**: correlation between EUR/USD and NDX
  event-window returns, reported both raw and after applying the USD
  proxy convention.

**Extensions (Section 5)**:

- **C1**: cluster-level analogue of H2.
- **C2**: range and max-absolute-move outcomes versus matched baseline.
  These have proved to be the strongest individual results in the
  battery and are reported alongside H1.
- **C3**: standardised abnormal $z$-scores (Section 4.4) for all four
  outcomes.
- **C4**: per-category targeted regressions for `central_bank`,
  `geopolitical`, `politics`, `energy`, and `corporate`, replacing the
  redundant H7 omnibus ANOVA.
- **C5**: stability of the central effects across the
  pre/post 15 January 2026 split. This date is the knowledge cutoff of
  the sentiment LLM, and the split lets us address the obvious
  memorisation concern.
- **C6**: multivariate OLS controlling for category dummies, surprise
  level, expected magnitude, confidence, cluster size, headline length,
  and pre-event move; cluster-robust standard errors.
- **C7**: winsorisation at the 1 percent tails as a robustness check
  against the influence of extreme observations.

**Reported only in Limitations and Appendix**:

- H5 and H13 (LLM auxiliary labels: expected magnitude and surprise
  level) are consolidated into a single appendix subsection because
  both depend on the same kind of LLM-derived ordinal categorisation
  and both yielded modest or null evidence of incremental information.
- H6 (LLM confidence calibration via Brier score) is reported in
  Limitations as a null finding: the model's self-reported confidence
  is not calibrated as a probability of correctness.
- H7 (categorical omnibus ANOVA) is subsumed by C4 and not
  reported separately.
- H10 (volume effects) is reported as exploratory only, given that the
  Dukascopy NDX series is tick volume rather than consolidated
  exchange volume.
- H12 (bull-versus-bear asymmetry) is reported as a null finding in
  Limitations.
- C8 (cross-model consensus on a 200-event subsample, comparing
  `deepseek-v4-flash` and `deepseek-v4-pro`) is described in
  Limitations as exploratory; the subsample is underpowered for the
  inference suggested by the headline numbers.

## 4.6 Multiple Testing

The full hypothesis battery generates more than one hundred individual
$p$-values across the main tests, the auxiliary tests, and the cells
of stratified analyses. Reporting raw $p$-values at conventional
thresholds would substantially overstate the level of evidence. We
therefore apply the Benjamini-Hochberg false discovery rate procedure
[@benjamini1995controlling] across the union of all $p$-values
produced by the pipeline (all columns prefixed by `p_` in the
`h*_results.csv` outputs) and report the resulting $q$-values alongside
the raw $p$-values. The primary conclusions of Section 5 are drawn
exclusively from $q$-values; raw $p$-values are reported for
transparency.

## 4.7 Sentiment Validation

The LLM sentiment labels are the central novel input of the analysis.
To make the LLM choice defensible, we compare it against two
baselines and reserve a held-out validation sample for human
adjudication.

**Dictionary baseline.** We re-classify every event using the
Loughran-McDonald finance sentiment dictionary [@loughran2011liability]
via `pysentiment2` [@pysentiment2]. The dictionary produces a single
polarity per document, which we threshold at $|\text{polarity}| \geq
0.1$ to recover the bull/bear/neutral classes. Because the dictionary
has no asset awareness, the resulting USD and NDX classifications are
identical by construction. We then re-run the H2-equivalent direction
test on the LM labels and compare hit rates side by side with the LLM
labels (Section [N]).

**Cross-model consensus.** A 200-event subsample is independently
classified by `deepseek-v4-flash` and `deepseek-v4-pro` to measure
intra-LLM agreement; this is reported as exploratory due to sample
size.

**Manual validation.** A separate sample of 200 events,
stratified across categories and split pre and post the LLM knowledge
cutoff, is reserved for double-coded human annotation. We report
Cohen's $\kappa$ between annotators, $F_1$ of the LLM against the
two-annotator consensus, and the same split-by-cutoff comparison to
address memorisation concerns. The annotation infrastructure
(`prepare_manual_validation.py`, `score_manual_validation.py`) is in
place; annotation is in progress at the time of writing.
