# equity-intel-mcp — MCP server (stdio transport).
# Cumple el requisito de Glama: la imagen arranca el server y responde a introspección.
FROM python:3.11-slim

WORKDIR /app

# Manifiestos primero (cache de capas)
COPY requirements.txt pyproject.toml README.md ./
COPY equity_intel_mcp ./equity_intel_mcp

# Deps + instalar el paquete (deja el console-script `equity-intel-mcp`)
RUN pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir --no-deps .

# SEC EDGAR (fair-access) pide una identidad de contacto. Se puede sobre-escribir en runtime.
# El resto de tools corre con datos gratis; sin secretos horneados en la imagen.
ENV EDGAR_IDENTITY="equity-intel-mcp contact@example.com"

# El server habla por stdio (Claude Desktop / Claude Code / introspección de Glama).
ENTRYPOINT ["equity-intel-mcp"]
