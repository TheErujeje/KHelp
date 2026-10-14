# Klaudesk API + agent runner. Build from the repo root:
#   docker build -f apps/api/Dockerfile .
FROM node:22-bookworm-slim AS node

FROM python:3.12-slim-bookworm
ENV PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

# Node is only needed for the borrowed filesystem MCP server, installed once here.
COPY --from=node /usr/local/bin/node /usr/local/bin/node
COPY --from=node /usr/local/lib/node_modules /usr/local/lib/node_modules
RUN ln -s /usr/local/lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \
 && npm install -g @modelcontextprotocol/server-filesystem@1.0.0 \
 && npm cache clean --force

COPY --from=ghcr.io/astral-sh/uv:0.8.4 /uv /usr/local/bin/uv

WORKDIR /app
COPY pyproject.toml uv.lock .python-version ./
COPY packages packages
COPY apps/api apps/api
RUN uv sync --frozen --no-dev

COPY sats sats
COPY data/synthetic data/synthetic
COPY deploy/api-entrypoint.sh /usr/local/bin/api-entrypoint.sh

RUN useradd --create-home --uid 10001 khelp \
 && mkdir -p /app/data/intake && chown -R khelp /app/data/intake
USER khelp

ENV PATH="/app/.venv/bin:$PATH" \
    KHELP_SATS_DIR=/app/sats \
    KHELP_INTAKE_DIR=/app/data/intake \
    KHELP_FILESYSTEM_SERVER_BIN=mcp-server-filesystem

EXPOSE 8000
CMD ["api-entrypoint.sh"]
