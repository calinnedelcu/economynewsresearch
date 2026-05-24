# Abstract

We study the intraday response of EUR/USD and the Nasdaq-100 index to
$2{,}449$ unscheduled news events from a public real-time newsfeed
(FinancialJuice Discord) over a thirteen-month sample from
24 March 2025 to 5 May 2026, with each event independently labelled by
a large language model ($\texttt{deepseek-v4-flash}$) and benchmarked
against the Loughran-McDonald finance dictionary and the FinBERT-tone
neural classifier. Using a matched, hour-of-day and day-of-week
stratified baseline, with cluster-robust standard errors and
uniform Benjamini-Hochberg false discovery rate adjustment, we find
that news events are robustly associated with intraday magnitude
that is $1.3\times$ to $1.9\times$ the baseline level on every
asset-window cell, and that the intra-window range and maximum
absolute move are the most stable single results. The directional
content of LLM sentiment is modest ($49$-$54\%$ hit rate) and below
transaction costs in a backtest, but the LLM outperforms both
baselines by $2$-$6$ percentage points on the primary windows and is
the only classifier that produces asset-specific sentiment, doing so
on $73.5\%$ of events. The pre-event absolute return is comparable in
magnitude to the post-event return, indicating that the Discord
publication time is not the underlying informational event time and
that entry at the headline timestamp is, on average, already late.
The initial price reaction extends rather than reverses over the
subsequent hours. The full pipeline, including the LLM cache, the
dictionary and FinBERT baselines, the matched-baseline construction,
and the validation harness, is released as a single seeded
reproducible repository.

**Keywords**: event study, intraday returns, sentiment analysis,
large language models, financial dictionaries, news, EUR/USD,
Nasdaq-100, false discovery rate.
