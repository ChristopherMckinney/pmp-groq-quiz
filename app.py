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

st.set_page_config(page_title="OpSynergy PM & Agile Exam Hub", layout="centered")

# ---------- Styles ----------
st.markdown("""
<style>
  /* Hide Streamlit chrome */
  [data-testid="stToolbar"] { visibility: hidden; height: 0; position: fixed; }
  [data-testid="stDecoration"] { display: none; }
  [data-testid="stStatusWidget"] { display: none; }

  /* Question text normalization */
  .qtext { font-style: normal; }
  .qtext em, .qtext i { font-style: normal !important; }

  /* Muted helper text */
  .muted { color: #555; font-size: 0.95rem; }

  /* Section titles */
  .page-title {
    font-size: 1.6rem;
    font-weight: 700;
    margin: 0.25rem 0 0.75rem 0;
  }

  /* ===== RADIO BUTTON ANSWERS (FORCE FONT SIZE) ===== */
  div[role="radiogroup"] label p,
  div[role="radiogroup"] label span,
  div[role="radiogroup"] label div {
    font-size: 1.25rem !important;
    line-height: 1.6 !important;
  }

  div[role="radiogroup"] label {
    padding: 0.25rem 0 !important;
  }

  div[role="radiogroup"] input[type="radio"] {
    transform: scale(1.15);
    margin-right: 0.6rem;
  }

  @media (min-width: 600px) {
    div[role="radiogroup"] label p,
    div[role="radiogroup"] label span,
    div[role="radiogroup"] label div {
      font-size: 1.35rem !important;
    }
  }

  @media (min-width: 900px) {
    div[role="radiogroup"] label p,
    div[role="radiogroup"] label span,
    div[role="radiogroup"] label div {
      font-size: 1.4rem !important;
    }
  }
</style>
""", unsafe_allow_html=True)

# ---------- Helpers ----------
def _strip_wrapped_emphasis(s: str) -> str:
    s = re.sub(r'_(.+?)_', r'\1', s)
    s = re.sub(r'\*(.+?)\*', r'\1', s)
    return s

def _break_inline_emphasis(s: str) -> str:
    s = re.sub(r'(?<=\w)_(?=\w)', ' ', s)
    s = re.sub(r'(?<=\w)\*(?=\w)', ' ', s)
    return s

def safe_inline(text: str) -> str:
    s = str(text)
    s = _strip_wrapped_emphasis(s)
    s = _break_inline_emphasis(s)
    s = html.escape(s, quote=False)
    s = s.replace('$', '&#36;')
    return s

def safe_plain(text: str) -> str:
    s = str(text)
    s = _strip_wrapped_emphasis(s)
    s = _break_inline_emphasis(s)
    s = s.replace('$', '$\u200B')
    return s

def sanitize_explanation(raw_text: str) -> str:
    if not isinstance(raw_text, str):
        raw_text = str(raw_text)
    txt = re.sub(r'(?i)\bthe\s+correct\s+answer\s+is\s+[A-D]\b[:.\s-]*', '', txt := raw_text)
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
        "question_data": None,
        "show_result": False,
        "score": 0,
        "total": 0,
        "question_start": None,
        "history": [],
        "generate_request": False,
    }
    for k, v in keys_defaults.items():
        st.session_state[k] = v
    # Do not pre-select any exam or answer
    st.session_state.pop("exam_track", None)
    st.session_state.pop("selected_answer", None)

# ---------- Banner ----------
# ---------- Banner ----------
st.markdown("""
    <div style="width:100%; height:70px;
      background: linear-gradient(90deg, #216A9E 0%, #216A9E 35%, #FF2728 100%);
      display:flex; align-items:center; justify-content:center;
      margin-bottom:12px; border-radius:10px;">
        <h1 style="color:#fff; font-size:2rem; font-weight:700; margin:0;
                   text-shadow:0 1px 2px rgba(0,0,0,.25);">
          OpSynergy PM &amp; Agile Exam Hub
        </h1>
    </div>
""", unsafe_allow_html=True)

st.markdown(
    "<div class='muted' style='margin-bottom:18px;'>"
    "One simulator for PMP, CAPM, DASM, and PMI-ACP exam prep."
    "</div>",
    unsafe_allow_html=True
)

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
    new_correct_letter = "A"

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
                "Require judgment to select the best right answer. Distractors must be strong.")
    return ("Use situational questions with moderate complexity that test application of concepts, "
            "stakeholder analysis, sequencing, and change control without excess ambiguity.")

# ---------- Exam configs ----------
EXAM_TRACKS = {
    "PMP": {
        "display": "PMP",
        "topic_label": "Topic",
        "topic_placeholder": "Type a PMP topic (or leave blank for random)",
        "default_categories": [
            "Project Integration Management",
            "Project Scope Management",
            "Project Schedule Management",
            "Critical Path analysis",
            "Project Cost Management",
            "Earned Value Management",
            "Project Quality Management",
            "Project Resource Management",
            "Project Communications Management",
            "Project Risk Management",
            "Project Procurement Management",
            "Project Stakeholder Management",
            "Agile and Hybrid approaches",
            "Change control",
            "Leadership and team development",
            "Conflict resolution",
            "Governance and compliance"
        ],
        "prompt_variants": [
            "Generate a PMP exam-style scenario question from the domain: {selected}.",
            "Write a realistic PMP scenario-based question focused on: {selected}.",
            "Create a unique PMP exam question related to: {selected}."
        ],
        "scope_rule": "The scenario must align ONLY with PMP content and the selected domain."
    },
    "CAPM": {
        "display": "CAPM",
        "topic_label": "Topic",
        "topic_placeholder": "Type a CAPM topic (or leave blank for random)",
        "default_categories": [
            "Project Integration Management fundamentals",
            "Project Scope Management fundamentals",
            "Project Schedule Management fundamentals",
            "Project Cost Management fundamentals",
            "Project Quality Management fundamentals",
            "Project Resource Management fundamentals",
            "Project Communications Management fundamentals",
            "Project Risk Management fundamentals",
            "Project Procurement Management fundamentals",
            "Project Stakeholder Management fundamentals",
            "Work Breakdown Structure concepts",
            "Requirements and scope baseline",
            "Schedule basics and sequencing",
            "Cost baseline and budgeting basics",
            "Quality assurance versus quality control",
            "Risk register basics and responses",
            "Change control fundamentals",
            "Issue management fundamentals",
            "Basic governance and roles",
            "Agile and Hybrid fundamentals"
        ],
        "prompt_variants": [
            "Generate a CAPM exam-style question focused on: {selected}.",
            "Write a CAPM knowledge check question about: {selected}.",
            "Create a CAPM practice question related to: {selected}."
        ],
        "scope_rule": "The question must align ONLY with CAPM-level concepts and the selected topic."
    },
    "DASM": {
        "display": "DASM",
        "topic_label": "Focus Area",
        "topic_placeholder": "Type a Scrum or Disciplined Agile focus area (or leave blank for random)",
        "default_categories": [
            "Scrum roles, events, and artifacts",
            "Sprint Planning, Daily Scrum, Sprint Review, Sprint Retrospective",
            "Backlog refinement and prioritization",
            "Definition of Done and acceptance criteria",
            "Servant leadership behaviors",
            "Facilitation and coaching techniques",
            "Impediment removal and escalation",
            "Team norms and working agreements",
            "Agile estimation such as story points and relative sizing",
            "Flow concepts and limiting work in progress",
            "Disciplined Agile mindset and principles",
            "Choosing and tailoring an approach based on context",
            "Agile metrics such as velocity and cycle time",
            "Conflict resolution in Agile teams"
        ],
        "prompt_variants": [
            "Generate a Scrum and Disciplined Agile question focused on: {selected}.",
            "Write a scenario-based question for a Scrum Master candidate about: {selected}.",
            "Create a knowledge check question aligned to Scrum and Disciplined Agile on: {selected}."
        ],
        "scope_rule": "The scenario must align ONLY with Scrum and Disciplined Agile content and the selected focus area."
    },
    "PMI-ACP": {
        "display": "PMI-ACP",
        "topic_label": "Domain",
        "topic_placeholder": "Type a PMI-ACP domain or technique (or leave blank for random)",
        "default_categories": [
            "Agile principles and mindset",
            "Value-driven delivery",
            "Stakeholder engagement in Agile",
            "Adaptive planning",
            "Problem detection and resolution",
            "Continuous improvement",
            "Agile project estimation",
            "Risk management in Agile environments",
            "Team performance and collaboration",
            "Agile coaching and facilitation",
            "Scaling Agile considerations",
            "Hybrid delivery considerations",
            "Agile metrics and information radiators"
        ],
        "prompt_variants": [
            "Generate a PMI-ACP style scenario question focused on: {selected}.",
            "Write a realistic Agile scenario question aligned to PMI-ACP on: {selected}.",
            "Create a PMI-ACP exam-style question related to: {selected}."
        ],
        "scope_rule": "The scenario must align ONLY with PMI-ACP and Agile practices relevant to the selected domain."
    }
}

def get_track_config(track_key: str) -> dict:
    return EXAM_TRACKS.get(track_key, EXAM_TRACKS["PMP"])

# ---------- Prompt generation ----------
def generate_prompt(track_key: str, topic: str, level: str) -> str:
    cfg = get_track_config(track_key)
    random_id = str(uuid.uuid4())

    categories = cfg["default_categories"]
    selected = topic.strip() if topic and topic.strip() else random.choice(categories)
    topic_prompt = random.choice(cfg["prompt_variants"]).format(selected=selected)

    return f"""
Before generating the question, avoid repetitive structures such as 'You are a project manager and you have a problem.'
Vary scenario type, tone, setting, and narrative style.

Exam track: {cfg["display"]}
{topic_prompt}
Difficulty guidance: {difficulty_instructions(level)}

Return ONLY valid JSON in this schema:
{{
  "question": "Your question here",
  "choices": {{
    "A": "Option A",
    "B": "Option B",
    "C": "Option C",
    "D": "Option D"
  }},
  "correct": "B",
  "explanation": "Reasoning only. Do not mention which option is correct.",
  "rationales": {{
    "A": "Reason for A.",
    "B": "Reason for B.",
    "C": "Reason for C.",
    "D": "Reason for D."
  }}
}}

Rules:
- 'correct' must be A, B, C, or D.
- Explanation must NOT refer to the correct letter.
- {cfg["scope_rule"]}
- The scenario must align ONLY with the selected domain or focus area: {selected}.
- Make the structure different from previous typical exam questions.

Session: {random_id}
"""

def parse_question(raw_text):
    text = re.sub(r"```(?:json)?|```", "", raw_text).strip()
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        raise ValueError("Failed to extract JSON")
    data = json.loads(m.group())
    data.setdefault("rationales", {"A": "", "B": "", "C": "", "D": ""})
    return shuffle_answers(data)

# ---------- Safe generation pattern ----------
def request_generation():
    ss.generate_request = True
    st.rerun()

def run_generation_now(selected_exam: str, topic: str, difficulty: str):
    try:
        with st.spinner("Generating..."):
            prompt = generate_prompt(selected_exam, topic, difficulty)
            raw_output = call_groq(prompt)
            qd = parse_question(raw_output)

            ss.question_data = qd
            ss.show_result = False
            ss.question_start = time.time()

            # IMPORTANT: clear widget key safely (do NOT assign after widget exists)
            ss.pop("selected_answer", None)

    except Exception as e:
        st.error("Sorry, something went wrong generating the question.")
        st.caption(f"{e}")

# ---------- Views ----------
view = get_view()

if view == "quiz":

    st.markdown("<div class='page-title'>Select an exam simulator</div>", unsafe_allow_html=True)

    EXAM_OPTIONS = ["PMP", "CAPM", "DASM", "PMI-ACP"]

    # Prevent Streamlit crash if stale/invalid state exists
    if ss.get("exam_track") not in EXAM_OPTIONS:
        ss.pop("exam_track", None)

    selected_exam = st.radio(
        "Exam Simulator",
        options=EXAM_OPTIONS,
        index=None,                   # no selection by default
        key="exam_track",
        label_visibility="collapsed", # remove redundant label
        horizontal=False              # vertical for mobile
    )

    exam_selected = bool(selected_exam)
    cfg = get_track_config(selected_exam) if exam_selected else None

    st.markdown("---")

    col1, col2 = st.columns([4, 1])
    with col1:
        topic = st.text_input(
            cfg["topic_label"] if cfg else "Topic",
            value="",
            placeholder=cfg["topic_placeholder"] if cfg else "Select an exam simulator above",
            label_visibility="visible",
            disabled=(not exam_selected)
        )
    with col2:
        difficulty = st.selectbox(
            "Difficulty",
            options=["Easy", "Moderate", "Hard"],
            index=1,
            disabled=(not exam_selected)
        )

    # Top generate button: request then rerun (prevents widget-state conflicts)
    if st.button("Generate New Question", disabled=(not exam_selected), key="gen_top"):
        request_generation()

    if not exam_selected:
        st.info("Select an exam simulator to begin.")
    else:
        st.markdown(
            f"<div class='muted'>Selected exam: {safe_inline(get_track_config(selected_exam)['display'])}</div>",
            unsafe_allow_html=True
        )

    # If a generation was requested, do it BEFORE rendering the answer widget
    if exam_selected and ss.get("generate_request"):
        ss.generate_request = False
        run_generation_now(selected_exam, topic, difficulty)

    if ss.question_data and exam_selected:
        q = ss.question_data

        st.markdown(
            f"<h3 class='qtext tex2jax_ignore mathjax_ignore'>{safe_inline(q['question'])}</h3>",
            unsafe_allow_html=True
        )

        shown_topic = topic.strip() or "Random"
        st.markdown(
            f"<div class='muted'>Exam: {safe_inline(get_track_config(selected_exam)['display'])} "
            f"• Topic: {safe_inline(shown_topic)} • Difficulty: {safe_inline(difficulty)}</div>",
            unsafe_allow_html=True
        )

        display_options = [(L, safe_plain(txt)) for L, txt in q["choices"].items()]
        selected = st.radio(
            "Choose your answer:",
            options=display_options,
            format_func=lambda x: f"{x[0]}. {x[1]}",
            index=None,
            key="selected_answer"
        )

        if selected and not ss.show_result:
            ss.show_result = True
            ss.total += 1
            is_correct = (selected[0] == q["correct"])
            if is_correct:
                ss.score += 1

            elapsed = round(time.time() - ss.question_start, 1) if ss.question_start else None
            ss.history.append({
                "exam": get_track_config(selected_exam)["display"],
                "question": q["question"],
                "choices": q["choices"],
                "correct": q["correct"],
                "chosen": selected[0],
                "is_correct": is_correct,
                "explanation": q.get("explanation", ""),
                "rationales": q.get("rationales", {}),
                "time_sec": elapsed,
                "topic": shown_topic,
                "difficulty": difficulty
            })

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

            # Bottom Generate button: request then rerun (safe)
            if st.button("Generate New Question", disabled=(not exam_selected), key="gen_bottom"):
                request_generation()

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

                st.markdown(f"<div>Exam: <strong>{safe_inline(h.get('exam',''))}</strong></div>", unsafe_allow_html=True)
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

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "exam", "topic", "difficulty", "question",
            "choice_A", "choice_B", "choice_C", "choice_D",
            "chosen", "correct", "is_correct", "time_sec", "explanation"
        ])
        for h in ss.history:
            ch = h["choices"]
            writer.writerow([
                h.get("exam", ""),
                h["topic"], h["difficulty"], h["question"],
                ch.get("A",""), ch.get("B",""), ch.get("C",""), ch.get("D",""),
                h["chosen"], h["correct"], "TRUE" if h["is_correct"] else "FALSE",
                h["time_sec"] if h["time_sec"] is not None else "",
                sanitize_explanation(h["explanation"])
            ])
        csv_bytes = output.getvalue().encode("utf-8")
        st.download_button("Download results (CSV)", data=csv_bytes, file_name="opsynergy_exam_session.csv", mime="text/csv")

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
