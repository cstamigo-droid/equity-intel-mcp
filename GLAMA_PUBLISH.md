# Publicación en Glama + awesome-mcp-servers — equity-intel-mcp
> Guía para listar este server en `punkpeye/awesome-mcp-servers` bajo el nuevo proceso (2026).
> Contexto: el PR #8423 (5 servers juntos) fue CERRADO — piden **1 server por PR** + **registro en Glama**.

## ✅ Estado (hecho + verificado 2026-07-06)
- **Dockerfile** creado (`./Dockerfile`, Python 3.11-slim, stdio).
- **Imagen construida OK** (`docker build`).
- **Introspección VERIFICADA**: el contenedor arranca y responde `tools/list` con **7 tools**
  (`equity_get_quote`, `equity_insider_activity`, `equity_superinvestors`, `equity_analyst_consensus`,
  `equity_valuation`, `equity_options_signal`, `equity_analyze_ticker`). serverInfo `equity_intel_mcp v1.28.1`.
- **`glama.json`** ya existe (maintainer `cstamigo-droid`).
→ Cumple el requisito técnico de Glama ("el server debe arrancar y responder a introspección").

Reproducir la verificación:
```bash
docker build -t equity-intel-mcp .
printf '%s\n' \
 '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"t","version":"1"}}}' \
 '{"jsonrpc":"2.0","method":"notifications/initialized"}' \
 '{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}' \
 | docker run -i --rm equity-intel-mcp   # devuelve las 7 tools
```

## 🙋 Pasos que necesitan TU cuenta (Cristian)
1. **Registrar en Glama:** ir a https://glama.ai/mcp/servers → añadir/enlazar el repo
   `github.com/cstamigo-droid/equity-intel-mcp`. Glama detecta el `Dockerfile` y corre la introspección
   (ya la pasa). Confirmar que quede con **score** y anotar la **ruta Glama** que te asigne
   (algo tipo `glama.ai/mcp/servers/<id>` o `.../@cstamigo-droid/equity-intel-mcp`).
2. **Commit del Dockerfile + glama.json** a GitHub (yo dejo el Dockerfile listo; falta `git push`).

## 📝 Texto del PR (UNO por server — a `punkpeye/awesome-mcp-servers`)
**Título:** `Add equity-intel-mcp (institutional equity analysis)`

**Entrada para el README** (ubicar en la sección de Finance/Stocks, orden alfabético):
```
- [cstamigo-droid/equity-intel-mcp](https://github.com/cstamigo-droid/equity-intel-mcp) 🐍 🏠 - Institutional-grade equity analysis over MCP: insider (SEC Form 4), superinvestor holdings (Dataroma), analyst consensus, valuation, and options signal — 7 tools on free data.
```
*(Leyenda del repo: 🐍 = Python · 🏠 = servicio local/stdio.)*

**Badge de score de Glama** (va DESPUÉS de la descripción del server; reemplazar `<GLAMA_PATH>`
por la ruta que Glama asignó en el paso 1):
```
[![equity-intel-mcp MCP server](https://glama.ai/mcp/servers/<GLAMA_PATH>/badges/score.svg)](https://glama.ai/mcp/servers/<GLAMA_PATH>)
```

## Reglas del proceso (no re-tropezar)
- **1 server por PR** (el bundle de 5 fue rechazado). Este PR = SOLO equity-intel-mcp.
- Server debe **arrancar + responder introspección** (✅ verificado arriba).
- Badge de Glama **obligatorio** en el PR.
- Siguientes en la cola (mismo proceso, cada uno su PR): `signal-scanner`, `market-data-mcp`,
  `crypto-intel-mcp`, `rag-starter`.
