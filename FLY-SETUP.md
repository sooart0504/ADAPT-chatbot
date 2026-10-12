# Moving the ADAPT chatbot to Fly.io (no Terminal needed)

Everything below happens in a web browser. It follows the same steps you used for the Future Self Formative repo, with two differences: there is **one app** instead of three, and the secrets are entered **one per field** (the Formative guide's single `STREAMLIT_SECRETS_TOML` secret was replaced by separate secrets in its final, tested version, and this repo uses that version).

About 30 minutes, mostly waiting.

| Website | What for |
|---|---|
| github.com | Your code, and the deploy button |
| fly.io/dashboard | Creating a token, storing your keys, reading logs |
| share.streamlit.io | Copying your current OpenAI keys |
| console.cloud.google.com | Downloading a Google service-account key |
| sheets.google.com | The sheet the chatbot saves to |

---

## Step 1. Put the new files in the repo

1. Unzip `adapt-chatbot-fly.zip`. It contains a folder with the files below.
2. Go to <https://github.com/sooart0504/ADAPT-chatbot> → **Add file** → **Upload files**.
3. In Finder, open the unzipped folder, press **⌘ + Shift + .** (period) so the dot-files show, select everything **except the `.github` folder**, and drag it onto the page. GitHub replaces the files that already exist.
4. Commit message: `Add Fly.io deployment and fix save bugs` → **Commit changes**.

Files you are uploading:

| File | New or changed |
|---|---|
| `chatbot1_app.py` | changed (bug fixes) |
| `chatbot1_config.toml` | changed (header comment only) |
| `requirements.txt` | changed (exact tested versions; unused Twilio removed) |
| `Dockerfile`, `fly.toml`, `entrypoint.sh` | new (how Fly builds and starts the app) |
| `.dockerignore`, `.gitignore` | new (keep secrets out of the image and out of GitHub) |
| `README.md`, `FLY-SETUP.md` | new (documentation) |

> **Heads up:** if the chatbot is still deployed on Streamlit Cloud from this repo, Streamlit Cloud will pick up the new code automatically. That is fine. It still needs only the keys it already has, and it was not saving data anyway.

### 1b. Add the deploy button

1. **Add file** → **Create new file**.
2. Filename, typed exactly (the slashes create folders): `.github/workflows/deploy-fly.yml`
3. Open `deploy-fly.yml` from the zip's `.github/workflows` folder in TextEdit, copy all, paste into GitHub.
4. **Commit changes** → **Commit changes**.

---

## Step 2. Give GitHub a Fly token

GitHub secrets belong to one repo, so the token you added to the Formative repo does not carry over.

1. <https://fly.io/dashboard> → **Tokens** → **Create org deploy token**. Name it `github-actions-adapt`, longest expiry, **Create**.
2. Copy the **whole** token, including `FlyV1 ` at the start.
3. <https://github.com/sooart0504/ADAPT-chatbot/settings/secrets/actions> → **New repository secret**.
4. Name: `FLY_API_TOKEN`. Secret: the token. **Add secret**.

> **Which Fly organization?** The deploy button creates the app in the same Fly organization as the Formative study (`future-selves-126872`), so it is billed to the same place. If the RCT should be billed elsewhere, add a repository **variable** (Settings → Secrets and variables → Actions → **Variables** tab) named `FLY_ORG` with the other organization's slug before Step 3.

---

## Step 3. Click Run (first time): create the app

1. <https://github.com/sooart0504/ADAPT-chatbot/actions> → **Deploy to Fly.io** → **Run workflow**.
2. Leave it on **create-app-only** → **Run workflow**.
3. Wait for the green check (about a minute). You now have an empty app called `adapt-rct-chatbot`.

If it fails with **name is already taken**, edit the `app = "adapt-rct-chatbot"` line in `fly.toml` on GitHub (pencil icon) to something like `heartsteps-adapt-chatbot`, commit, and run again.

---

## Step 4. Set up the Google Sheet

1. Create a **new** Google Sheet for the RCT chatbot (do not reuse the Formative sheet). Leave it blank: the chatbot writes the header row itself on the first save.
2. Copy its ID from the address bar: `https://docs.google.com/spreadsheets/d/`**`THIS_PART`**`/edit`. That is `GOOGLE_SHEET_KEY`.
3. Get a service-account key (`GOOGLE_CREDENTIALS`). The simplest option is to reuse the Formative study's service account:
   - <https://console.cloud.google.com> → pick the Formative study's project → **IAM & Admin** → **Service accounts** → click the account → **Keys** → **Add key** → **Create new key** → **JSON** → **Create**. A `.json` file downloads.
   - (Fly secrets cannot be read back, so you cannot copy it out of the Formative app's Fly settings.)
4. Open the `.json` file and find `client_email`. In the Google Sheet, click **Share**, paste that email, give it **Editor**, untick "Notify people", **Share**.

---

## Step 5. Add the secrets in Fly

<https://fly.io/dashboard> → `adapt-rct-chatbot` → **Secrets**. Add each one separately, with names typed exactly:

| Name | Value | Where to find it |
|---|---|---|
| `OPENAI_API_KEY` | the UM GPT Toolkit key | share.streamlit.io → the ADAPT chatbot app → **Settings** → **Secrets** |
| `OPENAI_API_BASE` | the UM GPT Toolkit URL | same place |
| `GOOGLE_SHEET_KEY` | the sheet ID from Step 4.2 | |
| `GOOGLE_CREDENTIALS` | the **entire** contents of the `.json` file from Step 4.3 | open it in TextEdit, select all, copy, paste with no quotes around it |

Optional (leave these out unless you need them):

| Name | Value | Why |
|---|---|---|
| `LANGCHAIN_TRACING` | `true` | Turns LangSmith tracing on. **Off by default**, because it sends every participant conversation to LangSmith's servers. Only for debugging with test PIDs. |
| `LANGCHAIN_API_KEY` | your LangSmith key | Required only if tracing is on. |
| `LANGCHAIN_PROJECT` | e.g. `adapt-chatbot` | Optional with tracing. |

> Your keys never touch GitHub. GitHub only holds the Fly token, which can deploy but cannot read your OpenAI or Google credentials.

---

## Step 6. Click Run (second time): deploy

1. **Actions** → **Deploy to Fly.io** → **Run workflow** → choose **deploy** → **Run workflow**.
2. It takes about 5 minutes the first time.

---

## Step 7. Test

1. Open <https://adapt-rct-chatbot.fly.dev/?pid=TEST01> and complete a short session.
2. Check the Google Sheet: you should see a header row and **one** row for `TEST01`.
3. Also open <https://adapt-rct-chatbot.fly.dev/> with no `?pid=`. It should say the link is missing a participant ID instead of starting.
4. Delete the `TEST01` rows (keep the header) before real participants start.

To see what the app is doing: Fly dashboard → `adapt-rct-chatbot` → **Logs**. On a good start you'll see `secrets.toml written and verified`, the service-account email, and `LangSmith tracing: off`.

### After it works

- [ ] Update every place that links to the old `.streamlit.app` address (wherever participants get the link, coordinator scripts, the HS-ADAPT spec).
- [ ] Delete the app on share.streamlit.io (the university has not approved Streamlit's hosted service).
- [ ] Optional: delete the downloaded `.json` key from your Downloads folder once it is in Fly.

---

## Making changes later

Edit a file on GitHub (pencil icon) → **Commit changes** → **Actions** → **Deploy to Fly.io** → **Run workflow** → **deploy**. Nothing reaches participants until you click Run.

---

## If something goes wrong

| What you see | What it means | What to do |
|---|---|---|
| Red X, `FLY_API_TOKEN is empty` | Step 2 didn't take | Re-add the secret; name must be exactly `FLY_API_TOKEN` |
| Red X, `not authorized` | Token wrong, read-only, or expired | Make a new deploy token (Step 2) and replace it |
| Red X, `name is already taken` | Someone else owns that app name | Change the `app =` line in `fly.toml` (Step 3) |
| Site won't load; Logs say `FATAL: these required secrets are not set` | A Step 5 secret is missing or misnamed | Check the four names exactly |
| Logs say `GOOGLE_CREDENTIALS is not valid JSON` | Part of the key file was missed, or it was wrapped in quotes | Paste the whole file again, starting with `{` and ending with `}` |
| Chatbot loads, but every reply says "trouble responding" | OpenAI key or URL is wrong | Recheck `OPENAI_API_KEY` and `OPENAI_API_BASE`; Logs show the exact error |
| End screen says "We couldn't save your responses" | The sheet isn't shared with the service account, or the sheet ID is wrong | Share the sheet with the `client_email` as **Editor**; recheck `GOOGLE_SHEET_KEY` |

---

## Cost

About **$5 to $6 a month**: one always-on machine with 1 GB of memory. It is set to stay awake rather than sleep, because 24/7 availability is an IRB requirement and a sleeping machine takes several seconds to wake. Please don't change that setting.
