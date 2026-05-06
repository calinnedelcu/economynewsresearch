# Status proiect

Ultima actualizare: 2026-05-06, dupa reparatii metodologice.

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
  - H4 summary separat de perioade (`h4_results.csv` si `h4_periods.csv`);
  - H8 fara `mean_post_abs = NaN`;
  - H10 cu caveat explicit pentru volum proxy.
- `parse_fj_discord.py` include acum categoria `corporate`.
- `download_prices.py` descarca implicit din `2025-03-24` pana azi UTC si poate face merge cu CSV-urile existente.
- `make_report.py` genereaza raportul doar din CSV-urile curente, fara rezultate hardcodate.
- `validate_outputs.py` verifica automat output-urile sensibile metodologic.
- `prepare_manual_validation.py` genereaza esantionul de 200 evenimente pentru doi etichetatori.
- `score_manual_validation.py` calculeaza Cohen's kappa si F1 dupa completarea etichetelor.
- `requirements.txt` include dependintele statistice reale.

## Date curente

- Mesaje parsate: 63,016.
- Evenimente gold: 2,449.
- Evenimente folosite in event-study dupa filtrarea intervalului comun: 2,449.
- Evenimente eliminate in afara intervalului de preturi: 0.
- Clustere de evenimente, gap 15 minute: 1,405.
- Preturi:
  - EUR/USD: 416,500 bare 1-min, `2025-03-24` -> `2026-05-05`.
  - NDX CFD: 381,122 bare 1-min, `2025-03-24` -> `2026-05-05`.

## Verdict rezultate dupa corectii

| H | Verdict | Nota pentru paper |
|---|---|---|
| H1 | robust | Rezultatul central: evenimentele produc miscari absolute peste baseline. |
| H2 | modest/mixed | Edge directional mic; nu trebuie vandut ca predictor puternic. |
| H3 | partial | NDX +5m/+15m ramane interesant dupa SE clusterizate. |
| H4 | partial | NDX closed-period gap semnificativ; EUR/USD marginal. |
| H5 | slab/partial | Magnitude labels sunt exploratorii. |
| H6 | slab | Confidence necalibrat; discutat ca limitation. |
| H7 | partial | Categoria `corporate` a fost adaugata; EUR/USD are semnal modest. |
| H8 | robust cu caveat | Formulare corecta: pre-event drift / feed latency, nu dovada directa de front-running. |
| H9 | robust | Persistenta miscarii ramane o constatare solida. |
| H10 | proxy only | Volumul Dukascopy nu este volum consolidat. |
| H11 | partial | Time-of-day mai ales pe EUR/USD. |
| H12 | slab | Asimetrie bear/bull mica. |
| H13 | slab/partial | Surprise-level ajuta mai ales NDX pe termen foarte scurt. |
| H14 | robust dar conventional | Semnul depinde de EUR/USD vs USD proxy. |

## Comenzi de reproducere

```bash
.venv/Scripts/python.exe parse_fj_discord.py "data/FinancialJuice ... .json" -o outputs/events.csv --summary
.venv/Scripts/python.exe download_prices.py --start 2025-03-24 --merge-existing
.venv/Scripts/python.exe sentiment.py outputs/events.csv -o outputs/events_sentiment.csv --workers 15
.venv/Scripts/python.exe event_study.py
.venv/Scripts/python.exe validate_outputs.py
.venv/Scripts/python.exe make_report.py --also-copy docs/report.html
.venv/Scripts/python.exe prepare_manual_validation.py
# dupa completarea etichetelor:
.venv/Scripts/python.exe score_manual_validation.py
```

## Ce mai trebuie inainte de paper final

- Mentinere preturi actualizate daca exportul de stiri se extinde dupa `2026-05-05`.
- Validare manuala a sentimentului pe 200 evenimente:
  - doi etichetatori;
  - Cohen's kappa;
  - F1 LLM vs consens;
  - split pre/post cutoff pentru memorization risk.
- `references.bib` / lista APA 7 verificata.
- Tabel central pentru paper, cu verdict conservator pe fiecare ipoteza.
- Case studies manuale cu timestamp verificat fata de sursa de stire, nu doar fata de Discord.

## Atentie

Fisierele `.docx` din `docs/` sunt originale/legacy. Pentru starea actuala a proiectului, foloseste Markdown-ul si raportul HTML regenerate.
