import os
import streamlit as st
import requests
import json
import re
import uuid
import random
import time
import csv
import io
from html import escape

st.set_page_config(page_title="OpSynergy PMP AI Quiz Generator", layout="centered")

# Hide Streamlit chrome and normalize italics
st.markdown("""
<style>
  [data-testid="stToolbar"] {visibility: hidden; height: 0; position: fixed;}
  [data-testid="stDecoration"] {display: none;}
  [data-testid="stStatusWidget"] {display: none;}
  .qtext { font-style: normal; }
  .qtext em, .qtext i { font-style: normal !important; }
  .muted { color:#555; font-size:0.9rem; }
</style>
""", unsafe_allow_html=True)

# --- Banner ---
st.markdown("""
    <div style='width:100%; height:70px; background: linear-gradient(90deg, #D32F2F 0%, #FFFFFF 50%, #1976D2 100%);
    display:flex; align-items:center; justify-content:center; margin-bottom:30px; border-radius:10px;'>
        <h1 style='color:#222; font-size:2rem; font-weight:700;'>OpSynergy PMP AI Quiz Generator</h1>
    </div>
""", unsafe_allow_html=True)

# Inputs row
col1, col2 = st.columns([3, 2])
with col1:
    topic = st.text_input(
        "",
        value="",
        placeholder="Type a PMP topic (or leave blank for random)",
        label_visibility="collapsed"
    )
with col2:
    difficulty = st.selectbox(
        "Difficulty",
        options=["Easy", "Moderate", "Hard"],
        index=1
    )

# ---- Session state ----
ss = st.session_state
if "question_data" not in ss:
    ss.question_data = None
if "show_result" not in ss:
    ss.show_result = False
if "selected_answer" not in ss:
    ss.selected_answer = None
if "score" not in ss:
    ss.score = 0
if "total" not in ss:
    ss.total = 0
if "question_start" not in ss:
    ss.question_start = None
if "history" not in ss:
    # each item: {question, choices, correct, chosen, is_correct, explanation, rationales, time_sec, topic, difficulty}
    ss.history = []

def shuffle_answers(data):
    choices_dict = data.get("choices", {})
    correct_letter = data.get("correct")

    original_choices = list(choices_dict.items())  # [(A, text), ...]
    correct_text = choices_dict.get(correct_letter)
    random.shuffle(original_choices)

    new_labels = ["A", "B", "C", "D"]
    new_choices = {label: choice[1] for label, choice in zip(new_labels, original_choices)}

    # remap rationales to the new labels if present
    ration = data.get("rationales", {}) or {}
    original_rationales = [(k, ration.get(k, "")) for k, _ in choices_dict.items()]
    # Align rationales with shuffled order
    shuffled_rationales_texts = [r for (_, r) in original_rationales]
    # Build mapping letter->text for shuffled order
    new_rationales = {label: text for label, text in zip(new_labels, [r for (_, r) in zip(original_choices, shuffled_rationales_texts)])}

    # Find new label of the correct answer by matching text
    new_correct = None
    for new_label, (_, text) in zip(new_labels, original_choices):
        if text == correct_text:
            new_correct = new_label
            break

    data["choices"] = new_choices
    data["rationales"] = new_rationales
    data["correct"] = new_correct or "A"
    return data

def _post_groq(body):
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {os.getenv('GROQ_API_KEY')}",
        "Content-Type": "application/json"
    }
    resp = requests.post(url, headers=headers, json=body, timeout=60)
    if resp.status_code != 200:
        raise RuntimeError(f"{resp.status_code} {resp.reason} | {resp.text}")
    return resp.json()["choices"][0]["message"]["content"]

def call_groq(prompt):
    preferred = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
    fallbacks = ["llama-3.1-8b-instant"]

    try:
        body = {
            "model": preferred,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.9
        }
        return _post_groq(body)
    except Exception as e_primary:
        last_err = e_primary
        for fb in fallbacks:
            try:
                body = {
                    "model": fb,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.9
                }
                return _post_groq(body)
            except Exception as e_fb:
                last_err = e_fb
        raise last_err

def difficulty_instructions(level: str) -> str:
    if level == "Easy":
        return ("Prefer foundational knowledge, definitions, and straightforward scenarios. "
                "Avoid deep ambiguity. One clearly best answer.")
    if level == "Hard":
        return ("Use complex, realistic scenarios with competing constraints and multiple plausible options. "
                "Require judgment to select the best right answer. Distractors must be strong and tempting.")
    return ("Use situational questions with moderate complexity that test application of concepts, "
            "stakeholder analysis, sequencing, and change control without being overly ambiguous.")

def generate_prompt(topic, level):
    random_id = str(uuid.uuid4())
    topic_clean = topic.strip() if topic.strip() else "Any PMP-related topic"

    prompt_templates = [
        f"Generate a PMP exam-style multiple-choice question related to {topic_clean}, using a realistic project scenario.",
        f"Write a scenario-based PMP question involving {topic_clean}, focusing on application and judgment.",
        f"Create a challenging PMP question using {topic_clean} in a real-world situation."
    ]
    topic_prompt = random.choice(prompt_templates)

    return f"""
{topic_prompt}
Difficulty guidance: {difficulty_instructions(level)}

Return only valid JSON in this exact schema:
{{
  "question": "Your question here",
  "choices": {{
    "A": "Option A",
    "B": "Option B",
    "C": "Option C",
    "D": "Option D"
  }},
  "correct": "B",
  "explanation": "Reasoning only. Do not mention any option letter or say which answer is correct.",
  "rationales": {{
    "A": "One-sentence reason addressing A.",
    "B": "One-sentence reason addressing B.",
    "C": "One-sentence reason addressing C.",
    "D": "One-sentence reason addressing D."
  }}
}}

Rules:
- 'correct' must be a single letter A, B, C, or D.
- 'explanation' provides reasoning ONLY. Do not restate which option is correct.
- Each 'rationales' entry gives a concise justification for that option (why it is right or not best).
- Do not include markdown, comments, or extra text — only raw JSON.
- The question must be unique and suitable for PMP preparation.

Session ID: {random_id}
"""

def parse_question(raw_text):
    text = re.sub(r"```(?:json)?|```", "", raw_text).strip()
    json_match = re.search(r"\{.*\}", text, re.DOTALL)
    if not json_match:
        raise ValueError("Failed to extract JSON")
    data = json.loads(json_match.group())
    # Ensure rationales exists
    data.setdefault("rationales", {"A": "", "B": "", "C": "", "D": ""})
    return shuffle_answers(data)

# Remove any stray "correct answer is X" claims in explanation or rationales
def sanitize_explanation(raw_text: str) -> str:
    if not isinstance(raw_text, str):
        raw_text = str(raw_text)
    txt = re.sub(r'(?i)\bthe\s+correct\s+answer\s+is\s+[A-D]\b[:.\s-]*', '', raw_text)
    txt = re.sub(r'(?i)\b(answer|option)\s+[A-D]\s+(is|was)\s+correct[:.\s-]*', '', txt)
    txt = re.sub(r'\s+', ' ', txt).strip()
    return txt

# Generate button
if st.button("Generate New Question"):
    try:
        with st.spinner("Generating..."):
            prompt = generate_prompt(topic, difficulty)
            raw_output = call_groq(prompt)
            question_data = parse_question(raw_output)
            ss.question_data = question_data
            ss.show_result = False
            ss.selected_answer = None
            ss.question_start = time.time()
    except Exception as e:
        st.error("Sorry, something went wrong parsing the question.")
        st.caption(f"{e}")

# Render question
if ss.question_data:
    q = ss.question_data

    clean_q = re.sub(r'(?<=\w)_(?=\w)', ' ', q['question'])
    st.markdown(f"<h3 class='qtext'>{escape(clean_q)}</h3>", unsafe_allow_html=True)
    st.markdown(f"<div class='muted'>Topic: {escape(topic.strip() or 'Random')} • Difficulty: {difficulty}</div>", unsafe_allow_html=True)

    selected = st.radio(
        "Choose your answer:",
        options=list(q["choices"].items()),
        format_func=lambda x: f"{x[0]}. {x[1]}",
        index=None,
        key="selected_answer"
    )

    # When an answer is selected the first time, finalize
    if selected and not ss.show_result:
        ss.show_result = True
        ss.total += 1
        is_correct = (selected[0] == q["correct"])
        if is_correct:
            ss.score += 1

        # timing
        elapsed = None
        if ss.question_start:
            elapsed = round(time.time() - ss.question_start, 1)

        # save history row
        ss.history.append({
            "question": q["question"],
            "choices": q["choices"],
            "correct": q["correct"],
            "chosen": selected[0],
            "is_correct": is_correct,
            "explanation": q.get("explanation", ""),
            "rationales": q.get("rationales", {}),
            "time_sec": elapsed,
            "topic": topic.strip() or "Random",
            "difficulty": difficulty
        })

    # Show result + explanations
    if ss.show_result and selected:
        if selected[0] == q["correct"]:
            st.success("Correct.")
        else:
            st.error(f"Incorrect. Correct answer is {q['correct']}.")

        # Main reasoning (letter-free)
        st.info(f"Explanation: {sanitize_explanation(q.get('explanation', ''))}")

        # Elimination block
        with st.expander("Why the other options are not the best choice"):
            ration = q.get("rationales", {}) or {}
            correct_letter = q["correct"]
            for letter in ["A", "B", "C", "D"]:
                if letter == correct_letter:
                    # Show the correct option’s brief justification too
                    st.markdown(f"- **{letter}. {q['choices'][letter]}** — {sanitize_explanation(ration.get(letter, ''))}")
                else:
                    st.markdown(f"- {letter}. {q['choices'][letter]} — {sanitize_explanation(ration.get(letter, ''))}")

        # Running score
        st.markdown(f"Score: {ss.score} out of {ss.total} this session")

# --- Session Summary / Export ---
st.markdown("---")
colL, colR = st.columns([2, 3])
with colL:
    if st.button("End Session & Review"):
        ss.review_open = True
with colR:
    st.markdown(f"<div class='muted'>Tip: End session to review wrong answers and download your results.</div>", unsafe_allow_html=True)

if ss.get("review_open") and ss.history:
    total = len(ss.history)
    correct = sum(1 for h in ss.history if h["is_correct"])
    avg_time = round(sum((h["time_sec"] or 0) for h in ss.history) / total, 1) if total else 0.0

    st.subheader("Session Summary")
    st.markdown(f"- Questions answered: {total}")
    st.markdown(f"- Correct: {correct}  •  Accuracy: {round(100*correct/total,1)}%")
    st.markdown(f"- Average response time: {avg_time} seconds")

    # List incorrect answers with explanations
    wrong = [h for h in ss.history if not h["is_correct"]]
    if wrong:
        st.markdown("#### Review your incorrect answers")
        for i, h in enumerate(wrong, start=1):
            st.markdown(f"**{i}. {h['question']}**")
            for L in ["A", "B", "C", "D"]:
                st.markdown(f"- {L}. {h['choices'][L]}")
            st.markdown(f"- Your answer: {h['chosen']}")
            st.markdown(f"- Correct answer: {h['correct']}")
            st.info(f"Explanation: {sanitize_explanation(h['explanation'])}")
            with st.expander("Why each option was or wasn't correct"):
                r = h.get("rationales", {}) or {}
                for L in ["A", "B", "C", "D"]:
                    st.markdown(f"- {L}. {sanitize_explanation(r.get(L, ''))}")
            st.markdown("---")

    # CSV export (no pandas dependency)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["topic","difficulty","question","choice_A","choice_B","choice_C","choice_D","chosen","correct","is_correct","time_sec","explanation"])
    for h in ss.history:
        ch = h["choices"]
        writer.writerow([
            h["topic"], h["difficulty"], h["question"],
            ch.get("A",""), ch.get("B",""), ch.get("C",""), ch.get("D",""),
            h["chosen"], h["correct"], "TRUE" if h["is_correct"] else "FALSE",
            h["time_sec"] if h["time_sec"] is not None else "",
            sanitize_explanation(h["explanation"])
        ])
    csv_bytes = output.getvalue().encode("utf-8")
    st.download_button("Download results (CSV)", data=csv_bytes, file_name="opsynergy_pmp_session.csv", mime="text/csv")

# --- Footer disclaimer ---
st.markdown("---")
st.markdown(
    "<small>All questions are generated by AI and should be reviewed for accuracy. "
    "OpSynergy is not responsible for the validity or appropriateness of any content generated by this simulator. "
    "This tool is not affiliated with or endorsed by PMI.</small>",
    unsafe_allow_html=True
)
