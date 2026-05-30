# Style Guide Analysis and Improvement Plan

> **Development note.** Historical planning document; the current
> canonical paper sources are `paper/sections/*.tex`.

Document de lucru. Analizeaza conventiile paper-urilor top-tier in finance
(Journal of Finance, Journal of Financial Economics, Review of Financial
Studies) si propune lista concreta de imbunatatiri pentru paper-ul nostru
ca sa ajunga la nivel de submission credibil.

Surse principale verificate:
- Journal of Finance Style Guidelines (Feb 2017, AFA)
- JFE Submission Guidelines (Elsevier)
- Tetlock 2007 JF (model pentru sentiment+returns)
- Loughran-McDonald 2011 JF (model pentru text+10K)
- Andersen-Bollerslev-Diebold-Vega 2003 AER (model pentru intraday FX)
- Calomiris-Mamaysky 2019 JFE (model pentru text+returns multi-country)
- Heston-Sinha 2017 FAJ (model pentru news vs sentiment)

---

# Partea I: Cum scriu paper-urile top-tier

## 1. Structura standard

Sectiunile sunt aproape universal numerotate cu cifre romane sau arabice
(I/II/III sau 1/2/3). Heading-urile sunt scurte si descriptive, nu
intrebari. Structura tipica pentru un empirical finance paper de
50-60 pagini:

1. **Introduction** (4-6 pagini): motiveaza, plaseaza in literatura cu
   ~5-15 citatii in primele 3 paragrafe, declara contributia explicit
   in 3-4 bullets, anunta findings principale cu cifre concrete, road-map.
2. **Related literature** (3-4 pagini) - optional, uneori integrat in
   Introduction. Daca este separat, este organizat pe sub-teme nu
   cronologic.
3. **Data** (3-5 pagini): sursa, frecventa, perioada, filtre, sample
   sizes finale, Table 1 cu summary statistics.
4. **Methodology** (4-6 pagini): definitii formale (ecuatii
   numerotate), specificatii regresii, conventii, multiple testing.
5. **Main results** (8-15 pagini, cea mai lunga): Tabele 2-N cu
   rezultatele principale. Fiecare tabel are 1-2 paragrafe de
   interpretare. Subsectiunile sunt grupate tematic (volatilitate,
   directie, etc.), nu pe ipoteze.
6. **Robustness** (4-6 pagini): alternative specifications, sub-samples,
   placebo tests. Tabele in main paper sau internet appendix.
7. **Discussion / Mechanism** (2-4 pagini): interpretare economica,
   ce mecanisme sunt consistente cu rezultatele.
8. **Conclusion** (1-2 pagini): re-stateaza findings, limitations, future.
9. **References** (3-5 pagini): toate citatiile, APA-like format JF
   sau Harvard JFE.
10. **Appendix** (5-15 pagini): proofs, variable definitions, robustness.
11. **Internet/Online Appendix** (10-30 pagini, separat): tabele
    suplimentare, robustness extinsa, simulation studies.

Lungime tipica main paper: 40-55 pagini double-spaced sau 25-35 single.
Abstract: 150-250 cuvinte, single paragraf, structurat (motivation -
data - method - findings - implication).

## 2. Tabele

Conventii din JF Style Guide (Feb 2017):
- Self-contained: cititorul nu trebuie sa caute in text ca sa inteleaga
- Maximum 8 coloane in portrait orientation
- Caption lung > 300 cuvinte se muta in definitions appendix
- Footnotes doar pentru detalii tehnice (significance levels, sample
  restrictions)
- Referintele la surse de date in italic in body si tabele

Format standard al unei celule de regresie:
```
0.268***
(0.106)
```
unde 0.268 este coeficientul, 0.106 standard error in paranteze, si
asterisk-urile sunt *p<0.10, **p<0.05, ***p<0.01. Unele paper-uri
folosesc t-statistics in paranteze in loc de SE - declara explicit
in nota tabelului.

Decimale: in mod tipic 2-3 decimale pentru coeficienti de regresie,
3-4 pentru returns intraday (foarte mici), 0-1 pentru sample sizes.

Numerotare: Tabel 1 este aproape intotdeauna summary statistics
(mean, std, min, max, N pe fiecare variabila cheie). Tabel 2 este
prima specificatie principala. Tabelele cresc in complexitate spre
final.

## 3. Figuri

Conventii din JF si JFE:
- Color permis si gratis in versiunea online; verifica si in grayscale
  pentru print
- Axe etichetate cu unitati explicite (e.g. "Abnormal return (\%)")
- Font sans-serif 8-14pt pentru text in figura
- Panels notate Panel A, Panel B, etc. cu titluri proprii
- Caption descriptiv sub figura (5-30 cuvinte) + nota lunga separat

Figura standard intr-un paper de intraday event study este event-time
plot: axa X de la -t la +t minute relativ la event time, axa Y este
average abnormal return cumulativ sau average absolute return.
Tetlock 2007 si Calomiris-Mamaysky 2019 folosesc ambele acest format.

## 4. Citatii

Stil "Author (Year)" pentru in-text:
- Single: Tetlock (2007) shows that...
- Pereche: Loughran and McDonald (2011) propose...
- Trei sau mai multi: Andersen et al. (2003) demonstrate...
- Mai multe in paranteze: ...as documented elsewhere (Tetlock 2007;
  Loughran and McDonald 2011; Calomiris and Mamaysky 2019).

Pagini doar pentru quote-uri directe. Citatie inceput de propozitie
este preferata fata de paranteza la sfarsit cand atribuirea e
importanta.

Densitate tipica: 1-3 citatii per paragraf in Introduction si Lit
Review, 0-1 in Results, 1-2 in Discussion. Total pentru un paper:
50-100 citatii.

Bibliografia este alfabetica pe primul autor. Format JF (APA-like):

> Tetlock, Paul C., 2007, Giving content to investor sentiment: The
> role of media in the stock market, Journal of Finance 62, 1139-1168.

Format JFE (Harvard):

> Tetlock, P. C. (2007). Giving content to investor sentiment: The
> role of media in the stock market. The Journal of Finance, 62(3),
> 1139-1168.

## 5. Notatia matematica

- Variabile cursive: $r_{i,t}$, $\beta$, $\sigma$
- Vectori/matrici bold: $\mathbf{X}$, $\boldsymbol{\beta}$
- Operatori in roman: $\mathrm{Var}(\cdot)$, $\mathbb{E}[\cdot]$
- Ecuatii display numerotate la dreapta cand sunt referite ulterior
- Subscripts: i pentru cross-section, t pentru time, w pentru window
- Conventie semn explicita cand este non-obvious (vezi conventia
  noastra $r^{\text{USD}} = -r^{\text{EURUSD}}$)

## 6. Reproducibility (devine standard 2025+)

Cele mai noi paper-uri include explicit:
- Link la repo public (GitHub) cu cod
- Seeds folosite
- Versiuni software
- Data sources cu access date
- AEA si JFE cer data and code availability statement obligatoriu

---

# Partea II: Audit al paper-ului nostru curent

## Ce avem deja la nivel competitiv

| Item | Status |
|---|---|
| 8 sectiuni clasice (Introduction -> Conclusion) | OK |
| Abstract 220 cuvinte | OK |
| Methodology cu ecuatii numerotate | OK |
| Conventie USD proxy explicit declarata | OK |
| Multiple testing (BH-FDR) | OK |
| Cluster-robust standard errors | OK |
| Pre-cutoff/post-cutoff robustness | OK |
| Winsorization robustness | OK |
| 3-way baseline comparison (LLM/LM/FinBERT) | OK |
| References.bib cu 17 citatii verificate | OK |
| Reproducibility statement separat | OK |
| Limitations cu null findings explicite | OK |

## Ce ne lipseste cu adevarat

| Lipsa | Impact pentru reviewer |
|---|---|
| **Niciun tabel formatat academic** in drafturi | Critic. Prose-only e ne-revizuibil. |
| **Nicio figura** | Critic. Top-tier papers au 4-8 figuri. |
| **Drafturi in Markdown, nu LaTeX/.docx** | Major. JF/JFE/RFS resping non-LaTeX/non-Word. |
| **Numerotare ecuatii lipseste in §4** | Minor. Cititorul nu poate referi $(4.2)$. |
| **Lipseste o sectiune de "Validation" formala** pentru LLM | Major dupa ce vine validarea manuala. |
| **Componenta operationala de trading** a fost scoasa din versiunea curenta | Rezolvat prin focus pe magnitudine, directie si validare. |
| **Niciun event-time plot** (avg AR de la -t la +t) | Critic. Este THE figure pentru event studies. |
| **Densitate citatii in Results = 0** | Minor. Lit review e separat. |
| **Tabel de variable definitions** lipseste | Important. JF cere asta in appendix. |
| **Caz study cu 3-5 evenimente concrete** lipseste | Important. Reviewer-ul vrea sa vada exemple reale. |
| **Heatmap categorie x asset** pentru directie/magnitude | Important. Vizualizeaza C4. |
| **Discutie despre power statistic** lipseste | Minor. |

---

# Partea III: Plan concret de imbunatatire

Grupat pe **prioritate vs efort**.

## A. Must-do inainte de submission (high impact, medium effort)

### A1. Convert la LaTeX
Markdown nu este acceptat de niciun journal top-tier. Trebuie convertit
in LaTeX. Pasi:
- Foloseste `pandoc` pentru o conversie initiala: `pandoc section_1.md
  -o section_1.tex`
- Aplica template-ul `elsarticle.cls` (JFE/Elsevier) sau template-ul
  AFA pentru JF
- Numeroteaza ecuatiile cu `\label{eq:...}` si refera-le cu `\eqref{}`
- Importa references.bib direct cu `\bibliographystyle{jfe}` sau
  `\bibliographystyle{jof}`

### A2. Tabele formatate
Genereaza 8-12 tabele in LaTeX `booktabs` style. Detalii in
**Anexa T** mai jos.

### A3. Figuri principale
Genereaza 6-8 figuri PDF/EPS din scripturile noastre Python. Detalii
in **Anexa F** mai jos. Cea mai importanta: event-time plot
(figura 1 obligatorie pentru orice event study credibil).

### A4. Human validation future work
Daca proiectul revine la validare umana pe esantionul FinancialJuice,
scrie subsectiunea **4.7.x Annotator Agreement** in §4 cu Cohen's
kappa, F1 LLM vs consens, split pre/post cutoff. Add Table cu
confusion matrix LLM vs annotator consensus.

## B. Should-do (high impact, low effort)

### B1. Numeroteaza ecuatiile in §4
Schimba toate `$$ ... $$` in:
```latex
\begin{equation}
r^{\text{target}}_{i,a,W} = ...
\label{eq:target_return}
\end{equation}
```
si refera in body ca "by equation (\ref{eq:target_return})".

### B2. Adauga sectiunea "Variable definitions" in Appendix
Lista cu fiecare variabila folosita: nume, formula, surse, unitati.
~1 pagina. Reduce footnotes in tabele.

### B3. Add 3-5 case studies in §5 sau Appendix
3 evenimente concrete care ilustreaza:
- Un eveniment central-bank (FOMC) - sentiment clar, miscare clara
- Un eveniment geopolitical (escalada Iran) - risk-off, divergenta USD/NDX
- Un eveniment cu LM si LLM in dezacord - de ce LLM are dreptate
Plot cu pretul pe 1 ora si timestamp-ul anotat.

### B4. Heatmap categorie x asset
Adauga Figura 5 sau 6: hit rate / mean |z| pe (categorie, asset,
window). Vizual mult mai puternic decat textul.

### B5. Tabel summary statistics expandat
Tabel 1 actual e prea scurt. Standard: 10-15 randuri cu mean, median,
std, min, max, p25, p75, N pentru fiecare variabila numerica
relevanta.

## C. Nice-to-have (medium impact, medium-high effort)

### C1. Sectiune "Identifying Assumptions" formala
Discuta explicit ce conditii ar trebui sa fie satisfacute pentru ca
event-study sa identifice causal effect. Standard in literatura
moderna post-2020.

### C2. Power analysis ex-post
Calculeaza minimum detectable effect size la sample size-ul nostru.
~1 paragraf in §4.6.

### C3. Comparison cu un eveniment placebo
Picks 1000 random non-event minutes si testeaza ca "evenimente
false" - confirmare ca rezultatele nu vin din specificatie.

### C4. Subsample analysis pe tipul de eveniment macro vs non-macro
Confirma ca rezultatul principal nu este driven doar de un tip.

## D. Stretch (high effort, high reviewer signal)

### D1. Online Appendix complet
30-50 pagini cu:
- Tabele detaliate pentru fiecare (asset, window) celula
- Robustness pe alternative cluster gaps (5min, 10min, 30min)
- Alternative thresholds pentru LM (0.05, 0.15, 0.20)
- Prompt LLM full reproduction
- Comparison cu alta LLM (Claude / GPT-4)

### D2. Bootstrap confidence intervals
In loc de Wilson CI doar pe hit rates, bootstrap 1000 iteratii pe
toate statisticile principale. Standard in JF din 2018+.

### D3. Real-time delay analysis
Caz study pe 50 evenimente unde verifici manual delay-ul Discord vs
Bloomberg. Pune-l ca sectiune separata in Appendix B.

---

# Anexa T: 11 tabele propuse

Notatie: `T_n. Title - what it shows`. Multe se genereaza direct din
CSV-urile noastre cu un script `make_tables.py` nou.

| ID | Titlu | Sursa | Coloane |
|---|---|---|---|
| T1 | **Sample summary** | methodology_summary.csv | News period, raw msgs, gold events, clusters, NDX bars, EUR/USD bars, LLM model |
| T2 | **Variable definitions** | hand-coded | Name, formula, unit, source, table where used |
| T3 | **Descriptive statistics** | events_sentiment.csv | Per variable: mean, median, std, min, p25, p75, max, N. ~12 randuri |
| T4 | **Sentiment distribution** | events_sentiment.csv + baseline + finbert | Bull/Bear/Neutral counts pe LLM/LM/FinBERT + pairwise agreement |
| T5 | **H1 main: event vs baseline magnitude** | h1_results.csv + range_outcomes | 6 randuri (3 windows x 2 assets), mean event, mean baseline, ratio, t-stat, q-value |
| T6 | **H2 main: direction hit rates LLM vs LM vs FinBERT** | sentiment_baseline_compare.csv | 6 randuri (3 windows x 2 assets) x 3 sources, n, hit rate, CI95, q |
| T7 | **Multivariate controls** | multivariate_results.csv | Coeficienti pentru categorie, surprise, cluster size, etc. cu robust SE |
| T8 | **Pre/post cutoff stability** | pre_post_stability_results.csv | Mean |z| in cele doua periode + diff-in-diff |
| T9 | **Per-category effect sizes** | targeted_category_results.csv | Mean |z| pe (categorie, asset, window) cu n_clusters |
| T10 | **Robustness: winsorisation** | outlier_robustness_results.csv | Raw vs winsorised mean si p-value pe primary cells |
| TA1-A5 | **Appendix robustness tables** | misc | Full window set (1m, 240m), Welch alternative, alternative cluster gaps |

Pentru fiecare tabel, scrie un mini-script Python `make_table_X.py` care
citeste CSV-ul si emite LaTeX cu `pandas.to_latex(buf, ...)` cu
formatare booktabs.

# Anexa F: 8 figuri propuse

| ID | Titlu | Tip | Detalii |
|---|---|---|---|
| F1 | **Event-time abnormal return profile** | Line plot, 2 panels | Panel A: EUR/USD, Panel B: NDX. X-axis: minute relative to event (-60 to +240). Y-axis: average |abnormal return| in %. Solid line: events. Dashed: matched baseline. Shaded 95% CI. **Cea mai importanta figura.** |
| F2 | **Event timeline density** | Histogram + line | Sample timeline cu count of events per day across 13 luni. Suprapus: line cu price level. Da reviewer-ului un sens al densitatii event-urilor. |
| F3 | **Distribution of returns** | Density plot, 2 panels | Event-window returns vs baseline pentru 15-min window. Doua kernel densities suprapuse. Ilustreaza vizual ca event distribution are fat tails. |
| F4 | **Range/max-move ratios by window** | Bar plot grouped | Pe X-axis 5/15/60m, pe Y-axis ratio event/baseline. Doua grupuri (EUR/USD, NDX) x trei outcome (delta, range, max_abs_move). Vizualizeaza C2 - cel mai puternic finding. |
| F5 | **Hit rate comparison LLM vs LM vs FinBERT** | Bar plot with CI | X-axis: window x asset (6 cells). Y-axis: hit rate %. 3 bars (LLM/LM/FinBERT) per cell cu Wilson CI95 error bars. Linie orizontala la 50%. |
| F6 | **Sentiment heatmap by category and asset** | Heatmap | Rows: 5 categorii. Columns: 2 (sentiment_usd, sentiment_ndx) x 2 (bull share, bear share). Color = proportion. Ilustreaza cross-asset disagreement. |
| F7 | **Pre vs post-event drift** | Symmetric line plot | X-axis: -15 to +15 minutes around event. Y-axis: mean |return|. Two assets in panels. Highlight pre-event elevation. **Figura cheie pentru H8.** |
| F8 | **Sign persistence scatter** | 4-quadrant scatter | X-axis: +15m signed return. Y-axis: +4h signed return. Color = asset. Cuadrantele NE+SW = sign match (57.6%), NW+SE = reversal. |
Pentru generarea figurilor, propun un script `make_figures.py` care
citeste din `outputs/event_study_windows.csv` si emite PDF/PNG la
`paper/figures/`. Vor folosi `matplotlib` deja in requirements.

---

# Anexa I: Ordinea recomandata de executie

Saptamana 1:
- B1 (numerotare ecuatii) - 1h
- B2 (variable definitions) - 2h
- A2.T1-T6 (cele 6 tabele principale) - 1 zi de Python+LaTeX
- A3.F1, F4, F5, F7 (cele 4 figuri principale) - 1 zi

Saptamana 2:
- B3 (case studies) - 1 zi
- B4 (heatmap categorie) - integrat in F6
- A2.T7-T10 + Anexa - 1 zi
- A3.F2, F3, F6, F8 - 1 zi
- A1 (LaTeX conversion) - 2-3 zile

Saptamana 3:
- Daca se reia validarea umana: A4 (validation section) - 1 zi
- C1-C4 - 2-3 zile in functie de timp
- Submission housekeeping (cover letter, response to potential
  reviewer questions, online appendix split)

---

# Anexa II: Echivalent LaTeX tabel/figura

Schimba acest model pentru orice tabel/figura din paper:

## Tabel typed in LaTeX (folosind booktabs)

```latex
\begin{table}[!htbp]
\centering
\caption{Event-window magnitude relative to matched baseline.}
\label{tab:h1_main}
\begin{tabular}{lcccccc}
\toprule
 & \multicolumn{3}{c}{EUR/USD (USD proxy)} & \multicolumn{3}{c}{Nasdaq-100} \\
\cmidrule(lr){2-4} \cmidrule(lr){5-7}
Window & 5m & 15m & 60m & 5m & 15m & 60m \\
\midrule
Mean $|r|$ event       & 0.0324 & 0.0532 & 0.0993 & 0.0839 & 0.1441 & 0.2682 \\
Mean $|r|$ baseline    & 0.0184 & 0.0314 & 0.0630 & 0.0539 & 0.0920 & 0.1874 \\
Ratio                  & 1.76   & 1.69   & 1.58   & 1.56   & 1.57   & 1.43   \\
$q$-value (MWU)        & ${<}10^{-46}$ & ${<}10^{-40}$ & ${<}10^{-35}$ & ${<}10^{-34}$ & ${<}10^{-32}$ & ${<}10^{-21}$ \\
$N$ clusters event     & 1{,}288 & 1{,}273 & 1{,}208 & 1{,}200 & 1{,}178 & 1{,}099 \\
\bottomrule
\end{tabular}
\begin{tablenotes}
\footnotesize
\item Note. Mean absolute return in percent over each window length.
Baseline drawn from non-event windows matched on asset, window
length, hour-of-day, and day-of-week. $q$-values from
Benjamini-Hochberg FDR adjustment applied uniformly across the
hypothesis battery. Cluster identifier is the news-burst id at 15-min gap.
\end{tablenotes}
\end{table}
```

## Figura typed in LaTeX

```latex
\begin{figure}[!htbp]
\centering
\includegraphics[width=0.95\textwidth]{figures/event_time_profile.pdf}
\caption{Event-time abnormal absolute return profile.}
\label{fig:event_time}
\begin{figurenotes}
\footnotesize
\item Note. Solid blue: average $|r|$ across all 2,449 gold events,
indexed to event time at minute zero. Dashed: average $|r|$ across
30,000 matched non-event baseline windows. Shaded: $\pm 1.96$
standard errors. Panel A: EUR/USD (USD proxy convention). Panel B:
Nasdaq-100 CFD.
\end{figurenotes}
\end{figure}
```

---

# Anexa III: Lista finala de fisiere noi de creat

Pentru implementare end-to-end a planului:

| Fisier | Rol |
|---|---|
| `make_tables.py` | Genereaza tabelele LaTeX si CSV cleaned |
| `make_figures.py` | Genereaza figurile PDF si PNG la 300dpi |
| `paper/figures/` | Directorul cu PDF-urile figurilor |
| `paper/tables/` | Directorul cu .tex inserts pentru tabele |
| `paper/main.tex` | Documentul LaTeX principal care assembleaza |
| `paper/elsarticle.cls` sau template AFA | Class file |
| `paper/case_studies.md` | Sectiunea cu 3-5 case studies, plot per event |
| `paper/online_appendix.tex` | 30-50 pagini de detalii |

Plus eventual:
- `cover_letter.md` cand stim journal-ul target
- `response_to_reviewers.md` dupa primul desk reject (asteapta-te la)
