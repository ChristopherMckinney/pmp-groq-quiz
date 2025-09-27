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
import html  # for HTML escaping

st.set_page_config(page_title="OpSynergy PMP AI Quiz Generator", layout="centered")

# ---------- Styles ----------
st.markdown("""
<style>
  [data-testid="stToolbar"] {visibility: hidden; height: 0; position: fixed;}
  [data-testid="stDecoration"] {display: none;}
  [data-testid="stStatusWidget"] {display: none;}
  .qtext { font-style: normal; }
  .qtext em, .qtext i { font-style: normal !important; }
  .muted { color:#555; font-size:0.9rem; }
  .page-title { font-size:1.6rem; font-weight:700; margin: 0.25rem 0 0.75rem 0; }
</style>
""", unsafe_allow_html=True)

# ---------- Helpers ----------
def _strip_wrapped_emphasis(s: str) -> str:
    # Remove wrapped emphasis markers while keeping contents
    s = re.sub(r'_(.+?)_', r'\1', s)
    s = re.sub(r'\*(.+?)\*', r'\1', s)
    return s

def _break_inline_emphasis(s: str) -> str:
    # Replace a_b / a*b joins with spaces
    s = re.sub(r'(?<=\w)_(?=\w)', ' ', s)
    s = re.sub(r'(?<=\w)\*(?=\w)', ' ', s)
    return s

def safe_inline(text: str) -> str:
    """
    For HTML-rendered blocks (we'll pass unsafe_allow_html=True).
    - Remove _..._ / *...* wrappers
    - Break a_b / a*b joins
    - Escape &, <, > (leave quotes so we don't get &#x27;)
    - Replace $ with &#36; AFTER escaping so MathJax won't trigger
    - Result can be inserted inside HTML safely.
    """
    s = str(text)
    s = _strip_wrapped_emphasis(s)
    s = _break_inline_emphasis(s)
    s = html.escape(s, quote=False)
    s = s.replace('$', '&#36;')  # prevent MathJax in HTML context
    return s

def safe_plain(text: str) -> str:
    """
    For plain-text contexts (e.g., Streamlit radio labels).
    - Remove _..._ / *...* wrappers
    - Break a_b / a*b joins
    - Insert ZWSP after $ so MathJax can't see a delimiter ($1 shows as $1)
    - Do NOT HTML-escape (plain text).
    """
    s = str(text)
    s = _strip_wrapped_emphasis(s)
    s = _break_inline_emphasis(s)
    s = s.replace('$', '$\u200B')  # $ + zero-width space
    return s

def sanitize_explanation(raw_text: str) -> str:
    """Remove any stray 'correct answer is X' claims and tidy whitespace."""
    if not isinstance(raw_text, str):
        raw_text = str(raw_text)
    txt = re.sub(r'(?i)\bthe\s+correct\s+answer\s+is\s+[A-D]\b[:.\s-]*', '', raw_text)
    txt = re.sub(r'(?i)\b(answer|option)\s+[A-D]\s+(is|was)\s+correct[:.\s-]*', '', txt)
    txt = re.sub(r'\s+', ' ', txt).strip()
    return txt

# Stable query param helpers
def set_view(view: str):
    st.query_params["view"] = view
    st.rerun()

def get_view() -> str:
    val = st.query_params.get("view", "quiz")
    if isinstance(val, list):
        return val[0] if val else "quiz"
    return val or "quiz"

def reset_session():
    keys_defaults = {
        "question_data": None, "show_result": False, "selected_answer": None,
        "score": 0, "total": 0, "question_start": None, "history": []
    }
    for k, v in keys_defaults.items():
        st.session_state[k] = v

# ---------- Banner ----------
st.markdown("""
    <div style='width:100%; height:70px; background: linear-gradient(90deg, #D32F2F 0%, #FFFFFF 50%, #1976D2 100%);
    display:flex; align-items:center; justify-content:center; margin-bottom:30px; border-radius:10px;'>
        <h1 style='color:#222; font-size:2rem; font-weight:700;'>OpSynergy PMP AI Quiz Generator</h1>
    </div>
""", unsafe_allow_html=True)

# ---------- Session state ----------
ss = st.session_state
if "question_data" not in ss:
    reset_session()

# ---------- LLM plumbing ----------
def shuffle_answers(data: dict) -> dict:
    choices = data.get("choices", {}) or {}
    correct_letter = data.get("correct")
    rationales = data.get("rationales", {}) or {}

    original_items = list(choices.items())
    random.shuffle(original_items)

    new_labels = ["A", "B", "C", "D"]
    new_choices, new_rationales = {}, {}
    new_correct_letter = "A"  # fallback

    for i, (old_label, text) in enumerate(original_items):
        nl = new_labels[i]
        new_choices[nl] = text
        new_rationales[nl] = rationales.get(old_label, "")
        if old_label == correct_letter:
            new_correct_letter = nl

    data["choices"] = new_choices
    data["rationales"] = new_rationales
    data["correct"] = new_correct_letter
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
        body = {"model": preferred, "messages": [{"role": "user", "content": prompt}], "temperature": 0.9}
        return _post_groq(body)
    except Exception as e_primary:
        last_err = e_primary
        for fb in fallbacks:
            try:
                body = {"model": fb, "messages": [{"role": "user", "content": prompt}], "temperature": 0.9}
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
    topic_prompt = random.choice([
        f"Generate a PMP exam-style multiple-choice question related to {topic_clean}, using a realistic project scenario.",
        f"Write a scenario-based PMP question involving {topic_clean}, focusing on application and judgment.",
        f"Create a challenging PMP question using {topic_clean} in a real-world situation."
    ])
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
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        raise ValueError("Failed to extract JSON")
    data = json.loads(m.group())
    data.setdefault("rationales", {"A": "", "B": "", "C": "", "D": ""})
    return shuffle_answers(data)

# ---------- Views ----------
view = get_view()

if view == "quiz":
    # Inputs row
    col1, col2 = st.columns([3, 2])
    with col1:
        topic = st.text_input(
            "Topic",
            value="",
            placeholder="Type a PMP topic (or leave blank for random)",
            label_visibility="visible"
        )
    with col2:
        difficulty = st.selectbox("Difficulty", options=["Easy", "Moderate", "Hard"], index=1)

    # Generate button
    if st.button("Generate New Question"):
        try:
            with st.spinner("Generating..."):
                prompt = generate_prompt(topic, difficulty)
                raw_output = call_groq(prompt)
                qd = parse_question(raw_output)
                ss.question_data = qd
                ss.show_result = False
                ss.selected_answer = None
                ss.question_start = time.time()
        except Exception as e:
            st.error("Sorry, something went wrong parsing the question.")
            st.caption(f"{e}")

    # Render question flow
    if ss.question_data:
        q = ss.question_data

        st.markdown(
            f"<h3 class='qtext tex2jax_ignore mathjax_ignore'>{safe_inline(q['question'])}</h3>",
            unsafe_allow_html=True
        )
        st.markdown(
            f"<div class='muted'>Topic: {safe_inline(topic.strip() or 'Random')} • Difficulty: {safe_inline(difficulty)}</div>",
            unsafe_allow_html=True
        )

        # Build sanitized radio options (plain text safe)
        display_options = [(L, safe_plain(txt)) for L, txt in q["choices"].items()]
        selected = st.radio(
            "Choose your answer:",
            options=display_options,
            format_func=lambda x: f"{x[0]}. {x[1]}",
            index=None,
            key="selected_answer"
        )

        # Grade first selection
        if selected and not ss.show_result:
            ss.show_result = True
            ss.total += 1
            is_correct = (selected[0] == q["correct"])
            if is_correct:
                ss.score += 1

            elapsed = round(time.time() - ss.question_start, 1) if ss.question_start else None
            ss.history.append({
                "question": q["question"],
                "choices": q["choices"],  # keep originals for review (we sanitize on render)
                "correct": q["correct"],
                "chosen": selected[0],
                "is_correct": is_correct,
                "explanation": q.get("explanation", ""),
                "rationales": q.get("rationales", {}),
                "time_sec": elapsed,
                "topic": topic.strip() or "Random",
                "difficulty": difficulty
            })

        # Show result
        if ss.show_result and selected:
            if selected[0] == q["correct"]:
                st.success("Correct.")
            else:
                st.error(f"Incorrect. Correct answer is {q['correct']}.")

            expl = safe_inline(sanitize_explanation(q.get("explanation", "")))
            st.info(f"Explanation: {expl}")

            with st.expander("Why the other options are not the best choice"):
                ration = q.get("rationales", {}) or {}
                correct_letter = q["correct"]
                items = []
                for letter in ["A", "B", "C", "D"]:
                    if letter == correct_letter:
                        continue
                    items.append(
                        f"<li>{letter}. {safe_inline(q['choices'][letter])} — "
                        f"{safe_inline(sanitize_explanation(ration.get(letter, '')))}</li>"
                    )
                st.markdown(f"<ul>{''.join(items)}</ul>", unsafe_allow_html=True)

            st.markdown(f"<div>Score: {ss.score} out of {ss.total} this session</div>", unsafe_allow_html=True)

    # Footer actions for quiz view
    st.markdown("---")
    colL, colR = st.columns([2, 3])
    with colL:
        if st.button("End Session & Review"):
            set_view("review")
    with colR:
        st.markdown("<div class='muted'>Tip: End session to review wrong answers and download your results.</div>", unsafe_allow_html=True)

else:  # view == "review"
    st.markdown("<div class='page-title'>Session Summary</div>", unsafe_allow_html=True)

    if not ss.history:
        st.info("No questions answered yet.")
    else:
        total = len(ss.history)
        correct = sum(1 for h in ss.history if h["is_correct"])
        avg_time = round(sum((h["time_sec"] or 0) for h in ss.history) / total, 1) if total else 0.0

        st.markdown(f"- Questions answered: {total}")
        st.markdown(f"- Correct: {correct}  •  Accuracy: {round(100*correct/total,1)}%")
        st.markdown(f"- Average response time: {avg_time} seconds")

        wrong = [h for h in ss.history if not h["is_correct"]]
        if wrong:
            st.markdown("#### Review your incorrect answers")
            for i, h in enumerate(wrong, start=1):
                st.markdown(
                    f"<strong class='qtext tex2jax_ignore mathjax_ignore'>{i}. {safe_inline(h['question'])}</strong>",
                    unsafe_allow_html=True
                )

                lis = [f"<li>{L}. {safe_inline(h['choices'][L])}</li>" for L in ["A","B","C","D"]]
                st.markdown(f"<ul>{''.join(lis)}</ul>", unsafe_allow_html=True)

                st.markdown(f"<div>Your answer: <strong>{safe_inline(h['chosen'])}</strong></div>", unsafe_allow_html=True)
                st.markdown(f"<div>Correct answer: <strong>{safe_inline(h['correct'])}</strong></div>", unsafe_allow_html=True)

                st.info(f"Explanation: {safe_inline(sanitize_explanation(h['explanation']))}")

                with st.expander("Why each incorrect option was not the best"):
                    r = h.get("rationales", {}) or {}
                    items = []
                    for L in ["A", "B", "C", "D"]:
                        if L == h["correct"]:
                            continue
                        items.append(f"<li>{L}. {safe_inline(sanitize_explanation(r.get(L, '')))}</li>")
                    st.markdown(f"<ul>{''.join(items)}</ul>", unsafe_allow_html=True)
                st.markdown("---")

        # CSV export
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

    st.markdown("---")
    colA, colB = st.columns(2)
    with colA:
        if st.button("Start New Session"):
            reset_session()
            set_view("quiz")
    with colB:
        if st.button("Back to Quiz (keep session)"):
            set_view("quiz")

# ---------- Footer ----------
st.markdown("---")
st.markdown(
    "<small>All questions are generated by AI and should be reviewed for accuracy. "
    "OpSynergy is not responsible for the validity or appropriateness of any content generated by this simulator. "
    "This tool is not affiliated with or endorsed by PMI.</small>",
    unsafe_allow_html=True
)
