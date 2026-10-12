"""
chatbot1_app.py
HeartSteps (ADAPT RCT) — Future Self chatbot: Ideal Future Self narrative

State machine:
  start → gen_stories → pick_persona
        → rate_story → [revise_story] → complete

URL params:
  ?pid=<participant ID>     (required — the app will not start without it)

Saves one row per completed session to the first tab of the Google Sheet
named by GOOGLE_SHEET_KEY. See SHEET_COLUMNS below for the column order.
"""

import os
import sys
import json
import time
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime, timezone

from langchain_community.chat_message_histories import StreamlitChatMessageHistory
from langchain_classic.memory import ConversationBufferMemory
from langchain_core.prompts import PromptTemplate
from langchain_classic.chains import ConversationChain
from langchain_openai import ChatOpenAI
from langchain_core.output_parsers.json import SimpleJsonOutputParser
from langsmith import traceable
import streamlit as st
import streamlit.components.v1 as components

from llm_config import LLMConfig


st.set_page_config(page_title="Future Self — Part 1", page_icon="🌱")
st.markdown("<style>[data-testid='stToolbarActions']{visibility:hidden;}</style>", unsafe_allow_html=True)


# ── Environment ───────────────────────────────────────────────────────────────
os.environ["OPENAI_API_KEY"]  = st.secrets["OPENAI_API_KEY"]
os.environ["OPENAI_API_BASE"] = st.secrets["OPENAI_API_BASE"]

# LangSmith tracing copies every participant conversation to LangSmith's
# servers. It is OFF by default (the Formative study turned it off too).
# To turn it on for testing only, add the secret LANGCHAIN_TRACING = "true"
# plus LANGCHAIN_API_KEY (and optionally LANGCHAIN_PROJECT).
TRACING_ON = str(st.secrets.get("LANGCHAIN_TRACING", "false")).strip().lower() == "true"
os.environ["LANGCHAIN_TRACING_V2"] = "true" if TRACING_ON else "false"
if TRACING_ON:
    os.environ["LANGCHAIN_API_KEY"] = st.secrets["LANGCHAIN_API_KEY"]
    os.environ["LANGCHAIN_PROJECT"] = st.secrets.get("LANGCHAIN_PROJECT", "adapt-chatbot")

# ── Config ────────────────────────────────────────────────────────────────────
input_args  = sys.argv[1:]
config_file = input_args[0] if input_args else st.secrets.get("CONFIG_FILE_CB1", "chatbot1_config.toml")
cfg = LLMConfig(config_file)


# ── Participant ID ────────────────────────────────────────────────────────────
# Without a PID the saved row can't be linked to anyone, so stop before the
# participant spends 15–20 minutes on a session that would be unusable.
participant_id = str(st.query_params.get("pid", "")).strip()
if not participant_id:
    st.error(
        "This link is missing your participant ID, so we can't start yet. "
        "Please use the exact link the study team sent you, or contact them for a new one."
    )
    st.stop()


def now_utc():
    """Timestamp with an explicit UTC offset, so it is unambiguous in the sheet."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ── Session state ─────────────────────────────────────────────────────────────
defaults = {
    "agentState":          "start",
    "consent":             False,
    "created_time":        now_utc(),
    "answers_t1":          {},
    "topic1_stories":      [],
    "locked_persona":      None,
    "locked_persona_name": None,
    "story_final":         None,
    "revision_history":    [],
    "revision_count":      0,
    "saved":               False,
    "llm_model":           "gpt-4o",
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v


# ── Per-topic message histories ───────────────────────────────────────────────
msgs_t1   = StreamlitChatMessageHistory(key="msgs_topic1")
memory_t1 = ConversationBufferMemory(memory_key="history", chat_memory=msgs_t1)


# ── Google Sheets ─────────────────────────────────────────────────────────────
SHEET_KEY = st.secrets.get("GOOGLE_SHEET_KEY", "")

# Column order for the first tab. The first 12 columns are unchanged from the
# earlier version; the last 4 were added so no generated data is thrown away.
SHEET_COLUMNS = [
    "pid",
    "timestamp_start_utc",
    "timestamp_end_utc",
    "persona_selected",
    "values",
    "full_life",
    "health_foundation",
    "future_self_description",
    "timeline",
    "narrative_final",
    "revision_count",
    "chat_log",                # JSON list of {"role", "content"}
    "story_option_1",
    "story_option_2",
    "story_option_3",
    "revision_history",        # JSON list of {"round", "request", "new_story"}
]

# Google Sheets refuses any cell longer than 50,000 characters.
MAX_CELL_CHARS = 49_000


def cell(value):
    """Turns a value into sheet-safe text: None becomes blank, long text is cut."""
    text = "" if value is None else str(value)
    if len(text) > MAX_CELL_CHARS:
        text = text[:MAX_CELL_CHARS] + " …[TRUNCATED]"
    return text


def chat_log_json(messages):
    """Readable, machine-parseable transcript (replaces the old Python repr)."""
    return json.dumps(
        [{"role": m.type, "content": m.content} for m in messages],
        ensure_ascii=False,
    )


def get_worksheet():
    creds  = Credentials.from_service_account_info(
        st.secrets["gcp_service_account"],
        scopes=["https://www.googleapis.com/auth/spreadsheets"]
    )
    client = gspread.authorize(creds)
    return client.open_by_key(SHEET_KEY).get_worksheet(0)


def build_row():
    t1      = st.session_state.get("answers_t1", {}) or {}
    stories = list(st.session_state.get("topic1_stories", [])) + ["", "", ""]

    return [cell(v) for v in [
        participant_id,
        st.session_state.get("created_time", ""),
        now_utc(),
        st.session_state.get("locked_persona_name", ""),

        # Topic 1 extracted answers (5 fields)
        t1.get("values"),
        t1.get("full_life"),
        t1.get("health_foundation"),
        t1.get("future_self_description"),
        t1.get("timeline"),

        # Final narrative + revision count
        st.session_state.get("story_final", ""),
        st.session_state.get("revision_count", 0),

        # Full chat log (topic 1 only)
        chat_log_json(msgs_t1.messages),

        # The three generated versions, and every revision
        stories[0], stories[1], stories[2],
        json.dumps(st.session_state.get("revision_history", []), ensure_ascii=False),
    ]]


def save_to_sheet():
    """Appends this session as one row to Tab 1. Writes the header row first if the tab is empty."""
    sheet = get_worksheet()
    if not sheet.row_values(1):
        sheet.append_row(SHEET_COLUMNS, value_input_option="RAW")
    # RAW: participant text is stored as typed, never interpreted as a formula.
    sheet.append_row(build_row(), value_input_option="RAW")


def save_with_retry(attempts=3):
    """Google's API occasionally fails for a moment; try a few times before giving up."""
    for attempt in range(1, attempts + 1):
        try:
            save_to_sheet()
            return
        except Exception as exc:
            # Log the error type only, never participant content.
            print(f"[SAVE] attempt {attempt}/{attempts} failed for pid={participant_id}: "
                  f"{type(exc).__name__}: {exc}", flush=True)
            if attempt == attempts:
                raise
            time.sleep(2 * attempt)


# ── Helpers ───────────────────────────────────────────────────────────────────
def get_llm(temperature=0.3):
    return ChatOpenAI(
        temperature=temperature,
        model=st.session_state.llm_model,
        openai_api_key=st.secrets["OPENAI_API_KEY"],
        openai_api_base=st.secrets["OPENAI_API_BASE"]
    )


def extract_answers(msgs, keys, extraction_template):
    """Extracts structured answers from a conversation."""
    template    = PromptTemplate(input_variables=["conversation_history"], template=extraction_template)
    chain       = template | get_llm(0.1) | SimpleJsonOutputParser()
    result      = chain.invoke({"conversation_history": msgs})
    if not isinstance(result, dict):
        raise ValueError(f"Answer extraction returned {type(result).__name__}, expected a JSON object")
    return result


# ── Topic conversation runner ─────────────────────────────────────────────────
def run_topic_conversation(topic_num, msgs, memory, prompt_template, container):
    """
    Runs the Q&A conversation for a topic.
    Returns True when FINISHED, False if still ongoing.
    """
    if len(msgs.messages) == 0:
        intro_text = cfg.intro if topic_num == 1 else getattr(cfg, f"topic{topic_num}_transition")
        msgs.add_ai_message(intro_text)

    # Show last AI message
    if msgs.messages and msgs.messages[-1].type == "ai":
        with container:
            st.chat_message("ai").write(msgs.messages[-1].content)

    if prompt:
        prompt_obj   = PromptTemplate(input_variables=["history", "input"], template=prompt_template)
        conversation = ConversationChain(prompt=prompt_obj, llm=get_llm(0.3), verbose=False, memory=memory)

        with container:
            st.chat_message("human").write(prompt)
            try:
                response = conversation.invoke(input=prompt)
            except Exception as exc:
                # Nothing is added to the history when a call fails, so the
                # participant can simply send the same message again.
                print(f"[LLM] conversation call failed for pid={participant_id}: "
                      f"{type(exc).__name__}: {exc}", flush=True)
                st.warning("Sorry, I had trouble responding just now. Please send your message again.")
                return False

            if "FINISHED" in response["response"]:
                st.divider()
                st.chat_message("ai").write(cfg.questions_outro)
                return True
            else:
                st.chat_message("ai").write(response["response"])

    return False


# ── Story generation ──────────────────────────────────────────────────────────
@traceable
def generate_stories():
    """
    Extracts answers from topic 1, generates 3 persona stories,
    stores them in session state, transitions to pick_persona.
    """
    st.session_state["answers_t1"] = extract_answers(
        msgs_t1.messages, cfg.topic1_keys, cfg.topic1_extraction_template)

    t1_answers  = st.session_state["answers_t1"]
    # Missing answers go in as blank text, not the word "None".
    all_answers = {k: (t1_answers.get(k) or "") for k in cfg.topic1_keys}

    prompt_obj  = PromptTemplate.from_template(cfg.story_prompt_template)
    json_parser = SimpleJsonOutputParser()
    chain       = prompt_obj | get_llm(0.7) | json_parser

    progress = st.progress(0, "Generating your stories...")
    stories  = []

    for i, persona in enumerate(cfg.personas):
        result = chain.invoke({
            "persona":    persona,
            "one_shot":   cfg.one_shot,
            "end_prompt": (
                "Create an ideal future self micro-narrative based on the information above. "
                "This person is a recent cardiac rehab graduate moving from a supervised program into "
                "managing physical activity on their own. The narrative MUST do all of the following:\n"
                "1. Open by grounding the story in 1–2 of this person's core values, "
                "using their own words or close paraphrases — make the values feel specific to them, not generic. "
                "You may treat their heart experience as the turning point that clarified those values, but keep "
                "this light and forward-looking — do not dwell on the illness, fear, or hardship, and never make "
                "the future self feel fragile.\n"
                "2. Show explicitly how staying physically active ENABLES this person to live in "
                "alignment with those values — not as a separate medical goal, but as the foundation "
                "that makes their valued life possible, and as a source of confidence and independence. "
                "Frame activity as steady and sustainable, never as strain or pushing hard. This connection must be unmistakable.\n"
                "3. Paint a vivid, specific scene of this person as their future self — active, capable, "
                "and living the life they described — in a moment that captures how staying active and "
                "their personal values are intertwined.\n"
                "The tone, length, and voice should match the persona you have been given."
            )
        } | all_answers)
        story = (result or {}).get("output_scenario", "") if isinstance(result, dict) else ""
        if not story.strip():
            raise ValueError(f"Story {i + 1} came back empty")
        stories.append(story)
        progress.progress(int((i + 1) / len(cfg.personas) * 100), "Generating your stories...")

    st.session_state["topic1_stories"] = stories
    st.session_state["agentState"]     = "pick_persona"
    st.rerun()


def show_persona_picker():
    """Shows 3 story options for participant to choose from."""
    stories = st.session_state.get("topic1_stories", [])

    st.chat_message("ai").write(
        "Here are three versions of your future self story. "
        "Each one is based on what you shared — just written in a different voice. "
        "Take a moment to read them and choose the one that resonates most with you."
    )
    st.divider()

    col1, col2, col3 = st.columns(3)

    with col1:
        st.subheader("Version 1")
        st.write(stories[0] if len(stories) > 0 else "")
        if st.button("Choose Version 1", key="pick1"):
            lock_persona(0, stories[0])

    with col2:
        st.subheader("Version 2")
        st.write(stories[1] if len(stories) > 1 else "")
        if st.button("Choose Version 2", key="pick2"):
            lock_persona(1, stories[1])

    with col3:
        st.subheader("Version 3")
        st.write(stories[2] if len(stories) > 2 else "")
        if st.button("Choose Version 3", key="pick3"):
            lock_persona(2, stories[2])


def lock_persona(index, story):
    """Saves chosen story and persona, transitions to rate_story."""
    st.session_state["locked_persona"]      = cfg.personas[index]
    st.session_state["locked_persona_name"] = cfg.persona_names[index]
    st.session_state["story_final"]         = story
    st.session_state["agentState"]          = "rate_story"
    st.rerun()


# ── Story review ──────────────────────────────────────────────────────────────
def show_rate_story():
    """
    Shows the chosen story for review.
    Anchoring statements are displayed below it, read-only.
    """
    st.chat_message("ai").write(
        "Here is your story. Read it through and let us know how it feels."
    )
    st.markdown(f"> {st.session_state['story_final']}")
    st.divider()

    st.chat_message("ai").write("How well does this story capture what you had in mind?")

    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button("Needs some edits", key="rate_edits"):
            st.session_state["agentState"] = "revise_story"
            st.rerun()
    with col2:
        if st.button("Pretty good, I'd like to tweak it", key="rate_tweak"):
            st.session_state["agentState"] = "revise_story"
            st.rerun()
    with col3:
        if st.button("This captures it perfectly!", key="rate_good"):
            st.session_state["agentState"] = "complete"
            st.rerun()


# ── Revision loop ─────────────────────────────────────────────────────────────
def show_revise_story():
    """Revision loop — story only, max 2 rounds."""

    revision_count = st.session_state.get("revision_count", 0)

    st.chat_message("ai").write("Here is your current story:")
    st.markdown(f"> {st.session_state['story_final']}")
    st.divider()

    if revision_count >= 2:
        st.chat_message("ai").write(
            "You've made two rounds of revisions — that's the maximum. "
            "Here is your final story! You can continue when you're ready."
        )
        if st.button("Continue", key="continue_after_revisions"):
            st.session_state["agentState"] = "complete"
            st.rerun()
        return

    st.chat_message("ai").write(
        "What would you like to change? You can type a request below, or edit the story directly."
    )

    # Option A: typed request
    user_request = st.text_input(
        "Type your request (e.g. 'Make it feel more hopeful')",
        key=f"revision_input_{revision_count}"
    )
    if st.button("Apply my request", key=f"apply_revision_{revision_count}") and user_request:
        prompt_obj  = PromptTemplate(
            input_variables=["input", "scenario"],
            template=cfg.adaptation_prompt_template
        )
        chain = prompt_obj | get_llm(0.5) | SimpleJsonOutputParser()

        try:
            with st.spinner("Revising your story..."):
                result = chain.invoke({
                    "scenario": st.session_state["story_final"],
                    "input":    user_request
                })
        except Exception as exc:
            print(f"[LLM] revision call failed for pid={participant_id}: "
                  f"{type(exc).__name__}: {exc}", flush=True)
            st.warning("Sorry, I couldn't revise the story just now. Please tap “Apply my request” again.")
            return

        new_story = result.get("new_scenario") if isinstance(result, dict) else None
        new_story = new_story or st.session_state["story_final"]
        st.session_state["revision_history"].append({
            "round":     revision_count + 1,
            "request":   user_request,
            "new_story": new_story
        })
        st.session_state["story_final"]    = new_story
        st.session_state["revision_count"] += 1
        st.session_state["agentState"]     = "rate_story"
        st.rerun()

    st.divider()

    # Option B: direct edit
    st.write("Or edit the story directly:")
    edited = st.text_area(
        "Edit below:",
        value=st.session_state["story_final"],
        key=f"direct_edit_{revision_count}",
        height=200
    )
    if st.button("Save my edits", key=f"save_direct_{revision_count}"):
        st.session_state["revision_history"].append({
            "round":     revision_count + 1,
            "request":   "Direct edit by participant",
            "new_story": edited
        })
        st.session_state["story_final"]    = edited
        st.session_state["revision_count"] += 1
        st.session_state["agentState"]     = "complete"
        st.rerun()


# ── Completion ────────────────────────────────────────────────────────────────
def complete_session():
    """Saves to Google Sheets exactly once and shows completion message."""
    # Streamlit re-runs this whole script on every click or refresh. The
    # "saved" flag stops those re-runs from appending duplicate rows.
    if not st.session_state.get("saved"):
        try:
            with st.spinner("Saving your responses..."):
                save_with_retry()
            st.session_state["saved"] = True
        except Exception:
            # Everything is still held in this browser tab, so a retry loses nothing.
            st.error(
                "We couldn't save your responses just yet. Please keep this tab open "
                "and tap the button below to try again. If it still doesn't work, "
                "let the study team know before closing this page."
            )
            st.button("Try saving again", key="retry_save")
            return

    st.success("All done — thank you!")
    st.markdown(
        "Your story and responses have been saved. "
        "You can now close this tab and return to the session."
    )
    components.html('<script>setTimeout(function(){ window.close(); }, 4000);</script>')


# ── State machine ─────────────────────────────────────────────────────────────
def state_agent():
    state = st.session_state["agentState"]

    if state == "start":
        finished = run_topic_conversation(
            1, msgs_t1, memory_t1,
            cfg.topic1_prompt_template,
            entry_container
        )
        if finished:
            st.session_state["agentState"] = "gen_stories"
            st.rerun()

    elif state == "gen_stories":
        try:
            with st.spinner("Creating your stories — this takes about 30 seconds..."):
                generate_stories()
        except Exception as exc:
            # st.rerun() is not an Exception, so a successful run is not caught here.
            print(f"[LLM] story generation failed for pid={participant_id}: "
                  f"{type(exc).__name__}: {exc}", flush=True)
            st.warning("Something went wrong while creating your stories. Your answers are safe. "
                       "Please tap the button below to try again.")
            st.button("Try again", key="retry_stories")

    elif state == "pick_persona":
        show_persona_picker()

    elif state == "rate_story":
        show_rate_story()

    elif state == "revise_story":
        show_revise_story()

    elif state == "complete":
        complete_session()


# ── Consent gate ──────────────────────────────────────────────────────────────
def mark_consent():
    st.session_state["consent"] = True


if st.session_state["consent"]:
    entry_container = st.expander("Our conversation", expanded=True)
    prompt = st.chat_input()
    state_agent()

else:
    with st.container():
        st.markdown(cfg.intro_and_consent)
        st.button("I understand — let's begin", key="consent_btn", on_click=mark_consent)
