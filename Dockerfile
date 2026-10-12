# ─────────────────────────────────────────────────────────────────────────────
# HeartSteps (ADAPT RCT) — Future Self chatbot image for Fly.io
#
# Platform is pinned to amd64 because that is what Fly.io machines run, so
# builds are identical on Fly's builders and on a Mac.
# ─────────────────────────────────────────────────────────────────────────────
FROM --platform=linux/amd64 python:3.11-slim

# Python 3.11+ is required: llm_config.py uses tomllib.

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update \
 && apt-get install -y --no-install-recommends build-essential curl ca-certificates \
 && rm -rf /var/lib/apt/lists/*

# Dependencies are installed before the app code so that editing a prompt in
# the .toml file does not force a full reinstall on the next deploy.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN chmod +x /app/entrypoint.sh

EXPOSE 8080

ENTRYPOINT ["/app/entrypoint.sh"]
