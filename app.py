import os
import time
import json
import re
import uuid
import random
import requests
import streamlit as st
from html import escape

# =========================
# Streamlit page config
# =========================
st.set_page_config(page_title="OpSynergy PMP AI Quiz Generator", layout="centered")

# Hide Streamlit chrome and normalize italics
st.markdown("""
<style>
  [data-testid="stToolbar"] {visibility: hidden; height: 0; position: fixed;}
  [data-testid="stDecoration"] {display: none;}
  [data-testid="stStatusWidget"] {display: none;}
  .qtext { font-style: normal; }
  .qtext em, .qtext i { font-style: normal !important; }
</style>
""", unsafe_allow_html=True)

# =========================
# Groq API call
# =========================
def call_groq(prompt: str) -> str:
    """
    Calls Groq Chat Completions and returns message text.
    Raises RuntimeError with server-provided error body on non-200.
    """
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {os.getenv('GROQ_API_KEY') or ''}",
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "ops-pmp-quiz/1.0"
    }
    model = os.getenv("GROQ_MODEL", "llama3-70b-8192")
    body = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.9
    }

    start = time.time()
    resp = requests.post(url, headers=headers, json=body)
    elapsed = time.time() - start
    print(f"[PERF] Request took {elapsed:.2f}s")

    if resp.status_code != 200:
        # Surface server message so we can see missing key, bad model name, quota, etc.
        raise RuntimeError(f"{resp.status_code} {resp.reason} | {resp.text}")

    data = resp.json()
    return data["choices"][0]["message"]["content"]

# =========================
# Robust JSON parsing
# =========================
def extract_json_block(text: str) -> str:
    # Remove code fences if present
    text = re.sub(r"```(?:json)?|```", "", text).strip()
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        m = re.search(r"\[.*\]", text, re.DOTALL)
    if not m:
        raise ValueError("No JSON object or array found in model output.")
    return m.group(0)

def sanitize_json(text: str) -> str:
    # Normalize quotes
    text = text.replace("“", '"').replace("”", '"').replace("’", "'")
    # Remove trailing commas before } or ]
    text = re.sub(r",\s*([}\]])", r"\1", text)
    # Convert single-quoted JSON-like blocks if needed
    if text.strip().startswith("{") and "'" in text and '"' not in text:
        text = re.sub(r"'", '"', text)
    return text

def parse_question_json(raw: str) -> dict:
    block = extract_json_block(raw)
    block = sanitize_json(block)
    data = json.loads(block)

    # Accept either "correct" or "answer"
    if "answer" in data and "correct" not in data:
        data["correct"] = data["answer"]

    # Required keys
    for k in ["question", "choices", "correct", "explanation"]:
        if k not in data:
            raise ValueError(f"Missing key: {k}")

    # Normalize choices to dict A-D
    choices = data["choices"]
    if isinstance(choices, list):
        letters = ["A", "B", "C", "D"]
        choices = {letters[i]: choices[i] for i in range(min(4, len(choices)))}
    elif isinstance(choices, dict):
        ordered = {}
        for k in ["A", "B", "C", "D"]:
            if k in choices:
                ordered[k] = choices[k]
        choices = ordered
    else:
        raise ValueError("choices must be a dict or a list")

    # Normalize correct to a letter
    correct = data["correct"]
    if isinstance(correct, int):
        idx_map = {0: "A", 1: "B", 2: "C", 3: "D"}
        correct = idx_map.get(correct, "A")
    else:
        correct = str(correct).strip().upper()
        if correct not in ["A", "B", "C", "D"]:
            raise ValueError("correct must be A, B, C, or D")

    data["choices"] = choices
    data["correct"] = correct
    return data

def shuffle_answers(data: dict) -> dict:
    """Shuffle choices but keep track of the correct answer."""
    original_items = list(data["choices"].items())  # [(A, text), ...]
    correct_text = data["choices"][data["correct"]]
    random.shuffle(original_items)

    new_labels = ["A", "B", "C", "D"]
    new_choices = {lbl: txt for lbl, (_, txt) in zip(new_labels, original_items)}

    new_correct = None
    for lbl, (_, txt) in zip(new_labels, original_items):
        if txt == correct_text:
            new_correct = lbl
            break

    data["choices"] = new_choices
    data["correct"] = new_correct or "A"
    return data

# =========================
# Prompt builder
# =========================
def generate_prompt(topic: str) -> str:
    random_id = str(uuid.uuid4())
    topic_clean = topic.strip() if topic and topic.strip() else "Any PMP-related topic"
    topic_templates = [
        f"Generate a difficult PMP exam question related to {topic_clean}, using a unique project context.",
        f"Write a scenario-based PMP multiple-choice question involving {topic_clean}, focusing on judgment.",
        f"Produce a PMP-style question that tests applied understanding of {topic_clean}.",
        f"Create a challenging PMP question using {topic_clean} in a realistic project situation."
    ]
    topic_prompt = random.choice(topic_templates)

    # Strict JSON contract. No symbols such as plus or slash; spell them out.
    return f"""
{topic_prompt}

Output ONLY strict JSON with this schema:
{{
  "question": "string",
  "choices": {{"A":"string","B":"string","C":"string","D":"string"}},
  "correct": "A|B|C|D",
  "explanation": "string"
}}
No prose, no markdown, no code fences, no commentary. Write out words for symbols.
SessionID: {random_id}
"""

# =========================
# Session state defaults
# =========================
for key, default in [
    ("question_data", None),
    ("show_result", False),
    ("selected_answer", None),
    ("score", 0),
    ("total", 0),
]:
    if key not in st.session_state:
        st.session_state[key] = default

# =========================
# UI
# =========================
# Banner
st.markdown("""
    <div style='width:100%; height:70px; background: linear-gradient(90deg, #D32F2F 0%, #FFFFFF 50%, #1976D2 100%);
    display:flex; align-items:center; justify-content:center; margin-bottom:30px; border-radius:10px;'>
        <h1 style='color:#222; font-size:2rem; font-weight:700;'>OpSynergy PMP AI Quiz Generator</h1>
    </div>
""", unsafe_allow_html=True)

topic = st.text_input(
    "Enter a PMP topic or leave blank for a random question:",
    value="",
    label_visibility="visible"
)

show_raw = st.checkbox("Show raw model output (debug)")

# API health expander
with st.expander("API health (debug)"):
    key_present = bool(os.getenv("GROQ_API_KEY"))
    st.write(f"GROQ_API_KEY set: {'yes' if key_present else 'no'}")
    st.write(f"Current model: {os.getenv('GROQ_MODEL', 'llama3-70b-8192')}")
    if st.button("Test Groq /models endpoint"):
        try:
            r = requests.get(
                "https://api.groq.com/openai/v1/models",
                headers={"Authorization": f"Bearer {os.getenv('GROQ_API_KEY') or ''}"}
            )
            st.write(f"Status: {r.status_code}")
            st.code(r.text)
        except Exception as e:
            st.error(str(e))

# Generate
if st.button("Generate New Question"):
    try:
        with st.spinner("Generating..."):
            prompt = generate_prompt(topic)
            raw = call_groq(prompt)
            if show_raw:
                st.code(raw)
            data = parse_question_json(raw)
            data = shuffle_answers(data)
            st.session_state.question_data = data
            st.session_state.show_result = False
            st.session_state.selected_answer = None
    except Exception as e:
        st.error("Sorry, something went wrong parsing the question.")
        st.caption(f"Parser hint: {e}")
        try:
            with open("/mnt/data/last_model_output.txt", "w") as f:
                f.write(raw if 'raw' in locals() else "<no raw output>")
            st.download_button(
                "Download last model output",
                data=raw if 'raw' in locals() else "No raw output captured.",
                file_name="last_model_output.txt"
            )
        except Exception:
            pass
        st.stop()

# Render question / choices
if st.session_state.question_data:
    q = st.session_state.question_data

    clean_q = re.sub(r'(?<=\w)_(?=\w)', ' ', q["question"])
    st.markdown(f"<h3 class='qtext'>{escape(clean_q)}</h3>", unsafe_allow_html=True)

    letters = ["A", "B", "C", "D"]
    choice_keys = [k for k in letters if k in q["choices"]]
    selected = st.radio(
        "Choose your answer:",
        options=choice_keys,
        format_func=lambda k: f"{k}. {q['choices'][k]}",
        index=None,
        key="selected_answer"
    )

    if selected and not st.session_state.show_result:
        st.session_state.show_result = True
        st.session_state.total += 1
        if selected == q["correct"]:
            st.session_state.score += 1

    if st.session_state.show_result and selected:
        if selected == q["correct"]:
            st.success("Correct.")
        else:
            st.error(f"Incorrect. Correct answer is {q['correct']}.")
        st.info(f"Explanation: {q['explanation']}")
        st.markdown(f"Score: {st.session_state.score} out of {st.session_state.total} this session")

# Footer
st.markdown("---")
st.markdown(
    "<small>All questions are generated by AI and should be reviewed for accuracy. "
