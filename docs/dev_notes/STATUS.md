# Status proiect

> **Development note.** Historical project-status tracker; current
> outputs are generated from the pipeline and LaTeX sources.

Ultima actualizare: 2026-05-06, dupa extensii cluster/z-score/robustete.

## Stadiu curent

Pipeline-ul tehnic ruleaza end-to-end si are validator automat. Rezultatele au fost recalibrate metodologic fata de versiunea initiala, deci paper-ul trebuie scris cu un ton mai conservator.

## Ce s-a reparat

- `event_study.py` a fost refacut pentru:
  - filtrare automata la intervalul comun evenimente-preturi;
  - aliniere post-event la primul minut complet dupa timestamp;
  - aliniere pre-event la ultimul minut complet inainte de timestamp;
  - conventie corecta pentru EUR/USD: `sentiment_usd` este testat contra `-EUR/USD`;
  - clustere de evenimente la 15 minute;
  - baseline matched pe ora UTC si ziua saptamanii;
  - erori robuste/clusterizate pentru OLS;
  - q-values FDR Benjamini-Hochberg;
  - `range_pct`, `max_abs_move_pct`, `abnormal_return_pct` si z-score-uri matched-baseline;
  - output cluster-level explicit in `cluster_event_study_windows.csv`;
  - teste cluster sentiment, range/max-move, abnormal z, pre/post cutoff, target categories, multivariate controls si winsorization;
  - H4 summary separat de perioade (`h4_results.csv` si `h4_periods.csv`);
  - H8 fara `mean_post_abs = NaN`;
  - H10 cu caveat explicit pentru volum proxy.
- `parse_fj_discord.py` include acum categoria `corporate`.
- `download_prices.py` descarca implicit din `2025-03-24` pana azi UTC si poate face merge cu CSV-urile existente.
- `validate_outputs.py` verifica automat output-urile sensibile metodologic.
- Infrastructura locala pentru validare manuala a fost scoasa din release-ul curent; validarea umana ramane follow-up.
- `requirements.txt` include dependintele statistice reale.

## Date curente

- Mesaje parsate: 63,016.
- Evenimente gold: 2,449.
- Evenimente folosite in event-study dupa filtrarea intervalului comun: 2,449.
- Evenimente eliminate in afara intervalului de preturi: 0.
- Clustere de evenimente, gap 15 minute: 1,405.
- Randuri event-window: 24,490.
- Randuri cluster-window: 14,050.
- Preturi:
  - EUR/USD: 416,500 bare 1-min, `2025-03-24` -> `2026-05-05`.
  - NDX CFD: 381,122 bare 1-min, `2025-03-24` -> `2026-05-05`.

## Verdict rezultate dupa corectii

Coloana **Paper** indica destinatia finala in paper:
- **MAIN**: in Section 5 Results, raportat in tabel principal;
- **APX**: doar in Appendix (tabel complet, mentiune scurta in text);
- **LIM**: doar o propozitie in Section 7 Limitations;
- **CUT**: scos complet din raportare (redundant cu alt rezultat).

| H | Verdict | Paper | Nota |
|---|---|---|---|
| H1 | robust | MAIN | Rezultatul central: evenimentele produc miscari absolute peste baseline. §5.1. |
| H2 | modest/mixed | MAIN | Edge directional mic; nu trebuie vandut ca predictor puternic. §5.2. |
| H3 | partial | MAIN | NDX +5m/+15m ramane interesant dupa SE clusterizate. §5.2. |
| H4 | partial | MAIN | NDX closed-period gap semnificativ; EUR/USD marginal. §5.5. |
| H5 | slab/partial | APX | Magnitude labels exploratorii. Consolidat cu H13 intr-o subsectiune scurta. |
| H6 | slab | LIM | Confidence necalibrat. O propozitie in Limitations; tabele in appendix. |
| H7 | partial | CUT | Redundant cu C4 (categorical analysis). Eliminat din raportare. |
| H8 | robust cu caveat | MAIN | Pre-event drift / feed latency, nu dovada directa de front-running. §5.4. |
| H9 | robust | MAIN | Persistenta miscarii. §5.4. |
| H10 | proxy only | LIM | Volumul Dukascopy nu este volum consolidat. Limitations + appendix. |
| H11 | partial | MAIN | Time-of-day, focus EUR/USD. §5.3 (scurt). |
| H12 | slab | LIM | Asimetrie bear/bull mica. O propozitie in Limitations. |
| H13 | slab/partial | APX | Consolidat cu H5 ca "LLM auxiliary labels". |
| H14 | robust dar conventional | MAIN | Cross-asset, scurt. §5.5. |

## Verdict extensii noi

| Output | Verdict | Paper | Nota |
|---|---|---|---|
| C1 Cluster sentiment | partial | MAIN | §5.2, alaturi de H2. |
| C2 Range/max move | foarte robust | MAIN | Cel mai puternic rezultat nou. §5.1. |
| C3 Abnormal z-score | robust | MAIN | §5.1, standardizare. |
| C4 Targeted categories | util | MAIN | §5.3. Inlocuieste H7. |
| C5 Pre/post cutoff | robust | MAIN | §5.6 robustness. |
| C6 Multivariate controls | defensabil | MAIN | §5.6 robustness. |
| C7 Outlier robustness | robust | MAIN | §5.6 robustness. |

## Window strategy in paper

- **Primary in Section 5 tables**: 5m, 15m, 60m.
- **Appendix robustness**: 1m (bid-ask bounce), 240m (margin of "intraday").
- Reduce tabelele cu ~40% fara pierdere de concluzii.

## Comenzi de reproducere

```bash
.venv/Scripts/python.exe parse_fj_discord.py "data/FinancialJuice ... .json" -o outputs/events.csv --summary
.venv/Scripts/python.exe download_prices.py --start 2025-03-24 --merge-existing
.venv/Scripts/python.exe sentiment.py outputs/events.csv -o outputs/events_sentiment.csv --workers 15
.venv/Scripts/python.exe event_study.py
.venv/Scripts/python.exe validate_outputs.py
```

## Ce mai trebuie inainte de paper final

Ordine de prioritate (vezi sectiunea Pre-submission TODO din `Structura_paper.md` pentru detalii):

**Blocking**:
1. Validare manuala sentiment (200 evenimente, 2 etichetatori, Cohen's kappa, F1 vs consens, split pre/post `2026-01-15`) ramane follow-up; nu exista infrastructura activa in release-ul curent.

**Strong nice-to-have**:
2. Baseline comparison cu FinBERT + Loughran-McDonald dictionary (1-2 zile cod). Raspunde la "why LLM, not dictionary?".
3. Case studies cu timestamp verificat la sursa primara (Bloomberg/Reuters) pe 5-10 stiri.

**Submission housekeeping**:
4. `references.bib` in APA 7 verificat manual.
5. Reproducibility statement (link repo, seed, comanda validator).
6. Mentinere preturi actualizate daca exportul de stiri se extinde dupa `2026-05-05`.

## Cleanup proiect aplicat 2026-05-24

- Sters root JSON partial (137KB, 2 zile).
- Sters legacy `docs/Plan_proiect_economie.{md,docx}` si `docs/Structura_paper.docx`.
- Sters `outputs/events_sentiment_new.csv` (test rezidual).
- Sters `__pycache__/`.
- Sters `trader_insights.py` + outputs (redundant cu C4).
- Sters componenta trader si interpretarea practitioner pentru a pastra repo-ul centrat pe paper.
- Componenta de consens intre modele a fost scoasa din release-ul curent.
