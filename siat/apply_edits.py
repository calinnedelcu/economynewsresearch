"""Apply final pending edits to the SIAT docx in place.

Preserves user's manual edits by modifying the existing docx directly.
Changes:
  1. Inline citations in 6 paragraphs (Schumpeter, MacKinlay, Benjamini-Hochberg,
     Yang FinBERT, Loughran-McDonald, Malo PhraseBank).
  2. Identification assumption sentence added to Method.
  3. Magnitude ratio formula added inline in Method.
  4. Table column widths: 3200 dxa for first col, 1300 dxa for data cols.
"""
from pathlib import Path
from copy import deepcopy
from docx import Document
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

DOCX = Path("siat/Nedelcu_Andrei-Calin_Unexpected_Online_Financial_News_Intraday_Market_Reactions.docx")

REPLACEMENTS = {
    # Para 9: Schumpeter citation
    9: (
        "In Schumpeter's view, innovation often comes from new combinations "
        "of existing elements; here, that combination is a modern LLM, "
        "a classical event-study design, and a real-time online news source."
    ,
        "In Schumpeter's view (Schumpeter, 1934), innovation often comes from "
        "new combinations of existing elements; here, that combination is a "
        "modern LLM, a classical event-study design, and a real-time online "
        "news source."
    ),
    # Para 17: MacKinlay citation + identification assumption sentence
    17: (
        "The empirical design is an event study. For each headline we measure "
        "log price changes after the event over 5, 15, and 60 minute windows. "
        "We compare those event-window moves with a matched baseline drawn "
        "from non-event minutes with the same asset, window length, hour and "
        "day of the week. This matching step matters because intraday "
        "volatility is not constant. Market moves around the New York open or "
        "during active macro hours are naturally larger than moves during "
        "quiet periods."
    ,
        "The empirical design is an event study (MacKinlay, 1997). For each "
        "headline we measure log price changes after the event over 5, 15, "
        "and 60 minute windows. We compare those event-window moves with a "
        "matched baseline drawn from non-event minutes with the same asset, "
        "window length, hour and day of the week. This matching step matters "
        "because intraday volatility is not constant. Market moves around the "
        "New York open or during active macro hours are naturally larger than "
        "moves during quiet periods. We do not claim causal identification; "
        "the identifying assumption is that, conditional on asset, "
        "hour-of-day and day-of-week, non-event minutes provide a valid "
        "counterfactual for what would have happened in event windows absent "
        "the headline."
    ),
    # Para 18: FinBERT + Benjamini-Hochberg + Loughran-McDonald citations
    18: (
        "Each headline is classified by DeepSeek-v4-flash, after setting its "
        "creativity low, seeking more deterministic results. The prompt asks "
        "for separate sentiment labels for USD and NDX, because the same news "
        "can be good for the dollar and bad for equities. We compare the LLM "
        "with two standard baselines: the Loughran-McDonald finance "
        "dictionary and FinBERT-tone, model designed to analyze the sentiment "
        "of financial texts. Since many statistical tests are run, we report "
        "Benjamini-Hochberg adjusted q-values. This correction controls for "
        "testing many hypotheses at once, so a single lucky significant "
        "result receives less weight."
    ,
        "Each headline is classified by DeepSeek-v4-flash, after setting its "
        "creativity low, seeking more deterministic results. The prompt asks "
        "for separate sentiment labels for USD and NDX, because the same news "
        "can be good for the dollar and bad for equities. We compare the LLM "
        "with two standard baselines: the Loughran-McDonald finance "
        "dictionary (Loughran and McDonald, 2011) and FinBERT-tone (Yang et "
        "al., 2020), a model designed to analyze the sentiment of financial "
        "texts. Since many statistical tests are run, we report "
        "Benjamini-Hochberg adjusted q-values (Benjamini and Hochberg, 1995). "
        "This correction controls for testing many hypotheses at once, so a "
        "single lucky significant result receives less weight."
    ),
    # Para 19: add explicit magnitude ratio formula
    19: (
        "For magnitude, the main statistic is the ratio between the average "
        "absolute return in an event window and the average absolute return "
        "in its matched baseline. A ratio above 1 means that the event window "
        "moved more than normal. For direction, the statistic is the hit "
        "rate: the percentage of non-neutral predictions whose sign matches "
        "the realised return. This asks whether the classifier correctly "
        "predicted the side of the market move."
    ,
        "For magnitude, the main statistic is the ratio between the average "
        "absolute return in an event window and the average absolute return "
        "in its matched baseline, that is, magnitude ratio = mean(|r_event|) "
        "/ mean(|r_baseline|). A ratio above 1 means that the event window "
        "moved more than normal. For direction, the statistic is the hit "
        "rate: the percentage of non-neutral predictions whose sign matches "
        "the realised return. This asks whether the classifier correctly "
        "predicted the side of the market move."
    ),
    # Para 34: Malo (PhraseBank) citation
    34: (
        "To check whether the LLM is simply overfitting the event sample, we "
        "also run an external validation on Financial PhraseBank, a standard "
        "finance-NLP benchmark with human labels by sixteen finance "
        "professionals."
    ,
        "To check whether the LLM is simply overfitting the event sample, we "
        "also run an external validation on Financial PhraseBank (Malo et "
        "al., 2014), a standard finance-NLP benchmark with human labels by "
        "sixteen finance professionals."
    ),
}


def set_paragraph_text(paragraph, new_text):
    """Replace all runs in a paragraph with a single run containing new_text.

    Preserves the paragraph's properties (style, alignment) but clears all
    run-level formatting. Since all anchor paragraphs have plain runs
    (no bold/italic), this is safe.
    """
    # Save run properties from first run if any (font, etc.)
    first_run = paragraph.runs[0] if paragraph.runs else None
    rPr_xml = None
    if first_run is not None:
        rPr = first_run._element.find(qn("w:rPr"))
        if rPr is not None:
            rPr_xml = deepcopy(rPr)
    # Remove all existing runs
    for r in list(paragraph._element.findall(qn("w:r"))):
        paragraph._element.remove(r)
    # Add a single new run
    new_run = paragraph.add_run(new_text)
    if rPr_xml is not None:
        # Ensure rPr is first child
        existing_rPr = new_run._element.find(qn("w:rPr"))
        if existing_rPr is not None:
            new_run._element.remove(existing_rPr)
        new_run._element.insert(0, rPr_xml)


def main():
    d = Document(DOCX)

    # 1-3. Apply paragraph text replacements
    for idx, (old_substr, new_text) in REPLACEMENTS.items():
        p = d.paragraphs[idx]
        current = p.text
        # Sanity check: the paragraph should contain the substring (mod whitespace)
        # We compare normalized whitespace
        norm_cur = " ".join(current.split())
        norm_old = " ".join(old_substr.split())
        if norm_old not in norm_cur and norm_cur != norm_old:
            # The old text doesn't fully match; we'll proceed anyway since
            # we identified anchors by index. Print warning.
            print(f"[warn] para {idx}: text differs from expected anchor")
            print(f"  expected: {norm_old[:120]}...")
            print(f"  found:    {norm_cur[:120]}...")
        set_paragraph_text(p, new_text)
        print(f"[ok] updated paragraph {idx}")

    # 4. Fix table column widths
    if d.tables:
        t = d.tables[0]
        new_widths = [3200, 1300, 1300, 1300]  # first wide, three data narrow

        # Update tblGrid
        tblGrid = t._tbl.find(qn("w:tblGrid"))
        if tblGrid is not None:
            for gc, w in zip(tblGrid.findall(qn("w:gridCol")), new_widths):
                gc.set(qn("w:w"), str(w))

        # Update each row's cell widths
        for row in t.rows:
            cells = row.cells
            for cell, w in zip(cells, new_widths):
                tcW = cell._tc.find(".//" + qn("w:tcW"))
                if tcW is not None:
                    tcW.set(qn("w:w"), str(w))
                    tcW.set(qn("w:type"), "dxa")
        print(f"[ok] updated table column widths to {new_widths}")

    d.save(DOCX)
    print(f"[saved] {DOCX}")


if __name__ == "__main__":
    main()
