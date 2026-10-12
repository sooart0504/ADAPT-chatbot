#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# HeartSteps (ADAPT RCT) — chatbot startup script (adapted from the Future Self
# Formative Study's tested entrypoint-chatbot.sh)
#
# WHY THIS FILE EXISTS
#
# chatbot1_app.py reads its keys through st.secrets, a Streamlit feature that
# reads a file called .streamlit/secrets.toml. Streamlit Cloud created that
# file for you behind the scenes. Fly.io does not — it hands secrets to the app
# as environment variables. This script rebuilds the file Streamlit expects
# from those variables before starting the app.
#
# Every secret is a SINGLE LINE, because Fly's dashboard stores each secret in
# a one-line field and a multi-line value would be flattened into invalid TOML.
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

APP_DIR="${APP_DIR:-/app}"
SECRETS_DIR="${APP_DIR}/.streamlit"
SECRETS_FILE="${SECRETS_DIR}/secrets.toml"

mkdir -p "$SECRETS_DIR"

# ── Check everything required is present before doing anything ───────────────
# Failing here, at startup, means a missing key shows up in the deploy logs —
# not on a participant's screen at the end of a 20-minute session.
REQUIRED="OPENAI_API_KEY OPENAI_API_BASE GOOGLE_SHEET_KEY GOOGLE_CREDENTIALS"
MISSING=""
for var in $REQUIRED; do
  if [ -z "${!var:-}" ]; then
    MISSING="${MISSING} ${var}"
  fi
done

if [ -n "$MISSING" ]; then
  echo "FATAL: these required secrets are not set on this Fly app:" >&2
  for var in $MISSING; do echo "         - ${var}" >&2; done
  echo "" >&2
  echo "       Add them at: fly.io/dashboard -> this app -> Secrets." >&2
  echo "       Names must match exactly: capitals and underscores, no spaces." >&2
  exit 1
fi

if [ "$(echo "${LANGCHAIN_TRACING:-false}" | tr '[:upper:]' '[:lower:]')" = "true" ] \
   && [ -z "${LANGCHAIN_API_KEY:-}" ]; then
  echo "FATAL: LANGCHAIN_TRACING is \"true\" but LANGCHAIN_API_KEY is not set." >&2
  echo "       Either add LANGCHAIN_API_KEY, or delete LANGCHAIN_TRACING to keep tracing off." >&2
  exit 1
fi

# ── Build secrets.toml ────────────────────────────────────────────────────────
# GOOGLE_CREDENTIALS is the service-account key file's JSON on one line. It is
# expanded here into the [gcp_service_account] table that chatbot1_app.py expects.
SECRETS_FILE="$SECRETS_FILE" python3 <<'PYTHON'
import json, os, sys

secrets_file = os.environ["SECRETS_FILE"]

def toml_value(v):
    # JSON string escaping is compatible with TOML basic strings for the
    # characters that appear in keys and PEM blocks (\n, \", \\).
    return json.dumps(str(v))

lines = []
for key in ("OPENAI_API_KEY", "OPENAI_API_BASE",
            "GOOGLE_SHEET_KEY",
            "LANGCHAIN_TRACING", "LANGCHAIN_API_KEY", "LANGCHAIN_PROJECT",
            "CONFIG_FILE_CB1"):
    value = os.environ.get(key, "").strip()
    if value:
        lines.append(f"{key} = {toml_value(value)}")

raw = os.environ.get("GOOGLE_CREDENTIALS", "").strip()

# Tolerate a value that was pasted wrapped in single or double quotes.
if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in ("'", '"'):
    raw = raw[1:-1].strip()

try:
    creds = json.loads(raw)
except Exception as exc:
    print("FATAL: GOOGLE_CREDENTIALS is not valid JSON.", file=sys.stderr)
    print(f"       Parser said: {exc}", file=sys.stderr)
    print("       It must be the service-account key file's contents, starting", file=sys.stderr)
    print('       with {"type": "service_account", ... and ending with }.', file=sys.stderr)
    print("       Paste it with no surrounding quotes.", file=sys.stderr)
    sys.exit(1)

if not isinstance(creds, dict) or "client_email" not in creds:
    print("FATAL: GOOGLE_CREDENTIALS parsed as JSON but does not look like a", file=sys.stderr)
    print("       service-account key (no client_email field).", file=sys.stderr)
    sys.exit(1)

lines.append("")
lines.append("[gcp_service_account]")
for k, v in creds.items():
    lines.append(f"{k} = {toml_value(v)}")

with open(secrets_file, "w") as fh:
    fh.write("\n".join(lines) + "\n")

# Verify what we just wrote actually parses, so a bad value fails here with a
# clear message rather than deep inside Streamlit.
import tomllib
with open(secrets_file, "rb") as fh:
    parsed = tomllib.load(fh)

# Log NAMES only — never values.
top = [k for k in parsed if k != "gcp_service_account"]
print(f"secrets.toml written and verified. Keys: {', '.join(sorted(top))}")
print(f"  [gcp_service_account] fields: {len(parsed.get('gcp_service_account', {}))}")
print(f"  service account: {parsed['gcp_service_account'].get('client_email', '?')}")
print("  -> Share the Google Sheet with this service account as an Editor.")
tracing = str(parsed.get("LANGCHAIN_TRACING", "false")).lower() == "true"
print(f"  LangSmith tracing: {'ON (testing only)' if tracing else 'off'}")
PYTHON

chmod 600 "$SECRETS_FILE"

# ── Start the app ─────────────────────────────────────────────────────────────
APP_FILE="${APP_FILE:-chatbot1_app.py}"

if [ ! -f "${APP_DIR}/${APP_FILE}" ]; then
  echo "FATAL: APP_FILE is set to '${APP_FILE}' but ${APP_DIR}/${APP_FILE} does not exist." >&2
  exit 1
fi

echo "Starting Streamlit: ${APP_FILE} on port ${PORT:-8080}"

# toolbarMode=minimal hides Streamlit's developer menu and "Deploy" button,
# which participants would otherwise see in the top-right corner.

cd "$APP_DIR"
exec streamlit run "${APP_DIR}/${APP_FILE}" \
  --server.port="${PORT:-8080}" \
  --server.address=0.0.0.0 \
  --server.headless=true \
  --browser.gatherUsageStats=false \
  --client.toolbarMode=minimal
