FROM python:3.12-slim-bookworm AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /build

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:${PATH}"

COPY requirements.txt .
RUN pip install --upgrade pip setuptools wheel \
    && pip install -r requirements.txt

FROM python:3.12-slim-bookworm AS runtime

ENV PATH="/opt/venv/bin:${PATH}" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    ECHOBOT_SHELL_SAFETY_MODE=workspace-write

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates libgomp1 \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system --gid 10001 echobot \
    && useradd --system --uid 10001 --gid echobot --home-dir /app --shell /usr/sbin/nologin echobot

WORKDIR /app

COPY --from=builder /opt/venv /opt/venv
COPY --chown=echobot:echobot echobot ./echobot
COPY --chown=echobot:echobot assets ./assets
COPY --chown=echobot:echobot skills ./skills
COPY --chown=echobot:echobot README.md README_EN.md LICENSE NOTICE.md ./

RUN mkdir -p /app/.echobot \
    && chown -R echobot:echobot /app/.echobot

USER 10001:10001

EXPOSE 8000
VOLUME ["/app/.echobot"]

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=5).read()"

CMD ["python", "-m", "echobot", "app", "--host", "0.0.0.0", "--port", "8000"]
