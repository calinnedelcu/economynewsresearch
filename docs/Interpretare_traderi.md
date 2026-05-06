# Interpretare non-tehnica pentru traderi

Acest fisier traduce rezultatele din pipeline in limbaj practic: ce inseamna, ce este contraintuitiv si ce se poate lua concret din ele ca trader. Nu este recomandare financiara si nu este un sistem live de buy/sell. Este o baza de cercetare pentru reguli care trebuie backtestate cu costuri, slippage, risc si executie reala.

## Rezumat executiv

Concluzia mare nu este ca LLM-ul "prezice directia pietei". Concluzia mult mai solida este:

> Stirile neasteptate din feed sunt asociate cu miscare intraday anormala. Directia este greu de prezis, dar probabilitatea de volatilitate/range crescut este mult mai clara.

Pentru traderi, asta inseamna:

- feed-ul este mai util ca filtru de volatilitate decat ca semnal directional pur;
- dupa stiri puternice, are mai mult sens sa te intrebi "cat de mult se poate misca?" decat "sus sau jos?";
- directia devine ceva mai interesanta doar pe subseturi: NDX pe +5m/+15m la nivel de cluster si EUR/USD +5m cand Flash si Pro sunt de acord;
- pre-event drift-ul spune ca intrarea dupa timestamp-ul Discord poate fi deja tarzie;
- clusterizarea conteaza: mai multe headline-uri in 15 minute sunt un eveniment, nu 10 evenimente independente;
- rezultatele cele mai folosibile sunt pentru position sizing, volatility filters, stop/target design si timing, nu pentru semnale naive.

## Ce este cel mai contraintuitiv

1. Directia este mai slaba decat magnitudinea.

Intuitiv, ai vrea ca "bull" sa duca sus si "bear" sa duca jos. In realitate, piata reactioneaza mult mai clar prin miscare mare decat prin directie corecta. Asta sugereaza ca headline-ul creeaza incertitudine si repricing, dar directia depinde de context, pozitionare si ce era deja asteptat.

2. Stirile pot avea miscare inainte de timestamp.

H8 arata pre-event drift peste baseline. Asta nu trebuie interpretat automat ca front-running. Mai probabil, timestamp-ul Discord nu este timestamp-ul informatiei primare. Pentru trader, implicatia este dura: feed-ul poate fi confirmare, nu prima sursa.

3. Confidence-ul LLM nu este probabilitate de castig.

Un confidence mare nu inseamna automat trade mai bun. LLM-ul poate fi sigur pe interpretarea economica, dar piata poate avea alta informatie deja incorporata.

4. EUR/USD trebuie gandit invers cand testam sentiment USD.

Daca sentimentul este bullish USD, EUR/USD ar trebui sa scada. Rezultatele vechi pot fi interpretate gresit daca nu folosesti proxy-ul USD `-EUR/USD`.

5. Consensus-ul intre modele ajuta, dar doar pe subseturi.

Flash/Pro consensus are EUR/USD +5m la aproximativ 60.7% hit rate, dar esantionul e mic. Nu este suficient pentru strategie live fara confirmari suplimentare.

## Ce luam concret ca traderi

### 1. Foloseste stirile ca volatility trigger

Rezultatul principal: evenimentele au miscari absolute peste baseline pe toate activele si toate ferestrele. Ratio event/baseline este aproximativ:

- EUR/USD: `1.45x` pana la `1.87x` pe abs return;
- NDX: `1.33x` pana la `1.72x` pe abs return;
- range/max-move: `1.44x` pana la `1.89x`, toate semnificative.

Aplicatie practica:

- dupa headline-uri gold, mareste atentia la range expansion;
- evita sa folosesti aceleasi stop-uri ca intr-o perioada normala;
- poti construi reguli de tip "nu intru mean-reversion imediat dupa stire fara confirmare";
- poti testa strategii de breakout/volatility, nu doar long/short directional.

### 2. Trateaza directia ca edge mic, nu ca certitudine

H2 si C1 arata ca directia este modesta. Cel mai bun semnal cluster-level este NDX:

- NDX +5m: hit rate `53.9%`, q `0.0118`;
- NDX +15m: hit rate `53.2%`, q `0.0383`;
- EUR/USD este mai slab, cu exceptia unor ferestre/subseturi.

Aplicatie practica:

- nu transforma direct sentimentul LLM in market order;
- foloseste sentimentul ca filtru secundar dupa context, price action si liquidity;
- un edge de 53-54% poate fi valoros doar daca payoff-ul, costurile si risk management-ul sunt bune;
- pe NDX, ferestrele de +5m/+15m merita testate mai atent.

### 3. Clusterul conteaza mai mult decat headline-ul individual

Un burst de 6 stiri in 10 minute nu inseamna 6 observatii independente. Piata vede un episod informational.

Aplicatie practica:

- daca apar multe headline-uri apropiate, trateaza-le ca un singur regim de risc;
- nu reintra agresiv la fiecare headline din acelasi cluster;
- asteapta stabilizarea clusterului sau defineste reguli: primul headline, confirmare dupa 1-5 minute, sau trade doar daca sentimentul clusterului ramane coerent.

### 4. Range/max-move este mai folosibil decat close-to-close return

Close-to-close poate rata miscarea reala: pretul poate urca, cobori si inchide aproape flat. Range-ul si max_abs_move prind mai bine reactia.

Aplicatie practica:

- pentru strategie, masoara MFE/MAE si range, nu doar close after 5m;
- gandeste in termeni de stop/target si excursion, nu doar candle close;
- pentru intraday, un headline poate fi valoros chiar daca directia finala pe 15m nu ramane.

### 5. Pre-event drift inseamna ca feed-ul poate fi intarziat

Pre-event drift este robust. Asta inseamna ca pretul incepe uneori sa se miste inainte de timestamp-ul Discord.

Aplicatie practica:

- nu presupune ca feed-ul iti da primul semnal;
- verifica daca spread-ul si pretul au sarit deja inainte sa intri;
- evita chasing dupa prima lumanare daca miscarea initiala este deja consumata;
- pentru paper, spune "feed latency/information timing", nu "front-running".

### 6. Persistenta exista, dar nu inseamna hold orbeste

H9 arata ca semnul miscarii la +15m se potriveste cu +4h in jur de `57.6%` pentru ambele active.

Aplicatie practica:

- daca intri corect pe impuls, exista un argument pentru partial hold;
- dar 57.6% nu e suficient pentru hold fara trailing stop sau invalidare;
- poate fi util pentru reguli de "let winners run" dupa evenimente puternice.

### 7. Volumul confirma atentie, dar este proxy

H10 arata volum/tick volume peste baseline. Totusi, Dukascopy volume nu este volum real consolidat.

Aplicatie practica:

- foloseste-l ca semn de activitate, nu ca dovada institutionala;
- pentru execution real pe NDX ar fi mai bun futures/ETF volume;
- pentru FX ar fi nevoie de surse mai bune daca vrei concluzii despre flow.

### 8. Time-of-day conteaza

H11 arata ca ora conteaza, mai ales pentru EUR/USD.

Aplicatie practica:

- nu folosi aceleasi praguri pentru Asia, Londra si New York;
- baseline-ul trebuie adaptat la ora si ziua saptamanii;
- un headline la 03:00 UTC si unul la 14:30 UTC nu au acelasi regim de lichiditate.

### 9. Category targeting este util pentru selectia trade-urilor

Rezultatele targetate arata ca unele categorii au miscari mai clare, mai ales pe magnitudine:

- central_bank: miscari puternice pe EUR/USD si NDX;
- geopolitical: multe observatii, util mai ales ca volatility trigger;
- energy: sample mai mic, dar poate crea miscari mari;
- corporate: relevant mai ales pentru NDX, dar sample mic;
- politics: mixed, depinde mult de context.

Aplicatie practica:

- trateaza `central_bank` si `geopolitical` ca regimuri diferite;
- pentru corporate, NDX poate reactiona, dar ai nevoie de ticker/component context;
- nu pune toate stirile in aceeasi galeata.

### 10. Consensus LLM este interesant, dar exploratoriu

Pe sample-ul Flash/Pro:

- EUR/USD +5m consensus: hit rate `60.7%`, q `0.0299`;
- NDX +1m si +15m sunt promitatoare, dar nu trec la fel de curat dupa FDR.

Aplicatie practica:

- consensus-ul poate fi filtru de calitate, nu semnal final;
- daca doua modele sunt de acord si sentimentul este non-neutral, merita prioritate la analiza;
- pentru trading real trebuie sample mai mare si validare out-of-sample.

## Implicatia fiecarei ipoteze

| Test | Ce spune simplu | Implicatie pentru traderi | Verdict practic |
|---|---|---|---|
| H1 Events vs baseline | Stirile misca piata mai mult decat ferestre normale | Foloseste headline-urile ca volatility trigger | Foarte util |
| H2 Directie sentiment | Sentimentul prezice directia doar modest | Nu face buy/sell direct din eticheta bull/bear | Slab spre util |
| H3 Sentiment x trend | Trendul anterior schimba reactia | Contextul de pret conteaza la fel de mult ca headline-ul | Util pentru filtre |
| H4 Gaps in perioade inchise | Stirile din pauze pot explica gap-uri | Pentru weekend/closed market, sentiment agregat poate conta | Util dar specific |
| H5 Expected magnitude | Magnitude label ajuta limitat | Nu te baza doar pe low/med/high de la LLM | Exploratoriu |
| H6 Confidence | Confidence nu e calibrat | Nu mari pozitia doar fiindca LLM-ul e "confident" | Avertisment important |
| H7 Categorii | Categoriile difera | Segmenteaza strategiile pe tip de stire | Util |
| H8 Pre-event drift | Pretul se misca uneori inainte de feed | Ai risc de intrare tarzie si chasing | Foarte important |
| H9 Persistenta | Miscarea +15m continua uneori spre +4h | Testeaza trailing/partial hold dupa impuls | Util |
| H10 Volume proxy | Activitatea creste in jurul stirilor | Confirma atentie, dar nu flow real | Util cu caveat |
| H11 Ora/zi | Reactia depinde de ora | Praguri diferite pe sesiuni | Util |
| H12 Bear vs bull | Bear nu e mult mai puternic decat bull | Nu supra-pondera automat stirile negative | Slab |
| H13 Surprise level | Surprise ajuta partial | Shock/surprise sunt filtre bune, dar incomplete | Exploratoriu |
| H14 Cross-asset | EUR/USD si NDX trebuie interpretate cu conventie USD | Nu incurca EUR/USD price cu USD sentiment | Important metodologic |
| C1 Cluster sentiment | Clusterul imbunatateste usor directia pe NDX | Analizeaza burst-ul, nu headline-ul izolat | Util pe NDX |
| C2 Range/max move | Miscarea maxima este robust peste baseline | Cel mai bun semnal pentru volatility/range trading | Foarte util |
| C3 Abnormal z | Miscarea ramane mare dupa standardizare | Compara activele corect si seteaza praguri z-score | Foarte util |
| C4 Target categories | Semnalele difera pe categorie | Fa reguli separate pe central bank/geopolitical/corporate | Util |
| C5 Pre/post cutoff | Efectul ramane si dupa 2026-01-15 | Mai greu de atacat ca memorization | Aparare pentru paper |
| C6 Multivariate | Controalele conteaza mult | Include pre-move, category, cluster size in strategie | Foarte util pentru research |
| C7 Winsorization | Outlierii nu explica tot | Semnalul nu e doar cateva stiri extreme | Aparare buna |
| C8 Model consensus | Acordul intre modele ajuta pe subseturi | Filtru promitator, dar necesita sample mai mare | Exploratoriu |

## Reguli testabile, nu recomandari live

Acestea sunt idei de backtest, nu reguli de executat direct:

1. Volatility breakout dupa headline gold

- trigger: headline gold;
- intra doar daca range-ul primelor 1-5 minute depaseste un prag z-score;
- directia se ia din price action, nu doar din LLM;
- stop adaptat la range-ul post-news.

2. NDX sentiment cluster filter

- trigger: cluster cu sentiment NDX bull/bear;
- fereastra: +5m/+15m;
- filtru: evita neutral, cere agreement in cluster;
- testeaza daca hit rate-ul de 53-54% supravietuieste costurilor.

3. EUR/USD consensus filter

- trigger: Flash si Pro sunt de acord pe USD;
- fereastra: +5m;
- directie: USD bull inseamna EUR/USD short, USD bear inseamna EUR/USD long;
- necesita sample mai mare inainte de folosire.

4. No-chase rule dupa pre-move mare

- daca pretul s-a miscat deja anormal inainte de timestamp sau in prima lumanare, nu intra imediat;
- asteapta pullback/continuation confirmation;
- scop: sa eviti sa cumperi varful reactiei.

5. Event risk filter

- daca apare cluster central_bank/geopolitical, redu sau ajusteaza pozitiile mean-reversion;
- nu trata perioada ca regim normal de volatilitate;
- foloseste range mai mare pentru stop sau iesi din trade-uri care depind de liniste.

## Ce NU putem spune

- Nu putem spune ca LLM-ul este un predictor directional puternic.
- Nu putem spune ca pre-event drift dovedeste insider trading.
- Nu putem spune ca volumul Dukascopy este volum real de piata.
- Nu putem spune ca rezultatele consensus sunt finale, pentru ca sample-ul este mic.
- Nu putem spune ca aceste rezultate sunt profitabile dupa spread, slippage si latency fara backtest dedicat.

## Formula simpla pentru paper si prezentare

Varianta buna:

> Stirile neasteptate sunt asociate robust cu miscari intraday anormale, mai ales in range si maximum intrawindow move. Sentimentul LLM adauga un edge directional modest in anumite subseturi, dar valoarea practica principala este identificarea regimurilor de volatilitate si imbunatatirea timing-ului/risk management-ului.

Varianta de evitat:

> LLM-ul prezice piata si confirma toate ipotezele.

## Prioritatea pentru urmatorul pas

Pentru a transforma research-ul in ceva apropiat de trading system:

1. backtest cu reguli clare de intrare/iesire;
2. costuri realiste: spread, slippage, latency;
3. out-of-sample mai mare pentru consensus;
4. validare manuala sentiment pe 200 evenimente;
5. daca avem timp, adaugare DXY/QQQ pentru validare cross-asset.
