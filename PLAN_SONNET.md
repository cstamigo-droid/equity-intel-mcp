# PLAN DE EJECUCIÓN — equity-intel-mcp (para Sonnet)

> Plan diseñado en Opus (sesión 2026-06-14), verificado contra las APIs en vivo.
> **Sonnet: ejecuta las fases en orden. Todos los campos y fórmulas de abajo ya
> están comprobados en esta máquina** — no re-investigues APIs, pega y prueba.
>
> Reglas:
> - Patrón fijo: cada fuente es un archivo en `equity_intel_mcp/sources/<name>.py`
>   que expone `fetch(ticker: str) -> Signal`. Copia el estilo de
>   `sources/superinvestor.py` (cache + Signal + degradación graciosa).
> - **Nunca** devuelvas un score falso por falta de dato → usa `Signal.failed(...)`.
> - Después de CADA fase: corre el comando de prueba y confirma el resultado
>   esperado ANTES de pasar a la siguiente. Si falla 2 veces, para y reporta.
> - Entorno: Python global 3.14 (`python ...`), CWD = la carpeta del repo.
>   Usa `PYTHONUTF8=1` al imprimir en consola para evitar los `?` de cp1252.

---

## FASE 0 — Preparar entorno (1 paso)

Copia la API key de Finnhub al `.env` del repo (la fuente de analistas la necesita):

1. Lee la línea `FINNHUB_API_KEY=...` de `C:\Users\cstam\OneDrive\Escritorio\Dios\MAAT\.env`.
2. Añádela a `C:\Users\cstam\OneDrive\Escritorio\equity-intel-mcp\.env`
   (ese archivo ya existe con `EDGAR_IDENTITY`; añade la línea de Finnhub debajo).

`.env` queda así (gitignored, no se sube):
```
EDGAR_IDENTITY=Cristian Amigo cstamigo@gmail.com
FINNHUB_API_KEY=<la-key-de-MAAT>
```

---

## FASE 1 — `equity_analyst_consensus` (Finnhub)  [weight 0.20]

**Crear `equity_intel_mcp/sources/analysts.py`:**

```python
"""Wall Street analyst consensus from Finnhub (/stock/recommendation, free tier).

Score: (strongBuy*2 + buy - sell - strongSell*2) / (total*2) * 100.
Confidence capped at 0.75 — consensus lags price. Needs FINNHUB_API_KEY.
"""
from __future__ import annotations

import os

import requests

from .. import cache
from ..signal import Signal, clamp

_URL = "https://finnhub.io/api/v1/stock/recommendation"
_TTL_S = 3600.0
_CONF_CAP = 0.75


def _pull(ticker: str, key: str) -> dict | None:
    resp = requests.get(_URL, params={"symbol": ticker, "token": key}, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    return data[0] if isinstance(data, list) and data else None  # newest period first


def fetch(ticker: str) -> Signal:
    t = ticker.upper().strip()
    key = os.getenv("FINNHUB_API_KEY", "")
    if not key:
        return Signal.failed("analysts", "FINNHUB_API_KEY not set")
    try:
        rec = cache.get_or_fetch(f"finnhub:{t}", _TTL_S, lambda: _pull(t, key))
    except Exception as e:
        return Signal.failed("analysts", str(e))
    if not rec:
        return Signal.failed("analysts", f"no analyst coverage for {t}")

    sb, b = rec.get("strongBuy", 0), rec.get("buy", 0)
    h, s, ss = rec.get("hold", 0), rec.get("sell", 0), rec.get("strongSell", 0)
    total = sb + b + h + s + ss
    if total == 0:
        return Signal.failed("analysts", "0 analysts covering")

    score = clamp((sb * 2 + b - s - ss * 2) / (total * 2) * 100, -100.0, 100.0)
    confidence = min(total / 20.0, 1.0) * _CONF_CAP
    summary = (
        f"{total} analysts: {sb} strong buy / {b} buy / {h} hold / "
        f"{s} sell / {ss} strong sell (period {rec.get('period', '?')})."
    )
    return Signal(
        source="analysts",
        ok=True,
        score=round(score, 1),
        confidence=round(confidence, 2),
        summary=summary,
        data={
            "strong_buy": sb, "buy": b, "hold": h, "sell": s, "strong_sell": ss,
            "analysts_count": total, "period": rec.get("period", "?"),
            "url": f"https://finnhub.io/",
        },
    )
```

**Añadir tool en `server.py`** (copia el bloque de `equity_superinvestors`, cambia el cuerpo):
```python
from .sources import analysts, insider, quote, superinvestor   # add `analysts`

@mcp.tool(
    name="equity_analyst_consensus",
    annotations={"title": "Wall Street Analyst Consensus", "readOnlyHint": True,
                 "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
)
async def equity_analyst_consensus(params: TickerInput) -> str:
    """Get Wall Street buy/hold/sell consensus for a stock (Finnhub).

    Returns a directional score from the distribution of analyst ratings.
    Requires FINNHUB_API_KEY; returns "no signal" if unset or no coverage.
    Examples: "What do analysts think of AMD?" -> ticker='AMD'.
    """
    sig = await _run(analysts.fetch, params.ticker)
    return render(sig, f"Analyst Consensus — {params.ticker}", params.response_format)
```

**Probar:**
```bash
PYTHONUTF8=1 python -c "from dotenv import load_dotenv; load_dotenv('.env'); from equity_intel_mcp.sources import analysts; s=analysts.fetch('MSFT'); print(s.ok, s.score, s.confidence, s.summary)"
```
**Esperado:** `True ~71.0 0.75 ...` (MSFT consenso fuerte alcista, score positivo alto).

---

## FASE 2 — `equity_valuation` (yfinance .info)  [weight 0.15]

Adaptación de `Dios/MAAT/tools/valuation_tool.py`. **Todos los campos `.info` existen
(verificado en MSFT).** Ojo: `debtToEquity` viene en **porcentaje** (30.27 = 0.30x).

**Crear `equity_intel_mcp/sources/valuation.py`:**

```python
"""Intrinsic valuation + financial-health from Yahoo fundamentals.

Fair value = forward EPS x sector P/E band (free, deterministic — no premium API).
Score: cheap = +, rich = - (upside_pct x 2, clamped). A "cheap but fragile"
balance sheet (health < 40) halves a positive score (don't buy a falling knife).
"""
from __future__ import annotations

import yfinance as yf

from .. import cache
from ..signal import Signal, clamp

_TTL_S = 3600.0
_SECTOR_PE = {
    "Technology": 28.0, "Communication Services": 20.0, "Consumer Cyclical": 22.0,
    "Consumer Defensive": 20.0, "Healthcare": 22.0, "Financial Services": 14.0,
    "Industrials": 20.0, "Energy": 12.0, "Utilities": 18.0, "Real Estate": 30.0,
    "Basic Materials": 16.0,
}
_SECTOR_PE_DEFAULT = 18.0


def _interp(x, pts):
    if x <= pts[0][0]:
        return pts[0][1]
    if x >= pts[-1][0]:
        return pts[-1][1]
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        if x0 <= x <= x1:
            t = (x - x0) / (x1 - x0) if x1 != x0 else 0.0
            return y0 + t * (y1 - y0)
    return pts[-1][1]


def _health(info: dict) -> tuple[int | None, dict]:
    subs, detail = [], {}
    de = info.get("debtToEquity")
    if de is not None:
        de = float(de) / 100.0  # yfinance gives a percentage
        subs.append(_interp(de, [(0.0, 100), (1.0, 70), (2.0, 40), (3.0, 10)]))
        detail["debt_to_equity"] = round(de, 2)
    cr = info.get("currentRatio")
    if cr is not None:
        subs.append(_interp(float(cr), [(0.8, 20), (1.0, 50), (1.5, 80), (2.0, 100)]))
        detail["current_ratio"] = round(float(cr), 2)
    qr = info.get("quickRatio")
    if qr is not None:
        subs.append(_interp(float(qr), [(0.5, 20), (1.0, 70), (1.5, 100)]))
        detail["quick_ratio"] = round(float(qr), 2)
    gm = info.get("grossMargins")
    if gm is not None:
        subs.append(_interp(float(gm), [(0.10, 20), (0.30, 60), (0.50, 85), (0.65, 100)]))
        detail["gross_margin_pct"] = round(float(gm) * 100, 1)
    if not subs:
        return None, {}
    return round(sum(subs) / len(subs)), detail


def _pull(ticker: str) -> dict:
    tk = yf.Ticker(ticker)
    info = tk.info or {}
    if not info.get("currentPrice"):
        try:
            info["currentPrice"] = float(tk.fast_info["last_price"])
        except Exception:
            pass
    return info


def fetch(ticker: str) -> Signal:
    t = ticker.upper().strip()
    try:
        info = cache.get_or_fetch(f"info:{t}", _TTL_S, lambda: _pull(t))
    except Exception as e:
        return Signal.failed("valuation", str(e))

    price = info.get("currentPrice")
    eps_fwd = info.get("forwardEps") or info.get("trailingEps")
    if not price or not eps_fwd or eps_fwd <= 0:
        return Signal.failed("valuation", "no forward EPS / price to value")

    sector = info.get("sector") or ""
    pe_sector = _SECTOR_PE.get(sector, _SECTOR_PE_DEFAULT)
    fair_value = eps_fwd * pe_sector * 1.05  # midpoint of 0.95x..1.15x band
    upside_pct = (fair_value / float(price) - 1.0) * 100.0

    health_score, health_detail = _health(info)
    score = clamp(upside_pct * 2.0, -100.0, 100.0)
    if health_score is not None and health_score < 40 and score > 0:
        score *= 0.5  # cheap + fragile != buy

    inputs_ok = sum(x is not None for x in (eps_fwd, info.get("bookValue"),
                                            info.get("trailingPE"), health_score))
    confidence = {0: 0.0, 1: 0.25, 2: 0.4, 3: 0.5, 4: 0.6}[inputs_ok]

    tag = ("undervalued" if upside_pct >= 25 else "fairly valued"
           if upside_pct >= -5 else "overvalued" if upside_pct >= -20 else "richly valued")
    summary = (
        f"Fair value ~${fair_value:,.0f} vs ${price:,.0f} "
        f"({upside_pct:+.0f}% upside, {tag}); financial health "
        f"{health_score if health_score is not None else 'n/a'}/100."
    )
    return Signal(
        source="valuation",
        ok=True,
        score=round(score, 1),
        confidence=confidence,
        summary=summary,
        data={
            "fair_value": round(fair_value, 2), "price": round(float(price), 2),
            "upside_pct": round(upside_pct, 1), "tag": tag,
            "sector": sector, "sector_pe": pe_sector,
            "trailing_pe": info.get("trailingPE"),
            "health_score": health_score, **health_detail,
            "url": f"https://finance.yahoo.com/quote/{t}/key-statistics",
        },
    )
```

**Tool en `server.py`** (`equity_valuation`, copia el patrón). Docstring ej:
*"Estimate fair value and financial health for a stock."* Examples: ticker='KO'.

**Probar:**
```bash
PYTHONUTF8=1 python -c "from equity_intel_mcp.sources import valuation as v; s=v.fetch('KO'); print(s.ok, s.score, s.confidence); print(s.summary)"
```
**Esperado:** `ok=True`, score (KO suele salir levemente caro → score ~0 o negativo),
confidence 0.6, summary con fair value y health score. Prueba también `TSLA` y un
ticker en pérdidas (ej. `RIVN`) → debe dar `Signal.failed` o score negativo, sin crash.

---

## FASE 3 — `equity_options_signal` (yfinance option_chain)  [weight 0.10]

**Reimplementación limpia** (la de MAAT depende de Vision + sentinel.db, NO portable).
option_chain verificado: columnas incluyen `strike, lastPrice, impliedVolatility,
openInterest`. Elige el vencimiento más cercano a **~30 días** (implied move 1-mes).

`equity_intel_mcp/sources/options.py` — lógica:
```
1. exps = yf.Ticker(t).options ; spot = fast_info last_price
2. elige exp cuyo nº de días esté más cerca de 30 (parse 'YYYY-MM-DD').
3. oc = t.option_chain(exp); calls, puts = oc.calls, oc.puts
4. ATM call/put = fila con |strike - spot| mínimo (usa (df.strike-spot).abs().idxmin()).
5. straddle = atm_call.lastPrice + atm_put.lastPrice
   implied_move_pct = straddle / spot * 100
6. pc_oi = puts.openInterest.fillna(0).sum() / max(calls.openInterest.fillna(0).sum(), 1)
7. score (LOW conviction): clamp((1.0 - pc_oi) * 40, -40, 40)
   confidence = 0.40   (opciones son ruidosas — mantener bajo a propósito)
8. summary: f"1-month implied move +/-{implied_move_pct:.1f}% (to {exp}); put/call OI {pc_oi:.2f}."
9. data: implied_move_pct, expiry, days_to_expiry, atm_strike, pc_oi_ratio, url
```
Degradación graciosa: sin `exps` o sin spot → `Signal.failed("options", ...)`.
**Documenta el caveat** (en el docstring del tool): el implied move es el dato útil
(para dimensionar riesgo); el score direccional por skew es de baja convicción.

**Tool en `server.py`** (`equity_options_signal`). Examples: ticker='NVDA'.

**Probar:**
```bash
PYTHONUTF8=1 python -c "from equity_intel_mcp.sources import options as o; s=o.fetch('MSFT'); print(s.ok, s.score, s.confidence); print(s.summary)"
```
**Esperado:** `ok=True`, implied move ~3-6% (vencimiento ~30d), score modesto, conf 0.40.

---

## FASE 4 — Cablear las 3 al hero tool + smoke test

1. En `server.py`, dentro de `equity_analyze_ticker`, amplía el `asyncio.gather`:
```python
quote_sig, insider_sig, si_sig, analyst_sig, val_sig, opt_sig = await asyncio.gather(
    _run(quote.fetch, params.ticker),
    _run(insider.fetch, params.ticker),
    _run(superinvestor.fetch, params.ticker),
    _run(analysts.fetch, params.ticker),
    _run(valuation.fetch, params.ticker),
    _run(options.fetch, params.ticker),
)
signals = [quote_sig, insider_sig, si_sig, analyst_sig, val_sig, opt_sig]
```
   (importa `analysts, valuation, options` arriba). `analyze.SOURCE_WEIGHTS` ya
   tiene las 5 claves direccionales — no se toca.
2. Añade las 3 fuentes a `tests/test_smoke.py` (al tuple de sources).
3. **Smoke test final:**
```bash
PYTHONUTF8=1 python tests/test_smoke.py MSFT
PYTHONUTF8=1 python -c "import asyncio; from equity_intel_mcp.server import mcp; print(len(asyncio.run(mcp.list_tools())), 'tools')"
```
**Esperado:** 7 tools registradas; el composite de MSFT ahora muestra **coverage ~100%**
(5 fuentes direccionales) en vez de 40%, con tabla de 5 filas. Verifica que un ticker
raro (sin analistas/valuation) NO crashea y aparece en "No signal".

---

## FASE 5 — Evaluaciones (calidad / credibilidad)

Crea `evals/equity_intel_eval.xml` con **10 pares pregunta/respuesta** read-only,
estables y verificables (guía mcp-builder). Ejemplos de molde (verifica las
respuestas corriendo las tools tú mismo antes de fijarlas):
- "How many tracked superinvestors hold KO according to Dataroma?" → (nº exacto)
- "Over the last 180 days, are AAPL insiders net buyers or net sellers?" → "sellers"
- "What sector P/E does the tool use for a Technology stock?" → "28"
Crea un `evals/README.md` corto explicando cómo correrlas. (No requiere LLM key si
las verificas a mano.)

---

## FASE 6 — Cosas que hace CRISTIAN (no Sonnet)

Estas son acciones humanas — Sonnet solo deja todo listo y documentado:
- [ ] **Claude Desktop**: pegar el bloque `mcpServers` del README en
      `%APPDATA%\Claude\claude_desktop_config.json`, poner el `cwd` correcto,
      reiniciar Claude Desktop. Probar "give me a full read on NVDA".
- [ ] **Video demo 60s**: grabar esa llamada en vivo → pieza de portfolio Upwork.
- [ ] **GitHub**: crear repo público `equity-intel-mcp`, `git init`, primer commit,
      push. Topics: `mcp`, `claude`, `fintech`, `model-context-protocol`.
      (Sonnet puede preparar el `git init` + commit local cuando Cristian lo pida.)
- [ ] **Perfil Upwork**: añadir el repo + el video al portfolio.

---

## DEFINICIÓN DE TERMINADO (v0.2)
- 7 tools registradas y probadas con datos en vivo.
- Composite con coverage ~100% en un large-cap (5 fuentes direccionales).
- `tests/test_smoke.py <TICKER>` corre las 6 fuentes sin crashear.
- 10 evals escritas y verificadas.
- README + ROADMAP coherentes con el estado real (marcar las 🛠️ como ✅).
- `.env.example` documenta EDGAR_IDENTITY y FINNHUB_API_KEY.
