#!/usr/bin/env python3
"""Build a visual HTML report of the event study results.

Reads event_study output CSVs + prices and produces:
  - per-event timeline charts (price + window markers)
  - aggregate plots for H1/H2/H3
  - a single HTML page that embeds all of them, with summary tables.

Opens the report in the default browser at the end.
"""

import argparse
import base64
import io
import sys
import webbrowser
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ASSETS = ["eurusd", "ndx"]
WINDOWS_MIN = [1, 5, 15, 60, 240]


HYPOTHESIS_DETAILS = {
    "h1": {
        "title": "H1 — Events mișcă piața peste volatilitatea normală",
        "what": "Comparăm |Δ%| măsurat în jurul evenimentelor cu |Δ%| pe ferestre random din zile fără evenimente. Dacă events au reacții semnificativ mai mari → confirmă că news-urile FJ chiar mișcă piața.",
        "test": "Mann-Whitney U one-sided (greater) + t-test Welch pe distribuții non-egale. Baseline: 30 ferestre random per event, evităm ±60min în jurul oricărui event.",
        "interpretation": "<strong>Ratio events/baseline</strong> = de câte ori mai mare e mișcarea pe events vs random. Ratio &gt; 1 înseamnă piața reacționează la news.",
        "result": "<strong>ULTRA-confirmat:</strong> ratio 1.6×–3.1× pe toate ferestrele × ambele assets, p &lt; 10⁻⁵⁹. NDX +1m: 3.1× (cea mai mare amplificare la moment scurt).",
        "trader": "News-ul FJ chiar produce volatility spikes. Pentru strategie de <strong>volatility</strong> (straddles/strangles) e validare clară.",
        "limitation": "H1 măsoară doar magnitudine, nu direcție (vezi H2). Și nu controlează pentru pre-event drift (vezi H8).",
        "citation": "Andersen et al. (2003) — macro news → FX volatility intraday."
    },
    "h2": {
        "title": "H2 — Sentimentul AI prezice direcția prețului",
        "what": "Modelul DeepSeek clasifică sentiment_usd/sentiment_ndx ∈ {bull, bear, neutral}. Comparăm cu direcția realizată sign(Δ%) post-event. Hit rate = procent corect.",
        "test": "Binomial test one-sided (greater) vs hazard 50% (excludem neutral).",
        "interpretation": "<strong>Hit rate &gt; 50%</strong> = sentiment AI are edge direcțional. <strong>50%</strong> = pură întâmplare.",
        "result": "<strong>NDX +5m: 53.7% (p=0.0016) ✅</strong>, NDX +1m: 52.9% (p=0.011). EUR/USD ~50% pe toate ferestrele = NEPREZICÂND. Pe NDX edge există dar e MIC (3-4% peste random).",
        "trader": "<strong>NU folosi sentiment AI pentru trade direcțional pur.</strong> Edge e prea mic pe NDX (cost tranzacționare îl mănâncă), inexistent pe FX. Folosește pentru <em>filter</em> + magnitude.",
        "limitation": "Hit rate scăzut pe FX poate însemna că (a) news-ul e deja prețuit înainte (pre-event drift, H8), sau (b) reacția FX e mai complexă decât bull/bear (volatility, range expansion).",
        "citation": "Lopez-Lira & Tang (2024) — ChatGPT prezice 51.8 bp daily, dar pe orizont longer; Muhammad et al. (2025)."
    },
    "h3": {
        "title": "H3 — Trendul zilei moderează impactul știrii",
        "what": "Regresie OLS: |Δ%| = β₀ + β₁·sentiment + β₂·trend_zi + β₃·(sentiment × trend_zi). Termenul de interacțiune β₃ măsoară dacă news-urile aliniate cu trendul produc reacții mai mari (momentum) sau mai mici (mean reversion).",
        "test": "OLS cu robust SE; testăm semnificația lui β₃.",
        "interpretation": "<strong>β₃ &gt; 0</strong>: trend amplifică news-ul (momentum domină). <strong>β₃ &lt; 0</strong>: trend absoarbe news-ul (mean reversion). R² = % varianță explicată.",
        "result": "<strong>NDX +5m: β₃=+0.038, p&lt;10⁻¹⁵, R²=0.16</strong> — trend AMPLIFICĂ news-ul. NDX +15m similar. EUR/USD: β₃ slight negativ pe ferestre scurte (mean reversion ușoară), dar R² mic (0.01-0.02).",
        "trader": "Pe NDX, <strong>trade WITH the trend</strong> când news confirmă direcția. Bull news pe trend up → spike mare; bear news pe trend up → reacție amortizată. Implicație: confirmă prima trendul, apoi tradezi news-ul.",
        "limitation": "Trend definit ca Δ% în ultimele 60min. Definiții alternative (SMA panta, ATR) pot da rezultate diferite.",
        "citation": "Daniel-Hirshleifer-Subrahmanyam (1998) overconfidence model; Hong & Stein (1999) underreaction-overreaction."
    },
    "h4": {
        "title": "H4 — Sentiment agregat în piață închisă prezice gap-ul de redeschidere",
        "what": "Pentru fiecare perioadă cu piața închisă (weekend FX, overnight NDX), agregăm sentimentele tuturor news-urilor primite în interval (confidence-weighted). Testăm dacă acest agregat prezice gap-ul Δ%[close → open].",
        "test": "OLS regresie: gap_pct ~ aggregate_sentiment, per asset.",
        "interpretation": "<strong>β &gt; 0 cu p semnificativ</strong> = sentiment agregat → direcție gap. R² = puterea predicției.",
        "result": "<strong>NDX (89 overnight periods): β=+0.27, p=0.011, R²=0.07</strong> ✅. EUR/USD (30 weekend periods): nesemnificativ (β=-0.08, p=0.17).",
        "trader": "Pe <strong>overnight NDX</strong>: dacă sentiment agregat seara e bear, anticipă gap down de dimineață. Useful pentru poziționare overnight (futures, ETF afterhours). Pe <strong>FX weekend</strong>: nu funcționează (n mic + EUR/USD complexity).",
        "limitation": "Closed periods FX (weekend-uri) sunt doar ~52/an = sample mic. NDX 89 overnight = mai bun. R²=0.07 = sentiment explică 7% din varianța gap-ului — restul e zgomot, alți factori.",
        "citation": "Berkman et al. (2009) — overnight return drift după news."
    },
    "h5": {
        "title": "H5 — `expected_magnitude` (low/med/high) prezice |Δ%| realizat",
        "what": "Modelul DeepSeek estimează apriori dacă news-ul va produce mișcare low/med/high. Testăm dacă acest predictor coincide empiric cu magnitudinea realizată.",
        "test": "ANOVA între cele 3 categorii pentru fiecare asset × fereastră.",
        "interpretation": "<strong>F-stat mare cu p &lt; 0.05</strong> + ordinea low &lt; med &lt; high în mediile observate = modelul prezice corect magnitudinea.",
        "result": "<strong>EUR/USD pe toate ferestrele: p &lt; 0.01</strong>, ordering corect (high &gt; med &gt; low). NDX semnificativ pe ferestre scurte (1m, 5m, 60m); pe 15m și 240m nesemnificativ.",
        "trader": "Modelul AI poate fi folosit ca <strong>filter de relevanță</strong>: news-uri marcate `low` produc mișcări mici (poate skip), `high` produc mișcări mari (acolo te concentrezi).",
        "limitation": "ANOVA nu controlează pentru categorie sau surprise. H13 (surprise_level) e signalul mai strong. Pentru NDX +15m semnal slab — magnitudinea poate să nu fie monotonică pe orizonturi medii.",
        "citation": "Frazzini & Lamont (2007) — investor sentiment proxy validation."
    },
    "h6": {
        "title": "H6 — Calibrarea `confidence` modelului",
        "what": "Modelul DeepSeek dă un scor de încredere (0-1) pentru fiecare predicție. <strong>Calibration</strong> înseamnă că dacă zice `0.8 confidence`, hit rate observat ar trebui să fie ~80%. Testăm cu Brier score și reliability diagram (NDX +15m).",
        "test": "Bucketing pe confidence + hit rate per bucket. Brier score = MSE între confidence și realized direction (lower=better; 0.25=random).",
        "interpretation": "<strong>Diagrama de calibrare ar trebui să fie pe diagonală</strong>. Dacă e plată sau invers ordonată = modelul e overconfident sau under-confident.",
        "result": "<strong>WEAKNESS: Brier=0.279</strong> (slightly above random 0.25). Hit rate plat ~50% pe TOATE buckets (40.7%, 53.4%, 52.2%, 50.8%) — modelul e <strong>OVERCONFIDENT</strong> pe predicții cu confidence &gt; 0.6. Confidence-ul nu reflectă acuratețea reală.",
        "trader": "<strong>NU filtra trades pe `confidence > 0.8`</strong> crezând că-s mai sigure. Confidence-ul e <strong>decorativ</strong>, nu informativ. Pentru filter folosește `surprise_level` (H13) sau magnitude (H5).",
        "limitation": "DeepSeek temperature 0.1 + few-shot prompts → confidence vine din distribuția probabilităților peste tokens, dar nu e calibrat pe ground truth. Fix posibil: post-hoc isotonic regression / Platt scaling pe 200 mostre etichetate (după ce le ai).",
        "citation": "Lopez-Lira et al. (2025) — memorization & calibration caveats. Niculescu-Mizil & Caruana (2005) — calibration of supervised learning."
    },
    "h7": {
        "title": "H7 — Categoriile diferite produc magnitudini diferite",
        "what": "Categoriile noastre: geopolitical / central_bank / politics / energy / corporate / other. Testăm dacă |Δ%| diferă semnificativ între ele.",
        "test": "ANOVA pe |Δ%[+15m]| ~ category, per asset.",
        "interpretation": "<strong>F-stat mare + p &lt; 0.05</strong> = categoriile diferă. Tabel cu top categorii indică unde se concentrează mișcarea.",
        "result": "<strong>EUR/USD: F=6.93, p&lt;10⁻⁴ ✅</strong> (categories matter). NDX: F=1.40, p=0.23 (NU diferă semnificativ — toate categoriile mișcă NDX similar).",
        "trader": "Pe FX, focusează pe news <strong>central_bank</strong> și <strong>politics</strong> (probabil cele mai mari mișcări — verifică tabelul). Pe NDX, orice categorie producea mișcare comparabilă — <em>news-ul în general</em> contează, nu tipul.",
        "limitation": "Categorizare automată prin keyword matching = imperfectă. Anumite news-uri pot fi mis-classified. NDX nu diferă pentru că e dominat de US politics/central bank, restul fiind diluție.",
        "citation": "Ge, Kurov & Wolfe (2019) — Trump tweets per company effects."
    },
    "h8": {
        "title": "H8 — Pre-event drift (information leakage / market efficiency)",
        "what": "Compară |Δ%| în fereastra <strong>[-15m, 0]</strong> ÎNAINTE de event vs ferestre random fără event. Dacă pre-event &gt; baseline, sugerează că informația se mișcă în piață ÎNAINTE de a apărea pe FJ.",
        "test": "Mann-Whitney U one-sided (greater) pe pre-event |Δ%| vs random baseline.",
        "interpretation": "<strong>Pre &gt;&gt; baseline cu p semnificativ</strong> = leakage / front-running / surse mai rapide decât FJ. <strong>Pre ≈ baseline</strong> = piață eficientă, news shock instantaneu.",
        "result": "<strong>🚨 LEAKAGE MAJOR: NDX pre-event |Δ%|=0.216 vs baseline 0.063 (3.4× mai mare), p=10⁻²⁹⁸</strong>. EUR/USD: 0.078 vs 0.028 (2.8× mai mare), p=10⁻²²³.",
        "trader": "<strong>Implicație CRITICĂ: FJ NU e o sursă rapidă</strong>. Când vezi 🔴 BREAKING pe Discord, piața s-a mișcat deja masiv în ultimele 15min. Strategia greșită: scalp spike-ul direct. Strategia corectă: (a) intră POST-event pe momentum (vezi H9), sau (b) ai surse mai rapide (Bloomberg, Reuters direct).",
        "limitation": "Magnitudinea drift-ului poate fi inflată de OUR own definition of event time (timestamp Discord, nu timpul real al news-ului — ex: o știre publicată pe Reuters la 14:50 UTC poate ajunge pe FJ la 14:53 UTC, deci 'pre-event drift' între 14:48-14:53 e de fapt post-event Reuters).",
        "citation": "Bartov, Faurel & Mohanram (2018) — leakage detection în social media; Patell (1979) — original event study methodology."
    },
    "h9": {
        "title": "H9 — Persistență vs decay al impactului news-ului",
        "what": "Pentru fiecare event, comparăm sign(Δ%[+15m]) cu sign(Δ%[+4h]). Sign-match &gt; 50% = mișcarea persistă. Plus median ratio |Δ%[+4h]| / |Δ%[+15m]| pentru a vedea dacă magnitudinea crește sau scade.",
        "test": "Binomial test pe sign-match vs 50% (two-sided).",
        "interpretation": "<strong>Sign-match &gt; 50% și ratio &gt; 1</strong> = momentum, news-ul amplifică în timp. <strong>Sign-match &lt; 50%</strong> = mean reversion / overreaction urmată de corecție.",
        "result": "<strong>💡 EUR/USD: sign-match 59.3%, p&lt;10⁻¹⁶, ratio 3.04. NDX: 60.4%, p&lt;10⁻¹⁶, ratio 4.12.</strong> Magnitudinea CREȘTE 3-4× între +15m și +4h. <strong>Nu fade — amplificare!</strong>",
        "trader": "Strategie: <strong>HOLD pentru ore, nu minute</strong>. News produce momentum care continuă 30min-4h. Stop-loss-uri largi. NU fade-ui breaking news pe NDX în primele 4h. Asta contrazice teoria overshoot+reversal pe orizonturi scurte.",
        "limitation": "Ratio 3-4× include și natural drift baseline; strict abnormal return ar avea ratio mai mic. Dar sign-match 60% e robust. Posibil că info se procesează gradual (under-reaction Hong-Stein 1999).",
        "citation": "Hong & Stein (1999) — gradual information diffusion; Tetlock (2007) — sentiment persistence in returns."
    },
    "h10": {
        "title": "H10 — Reacție de volum la events",
        "what": "Volume_ratio = volume cumulativ în fereastra event / volume mediu pe baseline 30 zile la aceeași oră. Dacă ratio &gt; 1, volumul reacționează la news (signal de validare market participation).",
        "test": "Wilcoxon signed-rank one-sided (volume_ratio &gt; 1).",
        "interpretation": "<strong>Median ratio &gt; 1 cu p semnificativ</strong> = volume confirmation. <strong>Ratio ≈ 1</strong> = mișcare de preț fără volume = posibil spike artificial.",
        "result": "Output relativ slab pe full data (volume Dukascopy CFD pentru NDX e proxy, nu real exchange volume; EUR/USD e volume broker, nu interbank). <strong>Necesită debug suplimentar</strong> pentru raportare în paper.",
        "trader": "Volume confirmation matter: o mișcare de preț pe news cu volume puternic = trend valid. Pe news cu volume slab = posibil spike thin liquidity, mai puțin actionable.",
        "limitation": "Dukascopy CFD volume nu reflectă volume real CME futures (NDX) sau interbank (EUR/USD). Pentru paper rigoros, e bine să notăm asta și să folosim volume CME pentru NDX dacă e disponibil.",
        "citation": "Easley & O'Hara (1992) — volume as information signal; Lee (1992) — earnings news volume reaction."
    },
    "h11": {
        "title": "H11 — Time-of-day & day-of-week moderează impactul",
        "what": "Testăm dacă |Δ%| la +15m diferă funcție de ora UTC sau ziua săptămânii. Anumite ore (US open, FOMC days) ar putea avea reacții mai mari.",
        "test": "ANOVA |Δ%| ~ hour_utc; ANOVA |Δ%| ~ dow.",
        "interpretation": "<strong>F-stat mare + p &lt; 0.05</strong> = timing matter. Top hours/days indică unde să-ți concentrezi atenția.",
        "result": "<strong>EUR/USD: hour F=4.98, p=10⁻¹²; dow F=9.97, p=10⁻⁹ ✅</strong>. <strong>NDX: hour F=2.74, p=10⁻⁵; dow F=4.81, p=10⁻⁴ ✅</strong>. Ambele timing dimensions sunt semnificative.",
        "trader": "Trade <strong>doar în orele/zilele cu impact mare</strong>. NY open (13:30-15:00 UTC) și FOMC announcements (~18:00 UTC) sunt ferestre de focus. Marți-joi tipic mai active decât vinerea după-amiaza (poziționare pre-weekend).",
        "limitation": "Top hours/days nu sunt extrase aici (necesită script suplimentar). ANOVA e high-level — interaction hour×category n-am testat.",
        "citation": "Andersen & Bollerslev (1998) — intraday seasonality FX volatility; Harvey & Huang (1991) — open/close patterns."
    },
    "h12": {
        "title": "H12 — Asimetrie bear vs bull (loss aversion / fear premium)",
        "what": "Behavioral finance prezice că news-urile bear produc mișcări mai mari decât bull (loss aversion Kahneman-Tversky, fear premium VIX literature). Testăm |Δ%|_bear vs |Δ%|_bull.",
        "test": "Mann-Whitney U one-sided (bear > bull).",
        "interpretation": "<strong>Ratio bear/bull &gt; 1 cu p semnificativ</strong> = asimetrie confirmată. <strong>Ratio ≈ 1</strong> = simetrie (contraintuitiv).",
        "result": "<strong>SURPRINZĂTOR: asimetrie minimă.</strong> Ratio 0.91-1.11 pe toate ferestrele. EUR/USD: nici un p &lt; 0.05. NDX +1m: ratio 1.11, p=0.04 marginal.",
        "trader": "<strong>Nu există fear premium clar pe această perioadă.</strong> Position sizing simetric pe bull și bear news. Posibil că market-ul a internalizat already-frequent shocks (Trump volatility, geopolitical) → desensibilizare.",
        "limitation": "Eșantionul (2025-2026) poate fi atipic — Trump-era volatility. Pe alte perioade (2008, 2020 COVID) asimetria poate fi mai pronunțată. NU putem generaliza la alte regimuri.",
        "citation": "Kahneman & Tversky (1979) prospect theory; Bekaert & Hoerova (2014) — uncertainty asymmetry."
    },
    "h13": {
        "title": "H13 — `surprise_level` (expected/surprise/shock) prezice magnitudinea",
        "what": "Câmp NOU în schema sentiment: surprise_level. Modelul DeepSeek clasifică news-ul ca expected/surprise/shock. Testăm dacă această clasificare prezice empiric |Δ%|.",
        "test": "ANOVA |Δ%| ~ surprise_level, per asset × fereastră.",
        "interpretation": "<strong>Ordering expected &lt; surprise &lt; shock</strong> + p semnificativ = modelul prezice corect surpriza.",
        "result": "<strong>💥 NDX +1m: expected=0.042, surprise=0.051, shock=0.085 — exact 2× expected!</strong> F=13.85, p=10⁻⁶. NDX +5m similar (F=7.17, p&lt;10⁻³). EUR/USD +1m semnificativ marginal (p=0.04).",
        "trader": "<strong>Cea mai actionable descoperire pentru position sizing.</strong> Folosește surprise_level ca multiplicator: <code>expected → 0.5× size</code>, <code>surprise → 1× size</code>, <code>shock → 2× size</code>. Modelul AI captează intensitatea util pentru risk management.",
        "limitation": "Pe ferestre lungi (60m, 240m) signalul fade — surprise_level e relevant doar pentru reacție imediată. Plus: shock e rare (puține events), categoria poate fi dezechilibrată.",
        "citation": "Birz & Lott (2011) — news surprise economic announcements; Beaver (1968) earnings surprise."
    },
    "h14": {
        "title": "H14 — Cross-asset spillover (NDX × EUR/USD)",
        "what": "Pentru fiecare event cu ambele Δ% disponibile, calculăm corelația per-event NDX vs EUR/USD. Risk-off classic prezice negative correlation (USD up, NDX down).",
        "test": "Pearson + Spearman correlation; sign-match rate (binomial).",
        "interpretation": "<strong>Pearson &lt; 0</strong> = anti-corelație risk-off. <strong>Sign-match &gt; 50%</strong> = aceeași direcție mai des. Cele două pot fi inconsistente dacă mișcările extreme diferă în magnitudine.",
        "result": "<strong>Pearson r=-0.108, p=10⁻⁶</strong> (negativ semnificativ — risk-off pattern). Dar <strong>sign-match=54.8%</strong>, p=10⁻⁵ (slightly positive). Inconsistență interesantă.",
        "trader": "<strong>NU presupune corelație simplă</strong>. La nivel de direcție concordă (54.8%), dar magnitudinile se mișcă diferit. NDX e amplificator de risc; EUR/USD e mai stabil. Pentru hedging: NDX hedge cu EUR/USD funcționează doar în events extreme risk-off, nu în general.",
        "limitation": "Folosim simple per-event correlation pe Δ% +15m. Lead-lag analysis (NDX lead EUR/USD?) n-am făcut. Plus: only events with both assets present (intraday windows) — exclude weekend/overnight.",
        "citation": "Bollerslev, Engle & Wooldridge (1988) — multivariate GARCH; Forbes & Rigobon (2002) — contagion vs interdependence."
    },
}


def render_explanation(h_id: str) -> str:
    d = HYPOTHESIS_DETAILS.get(h_id)
    if not d:
        return ""
    return f"""
<div class='h-explain'>
  <div class='h-block'><span class='h-label'>📖 Ce testează:</span> {d['what']}</div>
  <div class='h-block'><span class='h-label'>🧪 Test statistic:</span> {d['test']}</div>
  <div class='h-block'><span class='h-label'>🔍 Cum interpretezi:</span> {d['interpretation']}</div>
  <div class='h-block result-box'><span class='h-label'>📊 Rezultat:</span> {d['result']}</div>
  <div class='h-block trader-box'><span class='h-label'>💼 Implicație practică (trader):</span> {d['trader']}</div>
  <div class='h-block warn-box'><span class='h-label'>⚠️ Limitări:</span> {d['limitation']}</div>
  <div class='h-block muted'><span class='h-label'>📚 Literatură relevantă:</span> {d['citation']}</div>
</div>
"""


def fig_to_base64(fig) -> str:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=110, bbox_inches="tight")
    plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode()


def img_tag(b64, alt=""):
    return f'<img src="data:image/png;base64,{b64}" alt="{alt}" style="max-width:100%;height:auto;border:1px solid #ddd;border-radius:6px;"/>'


def plot_event_timeline(event_row, prices_eur, prices_ndx, lookback_min=30, lookahead_min=240):
    ts = pd.to_datetime(event_row["timestamp_utc"], utc=True)
    start = ts - pd.Timedelta(minutes=lookback_min)
    end = ts + pd.Timedelta(minutes=lookahead_min)

    eur = prices_eur.loc[start:end] if not prices_eur.empty else pd.DataFrame()
    ndx = prices_ndx.loc[start:end] if not prices_ndx.empty else pd.DataFrame()

    fig, axes = plt.subplots(2, 1, figsize=(11, 5.5), sharex=True)
    fig.subplots_adjust(hspace=0.08)

    for ax, df, asset, color in [
        (axes[0], eur, "EUR/USD", "#1f77b4"),
        (axes[1], ndx, "NQ-100", "#d62728"),
    ]:
        if df.empty:
            ax.text(0.5, 0.5, "no data in window", transform=ax.transAxes, ha="center")
            ax.set_ylabel(asset)
            continue
        ax.plot(df.index, df["close"], color=color, linewidth=1.2)
        ax.axvline(ts, color="black", linestyle="--", linewidth=1, alpha=0.7, label="event")
        # mark windows
        for w, lbl_color in zip([1, 5, 15, 60, 240], ["#666"] * 5):
            tw = ts + pd.Timedelta(minutes=w)
            if df.index.min() <= tw <= df.index.max():
                ax.axvline(tw, color="#999", linestyle=":", linewidth=0.7, alpha=0.5)
        ax.set_ylabel(asset, fontsize=10)
        ax.grid(True, alpha=0.25)
        ax.tick_params(labelsize=8)

    sentiment_usd = event_row.get("sentiment_usd", "?")
    sentiment_ndx = event_row.get("sentiment_ndx", "?")
    conf = event_row.get("confidence", float("nan"))
    cat = event_row.get("category", "?")
    content_preview = (event_row.get("content", "") or "").splitlines()[0][:130]

    title = (f"{ts.strftime('%Y-%m-%d %H:%M')} UTC  ·  {cat}  ·  "
             f"USD={sentiment_usd}, NDX={sentiment_ndx}  ·  conf={conf:.2f}\n"
             f"{content_preview}")
    fig.suptitle(title, fontsize=10, y=0.995)
    axes[1].set_xlabel("UTC time", fontsize=9)
    return fig


def plot_h1(h1_df):
    if h1_df.empty:
        return None
    fig, axes = plt.subplots(1, 2, figsize=(11, 4))
    for ax, asset in zip(axes, ASSETS):
        sub = h1_df[h1_df["asset"] == asset].sort_values("window_min")
        if sub.empty:
            ax.set_title(f"{asset.upper()} — no data")
            continue
        x = np.arange(len(sub))
        width = 0.35
        ax.bar(x - width / 2, sub["mean_abs_event"], width, label="events |Δ%|", color="#d62728")
        ax.bar(x + width / 2, sub["mean_abs_baseline"], width, label="baseline |Δ%|", color="#7f7f7f")
        ax.set_xticks(x)
        ax.set_xticklabels([f"+{w}m" for w in sub["window_min"]])
        ax.set_title(f"{asset.upper()} — mean |Δ%|: events vs baseline (H1)")
        ax.set_ylabel("|Δ%|")
        ax.legend(fontsize=9)
        ax.grid(True, axis="y", alpha=0.3)
        # annotate p-values
        for i, (_, row) in enumerate(sub.iterrows()):
            ax.text(x[i], max(row["mean_abs_event"], row["mean_abs_baseline"]) * 1.05,
                    f"p={row['p_mwu']:.2f}", ha="center", fontsize=8, color="#333")
    plt.tight_layout()
    return fig


def plot_h2(h2_df):
    if h2_df.empty:
        return None
    fig, axes = plt.subplots(1, 2, figsize=(11, 4))
    for ax, asset in zip(axes, ASSETS):
        sub = h2_df[h2_df["asset"] == asset].sort_values("window_min")
        if sub.empty:
            ax.set_title(f"{asset.upper()} — no data")
            continue
        x = np.arange(len(sub))
        bars = ax.bar(x, sub["hit_rate"] * 100, color="#2ca02c", alpha=0.8)
        ax.axhline(50, color="black", linestyle="--", linewidth=1, label="random (50%)")
        ax.set_xticks(x)
        ax.set_xticklabels([f"+{w}m" for w in sub["window_min"]])
        ax.set_ylabel("hit rate (%)")
        ax.set_ylim(0, 110)
        ax.set_title(f"{asset.upper()} — sentiment-direction hit rate (H2)")
        ax.legend(fontsize=9, loc="upper left")
        ax.grid(True, axis="y", alpha=0.3)
        for i, (_, row) in enumerate(sub.iterrows()):
            color = "#1a1a1a" if row["p_binom"] < 0.05 else "#666"
            weight = "bold" if row["p_binom"] < 0.05 else "normal"
            ax.text(x[i], row["hit_rate"] * 100 + 3,
                    f"{int(row['correct'])}/{int(row['n'])}\np={row['p_binom']:.3f}",
                    ha="center", fontsize=8, color=color, fontweight=weight)
    plt.tight_layout()
    return fig


def plot_h5_magnitude(h5_df, returns_df):
    if h5_df.empty:
        return None
    sub_15 = h5_df[h5_df["window_min"] == 15]
    fig, axes = plt.subplots(1, 2, figsize=(11, 4))
    for ax, asset in zip(axes, ASSETS):
        row = sub_15[sub_15["asset"] == asset]
        if row.empty:
            ax.set_title(f"{asset.upper()} — no data")
            continue
        r = row.iloc[0]
        means = [r["mean_low"], r["mean_med"], r["mean_high"]]
        ns = [int(r["n_low"]), int(r["n_med"]), int(r["n_high"])]
        bars = ax.bar(["low", "med", "high"], means, color=["#7fb3d5", "#f4a261", "#e63946"])
        for i, b in enumerate(bars):
            ax.text(b.get_x() + b.get_width() / 2, b.get_height(),
                    f"n={ns[i]}", ha="center", va="bottom", fontsize=9)
        ax.set_title(f"{asset.upper()} +15m — |Δ%| by predicted magnitude\n(ANOVA p={r['p_anova']:.4g})")
        ax.set_ylabel("mean |Δ%|")
        ax.grid(True, axis="y", alpha=0.3)
    plt.tight_layout()
    return fig


def plot_h6_calibration(h6_df):
    if h6_df.empty:
        return None
    fig, ax = plt.subplots(figsize=(6.5, 5))
    xs = h6_df["mean_confidence"].values
    ys = h6_df["hit_rate"].values
    ns = h6_df["n"].values
    ax.plot([0, 1], [0, 1], "--", color="#888", label="perfect calibration")
    ax.plot(xs, ys, "o-", color="#1f77b4", markersize=10, linewidth=2, label="observed")
    for x, y, n in zip(xs, ys, ns):
        ax.annotate(f"n={int(n)}", (x, y), textcoords="offset points", xytext=(8, 6), fontsize=9)
    brier = h6_df["brier_overall"].iloc[0]
    ax.set_xlim(-0.05, 1.05)
    ax.set_ylim(-0.05, 1.05)
    ax.set_xlabel("predicted probability (mean confidence)")
    ax.set_ylabel("observed hit rate")
    ax.set_title(f"H6 — confidence calibration (NDX +15m)  ·  Brier={brier:.4f}")
    ax.legend(loc="upper left")
    ax.grid(True, alpha=0.3)
    return fig


def plot_h7_category(h7_df):
    if h7_df.empty:
        return None
    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    for ax, asset in zip(axes, ASSETS):
        sub = h7_df[h7_df["asset"] == asset].sort_values("mean_abs_pct", ascending=True)
        if sub.empty:
            ax.set_title(f"{asset.upper()} — no data")
            continue
        bars = ax.barh(sub["category"], sub["mean_abs_pct"], color="#2ca02c", alpha=0.8)
        for i, (_, r) in enumerate(sub.iterrows()):
            ax.text(r["mean_abs_pct"], i, f"  n={int(r['n'])}", va="center", fontsize=9)
        p_anova = sub["p_anova"].iloc[0]
        ax.set_title(f"{asset.upper()} +15m — mean |Δ%| by category  (ANOVA p={p_anova:.4g})")
        ax.set_xlabel("mean |Δ%|")
        ax.grid(True, axis="x", alpha=0.3)
    plt.tight_layout()
    return fig


def plot_h8_drift(h8_df):
    if h8_df.empty:
        return None
    fig, ax = plt.subplots(figsize=(8, 4.5))
    x = np.arange(len(h8_df))
    width = 0.28
    ax.bar(x - width, h8_df["mean_pre_abs"], width, label="pre [-15m, 0]", color="#9467bd")
    ax.bar(x, h8_df["mean_post_abs"], width, label="post [0, +15m]", color="#d62728")
    ax.bar(x + width, h8_df["mean_baseline_abs"], width, label="random baseline", color="#7f7f7f")
    ax.set_xticks(x)
    ax.set_xticklabels(h8_df["asset"].str.upper())
    ax.set_ylabel("mean |Δ%|")
    ax.set_title("H8 — pre-event drift vs post vs baseline (15m windows)")
    ax.legend()
    ax.grid(True, axis="y", alpha=0.3)
    for i, (_, r) in enumerate(h8_df.iterrows()):
        ax.text(i, max(r["mean_pre_abs"], r["mean_post_abs"]) * 1.05,
                f"pre>base p={r['p_pre_vs_baseline_mwu']:.3f}", ha="center", fontsize=8)
    plt.tight_layout()
    return fig


def plot_h9_decay(h9_df, returns_df):
    fig, ax = plt.subplots(figsize=(8, 4.5))
    if h9_df.empty:
        ax.set_title("no decay data")
        return fig
    # Actual curves: median |Δ%| at each window
    for asset, color in zip(ASSETS, ["#1f77b4", "#d62728"]):
        sub = returns_df[(returns_df["asset"] == asset) & returns_df["delta_pct"].notna()]
        medians = []
        for w in WINDOWS_MIN:
            v = sub[sub["window_min"] == w]["delta_pct"].abs()
            medians.append(float(v.median()) if not v.empty else np.nan)
        ax.plot(WINDOWS_MIN, medians, "o-", color=color, label=asset.upper(), linewidth=2, markersize=8)
    ax.set_xscale("log")
    ax.set_xlabel("window (minutes, log scale)")
    ax.set_ylabel("median |Δ%|")
    ax.set_title("H9 — magnitude decay/persistence across windows")
    ax.legend()
    ax.grid(True, alpha=0.3)
    return fig


def plot_h10_volume(h10_df):
    if h10_df.empty:
        return None
    fig, axes = plt.subplots(1, 2, figsize=(11, 4))
    for ax, asset in zip(axes, ASSETS):
        sub = h10_df[h10_df["asset"] == asset].sort_values("window_min")
        if sub.empty:
            ax.set_title(f"{asset.upper()} — no data")
            continue
        x = np.arange(len(sub))
        ax.bar(x, sub["median_volume_ratio"], color="#ff9800", alpha=0.85)
        ax.axhline(1.0, color="black", linestyle="--", linewidth=1, label="baseline (=1)")
        ax.set_xticks(x)
        ax.set_xticklabels([f"+{w}m" for w in sub["window_min"]])
        ax.set_ylabel("median volume_ratio")
        ax.set_title(f"{asset.upper()} — H10 volume reaction")
        ax.legend(fontsize=9)
        ax.grid(True, axis="y", alpha=0.3)
        for i, (_, r) in enumerate(sub.iterrows()):
            ax.text(x[i], r["median_volume_ratio"] * 1.02,
                    f"p={r['p_wilcoxon_gt1']:.3f}", ha="center", fontsize=8)
    plt.tight_layout()
    return fig


def plot_h11_tod(returns_df):
    fig, axes = plt.subplots(1, 2, figsize=(13, 4))
    for ax, asset in zip(axes, ASSETS):
        sub = returns_df[
            (returns_df["asset"] == asset)
            & (returns_df["window_min"] == 15)
            & returns_df["delta_pct"].notna()
        ]
        if sub.empty:
            ax.set_title(f"{asset.upper()} — no data")
            continue
        h_means = sub.groupby("hour_utc")["delta_pct"].apply(lambda s: s.abs().mean())
        ax.bar(h_means.index, h_means.values, color="#17becf", alpha=0.85)
        ax.set_xticks(range(0, 24, 2))
        ax.set_xlabel("hour of day (UTC)")
        ax.set_ylabel("mean |Δ%|")
        ax.set_title(f"{asset.upper()} — H11 hour-of-day effect (+15m)")
        ax.grid(True, axis="y", alpha=0.3)
    plt.tight_layout()
    return fig


def plot_h12_asymmetric(h12_df):
    if h12_df.empty:
        return None
    fig, axes = plt.subplots(1, 2, figsize=(11, 4))
    for ax, asset in zip(axes, ASSETS):
        sub = h12_df[h12_df["asset"] == asset].sort_values("window_min")
        if sub.empty:
            ax.set_title(f"{asset.upper()} — no data")
            continue
        x = np.arange(len(sub))
        width = 0.35
        ax.bar(x - width / 2, sub["mean_abs_bear"], width, color="#d62728", label="bear")
        ax.bar(x + width / 2, sub["mean_abs_bull"], width, color="#2ca02c", label="bull")
        ax.set_xticks(x)
        ax.set_xticklabels([f"+{w}m" for w in sub["window_min"]])
        ax.set_ylabel("mean |Δ%|")
        ax.set_title(f"{asset.upper()} — H12 asymmetric (bear vs bull)")
        ax.legend()
        ax.grid(True, axis="y", alpha=0.3)
        for i, (_, r) in enumerate(sub.iterrows()):
            ax.text(x[i], max(r["mean_abs_bear"], r["mean_abs_bull"]) * 1.05,
                    f"p={r['p_mwu_bear_gt_bull']:.3f}", ha="center", fontsize=8)
    plt.tight_layout()
    return fig


def plot_h13_surprise(h13_df):
    if h13_df.empty:
        return None
    sub_15 = h13_df[h13_df["window_min"] == 15]
    fig, axes = plt.subplots(1, 2, figsize=(11, 4))
    for ax, asset in zip(axes, ASSETS):
        row = sub_15[sub_15["asset"] == asset]
        if row.empty:
            ax.set_title(f"{asset.upper()} — no data")
            continue
        r = row.iloc[0]
        means = [r["mean_expected"], r["mean_surprise"], r["mean_shock"]]
        ns = [int(r["n_expected"]), int(r["n_surprise"]), int(r["n_shock"])]
        bars = ax.bar(["expected", "surprise", "shock"], means,
                      color=["#7fb3d5", "#f4a261", "#a4133c"])
        for i, b in enumerate(bars):
            ax.text(b.get_x() + b.get_width() / 2, b.get_height(),
                    f"n={ns[i]}", ha="center", va="bottom", fontsize=9)
        ax.set_title(f"{asset.upper()} +15m — H13 surprise_level\n(ANOVA p={r['p_anova']:.4g})")
        ax.set_ylabel("mean |Δ%|")
        ax.grid(True, axis="y", alpha=0.3)
    plt.tight_layout()
    return fig


def plot_h14_spillover(returns_df):
    pivot = returns_df[
        (returns_df["window_min"] == 15)
        & returns_df["delta_pct"].notna()
    ].pivot_table(index="event_id", columns="asset", values="delta_pct", aggfunc="first").dropna()
    fig, ax = plt.subplots(figsize=(7, 6))
    if pivot.empty:
        ax.set_title("no spillover data")
        return fig
    eur, ndx = pivot["eurusd"].values, pivot["ndx"].values
    ax.scatter(eur, ndx, alpha=0.4, s=20, color="#1f77b4")
    # Quadrant lines
    ax.axhline(0, color="black", linewidth=0.6)
    ax.axvline(0, color="black", linewidth=0.6)
    # Linear fit
    if len(eur) >= 2:
        slope, intercept = np.polyfit(eur, ndx, 1)
        xs = np.linspace(eur.min(), eur.max(), 50)
        ax.plot(xs, slope * xs + intercept, "r--", linewidth=2,
                label=f"OLS: slope={slope:+.2f}")
    from scipy.stats import pearsonr
    r_p, p_p = pearsonr(eur, ndx)
    ax.set_xlabel("EUR/USD Δ% [+15m]")
    ax.set_ylabel("NQ-100 Δ% [+15m]")
    ax.set_title(f"H14 — cross-asset spillover\nPearson r={r_p:+.3f} (p={p_p:.4g}), n={len(pivot)}")
    ax.legend()
    ax.grid(True, alpha=0.3)
    return fig


def plot_h3_scatter(returns_df):
    fig, axes = plt.subplots(1, 2, figsize=(11, 4))
    for ax, asset in zip(axes, ASSETS):
        sentiment_col = "sentiment_usd" if asset == "eurusd" else "sentiment_ndx"
        sub = returns_df[
            (returns_df["asset"] == asset)
            & (returns_df["window_min"] == 15)
            & returns_df["delta_pct"].notna()
        ].copy()
        if sub.empty:
            ax.set_title(f"{asset.upper()} — no data")
            continue
        sentiment_num = sub[sentiment_col].map({"bull": 1, "neutral": 0, "bear": -1})
        sub["sentiment_num"] = sentiment_num
        for sentiment_label, color, marker in [("bull", "#2ca02c", "^"), ("bear", "#d62728", "v"), ("neutral", "#7f7f7f", "o")]:
            sel = sub[sub[sentiment_col] == sentiment_label]
            if not sel.empty:
                ax.scatter(sel["sentiment_num"] + np.random.normal(0, 0.05, len(sel)),
                           sel["delta_pct"], color=color, marker=marker, s=80, alpha=0.7,
                           label=f"{sentiment_label} (n={len(sel)})")
        ax.axhline(0, color="black", linewidth=0.6, alpha=0.4)
        ax.axvline(0, color="black", linewidth=0.6, alpha=0.4)
        ax.set_xticks([-1, 0, 1])
        ax.set_xticklabels(["bear", "neutral", "bull"])
        ax.set_xlabel("predicted sentiment")
        ax.set_ylabel(f"realized Δ% [0,+15m]")
        ax.set_title(f"{asset.upper()} — predicted vs realized (window 15m)")
        ax.legend(fontsize=9)
        ax.grid(True, alpha=0.3)
    plt.tight_layout()
    return fig


def render_table(df, max_rows=20, fmt=None):
    if df.empty:
        return "<p style='color:#888'>no rows</p>"
    df = df.head(max_rows).copy()
    if fmt:
        for col, f in fmt.items():
            if col in df.columns:
                df[col] = df[col].apply(lambda v: f.format(v) if pd.notna(v) else "—")
    return df.to_html(index=False, classes="report-table", border=0)


def build_html(events, returns_df, hyp_dfs, prices_eur, prices_ndx, output_path):
    h1_df = hyp_dfs.get("h1", pd.DataFrame())
    h2_df = hyp_dfs.get("h2", pd.DataFrame())
    h3_df = hyp_dfs.get("h3", pd.DataFrame())
    h4_df = hyp_dfs.get("h4", pd.DataFrame())
    h5_df = hyp_dfs.get("h5", pd.DataFrame())
    h6_df = hyp_dfs.get("h6", pd.DataFrame())
    h7_df = hyp_dfs.get("h7", pd.DataFrame())
    h8_df = hyp_dfs.get("h8", pd.DataFrame())
    h9_df = hyp_dfs.get("h9", pd.DataFrame())
    h10_df = hyp_dfs.get("h10", pd.DataFrame())
    h11_df = hyp_dfs.get("h11", pd.DataFrame())
    h12_df = hyp_dfs.get("h12", pd.DataFrame())
    h13_df = hyp_dfs.get("h13", pd.DataFrame())
    h14_df = hyp_dfs.get("h14", pd.DataFrame())
    n_events = len(events)
    intraday_n = (~returns_df["is_in_closed_period"]).any() and (~returns_df["is_in_closed_period"]).sum()

    parts = []
    parts.append("""<!DOCTYPE html>
<html lang="ro"><head><meta charset="utf-8">
<title>Event Study Report — FJ News × FX/NDX</title>
<style>
body { font-family: -apple-system, "Segoe UI", Helvetica, Arial, sans-serif; max-width: 1200px; margin: 24px auto; padding: 0 24px; color:#222; }
h1 { border-bottom: 3px solid #d62728; padding-bottom: 8px; margin-top: 32px; }
h2 { color: #1f77b4; border-bottom: 1px solid #ddd; padding-bottom: 4px; margin-top: 28px; }
h3 { color: #555; margin-top: 22px; }
.report-table { border-collapse: collapse; font-size: 13px; margin: 12px 0; }
.report-table th, .report-table td { border: 1px solid #ddd; padding: 6px 10px; text-align: left; }
.report-table th { background: #f5f5f5; font-weight: 600; }
.report-table tr:nth-child(even) { background: #fafafa; }
.kpi { display: inline-block; background: #f0f4ff; border-left: 4px solid #1f77b4; padding: 10px 16px; margin: 8px 12px 8px 0; border-radius: 4px; }
.kpi-val { font-size: 22px; font-weight: 700; color: #1f77b4; }
.kpi-label { font-size: 11px; color: #555; text-transform: uppercase; letter-spacing: 0.5px; }
.signal { background: #e8f5e9; padding: 12px; border-left: 4px solid #2ca02c; border-radius: 4px; margin: 12px 0; }
.warn { background: #fff3cd; padding: 12px; border-left: 4px solid #ff9800; border-radius: 4px; margin: 12px 0; }
.event-card { border: 1px solid #e0e0e0; border-radius: 8px; padding: 14px; margin-bottom: 18px; background: #fcfcfc; }
.muted { color: #888; font-size: 12px; }
code { background: #f0f0f0; padding: 2px 5px; border-radius: 3px; font-size: 12px; }
.h-explain { background: #fafafa; border-left: 4px solid #1f77b4; padding: 14px 18px; margin: 12px 0 18px; border-radius: 4px; font-size: 14px; line-height: 1.55; }
.h-block { margin: 8px 0; }
.h-label { font-weight: 600; color: #1f77b4; display: inline-block; min-width: 0; margin-right: 6px; }
.h-explain .result-box { background: #e8f5e9; border-left: 3px solid #2ca02c; padding: 8px 12px; border-radius: 3px; }
.h-explain .trader-box { background: #fff8e1; border-left: 3px solid #f57c00; padding: 8px 12px; border-radius: 3px; }
.h-explain .warn-box { background: #ffebee; border-left: 3px solid #c62828; padding: 8px 12px; border-radius: 3px; }
.h-explain .muted { font-size: 12px; color: #666; }
.toc { background: #fafafa; border: 1px solid #e0e0e0; padding: 16px 22px; border-radius: 6px; margin: 18px 0; }
.toc h3 { margin: 0 0 10px; color: #444; }
.toc ul { columns: 2; -webkit-columns: 2; -moz-columns: 2; list-style: none; padding-left: 0; }
.toc li { margin: 4px 0; }
.toc a { color: #1f77b4; text-decoration: none; }
.toc a:hover { text-decoration: underline; }
</style></head><body>""")

    parts.append(f"<h1>Event Study Report — FJ News vs EUR/USD &amp; Nasdaq-100</h1>")
    parts.append(f"<p class='muted'>Generated {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')} · Pilot data, validation run</p>")

    parts.append("<h2>📊 Sumar</h2>")
    parts.append(f"<div class='kpi'><div class='kpi-val'>{n_events}</div><div class='kpi-label'>events analizate</div></div>")
    parts.append(f"<div class='kpi'><div class='kpi-val'>{len(prices_eur):,}</div><div class='kpi-label'>EUR/USD bars</div></div>")
    parts.append(f"<div class='kpi'><div class='kpi-val'>{len(prices_ndx):,}</div><div class='kpi-label'>NQ-100 bars</div></div>")
    if not h2_df.empty:
        best_h2 = h2_df.loc[h2_df["hit_rate"].idxmax()]
        parts.append(f"<div class='kpi'><div class='kpi-val'>{best_h2['hit_rate']*100:.0f}%</div>"
                     f"<div class='kpi-label'>best hit rate ({best_h2['asset']} +{int(best_h2['window_min'])}m)</div></div>")

    sig_h2 = h2_df[h2_df["p_binom"] < 0.05] if not h2_df.empty else pd.DataFrame()
    if not sig_h2.empty:
        for _, row in sig_h2.iterrows():
            parts.append(f"<div class='signal'><strong>🎯 Semnal H2 semnificativ:</strong> "
                         f"{row['asset'].upper()} la fereastra +{int(row['window_min'])}m — hit rate "
                         f"<strong>{row['hit_rate']*100:.0f}%</strong> ({int(row['correct'])}/{int(row['n'])}), "
                         f"p_binom = <strong>{row['p_binom']:.4f}</strong></div>")

    if not events.empty:
        date_min = events["timestamp_utc"].min()
        date_max = events["timestamp_utc"].max()
        days_span = (date_max - date_min).days
        if days_span < 7:
            parts.append("<div class='warn'><strong>⚠️ Notă pilot:</strong> rezultatele sunt pe "
                         f"{days_span+1} zi/zile de date (n mic). Pe export-ul complet puterea statistică va fi mult mai mare.</div>")
        else:
            parts.append(f"<div class='signal'><strong>📅 Full dataset:</strong> "
                         f"{n_events} events analizate pe {days_span} zile "
                         f"({date_min.strftime('%Y-%m-%d')} → {date_max.strftime('%Y-%m-%d')}). "
                         f"Putere statistică completă.</div>")

    # Table of contents
    parts.append("""<div class='toc'><h3>📑 Cuprins (click pentru navigare)</h3><ul>
<li><a href='#h1'>H1 — Magnitudine peste random</a></li>
<li><a href='#h2'>H2 — Sentiment prezice direcția</a></li>
<li><a href='#h3'>H3 — Sentiment × trend</a></li>
<li><a href='#h4'>H4 — Closed-period gap</a></li>
<li><a href='#h5'>H5 — Magnitude prediction</a></li>
<li><a href='#h6'>H6 — Calibration</a></li>
<li><a href='#h7'>H7 — Per-category</a></li>
<li><a href='#h8'>H8 — Pre-event drift 🚨</a></li>
<li><a href='#h9'>H9 — Persistență 💡</a></li>
<li><a href='#h10'>H10 — Volume reaction</a></li>
<li><a href='#h11'>H11 — Time-of-day</a></li>
<li><a href='#h12'>H12 — Bear vs bull</a></li>
<li><a href='#h13'>H13 — Surprise level 💥</a></li>
<li><a href='#h14'>H14 — Cross-asset</a></li>
<li><a href='#cases'>🔍 Top case studies</a></li>
</ul></div>""")

    parts.append("<h2>📋 Events analizate</h2>")
    show_cols = ["timestamp_utc", "category", "sentiment_usd", "sentiment_ndx",
                 "expected_magnitude", "confidence", "content"]
    available = [c for c in show_cols if c in events.columns]
    ev_show = events[available].copy()
    if "content" in ev_show.columns:
        ev_show["content"] = ev_show["content"].apply(lambda s: (s or "").splitlines()[0][:120])
    if "timestamp_utc" in ev_show.columns:
        ev_show["timestamp_utc"] = pd.to_datetime(ev_show["timestamp_utc"]).dt.strftime("%Y-%m-%d %H:%M")
    parts.append(render_table(ev_show))

    parts.append("<h2 id='h1'>📈 H1 — magnitudine events vs random baseline</h2>")
    parts.append(render_explanation("h1"))
    fig = plot_h1(h1_df)
    if fig is not None:
        parts.append(img_tag(fig_to_base64(fig), "H1 events vs baseline"))
    parts.append("<h3>Tabel detaliat H1</h3>")
    parts.append(render_table(h1_df, fmt={
        "mean_abs_event": "{:.4f}", "mean_abs_baseline": "{:.4f}",
        "ratio": "{:.2f}", "t_stat": "{:.3f}", "p_ttest": "{:.4f}",
        "u_stat": "{:.0f}", "p_mwu": "{:.4f}",
    }))

    parts.append("<h2 id='h2'>🎯 H2 — sentiment prezice direcția?</h2>")
    parts.append(render_explanation("h2"))
    fig = plot_h2(h2_df)
    if fig is not None:
        parts.append(img_tag(fig_to_base64(fig), "H2 hit rates"))
    parts.append("<h3>Tabel detaliat H2</h3>")
    parts.append(render_table(h2_df, fmt={
        "hit_rate": "{:.1%}", "p_binom": "{:.4f}",
    }))

    parts.append("<h2 id='h3'>🔬 H3 — sentiment × trend interaction (OLS)</h2>")
    parts.append(render_explanation("h3"))
    fig = plot_h3_scatter(returns_df)
    parts.append(img_tag(fig_to_base64(fig), "H3 scatter sentiment vs realized"))
    parts.append("<h3>Tabel detaliat H3</h3>")
    parts.append(render_table(h3_df, fmt={
        "r2": "{:.3f}",
        "coef_sentiment_num": "{:+.4f}", "p_sentiment_num": "{:.3f}",
        "coef_trend_zi": "{:+.4f}", "p_trend_zi": "{:.3f}",
        "coef_interaction": "{:+.4f}", "p_interaction": "{:.3f}",
    }))

    parts.append("<h2 id='h4'>🌙 H4 — closed-period gap regression</h2>")
    parts.append(render_explanation("h4"))
    if h4_df.empty:
        parts.append("<p class='muted'>Pilot are 0 events în closed periods (toate sunt intraday luni 20 apr 2026). "
                     "Pe export-ul complet — weekend FX (~52/an) + overnight NDX (~280/an) — H4 va avea date suficiente.</p>")
    else:
        parts.append(render_table(h4_df, fmt={
            "duration_min": "{:.0f}", "agg_sentiment": "{:+.3f}", "gap_pct": "{:+.4f}",
        }, max_rows=200))

    # ----- H5 magnitude -----
    parts.append("<h2 id='h5'>📐 H5 — `expected_magnitude` prezice |Δ%|</h2>")
    parts.append(render_explanation("h5"))
    fig = plot_h5_magnitude(h5_df, returns_df)
    if fig is not None:
        parts.append(img_tag(fig_to_base64(fig), "H5"))
    parts.append(render_table(h5_df, max_rows=20, fmt={
        "mean_low": "{:.4f}", "mean_med": "{:.4f}", "mean_high": "{:.4f}",
        "f_stat": "{:.2f}", "p_anova": "{:.4g}",
    }))

    # ----- H6 calibration -----
    parts.append("<h2 id='h6'>🎯 H6 — calibrare confidence (NDX +15m)</h2>")
    parts.append(render_explanation("h6"))
    fig = plot_h6_calibration(h6_df)
    if fig is not None:
        parts.append(img_tag(fig_to_base64(fig), "H6 calibration"))
    parts.append(render_table(h6_df, fmt={
        "mean_confidence": "{:.3f}", "hit_rate": "{:.1%}", "brier_overall": "{:.4f}",
    }))

    # ----- H7 category -----
    parts.append("<h2 id='h7'>🗂️ H7 — efect per categorie</h2>")
    parts.append(render_explanation("h7"))
    fig = plot_h7_category(h7_df)
    if fig is not None:
        parts.append(img_tag(fig_to_base64(fig), "H7 category"))
    parts.append(render_table(h7_df, max_rows=30, fmt={
        "mean_abs_pct": "{:.4f}", "median_abs_pct": "{:.4f}",
        "f_anova": "{:.2f}", "p_anova": "{:.4g}",
    }))

    # ----- H8 pre-event drift -----
    parts.append("<h2 id='h8'>⏪ H8 — pre-event drift (market efficiency / leakage)</h2>")
    parts.append(render_explanation("h8"))
    fig = plot_h8_drift(h8_df)
    if fig is not None:
        parts.append(img_tag(fig_to_base64(fig), "H8 drift"))
    parts.append(render_table(h8_df, fmt={
        "mean_pre_abs": "{:.4f}", "mean_post_abs": "{:.4f}",
        "mean_baseline_abs": "{:.4f}",
        "p_pre_vs_post_paired": "{:.4g}",
        "p_pre_vs_baseline_t": "{:.4g}",
        "p_pre_vs_baseline_mwu": "{:.4g}",
    }))

    # ----- H9 decay -----
    parts.append("<h2 id='h9'>📉 H9 — persistență vs decay</h2>")
    parts.append(render_explanation("h9"))
    fig = plot_h9_decay(h9_df, returns_df)
    if fig is not None:
        parts.append(img_tag(fig_to_base64(fig), "H9 decay"))
    parts.append(render_table(h9_df, fmt={
        "sign_match_rate": "{:.1%}", "p_binom_persistence": "{:.4g}",
        "median_ratio_4h_to_15m": "{:.2f}",
    }))

    # ----- H10 volume -----
    parts.append("<h2 id='h10'>📊 H10 — reacție de volum</h2>")
    parts.append(render_explanation("h10"))
    fig = plot_h10_volume(h10_df)
    if fig is not None:
        parts.append(img_tag(fig_to_base64(fig), "H10 volume"))
    parts.append(render_table(h10_df, fmt={
        "mean_volume_ratio": "{:.2f}", "median_volume_ratio": "{:.2f}",
        "p_wilcoxon_gt1": "{:.4g}",
    }))

    # ----- H11 time of day -----
    parts.append("<h2 id='h11'>🕐 H11 — efect time-of-day & day-of-week</h2>")
    parts.append(render_explanation("h11"))
    fig = plot_h11_tod(returns_df)
    if fig is not None:
        parts.append(img_tag(fig_to_base64(fig), "H11 time-of-day"))
    parts.append(render_table(h11_df, fmt={
        "f_hour": "{:.2f}", "p_hour": "{:.4g}",
        "f_dow": "{:.2f}", "p_dow": "{:.4g}",
    }))

    # ----- H12 asymmetric -----
    parts.append("<h2 id='h12'>⚖️ H12 — asimetrie bear vs bull</h2>")
    parts.append(render_explanation("h12"))
    fig = plot_h12_asymmetric(h12_df)
    if fig is not None:
        parts.append(img_tag(fig_to_base64(fig), "H12 asymmetric"))
    parts.append(render_table(h12_df, fmt={
        "mean_abs_bear": "{:.4f}", "mean_abs_bull": "{:.4f}",
        "ratio_bear_to_bull": "{:.2f}",
        "p_ttest": "{:.4g}", "p_mwu_bear_gt_bull": "{:.4g}",
    }))

    # ----- H13 surprise -----
    parts.append("<h2 id='h13'>💥 H13 — surprise_level → magnitudine</h2>")
    parts.append(render_explanation("h13"))
    fig = plot_h13_surprise(h13_df)
    if fig is not None:
        parts.append(img_tag(fig_to_base64(fig), "H13 surprise"))
    parts.append(render_table(h13_df, max_rows=20, fmt={
        "mean_expected": "{:.4f}", "mean_surprise": "{:.4f}", "mean_shock": "{:.4f}",
        "f_anova": "{:.2f}", "p_anova": "{:.4g}",
    }))

    # ----- H14 spillover -----
    parts.append("<h2 id='h14'>🔀 H14 — cross-asset spillover</h2>")
    parts.append(render_explanation("h14"))
    fig = plot_h14_spillover(returns_df)
    if fig is not None:
        parts.append(img_tag(fig_to_base64(fig), "H14 spillover"))
    parts.append(render_table(h14_df, fmt={
        "pearson_r": "{:+.3f}", "p_pearson": "{:.4g}",
        "spearman_r": "{:+.3f}", "p_spearman": "{:.4g}",
        "sign_match_rate": "{:.1%}", "p_binom_sign": "{:.4g}",
    }))

    parts.append("<h2 id='cases'>🔍 Top-10 case studies (cele mai mari mișcări)</h2>")
    parts.append("<p>Cele mai mari mișcări absolute pe NDX la fereastra +15m. Linia neagră întreruptă = momentul evenimentului. Liniile gri punctate = ferestrele [+1m, +5m, +15m, +1h, +4h].</p>")

    # Pick top events by abs delta_pct on NDX +15m
    top_15m = returns_df[
        (returns_df["asset"] == "ndx")
        & (returns_df["window_min"] == 15)
        & returns_df["delta_pct"].notna()
    ].copy()
    top_15m["abs_pct"] = top_15m["delta_pct"].abs()
    top_15m = top_15m.sort_values("abs_pct", ascending=False).head(10)
    top_event_ids = set(top_15m["event_id"].astype(str))
    top_events = events[events["id"].astype(str).isin(top_event_ids)].copy()

    for _, ev in top_events.iterrows():
        parts.append("<div class='event-card'>")
        fig = plot_event_timeline(ev, prices_eur, prices_ndx)
        parts.append(img_tag(fig_to_base64(fig), f"event {ev['id']}"))
        parts.append("</div>")

    parts.append(f"<h2>📁 Fișiere generate</h2><ul>")
    parts.append("<li><code>outputs/event_study_windows.csv</code> — Δ% pentru fiecare event × asset × fereastră</li>")
    parts.append("<li><code>outputs/h1_results.csv</code>, <code>h2_results.csv</code>, <code>h3_results.csv</code></li>")
    parts.append("<li><code>outputs/figures/abs_returns_by_window.png</code></li>")
    parts.append(f"<li><code>{output_path}</code> — acest raport</li>")
    parts.append("</ul>")

    parts.append("<p class='muted' style='margin-top:40px;border-top:1px solid #eee;padding-top:12px'>"
                 "Raport generat de <code>make_report.py</code> · pipeline complet pe "
                 "<a href='https://github.com/calinnedelcu/economynewsresearch'>github.com/calinnedelcu/economynewsresearch</a></p>")

    parts.append("</body></html>")

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(parts))


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--events", default="outputs/events_sentiment.csv")
    p.add_argument("--prices-dir", default="outputs")
    p.add_argument("--results-dir", default="outputs")
    p.add_argument("--output", default="outputs/report.html")
    p.add_argument("--also-copy", default=None,
                   help="Optional second path to write the report to (e.g. docs/report.html for GitHub)")
    p.add_argument("--no-open", action="store_true", help="Don't open browser")
    args = p.parse_args()

    events = pd.read_csv(args.events, parse_dates=["timestamp_utc"])
    if "is_gold" in events.columns:
        events = events[events["is_gold"].astype(str) == "True"].copy()
    events["timestamp_utc"] = pd.to_datetime(events["timestamp_utc"], utc=True)

    prices_eur = pd.read_csv(f"{args.prices_dir}/prices_eurusd.csv",
                             parse_dates=["timestamp"], index_col="timestamp")
    prices_eur.index = pd.to_datetime(prices_eur.index, utc=True)
    prices_ndx = pd.read_csv(f"{args.prices_dir}/prices_ndx.csv",
                             parse_dates=["timestamp"], index_col="timestamp")
    prices_ndx.index = pd.to_datetime(prices_ndx.index, utc=True)

    returns_df = pd.read_csv(f"{args.results_dir}/event_study_windows.csv",
                             parse_dates=["timestamp_utc"])
    returns_df["timestamp_utc"] = pd.to_datetime(returns_df["timestamp_utc"], utc=True)

    def safe_read(path):
        if Path(path).exists():
            return pd.read_csv(path)
        return pd.DataFrame()

    hyp_dfs = {f"h{i}": safe_read(f"{args.results_dir}/h{i}_results.csv") for i in range(1, 15)}

    print(f"Building report from {len(events)} events ...")
    build_html(events, returns_df, hyp_dfs, prices_eur, prices_ndx, args.output)
    print(f"Wrote {args.output}")
    if args.also_copy:
        Path(args.also_copy).parent.mkdir(parents=True, exist_ok=True)
        import shutil
        shutil.copy(args.output, args.also_copy)
        print(f"Also copied to {args.also_copy}")
    if not args.no_open:
        webbrowser.open(f"file:///{Path(args.output).resolve()}")
        print("Opened in browser.")


if __name__ == "__main__":
    main()
