import os
import streamlit as st
import requests
import json
import re

st.set_page_config(page_title="OpSynergy PMP AI Quiz Generator", layout="centered")

# --- Styles and Banner ---
st.markdown("""
    <div style='width:100%; height:70px; background: linear-gradient(90deg, #D32F2F 0%, #FFFFFF 50%, #1976D2 100%);
    display:flex; align-items:center; justify-content:center; margin-bottom:30px; border-radius:0 0 10px 10px;'>
        <h1 style='color:#222; font-size:2rem; font-weight:700; margin:0;'>OpSynergy PMP AI Quiz Generator</h1>
    </div>
""", unsafe_allow_html=True)

# --- Description ---
st.subheader("Powered by Groq & LLaMA 3")
st.markdown("Enter a PMP topic or leave blank for a random question:")

topic = st.text_input("")
generate = st.button("Generate Question")

# --- Session state for score tracking ---
if "total_attempts" not in st.session_state:
    st.session_state.total_attempts = 0
if "correct_answers" not in st.session_state:
    st.session_state.correct_answers = 0

# --- Function to parse the AI response ---
def parse_question(raw):
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group())
    except json.JSONDecodeError:
        return None

# --- Handle generate button ---
if generate:
    with st.spinner("Generating question..."):
        try:
            api_key = os.getenv("GROQ_API_KEY")
            if not api_key:
                st.error("GROQ_API_KEY not set.")
                st.stop()

            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }

            prompt = f"""
You are a PMP exam simulator bot. Generate one PMP-style multiple choice question. Format your response strictly as JSON like this:

{{
  "question": "Your PMP-style question here",
  "choices": ["Option A", "Option B", "Option C", "Option D"],
  "correct_answer": "B",
  "explanation": "Explain why the correct answer is correct"
}}

Make sure there is only one correct answer and the output is in valid JSON. The topic is: {topic if topic else "random"}.
"""

            body = {
                "model": "llama3-8b-8192",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.7
            }

            response = requests.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=body)
            response.raise_for_status()
            data = response.json()
            content = data['choices'][0]['message']['content']

            parsed = parse_question(content)
            if not parsed:
                st.error("Sorry, something went wrong parsing the question.")
                st.stop()

            question = parsed["question"]
            choices = parsed["choices"]
            correct = parsed["correct_answer"]
            explanation = parsed["explanation"]

            st.markdown(f"### {question}")
            user_answer = st.radio("Choose your answer:", choices, key=question)

            if user_answer:
                if st.button("Submit Answer"):
                    st.session_state.total_attempts += 1
                    if user_answer.strip().lower() == choices[ord(correct.upper()) - 65].strip().lower():
                        st.session_state.correct_answers += 1
                        st.success("✅ Correct!")
                    else:
                        st.error("❌ Incorrect.")
                    st.info(f"**Explanation:** {explanation}")
                    st.info(f"**Score this session:** {st.session_state.correct_answers} out of {st.session_state.total_attempts}")

        except Exception as e:
            st.error(f"An error occurred: {e}")