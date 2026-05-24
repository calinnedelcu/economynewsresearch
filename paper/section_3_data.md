# 3. Data

## 3.1 News Data

We use the public newsfeed of the FinancialJuice Discord server, captured
via DiscordChatExporter into a single JSON archive. The export covers the
period from 24 March 2025 to 5 May 2026 (approximately thirteen months)
and contains 63,016 individual messages from the official `FinancialJuice`
account. The feed is a real-time aggregation of macroeconomic releases,
central bank communication, geopolitical headlines, political statements,
energy market news, and corporate announcements, intended primarily for an
audience of intraday traders. All timestamps are recorded by Discord at
the moment the message is published and converted to UTC.

To isolate market-relevant unscheduled events from routine data releases,
we apply a deterministic "gold" filter:

> A message is gold if (1) it is flagged with a red dot (`🔴`) or begins
> with `BREAKING`, and (2) it is not flagged with the `$MACRO` tag that
> the publisher attaches to scheduled macro indicator releases (CPI, NFP,
> PMI, etc.).

The first condition selects headlines that the publisher itself considers
high-impact; the second removes scheduled releases that would otherwise
dominate the sample and whose timing carries no informational surprise.
The filter retains 2,449 messages (3.9 percent of the raw feed), which we
treat as the working population of unscheduled news events.

We assign each gold event to one of seven categories using deterministic
keyword rules embedded in `parse_fj_discord.py`: `macro_release` (residual
data releases not caught by the `$MACRO` tag), `central_bank` (Federal
Reserve, ECB, Bank of England, etc.), `geopolitical` (war, sanctions,
diplomacy), `politics` (executive and legislative statements), `energy`
(OPEC, oil inventories, gas), `corporate` (named firm news), and `other`.
The category labels are used only for stratified hypothesis testing in
later sections and play no role in event selection.

## 3.2 Sentiment Labels

Each gold event is independently labelled by a large language model with
respect to its short-horizon directional implication for the U.S. Dollar
(USD) and the Nasdaq-100 Index (NDX). We use `deepseek-v4-flash` accessed
via an OpenAI-compatible API endpoint. The system prompt (reproduced in
the Appendix) restricts the model to a strict JSON schema with the
following fields per event:

| Field | Type | Description |
|---|---|---|
| `sentiment_usd` | `bull` / `bear` / `neutral` | Discrete USD direction |
| `sentiment_ndx` | `bull` / `bear` / `neutral` | Discrete NDX direction |
| `directional_strength_usd` | float in [−1, +1] | Signed intensity |
| `directional_strength_ndx` | float in [−1, +1] | Signed intensity |
| `expected_magnitude` | `low` / `med` / `high` | Anticipated price impact |
| `surprise_level` | `expected` / `surprise` / `shock` | Degree of novelty |
| `confidence` | float in [0, 1] | Self-reported confidence |
| `rationale` | string | One-sentence justification |

The prompt explicitly instructs the model to (a) base its judgment only
on the supplied text, (b) return `neutral` with low confidence when the
message is ambiguous, and (c) treat USD and NDX independently so that
risk-off events can map to `bull USD, bear NDX` simultaneously. Five
few-shot examples covering geopolitical, central bank, corporate, and
neutral cases are included verbatim in the system prompt to anchor the
output format. Calls are cached locally in SQLite, keyed on the
hash of the model name, system prompt, and event content, so that
re-runs during prompt iteration do not duplicate API costs.

The LLM-derived labels are the primary sentiment input throughout the
paper. In Section [N] we benchmark them against a deterministic
Loughran-McDonald dictionary baseline.

## 3.3 Price Data

We use one-minute open-high-low-close-volume (OHLCV) bars for two
target assets from Dukascopy: the EUR/USD spot exchange rate and the
`E_NQ-100` Nasdaq-100 contract for difference (CFD). The CFD price
track is used as a tradable proxy for the cash Nasdaq-100 index in the
absence of an authoritative consolidated tape at one-minute resolution.
We acknowledge the proxy nature of this series in the Limitations and
discuss its implications for the reported volume tests in Section [N].

The price coverage spans 24 March 2025 to 5 May 2026, identical to the
news coverage window. After de-duplication and gap detection, the EUR/USD
panel contains 416,500 bars and the NDX panel contains 381,122 bars; the
difference reflects the venue's CFD market hours (no weekend trading,
exchange holidays). Closed-period gaps are detected automatically and
events that fall inside them are diverted to the closed-period gap test
(Section [N]) rather than to the main intraday windows.

A reported volume series accompanies each bar. For EUR/USD, Dukascopy's
volume reflects the venue's executed flow; for the NDX CFD, the series
is best understood as tick volume rather than consolidated exchange
volume. Any volume-based test must therefore be interpreted accordingly.

## 3.4 Final Analysis Sample

The two coverage windows (news and prices) are identical, so the
intersection used for the event study is also 24 March 2025 to 5 May 2026,
and no gold events are dropped for falling outside the price range
(`events_after_common_range_dropped = 0` in `methodology_summary.csv`).
After cluster assignment at a 15-minute gap threshold, the 2,449 events
organise into 1,405 distinct news clusters; the median cluster contains
a single headline, but the largest contain dozens of related releases
issued within minutes of each other (typically central bank decisions
followed by press conferences, or geopolitical escalations followed by
official reactions). Cluster identity is preserved throughout the
analysis: non-regression tests use the first event per cluster as an
independent observation, and regression standard errors are clustered
on cluster identity.

Generating one event-asset-window record for each combination of (event,
asset in {EUR/USD, NDX}, window in {1, 5, 15, 60, 240} minutes) yields a
panel of 24,490 event-window rows. A parallel cluster-level panel
constructed from the first timestamp of each cluster yields 14,050
rows. Both panels are written to the project repository
(`event_study_windows.csv` and `cluster_event_study_windows.csv`).

Table 1 summarises the sample.

**Table 1.** Final analysis sample.

| Quantity | Value |
|---|---|
| News coverage | 2025-03-24 to 2026-05-05 (UTC) |
| Raw Discord messages | 63,016 |
| Gold events after filter | 2,449 |
| Events dropped (outside price range) | 0 |
| News clusters at 15-min gap | 1,405 |
| Event-window rows | 24,490 |
| Cluster-window rows | 14,050 |
| EUR/USD 1-min bars | 416,500 |
| Nasdaq-100 CFD 1-min bars | 381,122 |
| LLM sentiment model | `deepseek-v4-flash` |
