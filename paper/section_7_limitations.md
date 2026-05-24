# 7. Limitations

We collect the limitations of the design under five headings, each of
which suggests a corresponding direction for follow-up work.

## 7.1 Single news feed and proxy timestamps

The analysis uses one news feed (the FinancialJuice Discord
newsfeed) and the Discord publication timestamp as the event time.
The publication timestamp is downstream of the underlying primary
source-typically a wire service, an agency feed, or an official
release calendar-and the variable latency between the primary
source and the Discord publication is, in our reading, the most
plausible explanation for the pre-event drift reported in Section 5.4.
We cannot decompose this drift into "feed latency" and "true
pre-disclosure activity" with the data at hand. Future work should
either obtain primary-source timestamps directly, or compare a
sample of events against a higher-tier feed (e.g., Bloomberg, Reuters
Newscope) to estimate the latency distribution.

A consequence of using a single feed is that any feed-specific bias in
the curation of "gold" events propagates into the sample. The gold
filter is deterministic and reproducible, but it relies on the
publisher's own red-dot and `$MACRO` tagging conventions. We do not
have a counterfactual sample drawn from a different feed.

## 7.2 Two-asset universe and CFD proxy for NDX

We test two assets, EUR/USD spot and the Nasdaq-100 CFD. The choice
reflects the most liquid headline-FX pair and a tradable index proxy.
The findings should not be extrapolated to less-liquid currency pairs,
to individual equities (where firm-specific news effects dominate),
or to fixed-income markets without explicit testing. The Dukascopy
`E_NQ-100` series is a CFD price track for the Nasdaq-100, not the
authoritative consolidated tape; we use it because it offers
one-minute resolution with no gaps over our period, but readers
should treat the magnitude estimates on NDX as estimates on the CFD
price rather than on the cash index.

## 7.3 Volume series is a proxy

The volume series accompanying the Dukascopy NDX CFD is best
understood as tick volume (the count of price updates) rather than
consolidated exchange volume. The H10 test of event-window volume
elevation is reported in the Appendix with this caveat explicit;
readers should not interpret it as evidence on changes in
consolidated traded volume around news events. A defensible test of
the volume question requires consolidated tape access for the index
constituents.

## 7.4 Sentiment classifier not yet fully manually validated

We benchmark the LLM-derived sentiment against two reference
classifiers (Loughran-McDonald dictionary, FinBERT-tone). We have
prepared a 200-event subsample for double-coded human annotation
with the infrastructure to compute Cohen's $\kappa$ between
annotators, $F_1$ for the LLM against the consensus label, and a
split-by-knowledge-cutoff comparison to address memorisation
concerns. At the time of writing the annotation is in progress; we
update the paper with the results when complete. The
pre-cutoff/post-cutoff stability of the central magnitude
findings (Section 5.6, C5) provides indirect evidence against the
memorisation hypothesis, but is not a substitute for direct human
validation of the labels.

Additionally, the LLM-reported `confidence` field is uncalibrated
(H6, reported here as a null finding): the model's stated probability
that its direction is correct does not correspond to the empirical
hit rate within confidence buckets. We do not use the confidence as a
probability anywhere in the analysis, but its inclusion in the
LLM output schema invites misuse and should be removed or
re-calibrated in future versions of the pipeline.

Two further null findings should be reported explicitly. H12 (a test
of bear-versus-bull asymmetry in the price response) does not detect
a robust asymmetry in our sample; this is a limitation of either the
sample, the test, or the underlying phenomenon, and we cannot
distinguish among these. C8 (a cross-model consistency check on
$n=200$ events comparing `deepseek-v4-flash` and `deepseek-v4-pro`)
is exploratory: the subsample is underpowered for the inference
suggested by the headline numbers, and we report it in Limitations
rather than as a main result.

## 7.5 Multiple testing, dependence, and pre-specification

The pipeline runs more than a hundred individual $p$-values across
the main tests, the auxiliary tests, and the cells of stratified
analyses. We address this with uniform Benjamini-Hochberg false
discovery rate adjustment [@benjamini1995controlling], and we draw
the primary conclusions exclusively from $q$-values. Two residual
concerns remain.

First, the cluster-dependence structure means that adjacent events
in a news burst are not independent. We address this with the
cluster-dedupe convention in non-regression tests and with
cluster-robust standard errors in regression tests; both devices may
under-correct in long news bursts (cluster sizes occasionally exceed
twenty events).

Second, the C1-C7 extensions were added during methodological
revision after the H1-H14 pre-specification. The C extensions are
clearly demarcated in the code and in `STATUS.md`. Readers who wish
to apply a stricter pre-registration standard can re-read Section 5
attending only to the H1-H14 results; the central conclusions of
Section 5.1 (H1) and Section 5.4 (H8, H9) survive this restriction.

## 7.6 What would strengthen a follow-up

In addition to the manual validation and the primary-source
timestamp work mentioned above, the most promising extensions are:
(a) cross-feed replication on a second public news service to
quantify feed-specific bias; (b) cross-asset extension to a small
basket of individual equities for firm-specific news; (c) prompt
engineering and LLM ensembling on the directional task to test
whether the modest direction edge can be improved beyond the present
$2$-$6$ pp margin over baselines; and (d) integration of the
methodology with an order-flow or quote-imbalance dataset to
distinguish the magnitude response into a re-pricing component and a
liquidity-withdrawal component.
