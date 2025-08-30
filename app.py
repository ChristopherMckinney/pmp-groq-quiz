import os
import json
import re
import requests
import streamlit as st

# =========================
# Page Config + Minimal CSS
# =========================
st.set_page_config(
    page_title="OpSynergy PMP AI Quiz Generator",
    layout="wide",
    initial_sidebar_state="collapsed",
    menu_items={}
)

# Hide Streamlit toolbar/screencast
st.markdown(
    """
    <style>
      [data-testid="stToolbar"] {visibility: hidden;}
      [data-testid="stDecoration"] {visibility: hidden;}
      [data-testid="stStatusWidget"] {visibility: hidden;}
      div[role="radiogroup"] label { font-size: 18px !important; }
    </style>
    """,
    unsafe_allow_html=True
)

# ============
# API Settings
# ============
GROQ_API_KEY = os.getenv("GROQ_API_KEY") or os.getenv("GROK_API_KEY")
GROQ_ENDPOINT = "https://api.groq.com/openai/v1/chat/completions"
PRIMARY_MODEL = "llama3-70b-8192"
FALLBACK_MODEL = "llama3-8b-8192"
HEADERS = {
    "Authorization": f"Bearer {GROQ_API_KEY}" if GROQ_API_KEY else "",
    "Content-Type": "application/json",
}

# ============
# Helpers
# ============
def build_prompt(topic: str) -> str:
    return f"""
Generate one PMP exam-style multiple choice question.
Topic: {topic if topic.strip() else "random PMP domain"}.
Write the output as strict JSON ONLY, with this schema:
{{
  "question": "Question text here",
  "options": ["A. option1", "B. option2", "C. option3", "D. option4"],
  "answer": "A",
  "explanation": "Why the correct answer is correct."
}}
Make the distractors plausible and the explanation concise and accurate.
""".strip()

def call_groq(model_name: str, prompt: str):
    return requests.post(
        GROQ_ENDPOINT,
        headers=HEADERS,
        json={
            "model": model_name,
            "temperature": 0.9,
            "messages": [{"role": "user", "content": prompt}],
        },
        timeout=60,
    )

def coerce_options(options):
    """Ensure exactly four options prefixed A./B./C./D."""
    if not isinstance(options, list):
        return None
    letters = ["A", "B", "C", "D"]
    fixed = []
    for i, opt in enumerate(options[:4]):
        text = re.sub(r"^[A-D][\.\)]\s*", "", str(opt).strip())  # strip leading A) or A.
        fixed.append(f"{letters[i]}. {text}")
    return fixed if len(fixed) == 4 else None

def extract_json(text: str):
    """Parse JSON; if wrapped in prose, grab first {...} block."""
    try:
        return json.loads(text)
    except Exception:
        pass
    m = re.search(r"\{.*\}", text, flags=re.S)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            return None
    return None

def fetch_question(topic: str):
    if not GROQ_API_KEY:
        st.error("GROQ_API_KEY missing in Render → Environment.")
        return None
    prompt = build_prompt(topic)
    resp = call_groq(PRIMARY_MODEL, prompt)
    if resp.status_code != 200:
        # fall back once
        resp = call_groq(FALLBACK_MODEL, prompt)
    if resp.status_code != 200:
        st.error(f"Groq error {resp.status_code}: {resp.text[:300]}")
        return None
    try:
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
    except Exception as e:
        st.error(f"Groq response parse error: {e}")
        st.text(resp.text[:800])
        return None
    parsed = extract_json(content)
    if not parsed:
        st.error("Could not parse question JSON from model output.")
        st.text(content[:800])
        return None
    q = str(parsed.get("question", "")).strip()
    options = coerce_options(parsed.get("options"))
    ans_letter = str(parsed.get("answer", "")).strip().upper().replace(".", "")
    expl = str(parsed.get("explanation", "")).strip()
    if not q or not options or ans_letter not in {"A", "B", "C", "D"}:
        st.error("Generated content incomplete. Try again.")
        st.text(content[:800])
        return None
    return {"question": q, "options": options, "answer": ans_letter, "explanation": expl}

# =================
# Session State Init
# =================
if "question" not in st.session_state:
    st.session_state.question = None  # dict with question/choices/answer/expl
if "answered" not in st.session_state:
    st.session_state.answered = False
if "selected" not in st.session_state:
    st.session_state.selected = None  # "A. ...", "B. ...", etc.
if "correct_count" not in st.session_state:
    st.session_state.correct_count = 0
if "attempts" not in st.session_state:
    st.session_state.attempts = 0

# ======
# Banner
# ======
st.markdown(
    """
    <div style='width:100%; height:70px;
      background: linear-gradient(90deg, #D32F2F 0%, #FFFFFF 50%, #1976D2 100%);
      display:flex; align-items:center; justify-content:center; margin: 8px 0 24px 0;
      border-radius:12px;'>
      <h1 style='color:#222; font-size:24px; margin:0;'>OpSynergy PMP AI Quiz Generator</h1>
    </div>
    """,
    unsafe_allow_html=True
)

# =========
# Controls
# =========
topic = st.text_input("Enter a PMP topic or leave blank for a random question:", "")

colA, colB, colC = st.columns([1,1,1])
with colA:
    if st.button("Generate New Question"):
        st.session_state.question = fetch_question(topic)
        st.session_state.answered = False
        st.session_state.selected = None

with colB:
    if st.button("Submit Answer", disabled=not (st.session_state.question and st.session_state.selected)):
        if st.session_state.question and st.session_state.selected:
            picked = st.session_state.selected.split(".", 1)[0].strip()  # "A. ..." -> "A"
            st.session_state.attempts += 1
            if picked == st.session_state.question["answer"]:
                st.session_state.correct_count += 1
            st.session_state.answered = True

with colC:
    if st.button("Next Question", disabled=not st.session_state.answered):
        st.session_state.question = fetch_question(topic)
        st.session_state.answered = False
        st.session_state.selected = None

# =========
# Question
# =========
if st.session_state.question:
    # Bigger question font (20px)
    st.markdown(
        f"<p style='font-size:20px; line-height:1.4;'>{st.session_state.question['question']}</p>",
        unsafe_allow_html=True
    )

    # Radio for choices; keep selection in state across reruns
    st.session_state.selected = st.radio(
        "Choose your answer:",
        st.session_state.question["options"],
        index=None,
        key="choice_radio"
    )

    # Feedback after submission
    if st.session_state.answered:
        picked_letter = st.session_state.selected.split(".", 1)[0].strip() if st.session_state.selected else None
        if picked_letter == st.session_state.question["answer"]:
            st.success("Correct.")
        else:
            st.error(f"Incorrect. Correct answer: {st.session_state.question['answer']}")
        st.markdown(f"**Explanation:** {st.session_state.question['explanation']}")

# =======
# Score
# =======
st.markdown("---")
st.write(f"Score this session: **{st.session_state.correct_count} / {st.session_state.attempts}**")

# ==========
# Disclaimer
# ==========
st.markdown(
    """
    <hr>
    <p style='font-size:12px; text-align:center;'>
      All questions are generated by AI and should be reviewed for accuracy.
      OpSynergy is not responsible for the validity or appropriateness of any content generated by this simulator.
      This tool is not affiliated with or endorsed by PMI®.
    </p>
    """,
    unsafe_allow_html=True
)
