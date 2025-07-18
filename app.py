import os
import streamlit as st
import requests
import json
import re

st.set_page_config(page_title="PMP AI Quiz Generator", layout="centered")

# --- Banner ---
st.markdown("""
    <div style='width:100%; height:70px; background: linear-gradient(90deg, #D32F2F 0%, #FFFFFF 50%, #1976D2 100%);
    display:flex; align-items:center; justify-content:center; margin-bottom:30px; border-radius:0 0 10px 10px;'>
        <h1 style='color:#222; font-size:2rem; font-weight:700;'>PMP AI Quiz Generator</h1>
    </div>
""", unsafe_allow_html=True)

# --- Title ---
st.markdown("### Powered by Groq & LLaMA 3")
st.write("Enter a PMP topic or leave blank for a random question:")

# --- Input ---
topic = st.text_input("")
submit = st.button("Generate Question")

# --- Secure Key ---
api_key = os.getenv("OPENROUTER_API_KEY")

# --- Headers ---
headers = {
    "Authorization": f"Bearer {api_key}",
    "Content-Type": "application/json"
}

# --- Extract Function ---
def extract_question_data(response_text):
    try:
        json_str_match = re.search(r"\{.*?\}", response_text, re.DOTALL)
        if json_str_match:
            json_str = json_str_match.group(0)
            data = json.loads(json_str)
            return {
                "question": data["question"],
                "choices": data["choices"],
                "correct": data["correct"],
                "explanation": data["explanation"]
            }
    except Exception as e:
        print(f"Parsing error: {e}")
    return None

# --- Display Logic ---
if submit:
    prompt = f"""Generate a PMP multiple choice exam question in JSON format:
- Format:
{{
  "question": "...",
  "choices": {{
    "A": "...",
    "B": "...",
    "C": "...",
    "D": "..."
  }},
  "correct": "X",
  "explanation": "..."
}}
Only output the JSON, no markdown or extra commentary.
Topic: {topic if topic else "random"}"""

    response = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers=headers,
        json={
            "model": "meta-llama/llama-3-70b-instruct",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.7
        }
    )

    result = response.json()
    text = result['choices'][0]['message']['content']
    parsed = extract_question_data(text)

    if parsed:
        st.success("Question Generated:")
        st.markdown(f"**{parsed['question']}**")

        selected = st.radio("Choose your answer:", list(parsed['choices'].items()), format_func=lambda x: f"{x[0]}. {x[1]}")
        if selected:
            if selected[0] == parsed['correct']:
                st.success(f"✅ Correct! {parsed['explanation']}")
            else:
                st.error(f"❌ Incorrect. Correct answer is {parsed['correct']}.")
                st.info(f"Explanation: {parsed['explanation']}")
    else:
        st.error("Sorry, something went wrong parsing the question.")
