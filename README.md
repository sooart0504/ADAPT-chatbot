# HeartSteps (ADAPT RCT) Future Self chatbot

A Streamlit chatbot that guides a participant through five reflection questions, writes three versions of an "ideal future self" story (Steppy, Sunny, Maple voices), lets them pick one and revise it up to twice, then saves the session to Google Sheets. Adapted from the Future Self Formative Study's Chatbot 1.

**Link:** `https://adapt-rct-chatbot.fly.dev/?pid=<participant ID>` (the app will not start without `pid`).

## Files

| File | What it is |
|---|---|
| `chatbot1_app.py` | The app |
| `chatbot1_config.toml` | Consent text, questions, personas, example story. Edit prompts here. |
| `llm_config.py` | Builds the prompts from the config file |
| `Dockerfile`, `entrypoint.sh`, `fly.toml` | How Fly.io builds, starts and runs the app |
| `.github/workflows/deploy-fly.yml` | The "Deploy to Fly.io" button under the Actions tab |
| `FLY-SETUP.md` | Step-by-step setup, secrets, and troubleshooting |

## Where data goes

One row per completed session, appended to the **first tab** of the sheet in `GOOGLE_SHEET_KEY`. The header row is written automatically if the tab is empty.

`pid` · `timestamp_start_utc` · `timestamp_end_utc` · `persona_selected` · `values` · `full_life` · `health_foundation` · `future_self_description` · `timeline` · `narrative_final` · `revision_count` · `chat_log` · `story_option_1` · `story_option_2` · `story_option_3` · `revision_history`

- `chat_log` and `revision_history` are JSON, so they can be parsed later (for example when moving to MongoDB).
- Timestamps are UTC.
- Nothing is stored on Fly. Until the save step, the session lives only in the participant's browser tab.

## Secrets

Set in the Fly dashboard (app → Secrets): `OPENAI_API_KEY`, `OPENAI_API_BASE`, `GOOGLE_SHEET_KEY`, `GOOGLE_CREDENTIALS`. LangSmith tracing is off unless `LANGCHAIN_TRACING=true` and `LANGCHAIN_API_KEY` are set. Details in `FLY-SETUP.md`.

## Deploying a change

Commit on GitHub, then Actions → **Deploy to Fly.io** → Run workflow → **deploy**. Commits alone never change the live app.

## Running locally (optional)

Python 3.11+. Put the four secrets in `.streamlit/secrets.toml` (git-ignored; `GOOGLE_CREDENTIALS` goes in as a `[gcp_service_account]` table), then `pip install -r requirements.txt` and `streamlit run chatbot1_app.py`. Open `http://localhost:8501/?pid=TEST01`.
