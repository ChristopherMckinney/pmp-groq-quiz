import os
import requests
import streamlit as st
import json
import random

# --- App Configuration ---
st.set_page_config(page_title="OpSynergy PMP AI Quiz Generator", layout="centered")

# --- Styling ---
st.markdown("""
    <div style='width:100%; height:70px; background: linear-gradient(90deg, #D32F2F 0%, #FFFFFF 50%, #1976D2 100%);
    display:flex; align-items:center; justify-content:center; margin-bottom:30px; border-radius:0 0 10px 10px;'>
        <h1 style='color:#222; font-size:2rem; font-weight:700;'>OpSynergy PMP AI Quiz Generator</h1>
    </div>
""", unsafe_allow_html=True)

st.subheader("Powered by Groq & LLaMA 3")
st.caption("Enter a PMP topic or leave blank for a random question:")

# --- Text Input for Topic ---
topic = st.text_input("")

# --- Score Tracking ---
if "score" not in st.session_state:
    st.session_state.score = 0
if "attempts" not in st.session_state:
    st.session_state.attempts = 0

# --- Generate Button ---
if st.button("Generate Question"):
    st.session_state.selected = None
    prompt = f"Write a PMP multiple choice exam question in JSON format with 4 answer options. Only one correct. Topic: {topic if topic else 'any'}."
    
    headers = {
        "Authorization": f"Bearer {os.getenv('GROQ_API_KEY')}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": "llama3-8b-8192",
        "messages": [
            {"role": "system", "content": "You are a PMP exam coach generating valid, challenging questions."},
            {"role": "user", "content": prompt}
        ]
    }

    try:
        res = requests.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=payload)
        raw = res.json()["choices"][0]["message"]["content"]

        # --- Extract JSON from response ---
        json_string = raw.split("```")[1] if "```" in raw else raw
        parsed = json.loads(json_string)

        st.session_state.question = parsed.get("question", "No question provided.")
        st.session_state.choices = parsed.get("choices", {})
        st.session_state.correct = parsed.get("correct", "")
        st.session_state.explanation = parsed.get("explanation", "")
        st.session_state.selected = None

    except Exception as e:
        st.error("Sorry, something went wrong parsing the question.")
        st.stop()

# --- Display Question & Choices ---
if "question" in st.session_state:
    st.markdown(f"### {st.session_state.question}")
    options = list(st.session_state.choices.items())
    choice_labels = [f"{k}. {v}" for k, v in options]

    selected = st.radio("Choose your answer:", choice_labels, index=-1, key="user_answer")

    if selected:
        selected_key = selected.split(".")[0]
        st.session_state.attempts += 1

        if selected_key == st.session_state.correct:
            st.session_state.score += 1
            st.success("✅ Correct!")
        else:
            st.error(f"❌ Incorrect. Correct answer is {st.session_state.correct}.")

        st.info(f"**Explanation:** {st.session_state.explanation}")
        st.caption(f"Score: {st.session_state.score} out of {st.session_state.attempts} correct.")