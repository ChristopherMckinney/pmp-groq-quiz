import os
import streamlit as st
import requests
import json
import random

st.set_page_config(page_title="OpSynergy PMP AI Quiz Generator", layout="centered")

# --- Banner ---
st.markdown("""
    <div style='width:100%; height:70px; background: linear-gradient(90deg, #D32F2F 0%, #FFFFFF 50%, #1976D2 100%); 
    display:flex; align-items:center; justify-content:center; margin-bottom:30px; border-radius:0 0 10px 10px;'>
        <h1 style='color:#222; font-size:2rem; font-weight:700; margin:0;'>OpSynergy PMP AI Quiz Generator</h1>
    </div>
""", unsafe_allow_html=True)

st.markdown("### Powered by Groq & LLaMA 3")
st.write("Enter a PMP topic or leave blank for a random question:")

topic = st.text_input("")

if 'question' not in st.session_state:
    st.session_state.question = None
if 'choices' not in st.session_state:
    st.session_state.choices = []
if 'correct' not in st.session_state:
    st.session_state.correct = None
if 'explanation' not in st.session_state:
    st.session_state.explanation = ""
if 'user_answer' not in st.session_state:
    st.session_state.user_answer = None

def call_groq_api(topic):
    prompt = f"Generate a PMP exam-style multiple-choice question on {topic if topic else 'a random topic'}, with four answer options labeled A through D. Mark the correct answer clearly. Provide a short explanation."
    
    response = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {os.getenv('GROQ_API_KEY')}",
            "Content-Type": "application/json"
        },
        json={
            "model": "llama3-8b-8192",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 1.0
        }
    )

    content = response.json()['choices'][0]['message']['content']
    return parse_response(content)

def parse_response(content):
    try:
        question = ""
        choices = []
        correct_answer = ""
        explanation = ""

        lines = content.splitlines()
        for i, line in enumerate(lines):
            if line.strip().lower().startswith("question:"):
                question = line.split(":", 1)[1].strip()
            elif any(line.strip().startswith(opt) for opt in ["A.", "B.", "C.", "D."]):
                choices.append(line.strip())
            elif "correct answer" in line.lower():
                correct_answer = line.split(":")[-1].strip().split()[0]
            elif "explanation" in line.lower():
                explanation = line.split(":", 1)[-1].strip()

        if not (question and choices and correct_answer):
            raise ValueError("Missing data in response")

        return {
            "question": question,
            "choices": choices,
            "correct": correct_answer[0].upper(),
            "explanation": explanation
        }
    except Exception as e:
        return None

if st.button("Generate Question"):
    data = call_groq_api(topic)
    if data:
        st.session_state.question = data["question"]
        st.session_state.choices = data["choices"]
        st.session_state.correct = data["correct"]
        st.session_state.explanation = data["explanation"]
        st.session_state.user_answer = None
    else:
        st.error("Sorry, something went wrong parsing the question.")

if st.session_state.question:
    st.markdown(f"### {st.session_state.question}")
    st.session_state.user_answer = st.radio("Choose your answer:", st.session_state.choices, key="answer_choice")

    if st.button("Submit Answer"):
        if st.session_state.user_answer:
            selected_letter = st.session_state.user_answer.split(".")[0].strip().upper()
            if selected_letter == st.session_state.correct:
                st.success("✅ Correct!")
            else:
                st.error(f"❌ Incorrect. The correct answer is {st.session_state.correct}.")
            st.info(f"**Explanation:** {st.session_state.explanation}")