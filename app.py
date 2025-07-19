import os
import streamlit as st
import requests
import json
import re
import random
import datetime

st.set_page_config(page_title="OpSynergy PMP AI Quiz Generator", layout="centered")

# --- Banner ---
st.markdown("""
    <div style='width:100%; height:70px; background: linear-gradient(90deg, #D32F2F 0%, #FFFFFF 50%, #1976D2 100%);
    display:flex; align-items:center; justify-content:center; margin-bottom:30px; border-radius:0 0 10px 10px;'>
        <h1 style='color:#222; font-size:2rem; font-weight:700;'>OpSynergy PMP AI Quiz Generator</h1>
    </div>
""", unsafe_allow_html=True)

st.markdown("### Powered by Groq & LLaMA 3")
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
if "attempts" not in st.session_state:
    st.session_state.attempts = 0

def call_groq(prompt):
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {os.getenv('GROQ_API_KEY')}",
        "Content-Type": "application/json"
    }
    body = {
        "model": "llama3-70b-8192",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.6
    }

    response = requests.post(url, headers=headers, json=body)
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"]

def generate_prompt(topic):
    seed = random.randint(1000, 9999)
    timestamp = datetime.datetime.now().strftime("%f")

    return f"""
You are an expert PMP exam simulator.

Generate a *new*, realistic PMP multiple choice exam question in JSON format with 4 labeled answer choices. Make sure it is not a repeat of previous questions. Use subtle variations in wording, topic depth, or context.

Here is the required format:

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

Topic: {topic if topic.strip() else "Any PMP-related topic"}
Random seed: {seed}-{timestamp}

Only return the JSON. Do not include markdown formatting or commentary.
"""

def parse_question(raw_text):
    json_match = re.search(r"\{.*\}", raw_text, re.DOTALL)
    if not json_match:
        raise ValueError("Failed to extract JSON")
    return json.loads(json_match.group())

if st.button("Generate Question"):
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
    st.markdown(f"### {q['question']}")

    selected = st.radio(
        "Choose your answer:",
        options=list(q["choices"].items()),
        format_func=lambda x: f"{x[0]}. {x[1]}",
        index=None,
        key="selected_answer"
    )

    if selected and not st.session_state.show_result:
        st.session_state.show_result = True

    if st.session_state.show_result and selected:
        st.session_state.attempts += 1
        if selected[0] == q["correct"]:
            st.session_state.score += 1
            st.success("✅ Correct!")
        else:
            st.error(f"❌ Incorrect. Correct answer is {q['correct']}.")

        st.info(f"**Explanation:** {q['explanation']}")
        st.markdown(f"**Score this session:** {st.session_state.score} out of {st.session_state.attempts}")
