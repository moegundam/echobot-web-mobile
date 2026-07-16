FROM cgr.dev/chainguard/wolfi-base@sha256:02dab76bd852a70556b5b2002195c8a5fdab77d323c433bf6642aab080489795 AS python-base

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_DEFAULT_TIMEOUT=60 \
    PIP_NO_CACHE_DIR=1 \
    PIP_RETRIES=10 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

USER root

RUN apk add --no-cache ca-certificates libgomp py3.12-pip python-3.12 \
    && python3.12 -m venv /opt/venv
ENV PATH="/opt/venv/bin:${PATH}"

FROM python-base AS builder

WORKDIR /build

COPY requirements.txt .
RUN pip install --require-hashes -r requirements.txt

FROM python-base AS runtime

ENV PATH="/opt/venv/bin:${PATH}" \
    HOME=/app \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    ECHOBOT_SHELL_SAFETY_MODE=workspace-write

USER root

RUN mkdir -p /app/.echobot \
    && chown -R 65532:65532 /app

WORKDIR /app

COPY --from=builder /opt/venv /opt/venv
COPY --chown=65532:65532 echobot ./echobot
COPY --chown=65532:65532 assets ./assets
COPY --chown=65532:65532 skills ./skills
COPY --chown=65532:65532 README.md README_EN.md LICENSE NOTICE.md ./

USER 65532:65532

EXPOSE 8000
VOLUME ["/app/.echobot"]

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=5).read()"

CMD ["python", "-m", "echobot", "app", "--host", "0.0.0.0", "--port", "8000"]
