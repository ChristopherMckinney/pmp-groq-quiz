import os
import json
import re
import requests
import streamlit as st

# --- Page Config (wide + no dev menu) ---
st.set_page_config(
    page_title="OpSynergy PMP AI Quiz Generator",
    layout="wide",
    initial_sidebar_state="collapsed",
    menu_items={}
)

# --- Hide Streamlit toolbar/screencast ---
st.markdown(
    """
    <style>
      [data-testid="stToolbar"] {visibility: hidden;}
      [data-testid="stDecoration"] {visibility: hidden;}
      [data-testid="stStatusWidget"] {visibility: hidden;}
    </style>
    """,
    unsafe_allow_html=True
)

# --- Banner ---
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

# --- Constants / API setup ---
GROQ_API_KEY = os.getenv("GROQ_API_KEY") or os.getenv("GROK_API_KEY")
GROQ_ENDPOINT = "https://api.groq.com/openai/v1/chat/completions"
PRIMARY_MODEL = "llama3-70b-8192"
FALLBACK_MODEL = "llama3-8b-8192"
HEADERS = {
    "Authorization": f"Bearer {GROQ_API_KEY}" if GROQ_API_KEY else "",
    "Content-Type": "application/json",
}

def build_prompt(topic: str) -> str:
    return f"""
Generate one PMP exam-style multiple choice question.
Topic: {topic if topic.strip() else "random PMP domain"}.
Write the output as strict JSON ONLY, with this schema:
{{
  "question": "Question text here",
  "options": ["A. option1", "B. option2", "C. option3", "D. option4"],
  "answer": "A",   // just the letter A-D
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
    """Ensure exactly four options prefixed with A./B./C./D."""
    if not isinstance(options, list):
        return None
    letters = ["A", "B", "C", "D"]
    fixed = []
    for i, opt in enumerate(options[:4]):
        # Remove any existing leading label like "A. " or "A)"
        text = re.sub(r"^[A-D][\.\)]\s*", "", str(opt).strip())
        fixed.append(f"{letters[i]}. {text}")
    return fixed if len(fixed) == 4 else None

def extract_json(text: str):
    """Try to parse JSON; if model wrapped it in prose, pull the first {...} block."""
    try:
        return json.loads(text)
    except Exception:
        pass
    m = re.search(r"\{.*\}", text, flags=re.S)  # greedy to include arrays
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            return None
    return None

def generate_question(topic: str):
    if not GROQ_API_KEY:
        st.error("GROQ_API_KEY is missing in your environment settings on Render.")
        return None

    prompt = build_prompt(topic)

    # Primary model
    resp = call_groq(PRIMARY_MODEL, prompt)
    if resp.status_code != 200:
        st.warning(f"Primary model error {resp.status_code}: {resp.text[:300]}")
        # Fallback
        resp = call_groq(FALLBACK_MODEL, prompt)

    if resp.status_code != 200:
        st.error(f"Groq API call failed {resp.status_code}: {resp.text[:500]}")
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

    # Normalize fields
    q = str(parsed.get("question", "")).strip()
    options = coerce_options(parsed.get("options"))
    ans_letter = str(parsed.get("answer", "")).strip().upper().replace(".", "")
    expl = str(parsed.get("explanation", "")).strip()

    if not q or not options or ans_letter not in {"A", "B", "C", "D"}:
        st.error("Generated content is incomplete. Please try again.")
        st.text(content[:800])
        return None

    return {"question": q, "options": options, "answer": ans_letter, "explanation": expl}

# --- UI ---
topic = st.text_input("Enter a PMP topic or leave blank for a random question:", "")
if st.button("Generate New Question"):
    item = generate_question(topic)
    if item:
        st.subheader("Question")
        st.write(item["question"])
        choice = st.radio("Choose your answer:", item["options"], index=None)
        if choice:
            picked_letter = choice.split(".", 1)[0].strip()  # "A. something" -> "A"
            if picked_letter == item["answer"]:
                st.success("Correct.")
            else:
                st.error("Incorrect.")
            st.markdown(f"**Explanation:** {item['explanation']}")

# --- Disclaimer ---
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
