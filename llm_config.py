"""
llm_config.py
Shared configuration class for the Future Self Formative Study chatbots.
Handles both Chatbot 1 (Ideal Future Self + Anchoring) and Chatbot 2 (Feared Future Self).
"""

import tomllib


class LLMConfig:

    def __init__(self, filename):

        with open(filename, "rb") as f:
            config = tomllib.load(f)

        # ── Consent ───────────────────────────────────────────────────────────
        self.intro_and_consent = config["consent"]["intro_and_consent"].strip()

        # ── Shared collection settings ────────────────────────────────────────
        self.persona            = config["collection"]["persona"].strip()
        self.language_type      = config["collection"]["language_type"].strip()
        self.topic_restriction  = config["collection"]["topic_restriction"].strip()
        self.intro              = config["collection"]["intro"].strip()

        # ── Topic 1 (always present in both chatbots) ─────────────────────────
        self.topic1_questions   = config["collection"]["topic1"]["questions"]
        self.topic1_transition  = config["collection"]["topic1"]["transition"].strip()

        # ── Topic 2 (Chatbot 1 only — Ideal Day) ─────────────────────────────
        if "topic2" in config["collection"]:
            self.topic2_questions  = config["collection"]["topic2"]["questions"]
            self.topic2_transition = config["collection"]["topic2"]["transition"].strip()
            self.has_topic2        = True
        else:
            self.topic2_questions  = []
            self.topic2_transition = ""
            self.has_topic2        = False

        # ── Anchoring prompts (Chatbot 1 only) ────────────────────────────────
        if "anchoring" in config:
            self.anchoring_prompts = config["anchoring"]["prompts"]
            self.anchoring_fields  = config["anchoring"]["fields"]
            self.has_anchoring     = True
        else:
            self.anchoring_prompts = []
            self.anchoring_fields  = []
            self.has_anchoring     = False

        # ── Extraction templates ──────────────────────────────────────────────
        self.topic1_extraction_template = self._build_extraction_prompt(
            config["summaries"]["topic1_questions"])
        self.topic1_keys = list(config["summaries"]["topic1_questions"].keys())

        if self.has_topic2:
            self.topic2_extraction_template = self._build_extraction_prompt(
                config["summaries"]["topic2_questions"])
            self.topic2_keys = list(config["summaries"]["topic2_questions"].keys())
        else:
            self.topic2_extraction_template = None
            self.topic2_keys = []

        # ── Personas ──────────────────────────────────────────────────────────
        self.personas      = [p.strip() for p in config["summaries"]["personas"].values()]
        self.persona_names = list(config["summaries"]["personas"].keys())

        # ── One-shot example ──────────────────────────────────────────────────
        self.one_shot = self._build_one_shot(config["example"])

        # ── Conversation prompt templates ─────────────────────────────────────
        self.topic1_prompt_template = self._build_question_prompt(
            self.topic1_questions, is_first_topic=True)

        if self.has_topic2:
            self.topic2_prompt_template = self._build_question_prompt(
                self.topic2_questions, is_first_topic=False)

        # ── Story generation prompt ───────────────────────────────────────────
        # Both chatbots now use single-topic story prompt.
        # Chatbot 1: topic1 only (Ideal Day section removed from design).
        # Chatbot 2: topic1 only (feared future self).
        self.story_prompt_template = self._build_story_prompt(
            config["summaries"]["topic1_questions"]
        )

        # ── Revision prompt ───────────────────────────────────────────────────
        self.adaptation_prompt_template = self._build_adaptation_prompt()

        # ── Outro ─────────────────────────────────────────────────────────────
        self.questions_outro = "Thank you — I have everything I need. Let me put your story together!"


    # ── Prompt builders ───────────────────────────────────────────────────────

    def _build_question_prompt(self, questions, is_first_topic=False):
        """Conversation prompt for a topic's question list."""

        prompt  = f"{self.persona}\n\n"
        prompt += "Your goal is to gather thoughtful, heartfelt answers to the following questions:\n\n"

        for i, q in enumerate(questions):
            prompt += f"{i+1}. {q}\n"

        prompt += f"\nAsk each question one at a time. {self.language_type} "
        prompt += "Ensure you get at least a meaningful answer to each question before moving on. "
        prompt += "Never answer for the participant. "
        prompt += f"If you are unsure what they meant, gently ask again. {self.topic_restriction}"

        n = len(questions)
        prompt += f"\n\nOnce you have collected answers to all {n} question{'s' if n > 1 else ''}"
        prompt += ', stop the conversation and write a single word "FINISHED".\n\nCurrent conversation:\n{history}\nHuman: {input}\nAI:'

        return prompt


    def _build_extraction_prompt(self, questions_dict):
        """Extraction prompt for a given topic's structured fields."""

        keys = list(questions_dict.keys())
        keys_string = f"`{keys[0]}`"
        for key in keys[1:-1]:
            keys_string += f", `{key}`"
        if len(keys) > 1:
            keys_string += f", and `{keys[-1]}`"

        prompt = (
            "You are an expert extraction algorithm. "
            "Only extract relevant information from the Human answers in the text. "
            "Use only the words and phrases that the text contains. "
            "If you do not know the value of an attribute asked to extract, return null for the attribute's value.\n\n"
            f"You will output a JSON with {keys_string} keys.\n\n"
            f"These correspond to the following question{'s' if len(keys) > 1 else ''}:\n"
        )
        for i, (key, question) in enumerate(questions_dict.items()):
            prompt += f"{i+1}: {question}\n"

        prompt += "\nMessage to date: {conversation_history}\n\n"
        prompt += "Remember, only extract text that is in the messages above and do not change it."

        return prompt


    def _build_one_shot(self, example):
        """One-shot example string."""
        one_shot  = f"Example:\n{example['conversation']}"
        one_shot += f"\nThe story based on these responses: \"{example['scenario'].strip()}\""
        return one_shot


    def _build_combined_story_prompt(self, t1_questions, t2_questions):
        """Story prompt for Chatbot 1: weaves topic 1 + topic 2 answers together."""

        prompt  = "{persona}\n\n"
        prompt += "{one_shot}\n\n"
        prompt += "Your task:\n"
        prompt += "Create an ideal future self micro-narrative based on the following information "
        prompt += "about this person — their values, their ideal active life, and a vivid day in that future:\n\n"

        prompt += "THEIR VALUES AND IDEAL FUTURE SELF:\n"
        for key, question in t1_questions.items():
            prompt += f"Question: {question}\nAnswer: {{{key}}}\n"

        prompt += "\nTHEIR IDEAL DAY:\n"
        for key, question in t2_questions.items():
            prompt += f"Question: {question}\nAnswer: {{{key}}}\n"

        prompt += "\n{end_prompt}\n\n"
        prompt += "Your output should be a JSON with a single entry called 'output_scenario'."

        return prompt


    def _build_story_prompt(self, questions_dict):
        """
        Single-topic story prompt, shared by both chatbots.
        The specific framing (ideal vs. feared future self) is supplied at
        invoke time via {end_prompt}, so this template stays neutral.
        """

        prompt  = "{persona}\n\n"
        prompt += "{one_shot}\n\n"
        prompt += "Your task:\n"
        prompt += "Create a future self micro-narrative based on the following information:\n\n"

        for key, question in questions_dict.items():
            prompt += f"Question: {question}\nAnswer: {{{key}}}\n"

        prompt += "\n{end_prompt}\n\n"
        prompt += "Your output should be a JSON with a single entry called 'output_scenario'."

        return prompt


    def _build_adaptation_prompt(self):
        """Story revision/adaptation prompt."""

        return (
            "You are a helpful assistant supporting someone in refining their personal story. "
            "The original story:\n\n"
            "Story: {scenario}.\n\n"
            "Their current request is: {input}.\n\n"
            "Suggest an alternative version of the story. "
            "Keep the language and content as similar as possible while fulfilling their request. "
            "Return your answer as a JSON with a single entry called 'new_scenario'."
        )
