# 2. Literature Review

Our work intersects four established literatures. We organise the
review around those four threads, taking care to identify, for each,
the specific result that motivates a methodological choice in our own
design or that frames the contribution of our findings.

## 2.1 Event studies and intraday price discovery

The event-study method, formalised in its modern shape by
@mackinlay1997event, exploits the proposition that, under semi-strong
market efficiency [@fama1970efficient], the price response to an
informational event reveals its market-relevant content. The
classical approach computes abnormal returns relative to a market
model on daily data; the high-frequency extension reduces the
observation horizon to intraday windows of seconds or minutes.

The canonical high-frequency study on macro news is
@andersen2003micro, which uses six years of real-time foreign-exchange
quotes to characterise the conditional mean response of major USD
pairs to scheduled macroeconomic announcements. Two features of that
literature inform our design. First, the appropriate benchmark in the
high-frequency setting is a matched non-event window of the same
length, not a long-horizon market model, because intraday volatility
is dominated by hour-of-day and day-of-week seasonality that would
otherwise contaminate the abnormal-return estimate. Second, on FX,
USD strength is a derived quantity: a study that uses the EUR/USD
price directly to test a USD-oriented hypothesis (e.g., "good news
for the dollar produces a positive reaction") will assign the wrong
sign to every event whose target asset is the dollar rather than the
euro. We adopt both conventions: a matched, hour-of-day and
day-of-week stratified baseline (Section 4.4) and an explicit USD
proxy convention $r^{\text{USD}} = -r^{\text{EURUSD}}$ (Section 4.2).

Most of the existing high-frequency event-study literature focuses on
scheduled macro releases-CPI, non-farm payrolls, central-bank
decisions-because the release time is known in advance and clean
event windows are straightforward to construct. Unscheduled news,
such as geopolitical escalations or political statements, has
received comparatively less attention at the intraday horizon. Our
sample is dominated by such unscheduled events (we deliberately
filter out the publisher's `$MACRO` tag, which marks scheduled
releases), placing the analysis closer to the spirit of the news-text
literature than to the macro-announcement tradition.

## 2.2 Financial sentiment analysis: from dictionaries to LLMs

The textual analysis of financial news as a predictor of returns
begins with @tetlock2007giving, who shows that the fraction of
negatively-valenced words in the Wall Street Journal "Abreast of the
Market" column predicts next-day index returns and reverses over the
following week. Tetlock uses the Harvard IV-4 General Inquirer
dictionary, an inheritance from political-science content analysis.

@loughran2011liability subsequently establish that general-purpose
sentiment dictionaries misclassify a large share of words in
financial text-the canonical example is "liability," which is
financially neutral but Harvard-negative-and they construct a
finance-specific dictionary that has since become the standard
baseline in the field. We use the @loughran2011liability dictionary
explicitly as our reference baseline against which the LLM-derived
sentiment must improve in order to justify the methodological choice
of an LLM (Section 5.2). We do not use Harvard IV-4, partly because
@loughran2011liability themselves demonstrate its inadequacy in this
context.

@antweiler2004talk and @bollen2011twitter extend the textual-analysis
program from professional newspaper text to user-generated content
(stock message boards and Twitter respectively), demonstrating in
both settings that simple bullishness counts have non-trivial
predictive content for return and volatility, albeit small. Our
study is in this tradition in that the FinancialJuice Discord feed is
a real-time professional-curated aggregator broadcast to a primarily
retail audience, rather than a peer-reviewed wire service.

The modern wave of work uses neural language models. @heston2017news
benchmark a Thomson-Reuters proprietary neural network against
Harvard and Loughran-McDonald on a large news corpus and find that
the neural model captures both faster and more persistent reactions,
particularly for negative stories. @yang2020finbert release FinBERT,
a BERT-family model pre-trained on a 4.9-billion-token corpus of
financial communications, with state-of-the-art results on the
Financial PhraseBank benchmark. @calomiris2019news combine topic
modelling with sentiment and unusualness ("entropy") signals on a
multi-country Reuters corpus and show predictive content for
country-level returns and volatilities at horizons up to one year. We
extend this line of work to a contemporary large-language-model
classifier ($\texttt{deepseek-v4-flash}$) applied to a real-time
chat-aggregated news feed, with explicit benchmarking against the
dictionary baseline and a self-consistency check against a more
capable sibling model.

## 2.3 Online news, sentiment, and intraday reactions

The intersection of social or online news with intraday market
behaviour has been studied at the daily horizon by
@bollen2011twitter (mood from Twitter predicts the Dow Jones at
several days' lead) and at the search-volume level by @da2015fears
(aggregated Google Trends queries for words like "recession" and
"bankruptcy" predict short-term return reversals and volatility
increases). @antweiler2004talk show that the volume rather than the
direction of message-board posts predicts realised volatility-a
result we revisit in Section 5.6 with our $\log(\text{cluster size})$
control, where larger news bursts produce larger magnitude reactions
even after controlling for the LLM sentiment and category labels.

The relatively under-explored corner of this map is the
sub-fifteen-minute response to unscheduled news on a real-time public
chat feed, which is precisely the setting our dataset addresses.

## 2.4 Multiple testing and reproducibility

A practical concern when running a large pre-specified hypothesis
battery is that the number of tested cells inflates the family-wise
type-I error far beyond the nominal level. We follow the
Benjamini-Hochberg procedure [@benjamini1995controlling] and report
$q$-values that control the false discovery rate across the union of
all $p$-values produced by the pipeline. The procedure is more
appropriate than the Bonferroni correction for a large hypothesis
family in which a non-trivial fraction of nulls are expected to be
false. All conclusions in Section 5 are drawn from $q$-values, with
raw $p$-values reported for transparency. The full pipeline, the
seed, and the LLM cache are documented in the Reproducibility
Statement to support direct replication.
