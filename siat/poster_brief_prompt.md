# SIAT Poster Brief

Recommended default: electronic PDF in 16:9 landscape, because the
regulation asks for a poster in PDF format and does not specify A1/A0
printing. If the organizers confirm printed poster boards, convert the
same content to A1 portrait.

## Goal

The poster must support a 15-minute oral presentation without slides.
It should be readable in 30 seconds, but contain enough structure for a
full explanation.

## Core Message

Unscheduled online financial news is a strong short-term volatility
signal for EUR/USD and Nasdaq-100. It is much weaker as a standalone
directional signal.

## Layout

Use three columns:

1. Motivation and data
2. Method and main result
3. Direction, validation, and conclusion

Suggested section blocks:

- Research question
- Data: 63,016 raw messages, 2,449 filtered events, 24 Mar 2025-5 May 2026
- Method: event study, matched non-event baselines, LLM sentiment, LM and FinBERT baselines
- Main result: event windows move 1.3x-1.9x more than baseline
- Direction result: LLM hit rate 49%-54%, modest but above text baselines
- Asset-specific LLM result: USD and NDX sentiment differ on 73.5% of events
- Validation: Financial PhraseBank accuracy 84.6%, Cohen's kappa 0.72
- Timing caveat: pre-event drift suggests feed latency
- Conclusion: volatility filter > direction predictor

## Figures To Use

Use 2-3 figures maximum:

- `paper/figures/figure_1_event_time_profile.png`
- `paper/figures/figure_5_hit_rate_compare.png`
- optional: `paper/figures/figure_4_range_ratios.png`

The event-time profile should be the largest figure.

## Visual Direction

- Background: white or very light gray.
- Main text: near-black.
- Accent color: one strong finance-style accent, e.g. deep blue plus orange/red for highlights.
- Font: Inter, Source Sans, Aptos, or Open Sans.
- Title: very large, 54-72 pt on 16:9.
- Headers: 28-36 pt.
- Body: 20-26 pt.
- Use short bullets, not paragraphs.
- Avoid decorative finance stock imagery; the project is empirical, so figures should dominate.

## Copy Blocks

Title:
Unexpected Online Financial News and Intraday Market Reactions

Subtitle:
An event-study of EUR/USD and Nasdaq-100 prices using LLM-labelled FinancialJuice headlines

Research question:
Do unscheduled online financial headlines identify abnormal intraday market movement, and can language-model sentiment predict direction?

Data:
2,449 unscheduled FinancialJuice events from 63,016 Discord messages, matched to one-minute EUR/USD and Nasdaq-100 prices from 24 Mar 2025 to 5 May 2026.

Method:
For each headline, compare 5, 15, and 60 minute event-window returns with non-event windows matched by asset, hour-of-day, day-of-week, and window length. Classify each headline with an LLM and compare against Loughran-McDonald and FinBERT baselines.

Main result:
Event windows show absolute price moves about 1.3x-1.9x larger than matched non-event baselines across both assets.

Direction result:
The LLM reaches 49%-54% directional hit rates. This beats the dictionary baseline by about 1-6 percentage points and is competitive with FinBERT, but remains much weaker than the magnitude signal.

Asset-specific sentiment:
The LLM gives different USD and NDX labels on 73.5% of events, which a single dictionary or FinBERT polarity score cannot express.

Validation:
On Financial PhraseBank, the LLM reaches 84.6% accuracy and Cohen's kappa = 0.72 against human labels.

Conclusion:
Online financial news is best used as a short-term volatility alert. Directional sentiment adds information, but the main signal is magnitude, not direction alone.

## Prompt For Canva / PowerPoint / AI Design Tool

Create a clean 16:9 academic research poster PDF for a high-school economics science communication competition. The topic is "Unexpected Online Financial News and Intraday Market Reactions." Use a white/light-gray background, near-black text, deep blue section headers, and one orange/red accent for key numbers. Build a three-column layout with strong hierarchy and large empirical figures. The central visual should be an event-time absolute-return profile figure; a secondary visual should compare LLM, Loughran-McDonald, and FinBERT directional hit rates. The poster should feel rigorous, modern, and readable on a projector. Include these message blocks: research question, data, method, main magnitude result, directional result, asset-specific sentiment, external validation, timing caveat, conclusion. Keep text short, use no more than 700 words, and make the headline numbers visually prominent: 2,449 events; 1.3x-1.9x larger event-window moves; 49%-54% hit rate; 73.5% cross-asset label disagreement; 84.6% PhraseBank accuracy; kappa = 0.72. Do not use decorative stock market photos; let charts and typography carry the design.
