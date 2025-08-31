import os
import streamlit as st
import requests
import json
import re
import uuid
import random
from html import escape  # <-- added
import time  # <-- add this with your imports at the top

def call_groq(prompt):
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {os.getenv('GROQ_API_KEY')}",
        "Content-Type": "application/json"
    }
    body = {
        "model": "llama3-70b-8192",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.9
    }

    start = time.time()
    response = requests.post(url, headers=headers, json=body)
    elapsed = time.time() - start

    # This goes to Render’s Logs tab
    print(f"[PERF] Request took {elapsed:.2f}s")

    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"]


st.set_page_config(page_title="OpSynergy PMP AI Quiz Generator", layout="centered")

st.markdown("""
<style>
  /* Hide Streamlit's top-right menu & status */
  [data-testid="stToolbar"] {visibility: hidden; height: 0; position: fixed;}
  [data-testid="stDecoration"] {display: none;}
  [data-testid="stStatusWidget"] {display: none;}
</style>
""", unsafe_allow_html=True)


# (optional but safe) ensure question text never renders italic
st.markdown("""
<style>
  .qtext { font-style: normal; }
  .qtext em, .qtext i { font-style: normal !important; }
</style>
""", unsafe_allow_html=True)

# --- Banner ---
st.markdown("""
    <div style='width:100%; height:70px; background: linear-gradient(90deg, #D32F2F 0%, #FFFFFF 50%, #1976D2 100%);
    display:flex; align-items:center; justify-content:center; margin-bottom:30px; border-radius:10px;'>
        <h1 style='color:#222; font-size:2rem; font-weight:700;'>OpSynergy PMP AI Quiz Generator</h1>
    </div>
""", unsafe_allow_html=True)

st.markdown("Enter a PMP topic or leave blank for a random question:")

topic = st.text_input("")

if "question_data" not in st.session_state:
    st.session_state.question_data = None
if "show_result" not in st.session_state:
    st.session_state.show_result = False
if "selected_answer" not in st.session_state:
    st.session_state.selected_answer = None
if "score" not in st.session_state:
    st.session_state.score = 0
if "total" not in st.session_state:
    st.session_state.total = 0

def shuffle_answers(data):
    choices_dict = data.get("choices", {})
    correct_letter = data.get("correct")

    # Create a list of (letter, text) tuples
    original_choices = list(choices_dict.items())
    correct_text = choices_dict.get(correct_letter)

    # Shuffle
    random.shuffle(original_choices)

    # Re-map to new A/B/C/D structure
    new_labels = ["A", "B", "C", "D"]
    new_choices = {label: choice[1] for label, choice in zip(new_labels, original_choices)}

    # Find new label of the correct answer
    for new_label, (_, text) in zip(new_labels, original_choices):
        if text == correct_text:
            new_correct = new_label
            break

    data["choices"] = new_choices
    data["correct"] = new_correct
    return data

def call_groq(prompt):
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {os.getenv('GROQ_API_KEY')}",
        "Content-Type": "application/json"
    }
    body = {
        "model": "llama3-70b-8192",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.9
    }

    response = requests.post(url, headers=headers, json=body)
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"]

def generate_prompt(topic):
    random_id = str(uuid.uuid4())
    topic_clean = topic.strip() if topic.strip() else "Any PMP-related topic"

    prompt_templates = [
        f"Generate a difficult PMP exam question related to {topic_clean}, using a unique context or situation.",
        f"Write a scenario-based PMP multiple-choice question involving {topic_clean}, focusing on application and judgment.",
        f"Produce a PMP-style question that covers advanced understanding of {topic_clean}, not just definitions.",
        f"Create a challenging PMP exam question using {topic_clean} in a realistic project management situation."
    ]
    topic_prompt = random.choice(prompt_templates)

    return f"""
{topic_prompt}

Return only valid JSON, following this format exactly:
{{
  "question": "Your question here",
  "choices": {{
    "A": "Option A",
    "B": "Option B",
    "C": "Option C",
    "D": "Option D"
  }},
  "correct": "B",
  "explanation": "Explanation of why this is the correct answer"
}}

Session ID: {random_id}
Do not include markdown, comments, or extra text — only return the raw JSON.
"""

def parse_question(raw_text):
    json_match = re.search(r"\{.*\}", raw_text, re.DOTALL)
    if not json_match:
        raise ValueError("Failed to extract JSON")
    data = json.loads(json_match.group())
    return shuffle_answers(data)

if st.button("Generate New Question"):
    try:
        with st.spinner("Generating..."):
            prompt = generate_prompt(topic)
            raw_output = call_groq(prompt)
            question_data = parse_question(raw_output)
            st.session_state.question_data = question_data
            st.session_state.show_result = False
            st.session_state.selected_answer = None
    except Exception as e:
        st.error("Sorry, something went wrong parsing the question.")
        st.stop()

if st.session_state.question_data:
    q = st.session_state.question_data

    # SAFE render: normalize stray underscores & escape HTML/Markdown
    clean_q = re.sub(r'(?<=\w)_(?=\w)', ' ', q['question'])
    st.markdown(f"<h3 class='qtext'>{escape(clean_q)}</h3>", unsafe_allow_html=True)

    selected = st.radio(
        "Choose your answer:",
        options=list(q["choices"].items()),
        format_func=lambda x: f"{x[0]}. {x[1]}",
        index=None,
        key="selected_answer"
    )

    if selected and not st.session_state.show_result:
        st.session_state.show_result = True
        st.session_state.total += 1
        if selected[0] == q["correct"]:
            st.session_state.score += 1

    if st.session_state.show_result and selected:
        if selected[0] == q["correct"]:
            st.success("✅ Correct!")
        else:
            st.error(f"❌ Incorrect. Correct answer is {q['correct']}.")
        st.info(f"**Explanation:** {q['explanation']}")
        st.markdown(f"**Score:** {st.session_state.score} out of {st.session_state.total} attempts this session")

# --- Footer disclaimer ---
st.markdown("---")
st.markdown(
    "<small>All questions are generated by AI and should be reviewed for accuracy. "
    "OpSynergy is not responsible for the validity or appropriateness of any content generated by this simulator. "
    "This tool is not affiliated with or endorsed by PMI®.</small>",
    unsafe_allow_html=True
)
