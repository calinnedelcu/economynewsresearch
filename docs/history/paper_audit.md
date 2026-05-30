# Paper Audit and Improvement Plan

> **Historical note (2026-05-27).** This audit is retained as a
> development record. Several Wave 1--4 items identified below have
> since been implemented in the current `paper/sections/*.tex` sources
> and compiled PDFs. Treat `docs/history/STATUS.md`, the generated tables, and
> the current LaTeX sources as the authoritative project status.

Document de lucru pentru aducerea paper-ului la nivel de submission top-tier
finance journal. Bazat pe analiza:

- conventiile **JF, JFE, RFS, J Financial Markets** (style guides + 5+
  papers exemplificative);
- audit fisier cu fisier al `main.tex` si toate sectiunile;
- comparison cu Tetlock 2007, Loughran-McDonald 2011, ABDV 2003,
  Calomiris-Mamaysky 2019, Heston-Sinha 2017.

Verdict scurt: **paper-ul e in top 10% al draft-urilor de submission
empirice in finance NLP**. Are infrastructura corecta (FDR, cluster SE,
3 baselines, external benchmark, reproducibility statement). Lipsesc
~12 lucruri concrete care fac diferenta intre "credibil" si
"publishable in tier-1". Toate sunt fix-uri de 15 min - 2h fiecare, nu
re-design.

---

# Partea I: Conventiile top-tier finance pe care le-am verificat

## 1. Lungimi standard

| Sectiune | JF target | JFE target | Noi |
|---|---|---|---|
| Abstract | **<= 100 words** | <= 200 words | **275** ❌ |
| Introduction | 4-6 pages | 4-6 pages | ~5 pages ✓ |
| Literature | 3-4 pages (sau integrat in intro) | 2-4 pages | ~5 pages ✓ |
| Data | 3-5 pages | 3-5 pages | ~5 pages ✓ |
| Methodology | 4-6 pages | 4-6 pages | ~9 pages ⚠ |
| Results | 8-15 pages | 8-15 pages | ~13 pages ✓ |
| Discussion | combinat cu Results sau 2-4 pages | rar separat | 5 pages ⚠ |
| Limitations | rar separat (integrat in Discussion) | rar separat | 4 pages ⚠ |
| Conclusion | 1-2 pages | 1-2 pages | 2 pages ✓ |
| **Total body** | 35-55 pages double-spaced | 35-55 pages | 40 pages ✓ |

## 2. Conventii citatii (JF style)

- `Author (Year)` in text natural: `Tetlock (2007) shows...`
- `(Author, Year)` in paranteze: `prior literature documents this (Tetlock, 2007)`
- Three+ authors: `Andersen et al. (2003)`
- Multiple in same paranteza: `(Tetlock 2007; Loughran and McDonald 2011)`
- **Densitatea standard**: 1-3 citatii/paragraf in Intro+Lit, 0-1 in Results,
  1-2 in Discussion
- **Bibliography**: alfabetic pe primul autor, nume complet (NU initials) la JF;
  initials la JFE

## 3. Conventii tabele

- **Standard errors** (NU t-statistics) in paranteze sub coeficient
- Nota: `Standard errors in parentheses. *p<0.10, **p<0.05, ***p<0.01.`
- Booktabs `\toprule \midrule \bottomrule` (nu `\hline`)
- Max 8 coloane in portrait
- `threeparttable` cu `tablenotes` pentru note
- Decimale: 2-3 pentru coeficienti, 3-4 pentru returns intraday, 0 pentru N
- Caption SUS, tablenotes JOS

## 4. Conventii figuri

- Caption JOS de figura (1-3 propozitii)
- Multi-panel notate "Panel A", "Panel B"
- Axe etichetate cu unitati: `Abnormal return (\%)`
- Font sans-serif 8-14pt in figura
- Color permis online, grayscale-friendly pentru print
- Notes line sub caption pentru detalii

## 5. Stil scriere

- **Voce**: mix activ/pasiv. "We document...", "The results indicate..."
- **Persoana**: "we" pentru multi-author
- **Timp**: present pentru fapte general, past pentru proceduri specifice
- **Hedging**: foarte important. "These findings are consistent with..."
  in loc de "These findings prove..."
- **Liste**: rar folosite in body text. Convertit in prose unde posibil.
- **Bullets**: aproape niciodata in paper. Numerotat (1), (2), (3) inline preferat.
- **First person plural** standard chiar la solo-author

## 6. Structura specifica

- **Hypothesis development** subsection often comes between Lit Review si Data
- **Identification strategy** paragraph (modern requirement, 2020+)
- **Pre-registration / pre-specification** statement (devine standard)
- **Data Availability Statement** OBLIGATORIU la JFE din 2020
- **Acknowledgments** la finalul paper-ului inainte de References
- **JEL codes + Keywords** pe title page sau dupa abstract

## 7. Conventii matematice

- Variabile cursive: `$r_{i,t}$`, `$\beta$`
- Vectori bold: `$\mathbf{X}$`
- Operatori in roman: `$\mathrm{Var}(\cdot)$`
- Ecuatii display NUMEROTATE doar daca sunt referite ulterior
- Sub/superscripts: i pentru cross-section, t pentru time

---

# Partea II: Strengths (ce avem deja la nivel top-tier)

✅ Structura clasica 8 sectiuni + Appendix + References
✅ Booktabs tables cu threeparttable footnotes
✅ Vector PDF figures + grayscale-friendly palette
✅ Natbib `\citep{}` si `\citet{}` consistent (verificat)
✅ Ecuatii numerotate corect (5 ecuatii numbered in §4)
✅ BH-FDR uniform pe toate testele
✅ Cluster-robust standard errors pe toate regresiile
✅ External benchmark validation (PhraseBank κ = 0.72)
✅ 3 sentiment baselines compared
✅ Pre-cutoff/post-cutoff robustness
✅ Winsorisation robustness
✅ Reproducibility statement separat
✅ 18 citatii (toate verificate via WebSearch)
✅ Niveluri concrete de cifre (1.76×, 84.6%, $q < 10^{-46}$) - reviewer-ul vede precizie
✅ Limitations cu null findings explicite (H6, H12)
✅ Multi-classifier comparison ca diferentiator (LLM vs LM vs FinBERT)

---

# Partea III: Issues critice (must fix inainte de submission)

## C1. Abstract prea lung (275 vs 100-200)
**Problema**: JF limita stricta 100 cuvinte. JFE accepta 150-200. Noi: 275.
Reviewer-ul JF rejecteaza desk pentru asta.
**Fix**: rewrite la 200 cuvinte (pentru JFE/JFM) sau 100 (pentru JF).
**Effort**: 15 min.

## C2. Lipseste afiliere si email Andrei Cheroiu
**Problema**: Doar tu ai email + thanks. Andrei apare doar cu numele.
Reviewer-ul intreaba "cine e al doilea autor?".
**Fix**: cere afilierea + email-ul lui Andrei, adauga in title block.
**Effort**: 1 min cod, depinde de Andrei.

## C3. Lipseste Acknowledgments section
**Problema**: Standard la finalul paper-ului inainte de References. Multumeste
seminar participants, anonymous referees, RA-uri etc. Lipsa este vizibila.
**Fix**: adauga `\section*{Acknowledgments}` cu 2-3 propozitii placeholder.
**Effort**: 5 min.

## C4. Lipseste Data Availability Statement
**Problema**: JFE require explicit din 2020. JF si JFM cer si ele in
formulare diferite.
**Fix**: adauga subsectiune dupa Reproducibility statement cu link to
repo + listare data sources.
**Effort**: 10 min.

## C5. Lipseste explicit "Hypothesis Development" subsection
**Problema**: Top-tier finance papers au de obicei un sub-cap intre Lit
Review si Data unde dezvolta explicit ipotezele testate, motivate teoretic.
Noi le avem implicit in metodologie. Reviewer-ul vrea sa vada de ce
testam H1, H2, etc. cu motivatie economica.
**Fix**: adauga §2.5 sau §3.0 cu ~1 pagina pe motivatii teoretice pentru
H1 (volatility), H2 (direction), H8 (drift), H9 (persistence).
**Effort**: 1-2 ore.

## C6. "Practitioner" language inadecvata
**Problema**: 5 mentiuni de "practitioners" / "readers should infer" in
§5, §6, §8. Top finance journals au audience academica - reviewer-ul va
vedea aceste fraze ca informale/colocviale.
**Locatii exacte**:
  - §5.1: "we recommend that practitioners reading the paper attend to it more"
  - §6.1: "For practitioners, the practical implication is..."
  - §6.3: "The implication for practitioners is unambiguous"
  - §8: "For practitioners using this kind of feed..."
**Fix**: rewrite ca observatii neutre. Ex: "The economic interpretation
is that..." in loc de "Practitioners should...".
**Effort**: 30 min.

## C7. Overclaim language
**Problema**: 4-5 superlative "strongest single finding", "most useful new
result", "most stable result" - finance journals prefera fraze neutre.
**Fix**: rewrite ca "robust result" / "primary finding" / "particularly
strong association".
**Effort**: 15 min.

---

# Partea IV: Should fix (high impact, low-medium effort)

## S1. Description lists in §4.5 → prose
**Problema**: 3 `\begin{description}` lists in §4.5 cu H1, H2, etc. enumerate.
Top finance papers folosesc prose continuu, nu liste.
**Fix**: convertit in paragrafe ("H1 tests... H2 tests..."). Mai lung dar
mai conventional.
**Effort**: 1 ora.

## S2. §6 Discussion overlap cu §5 → combine
**Problema**: Multe top papers (JFE in special) combina Results &
Discussion. Noi avem repetare semnificativa intre §5 si §6 (especially
pre-event drift discussion).
**Fix**: merge §6 in §5 ca paragrafe scurte de interpretare la finalul
fiecarei subsectiuni. Ramane separat poate "6.6 What we do not test".
**Effort**: 1-2 ore.

## S3. §7 Limitations → integrat in Discussion + Conclusion
**Problema**: Limitations ca §7 separat e mai degraba din thesis writing,
nu din top journals. JF/JFE/RFS le integreaza in concluzie sau ca paragraf
in discussion.
**Fix**: scurta §7 la 1 pagina, muta majoritatea ca paragrafe in §6 si §8.
**Effort**: 1 ora.

## S4. Variable notation Python-style → math notation
**Problema**: Folosim `\texttt{sentiment\_usd}` (Python) in body. Top
finance: $s_i^{\mathrm{USD}}$ sau $S^{\mathrm{USD}}_i$.
**Fix**: in section §4 introduce notatia math, foloseste-o consistent in
§5. Pastreaza Python-style doar in Table 2 (variable definitions) si in
Reproducibility.
**Effort**: 30 min.

## S5. Hypothesis Development paragraf in §2 sau §3
**Problema**: Conexat cu C5. Reviewer-ul vrea sa stie de ce specific
H1-H14, ce literatura motiveaza fiecare.
**Fix**: rewriting §2.5 sau §3.1 cu motivatie + predictie pentru fiecare
H principal (H1, H2, H8, H9). H restul ca robustness.
**Effort**: 2 ore (overlap cu C5).

## S6. Sectiune Identification Strategy
**Problema**: Modern empirical finance (post-2020) cere explicit ce
identifying assumption se face. Noi avem implicit dar nu explicit.
**Fix**: paragraph nou in §4.5 (Hypothesis tests) sau §4.7 inainte de
Sentiment validation:
> "We do not claim causal identification of the price response to news.
> Our identifying assumption is that, conditional on hour-of-day and
> day-of-week, non-event windows provide a valid counterfactual for the
> price behaviour in the absence of the news event. We discuss threats
> to this assumption in Section 7."
**Effort**: 30 min.

## S7. JEL codes verifica
**Problema**: G14, G15, C58, C45. G15 (International FX) borderline.
Lipseste G17 (Financial Forecasting) si C53 (Forecasting Methods).
**Fix**: schimba in G14 (Information & Market Efficiency), G17 (Financial
Forecasting), C45 (Neural Networks), C58 (Financial Econometrics).
G15 il pastreaza doar daca subliniem componenta FX.
**Effort**: 1 min.

## S8. Overfull hboxes (6 instances)
**Problema**: 6 paragrafe in care textul depaseste marginile cu 5-100pt.
Vizual urat in PDF.
**Fix**: identifica liniile in log, micro-rewrite. Sau adauga `\sloppy`
local. Sau switch la `\usepackage{ragged2e}` cu `\RaggedRight` selective.
**Effort**: 30 min.

## S9. Float placement
**Problema**: Tables/figures plasate cu `[!htbp]` pot ajunge departe de
referinta in text. Layout final poate avea pagina cu 2 tabele consecutive
si pagina urmatoare cu textul care le refera.
**Fix**: add `\usepackage{placeins}` cu `\FloatBarrier` la finalul fiecarei
subsectiuni. Sau force `[!h]` strict cu `\usepackage{float}` si `[H]`.
**Effort**: 15 min, dar trebuie rebuild si verificat.

---

# Partea V: Nice to have (medium-high effort)

## N1. Online Appendix complet (10-30 pagini)
- Tabele complete pentru H6, H10 si H12
- Toate ferestrele 1m si 240m
- Welch t-test ca alternative pentru H1
- Pe categorii detaliate pentru C4
- Robustness pe alternative cluster gaps (5, 10, 15, 30 min)
- Prompt LLM full
**Effort**: 1-2 zile.

## N2. Bootstrap confidence intervals
**Problema**: Standard din 2018+ pentru finance, mai ales cluster-robust.
Noi avem Wilson CI doar pe hit rates.
**Fix**: bootstrap pe 1000 iteratii pentru ratios H1, coeficienti C6.
**Effort**: 2 ore + recompute.

## N3. Subsample analysis pe sentiment direction
**Problema**: Reviewer-ul intreaba "does the magnitude effect differ for
bull-events vs bear-events vs neutral?". Avem cifrele in data dar nu in
tabel.
**Fix**: split H1/C2 results pe sentiment_usd bull/bear/neutral. Adauga
ca Appendix table.
**Effort**: 1 ora.

## N4. Effect size in economic terms
**Problema**: Raportam "1.76× ratio" - reviewer-ul vrea sa stie "asta
inseamna 0.02% additional return absolute". Concrete dollar/bp value.
**Fix**: adauga 1-2 propozitii in §5.1 cu cifrele in pips/bp pentru EUR/USD
si in points/dollar pentru NDX.
**Effort**: 30 min.

## N5. Robustness pe cluster gap alternative
**Problema**: 15 min e arbitrar. Reviewer-ul intreaba "ce daca 5 sau 30?"
**Fix**: re-run event_study.py cu gap = {5, 10, 15, 30} min, raporteaza
H1 ratios in Appendix.
**Effort**: 1-2 ore cu re-runs.

## N6. Power analysis
**Problema**: 2449 events e mult dar dupa cluster dedupe 1405. Reviewer-ul
intreaba puterea statistica.
**Fix**: paragraph in §4.6 cu minimum detectable effect size.
**Effort**: 1 ora.

## N7. Case studies cu primary-source timestamps
**Problema**: Discutat anterior. Necesita verificare manuala Bloomberg/Reuters.
**Effort**: 1 zi human.

---

# Partea VI: Issues mai mici (polish, cumulativ important)

## P1. Lipseste \keywords si \jelcodes formal in title block
Noi le avem ca text after abstract. Convention LaTeX: ca macros separate.

## P2. \abstract environment vs custom block
Noi folosim `\begin{abstract}...\end{abstract}` care intra in default
article class. Default e bun.

## P3. Hyperref colors
Noi avem `hidelinks` - acceptabil. Alternativa: blue/dark-blue care
e mai modern.

## P4. Verifica orphan citations in references.bib
Posibil sa avem citatii care nu sunt folosite in text.
Verify cu: `bibtex` warns despre orphan citations.

## P5. footnotes density
Noi avem 1 footnote (corresponding author). Top papers au 10-30 footnotes
cu detalii tehnice. Lipsa lor e neobisnuita.
**Fix**: adauga 3-5 footnotes pentru clarificari (e.g., "We use HC3
because HC0 inflates standard errors at small N").

## P6. Conventia _ vs \_
In multe locuri folosim `\_` in tabele si secund. Verifica consistenta.

## P7. dash conventions
- Range: en-dash (--) — folosim 90%
- Compound modifier: en-dash (--) sometimes
- Em-dash for interruption (---) — verifica consistenta

## P8. Numar pagini estimat post-fixes
Curent: 40 pages
Post fix C1-C7: probabil 38-39 pages
Post fix S1-S6 (combine §5+§6, scurta §7): probabil 34-37 pages
Post adaugare hypothesis development (S5): +2 pages = 36-39 pages

Optimal pentru JFM/JFE submission: 35-45 pages. Suntem in target.

---

# Partea VII: Page-by-page comments

Bazat pe lectura PDF + tex sources:

## p.1 Title page
- Title block bun
- Autori: doar Calin are afiliere/email; **fix** Andrei
- Abstract: prea lung
- Keywords + JEL ar trebui in macro-uri separate, mai vizibile

## p.2-3 Introduction
- Structura OK
- "Three findings warrant emphasis" - bun framing
- "Our contribution is fourfold" - bun
- Ultima paragraf ("road-map") - convention bun

## p.3-5 Literature Review
- 4 subsectiuni tematice - bun
- Citatii ~15 - bun densitate
- Lipseste paragraph despre why our work fills a gap (specific niche
  identificare)

## p.5-9 Data
- Subsectiuni bine organizate
- **Table 1 (sample summary)** placement: post-text - OK
- **Table 2 (variable definitions)** - prea devreme? E mai degraba in
  appendix de obicei
- **Figure 2 (event timeline)** - OK
- **Table 4 (sentiment distribution)** - bun

## p.9-14 Methodology
- Ecuatii numerotate, OK
- 7 subsectiuni - **lung**. Top papers au 4-5.
- §4.5 Hypothesis tests cu description lists - convert la prose (S1)
- §4.7 Sentiment validation: bun dupa update PhraseBank

## p.14-25 Results
- 6 subsectiuni tematice - bun
- Tabele si figuri integrate bine
- **§5.1**: "strongest single finding" → softer (C7)
- **§5.2**: PhraseBank addition - excellent
- **§5.4 H8**: "Practitioners reading this section should infer..." → rewrite (C6)
- **§5.6** robustness: bun

## p.25-29 Discussion
- 6 subsectiuni - prea multe
- Overlap cu §5 - consolidate (S2)
- "Practitioners" mentions - rewrite (C6)
- "What we do not test" subsection - bun, pastreaza

## p.29-32 Limitations
- Detalii bune
- Prea lung pentru convention finance (S3)
- "Two further null findings should be reported explicitly" - bun
- "What would strengthen a follow-up" - bun

## p.32-33 Conclusion
- Lungime OK
- "Practitioners" - rewrite (C6)
- Synthesis bun

## p.33-35 References
- 17 referinte verificate ✓
- Format plainnat - acceptabil. JFE prefera "elsarticle-harv".
- Lipseste DOI in unele entries (avem in BibTeX dar nu apar in PDF)

## p.35-40 Reproducibility (Appendix)
- Detaliat, bun
- Comenzi reproductibile - bun
- **Lipseste Data Availability Statement separat** (C4)

---

# Partea VIII: Prioritized Action Plan

## Wave 1: Quick wins (1-2 ore total) - inainte de orice review extern
1. **C1** Abstract → 200 cuvinte (15 min)
2. **C2** Afiliere/email Andrei (1 min cod + depinde de el)
3. **C3** Acknowledgments section (5 min)
4. **C4** Data Availability Statement (10 min)
5. **C6** Practitioner → academic phrasing (30 min)
6. **C7** Superlative → neutral phrasing (15 min)
7. **S7** JEL codes update (1 min)
8. **S8** Overfull hboxes (30 min)
9. **P5** Add 3-5 footnotes pentru clarificari tehnice (30 min)

## Wave 2: Structural improvements (1 zi)
10. **S2** Combine §5 + §6 Results & Discussion (1-2 ore)
11. **S3** §7 Limitations scurtat la 1 pagina (1 ora)
12. **S4** Variable notation math (30 min)
13. **S6** Identification Strategy paragraph (30 min)
14. **S9** Float placement (15 min + verify)

## Wave 3: Major addition (1-2 zile)
15. **C5 + S5** Hypothesis Development section (2-3 ore)
16. **N4** Effect size in economic terms (30 min)
17. **N6** Power analysis paragraph (1 ora)

## Wave 4: Online Appendix (1-2 zile, opcional pentru submission initial)
18. **N1** Online Appendix complet
19. **N3** Subsample analysis pe sentiment
20. **N5** Cluster gap robustness

## Wave 5: Polish final (cateva ore)
21. Re-build PDF
22. Read-through complet pentru typo / consistency
23. Verifica all `\ref{}` resolve
24. Verifica all citations used

---

# Anexa A: 10 lucruri concrete pe care reviewer-ul VA intreba

Acestea ar trebui sa aiba raspuns clar in paper:

1. **"Why 15 min cluster gap? Why not 5 or 30?"** → N5 robustness
2. **"Why only EUR/USD and NDX? What about EUR/JPY, S&P500?"** → §7 limitation
3. **"Why CFD proxy for NDX? Why not E-mini futures?"** → §7 limitation
4. **"How sensitive are LLM labels to prompt variations?"** → mentionat
   ca future work, OK
5. **"What's your identification strategy?"** → S6 fix
6. **"Pre-event drift = front-running?"** → §5.4 + §6.3 fac discussion
7. **"How does LLM compare to off-the-shelf FinBERT?"** → T9 PhraseBank ✓
8. **"What's the effect in dollar terms / pips?"** → N4 fix
9. **"Power analysis?"** → N6 fix
10. **"Out-of-sample validation?"** → C5 pre/post cutoff ✓

# Anexa B: 5 lucruri pe care AS face daca am 1 saptamana

1. Hypothesis Development section (C5/S5)
2. Combine Results & Discussion (S2)
3. Acknowledgments + Data Availability + email Andrei (C2/C3/C4)
4. Identification Strategy paragraph (S6)
5. Online Appendix cu cluster gap robustness + subsample analysis (N1/N3/N5)

# Anexa C: 5 lucruri pe care AS face daca am 1 zi

1. Abstract scurtat la 200 cuvinte (C1)
2. Practitioner → academic phrasing (C6)
3. Superlative → neutral (C7)
4. JEL codes update (S7)
5. Acknowledgments + Data Availability (C3/C4)

Toate Wave 1 fixes = ~2 ore total → diferenta clara intre desk reject
si going to review.
