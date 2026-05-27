"""Build the short SIAT Word paper as a standalone .docx file.

The script writes a minimal OpenXML document using only the Python
standard library, so it does not require python-docx or Word automation.
"""

from __future__ import annotations

import datetime as dt
import os
import re
import struct
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "siat"
OUT_DOCX = OUT_DIR / "Nedelcu_Andrei-Calin_Unexpected_Online_Financial_News_Intraday_Market_Reactions.docx"
FIGURE = ROOT / "paper" / "figures" / "figure_1_event_time_profile.png"

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"


def clean_words(text: str) -> list[str]:
    return re.findall(r"[A-Za-z0-9]+(?:[-'][A-Za-z0-9]+)?", text)


def run(text: str, *, bold: bool = False, italic: bool = False, size: int | None = None) -> str:
    props = []
    if bold:
        props.append("<w:b/>")
    if italic:
        props.append("<w:i/>")
    if size is not None:
        props.append(f'<w:sz w:val="{size}"/>')
        props.append(f'<w:szCs w:val="{size}"/>')
    rpr = f"<w:rPr>{''.join(props)}</w:rPr>" if props else ""
    preserve = ' xml:space="preserve"' if text.startswith(" ") or text.endswith(" ") else ""
    return f"<w:r>{rpr}<w:t{preserve}>{escape(text)}</w:t></w:r>"


def para(
    text: str = "",
    *,
    style: str | None = None,
    align: str | None = None,
    bold: bool = False,
    italic: bool = False,
    size: int | None = None,
    before: int | None = None,
    after: int | None = None,
    first_line: int | None = None,
    hanging: int | None = None,
) -> str:
    ppr = []
    if style:
        ppr.append(f'<w:pStyle w:val="{style}"/>')
    if align:
        ppr.append(f'<w:jc w:val="{align}"/>')
    spacing = []
    if before is not None:
        spacing.append(f'w:before="{before}"')
    if after is not None:
        spacing.append(f'w:after="{after}"')
    spacing.append('w:line="360"')
    spacing.append('w:lineRule="auto"')
    ppr.append(f"<w:spacing {' '.join(spacing)}/>")
    if first_line is not None:
        ppr.append(f'<w:ind w:firstLine="{first_line}"/>')
    if hanging is not None:
        ppr.append(f'<w:ind w:left="{hanging}" w:hanging="{hanging}"/>')
    return f"<w:p><w:pPr>{''.join(ppr)}</w:pPr>{run(text, bold=bold, italic=italic, size=size)}</w:p>"


def heading(text: str, level: int = 1) -> str:
    return para(text, style=f"Heading{level}", before=180 if level == 1 else 120, after=60)


def table(rows: list[list[str]]) -> str:
    n_cols = max(len(r) for r in rows)
    grid_cols = "".join('<w:gridCol w:w="1600"/>' for _ in range(n_cols))
    out = [
        "<w:tbl>",
        "<w:tblPr>",
        '<w:tblW w:w="0" w:type="auto"/>',
        '<w:tblBorders><w:top w:val="single" w:sz="4" w:space="0" w:color="808080"/>'
        '<w:left w:val="single" w:sz="4" w:space="0" w:color="808080"/>'
        '<w:bottom w:val="single" w:sz="4" w:space="0" w:color="808080"/>'
        '<w:right w:val="single" w:sz="4" w:space="0" w:color="808080"/>'
        '<w:insideH w:val="single" w:sz="4" w:space="0" w:color="D0D0D0"/>'
        '<w:insideV w:val="single" w:sz="4" w:space="0" w:color="D0D0D0"/></w:tblBorders>',
        "<w:tblLook w:firstRow=\"1\" w:noHBand=\"0\" w:noVBand=\"1\"/>",
        "</w:tblPr>",
        f"<w:tblGrid>{grid_cols}</w:tblGrid>",
    ]
    for r_idx, row in enumerate(rows):
        out.append("<w:tr>")
        for cell in row:
            shade = '<w:shd w:fill="E9EEF5"/>' if r_idx == 0 else ""
            out.append(
                "<w:tc><w:tcPr>"
                '<w:tcW w:w="1600" w:type="dxa"/>'
                f"{shade}</w:tcPr>"
                f"{para(cell, bold=(r_idx == 0), size=20, after=0)}"
                "</w:tc>"
            )
        out.append("</w:tr>")
    out.append("</w:tbl>")
    return "".join(out)


def png_size(path: Path) -> tuple[int, int]:
    data = path.read_bytes()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError(f"Not a PNG: {path}")
    return struct.unpack(">II", data[16:24])


def image_para(path: Path, rid: str, *, max_width_in: float = 5.85, max_height_in: float = 2.75) -> str:
    width_px, height_px = png_size(path)
    width_emu = int(max_width_in * 914400)
    height_emu = int(width_emu * height_px / width_px)
    max_height_emu = int(max_height_in * 914400)
    if height_emu > max_height_emu:
        height_emu = max_height_emu
        width_emu = int(height_emu * width_px / height_px)
    return f"""
<w:p>
  <w:pPr><w:jc w:val="center"/><w:spacing w:before="60" w:after="60" w:line="360" w:lineRule="auto"/></w:pPr>
  <w:r>
    <w:drawing>
      <wp:inline distT="0" distB="0" distL="0" distR="0"
        xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing">
        <wp:extent cx="{width_emu}" cy="{height_emu}"/>
        <wp:effectExtent l="0" t="0" r="0" b="0"/>
        <wp:docPr id="1" name="Event-time profile"/>
        <wp:cNvGraphicFramePr/>
        <a:graphic xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
          <a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture">
            <pic:pic xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture">
              <pic:nvPicPr>
                <pic:cNvPr id="0" name="{escape(path.name)}"/>
                <pic:cNvPicPr/>
              </pic:nvPicPr>
              <pic:blipFill>
                <a:blip r:embed="{rid}"/>
                <a:stretch><a:fillRect/></a:stretch>
              </pic:blipFill>
              <pic:spPr>
                <a:xfrm><a:off x="0" y="0"/><a:ext cx="{width_emu}" cy="{height_emu}"/></a:xfrm>
                <a:prstGeom prst="rect"><a:avLst/></a:prstGeom>
              </pic:spPr>
            </pic:pic>
          </a:graphicData>
        </a:graphic>
      </wp:inline>
    </w:drawing>
  </w:r>
</w:p>
"""


TITLE = "Unexpected Online Financial News and Intraday Market Reactions"
AUTHORS = "Andrei Calin Nedelcu; Andrei Cheroiu"
SCHOOL = "Colegiul National de Informatica Tudor Vianu, Bucharest"


ABSTRACT = (
    "We test whether unscheduled online financial news is followed by intraday market reactions. "
    "Using 2,449 FinancialJuice headlines and one-minute EUR/USD and Nasdaq-100 prices, we label "
    "events with an LLM and compare event windows with matched baselines. News windows move "
    "1.3x-1.9x more than normal. Directional prediction is weaker, with 49%-54% hit rates, so the "
    "main empirical result is volatility detection rather than directional prediction alone."
)

KEYWORDS = (
    "financial news; event study; intraday prices; EUR/USD; Nasdaq-100; sentiment analysis; "
    "large language models"
)


INTRO = [
    (
        "Financial markets react to information, but the timing and strength of that reaction are "
        "hard to measure when news arrives continuously through online feeds. Scheduled macroeconomic "
        "announcements have exact release times and are widely studied. Unscheduled headlines are "
        "noisier: they often arrive through terminals, social platforms, or public reposting channels."
    ),
    (
        "Online newsfeeds such as the FinancialJuice Discord channel are followed in real time by "
        "many retail traders, yet evidence on whether such public feeds carry market-moving "
        "information at publication is sparse. If the public timestamp is not the true event time, "
        "the visible headline can arrive after the market has started moving."
    ),
    (
        "In Schumpeter's view, innovation often comes from new combinations of existing elements; "
        "here, that combination is a modern LLM, a classical event-study design, and a real-time "
        "online news source."
    ),
    (
        "This paper asks whether EUR/USD and the Nasdaq-100 move more than normal after an "
        "unscheduled headline, and whether language-model sentiment predicts the direction of that "
        "move. It makes four contributions. First, it builds a reproducible news-price dataset. "
        "Second, it separates magnitude from direction. Third, it documents that asset-specific LLM "
        "labels differ for USD and NDX on 73.5% of events. Fourth, it validates the classifier on "
        "Financial PhraseBank. It also highlights pre-event drift as a warning that repost timestamps "
        "are not always true information-arrival times."
    ),
]


DATA = [
    (
        "The news source is a public Discord export of FinancialJuice headlines covering 24 March "
        "2025 to 5 May 2026. The raw feed contains 63,016 messages. We keep only messages marked as "
        "breaking or high-importance and remove scheduled macroeconomic releases, leaving 2,449 "
        "unscheduled events. These events form 1,405 clusters when messages less than 15 minutes "
        "apart are grouped together. All timestamps are converted to UTC."
    ),
    (
        "The market data are one-minute OHLCV bars for EUR/USD and a Nasdaq-100 CFD from Dukascopy "
        "over the same period. EUR/USD is used as a proxy for the U.S. dollar reaction, while the "
        "Nasdaq-100 captures the reaction of a technology-heavy equity index. Combining the filtered "
        "headlines with one-minute prices creates 24,490 event-window rows and 14,050 cluster-window "
        "rows across the main windows used in the analysis."
    ),
    (
        "The filtering rule is intentionally conservative. Scheduled macro releases are removed "
        "because they are anticipated and would dominate the sample with well-known events such as "
        "inflation, employment, and central-bank announcements. The remaining events are closer to "
        "the type of news a trader, analyst, or student observer would experience as unexpected "
        "headline flow: geopolitical developments, policy comments, corporate-risk headlines, and "
        "market-moving updates that are not tied to a pre-announced calendar time."
    ),
]


METHOD = [
    (
        "The empirical design is an event study. For each headline we measure log price changes "
        "after the event over 5, 15, and 60 minute windows. We compare those event-window moves with "
        "a matched baseline drawn from non-event minutes with the same asset, window length, "
        "hour-of-day, and day-of-week. This matching step matters because intraday volatility is not "
        "constant: market moves around the New York open or during active macro hours are naturally "
        "larger than moves during quiet periods."
    ),
    (
        "Each headline is classified by DeepSeek-v4-flash with eight few-shot examples and API "
        "temperature 0.1. The prompt asks for separate sentiment labels for USD and NDX, because the "
        "same news can be good for the dollar and bad for equities. We compare the LLM with two "
        "standard baselines: the Loughran-McDonald finance dictionary and FinBERT-tone. Since many "
        "statistical tests are run, we report Benjamini-Hochberg adjusted q-values. This correction "
        "controls for testing many hypotheses at once, so a single lucky significant result receives "
        "less weight."
    ),
    (
        "For magnitude, the main statistic is the ratio between the average absolute return in an "
        "event window and the average absolute return in its matched baseline. A ratio above 1 means "
        "that the event window moved more than normal. For direction, the statistic is the hit rate: "
        "the percentage of non-neutral predictions whose sign matches the realised return. This is "
        "stricter than simply asking whether the event was important, because it asks whether the "
        "classifier correctly predicted the side of the market move."
    ),
]


RESULTS = [
    (
        "The clearest finding is on magnitude. Direction is harder to predict, as shown below. "
        "Across both assets and all three main windows, event-window absolute returns are larger than "
        "matched non-event returns. For EUR/USD, the event/baseline ratio falls from 1.76x at 5 "
        "minutes to 1.58x at 60 minutes, with 1.69x at 15 minutes. The Nasdaq-100 shows a similar "
        "pattern at slightly lower levels: 1.56x at 5 minutes, 1.57x at 15 minutes, and 1.43x at "
        "60 minutes. All six primary cells are significant after false-discovery-rate correction."
    ),
    (
        "Table 1 reports the core magnitude result. The values are small in ordinary percentage-point "
        "terms because the windows are short, but they are economically meaningful relative to the "
        "normal one-minute market environment. For example, a 15-minute EUR/USD event window has an "
        "average absolute return of 0.0532%, compared with 0.0314% in matched baseline windows."
    ),
    (
        "A concrete example illustrates the magnitude effect at the upper end of its range. On 9 April "
        "2025 at 17:21 UTC the FinancialJuice feed posted: \"BREAKING: Trump: 90-day pause applies to "
        "reciprocal and 10% tariffs.\" The LLM labelled this event bullish for the Nasdaq-100 with "
        "0.80 confidence and bearish for the U.S. dollar. Over the next 15 minutes the Nasdaq-100 "
        "rose by 2.53%, more than fifteen times the typical 15-minute baseline move, and EUR/USD "
        "moved consistently with the predicted USD weakness. Both signs of the LLM call matched the "
        "realised market response."
    ),
    (
        "The same week also shows why direction is harder than magnitude. In an isolated event on "
        "11 April 2025, a headline that the United States had warned China against retaliation was "
        "labelled bearish for the Nasdaq-100, yet the index rose by about 1.00% over the next "
        "15 minutes. Examples like this explain why we treat sentiment as a modest directional signal "
        "rather than the central result."
    ),
]


H1_TABLE = [
    ["Asset", "5 min", "15 min", "60 min"],
    ["EUR/USD event |r|", "0.0324%", "0.0532%", "0.0993%"],
    ["EUR/USD baseline |r|", "0.0184%", "0.0314%", "0.0630%"],
    ["EUR/USD ratio", "1.76x", "1.69x", "1.58x"],
    ["Nasdaq-100 event |r|", "0.0839%", "0.1441%", "0.2682%"],
    ["Nasdaq-100 baseline |r|", "0.0539%", "0.0920%", "0.1874%"],
    ["Nasdaq-100 ratio", "1.56x", "1.57x", "1.43x"],
]


MORE_RESULTS = [
    (
        "The range and maximum-move measures lead to the same conclusion as absolute returns. "
        "Event-window high-low ranges are about 1.5x-1.8x the matched baseline, and maximum absolute "
        "intra-window moves are also consistently elevated. This matters because the result is not "
        "driven by one particular return definition. Whether the window is measured by close-to-close "
        "movement, high-low range, or the largest move inside the window, the news windows are "
        "systematically more volatile."
    ),
    (
        "The directional signal is weaker. When neutral labels are removed, the LLM hit rate ranges "
        "from 49% to 54% across the main asset-window cells. It beats the Loughran-McDonald dictionary "
        "by roughly 1-6 percentage points and is competitive with FinBERT, but the advantage is not "
        "large enough to justify a standalone buy/sell rule after typical intraday costs. This "
        "calibrates the direction result: useful for interpreting sentiment, but much weaker than "
        "the magnitude signal."
    ),
    (
        "When nearby headlines are grouped into event clusters, the strongest directional cell is "
        "Nasdaq-100 at 5 minutes, with a 53.9% hit rate after FDR correction. This improves the "
        "signal but remains far weaker than the magnitude result."
    ),
    (
        "The 73.5% cross-asset disagreement rate is a distinct advantage of the LLM approach. The "
        "language model gives different USD and NDX labels on nearly three quarters of events, which "
        "matters for macro-financial headlines where the dollar and equity market often react in "
        "opposite ways. A dictionary score or a single FinBERT polarity label cannot represent that "
        "two-asset logic without additional modelling."
    ),
    (
        "To check whether the LLM is simply overfitting the event sample, we also run an external "
        "validation on Financial PhraseBank, a standard finance-NLP benchmark with human labels by "
        "sixteen finance professionals. On 4,840 sentences, the LLM reaches 84.6% accuracy, "
        "macro-F1 of 0.836, a balanced three-class score, and Cohen's kappa of 0.717, a measure of "
        "agreement beyond chance, against the gold labels. On the same benchmark, FinBERT-tone "
        "reaches 79.2% accuracy and kappa of 0.60, while the "
        "Loughran-McDonald dictionary reaches 57.4% accuracy and kappa of 0.22. This benchmark does "
        "not prove that every FinancialJuice label is correct, but it shows that the model performs "
        "well against an independent finance-text standard."
    ),
    (
        "Several robustness checks support the main interpretation. The magnitude result remains "
        "visible before and after the LLM training-data cutoff, which reduces the concern that the "
        "model simply memorised later events. It also survives winsorisation, where extreme price "
        "moves are capped before re-estimating the tests. Finally, a descriptive cluster-gap check "
        "shows that the conclusion is stable when nearby headlines are grouped more tightly or more "
        "loosely. These checks do not make the study perfect, but they make the core volatility "
        "finding harder to explain as a single modelling artefact."
    ),
    (
        "The most important methodological finding concerns timing. The fifteen minutes before the "
        "Discord headline already contain abnormal movement: EUR/USD pre-event absolute return is "
        "0.053% against a 0.031% baseline, while NDX is 0.158% against 0.092%. The most cautious "
        "explanation is feed latency: the public Discord timestamp is not necessarily the first moment "
        "the market learned the information. Future event studies using online feeds should therefore "
        "report pre-event drift rather than assuming that the visible headline timestamp is the true "
        "event time."
    ),
]


IMPLICATIONS = [
    (
        "The results connect two ideas from the literature. Event-study methods provide a way to "
        "measure abnormal price movement around a timestamp, while financial-text methods provide a "
        "way to convert headlines into quantitative signals. The contribution here is to apply both "
        "to a modern online newsfeed, to compare an LLM with conventional text baselines on the same "
        "events, and to show why timestamp quality matters in online-news event studies."
    ),
    (
        "The limitation is also clear. Public reposted news is not a clean timestamp of information "
        "arrival, and the LLM labels have not yet been manually audited on the specific FinancialJuice "
        "headlines. The external PhraseBank benchmark reduces this concern but does not eliminate it. "
        "Future work should add a human-labelled subsample and cleaner primary-source timestamps. For "
        "the present study, the conservative conclusion is that unexpected online headlines reliably "
        "identify abnormal short-term movement, while directional prediction remains much less certain."
    ),
]


CONCLUSIONS = [
    (
        "Unscheduled online financial news is associated with clear intraday market reactions. In a "
        "sample of 2,449 FinancialJuice headlines, EUR/USD and Nasdaq-100 event windows show absolute "
        "returns about 1.3x-1.9x larger than matched non-event windows. This result is robust across "
        "assets, windows, and several specification checks."
    ),
    (
        "The direction of the reaction is harder to predict. LLM sentiment performs better than a "
        "finance dictionary and is competitive with FinBERT, but hit rates of 49%-54% remain a modest "
        "directional signal. The main lesson is therefore not that online news directly predicts "
        "direction, but that it identifies moments when short-term volatility is unusually high."
    ),
    (
        "Future work should add a human validation sample for the specific FinancialJuice headlines, "
        "collect primary-source timestamps when possible, and test whether the same design generalises "
        "to other assets such as gold, oil, rates, or single stocks. The same tools also make this "
        "type of empirical finance research more accessible: the analysis relies on public APIs, "
        "open-source statistical libraries, and market data that can be audited and reused. This "
        "study shows that a reproducible pipeline can still produce a useful empirical finding: in "
        "modern markets, online news is immediately visible in intraday volatility, but direction "
        "remains the harder problem."
    ),
]


REFERENCES = [
    "Andersen, T. G., Bollerslev, T., Diebold, F. X., and Vega, C. (2003). Micro effects of macro announcements: Real-time price discovery in foreign exchange. American Economic Review.",
    "Benjamini, Y., and Hochberg, Y. (1995). Controlling the false discovery rate: A practical and powerful approach to multiple testing. Journal of the Royal Statistical Society.",
    "Heston, S. L., and Sinha, N. R. (2017). News vs. sentiment: Predicting stock returns from news stories. Financial Analysts Journal.",
    "Loughran, T., and McDonald, B. (2011). When is a liability not a liability? Textual analysis, dictionaries, and 10-Ks. Journal of Finance.",
    "MacKinlay, A. C. (1997). Event studies in economics and finance. Journal of Economic Literature.",
    "Malo, P., Sinha, A., Korhonen, P., Wallenius, J., and Takala, P. (2014). Good debt or bad debt: Detecting semantic orientations in economic texts. Journal of the Association for Information Science and Technology.",
    "Schumpeter, J. A. (1934). The Theory of Economic Development. Harvard University Press.",
    "Tetlock, P. C. (2007). Giving content to investor sentiment: The role of media in the stock market. Journal of Finance.",
    "Yang, Y., Uy, M. C. S., and Huang, A. (2020). FinBERT: A pretrained language model for financial communications. arXiv preprint.",
]


def document_xml() -> tuple[str, int]:
    parts: list[str] = []
    all_text: list[str] = []

    def add(p: str, text_for_count: str = "") -> None:
        parts.append(p)
        if text_for_count:
            all_text.append(text_for_count)

    add(para(TITLE, align="center", bold=True, size=32, before=0, after=80), TITLE)
    add(para(AUTHORS, align="center", size=24, after=20), AUTHORS)
    add(para(SCHOOL, align="center", italic=True, size=22, after=160), SCHOOL)

    add(heading("Abstract"), "Abstract")
    add(para(ABSTRACT, after=80), ABSTRACT)
    add(para(f"Keywords: {KEYWORDS}", bold=True, after=120), KEYWORDS)

    add(heading("Introduction"), "Introduction")
    for p in INTRO:
        add(para(p, first_line=360, after=60), p)

    add(heading("Scientific content"), "Scientific content")
    add(heading("Data", 2), "Data")
    for p in DATA:
        add(para(p, first_line=360, after=60), p)

    add(heading("Method", 2), "Method")
    for p in METHOD:
        add(para(p, first_line=360, after=60), p)

    add(heading("Main results", 2), "Main results")
    for p in RESULTS:
        add(para(p, first_line=360, after=60), p)
    add(table(H1_TABLE))
    add(para("Table 1. Event-window absolute return magnitude versus matched baseline.", align="center", italic=True, size=20, after=80))

    if FIGURE.exists():
        add(image_para(FIGURE, "rId1"))
        add(para("Figure 1. Average absolute-return profile around FinancialJuice headlines.", align="center", italic=True, size=20, after=80))

    for p in MORE_RESULTS:
        add(para(p, first_line=360, after=60), p)

    add(heading("Implications and limitations", 2), "Implications and limitations")
    for p in IMPLICATIONS:
        add(para(p, first_line=360, after=60), p)

    add(heading("Conclusions"), "Conclusions")
    for p in CONCLUSIONS:
        add(para(p, first_line=360, after=60), p)

    add(heading("References"), "References")
    for ref in REFERENCES:
        add(para(ref, hanging=360, after=20, size=20), ref)

    body = "".join(parts)
    sect = (
        "<w:sectPr>"
        '<w:pgSz w:w="11906" w:h="16838"/>'
        '<w:pgMar w:top="1417" w:right="1417" w:bottom="1417" w:left="1417" '
        'w:header="720" w:footer="720" w:gutter="0"/>'
        "</w:sectPr>"
    )
    xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        f"<w:body>{body}{sect}</w:body></w:document>"
    )
    return xml, len(clean_words(" ".join(all_text)))


def styles_xml() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:docDefaults>
    <w:rPrDefault>
      <w:rPr>
        <w:rFonts w:ascii="Times New Roman" w:hAnsi="Times New Roman" w:cs="Times New Roman"/>
        <w:sz w:val="24"/><w:szCs w:val="24"/>
      </w:rPr>
    </w:rPrDefault>
    <w:pPrDefault>
      <w:pPr><w:spacing w:line="360" w:lineRule="auto"/></w:pPr>
    </w:pPrDefault>
  </w:docDefaults>
  <w:style w:type="paragraph" w:default="1" w:styleId="Normal">
    <w:name w:val="Normal"/>
    <w:rPr><w:rFonts w:ascii="Times New Roman" w:hAnsi="Times New Roman"/><w:sz w:val="24"/></w:rPr>
  </w:style>
  <w:style w:type="paragraph" w:styleId="Heading1">
    <w:name w:val="Heading 1"/><w:basedOn w:val="Normal"/><w:next w:val="Normal"/><w:qFormat/>
    <w:pPr><w:keepNext/><w:spacing w:before="180" w:after="60" w:line="360" w:lineRule="auto"/><w:outlineLvl w:val="0"/></w:pPr>
    <w:rPr><w:rFonts w:ascii="Times New Roman" w:hAnsi="Times New Roman"/><w:b/><w:sz w:val="28"/></w:rPr>
  </w:style>
  <w:style w:type="paragraph" w:styleId="Heading2">
    <w:name w:val="Heading 2"/><w:basedOn w:val="Normal"/><w:next w:val="Normal"/><w:qFormat/>
    <w:pPr><w:keepNext/><w:spacing w:before="120" w:after="40" w:line="360" w:lineRule="auto"/><w:outlineLvl w:val="1"/></w:pPr>
    <w:rPr><w:rFonts w:ascii="Times New Roman" w:hAnsi="Times New Roman"/><w:b/><w:i/><w:sz w:val="24"/></w:rPr>
  </w:style>
</w:styles>"""


def content_types_xml(include_png: bool) -> str:
    png = '<Default Extension="png" ContentType="image/png"/>' if include_png else ""
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  {png}
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
  <Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
  <Override PartName="/word/settings.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.settings+xml"/>
  <Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
  <Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>
</Types>"""


def package_rels_xml() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
  <Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>
</Relationships>"""


def doc_rels_xml(include_png: bool) -> str:
    img_rel = (
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" '
        'Target="media/figure_1_event_time_profile.png"/>'
        if include_png
        else ""
    )
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  {img_rel}
  <Relationship Id="rIdStyles" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
  <Relationship Id="rIdSettings" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/settings" Target="settings.xml"/>
</Relationships>"""


def settings_xml() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:settings xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:zoom w:percent="100"/>
  <w:proofState w:spelling="clean" w:grammar="clean"/>
</w:settings>"""


def core_xml() -> str:
    now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties
  xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
  xmlns:dc="http://purl.org/dc/elements/1.1/"
  xmlns:dcterms="http://purl.org/dc/terms/"
  xmlns:dcmitype="http://purl.org/dc/dcmitype/"
  xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <dc:title>{escape(TITLE)}</dc:title>
  <dc:creator>{escape(AUTHORS)}</dc:creator>
  <cp:lastModifiedBy>Codex</cp:lastModifiedBy>
  <dcterms:created xsi:type="dcterms:W3CDTF">{now}</dcterms:created>
  <dcterms:modified xsi:type="dcterms:W3CDTF">{now}</dcterms:modified>
</cp:coreProperties>"""


def app_xml() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties"
  xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">
  <Application>Codex OpenXML builder</Application>
  <DocSecurity>0</DocSecurity>
  <ScaleCrop>false</ScaleCrop>
  <Company/>
  <LinksUpToDate>false</LinksUpToDate>
  <SharedDoc>false</SharedDoc>
  <HyperlinksChanged>false</HyperlinksChanged>
  <AppVersion>16.0000</AppVersion>
</Properties>"""


def build() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    document, word_count = document_xml()
    include_png = FIGURE.exists()
    try:
        zf = zipfile.ZipFile(OUT_DOCX, "w", compression=zipfile.ZIP_DEFLATED)
    except PermissionError as exc:
        raise SystemExit(
            f"Cannot overwrite {OUT_DOCX.name}. Close it in Word/Preview and rerun."
        ) from exc

    with zf as z:
        z.writestr("[Content_Types].xml", content_types_xml(include_png))
        z.writestr("_rels/.rels", package_rels_xml())
        z.writestr("word/document.xml", document)
        z.writestr("word/styles.xml", styles_xml())
        z.writestr("word/settings.xml", settings_xml())
        z.writestr("word/_rels/document.xml.rels", doc_rels_xml(include_png))
        z.writestr("docProps/core.xml", core_xml())
        z.writestr("docProps/app.xml", app_xml())
        if include_png:
            z.write(FIGURE, "word/media/figure_1_event_time_profile.png")

    print(f"Wrote {OUT_DOCX}")
    print(f"Approximate text word count: {word_count}")


if __name__ == "__main__":
    os.chdir(ROOT)
    build()
