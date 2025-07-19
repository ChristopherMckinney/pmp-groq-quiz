import os
import streamlit as st
import requests
import json
import random

st.set_page_config(page_title="OpSynergy PMP AI Quiz Generator", layout="centered")

st.markdown("""
    <div style='width:100%; height:70px; background: linear-gradient(90deg, #D32F2F 0%, #FFFFFF 50%, #1976D2 100%); 
    display:flex; align-items:center; justify-content:center; margin-bottom:30px; border-radius:0 0 10px 10px;'>
        <h1 style='color:#222; font-size:2rem; font-weight:700; margin:0;'>OpSynergy PMP AI Quiz Generator</h1>
    </div>
""", unsafe_allow_html=True)

st.markdown("**Powered by Groq & LLaMA 3**")
topic = st.text_input("Enter a PMP topic or leave blank for a random question:")

if "score" not in st.session_state:
    st.session_state.score = 0
    st.session_state.total = 0

if "question" not in st.session_state:
    st.session_state.question = None
if "choices" not in st.session_state:
    st.session_state.choices = []
if "answer" not in st.session_state:
    st.session_state.answer = ""
if "explanation" not in st.session_state:
    st.session_state.explanation = ""

if st.button("Generate Question"):
    prompt = f"Generate one random PMP multiple choice exam question{' about ' + topic if topic else ''}. Format it as JSON with keys: question, choices (a list of 4), answer (just the letter), and explanation."

    response = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {os.getenv('GROQ_API_KEY')}",
            "Content-Type": "application/json"
        },
        json={
            "model": "llama3-70b-8192",
            "messages": [
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.9
        }
    )

    try:
        content = response.json()["choices"][0]["message"]["content"]
        parsed = json.loads(content)
        st.session_state.question = parsed["question"]
        st.session_state.choices = parsed["choices"]
        st.session_state.answer = parsed["answer"].upper()
        st.session_state.explanation = parsed["explanation"]
        st.session_state.selected = None
    except Exception as e:
        st.session_state.question = None
        st.error("Sorry, something went wrong parsing the question.")

if st.session_state.question:
    st.write(f"### {st.session_state.question}")
    selected = st.radio("Choose your answer:", st.session_state.choices, key=random.random())

    if selected:
        correct_index = ord(st.session_state.answer) - 65
        if st.session_state.choices.index(selected) == correct_index:
            st.success("\u2705 Correct!")
            st.session_state.score += 1
        else:
            st.error(f"\u274C Incorrect. Correct answer is {st.session_state.answer}.")

        st.session_state.total += 1
        st.info(f"**Explanation:** {st.session_state.explanation}")
        st.info(f"**Score:** {st.session_state.score} out of {st.session_state.total} attempts this session.")