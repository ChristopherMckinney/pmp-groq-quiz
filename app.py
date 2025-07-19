import os
import streamlit as st
import requests
import json
import random

st.set_page_config(page_title="PMP AI Quiz Generator", layout="centered")

# --- Banner ---
st.markdown("""
    <div style='width:100%; height:70px; background: linear-gradient(90deg, #D32F2F 0%, #FFFFFF 50%, #1976D2 100%); 
    display:flex; align-items:center; justify-content:center; border-radius:0 0 10px 10px; margin-bottom:25px;'>
        <h1 style='color:#222; font-size:2rem; font-weight:700;'>PMP AI Quiz Generator</h1>
    </div>
""", unsafe_allow_html=True)

# --- Header ---
st.markdown("**Powered by Groq & LLaMA 3**")
st.write("Enter a PMP topic or leave blank for a random question:")

# --- Input and Button ---
topic = st.text_input("")
if 'score' not in st.session_state:
    st.session_state.score = 0
if 'total' not in st.session_state:
    st.session_state.total = 0

if st.button("Generate Question"):
    prompt_variants = [
        "Give me a PMP multiple choice exam question in JSON format.",
        "Generate a realistic PMP exam question with answer choices and explanation in JSON.",
        "Create a multiple choice question for the PMP exam. Format the output in JSON.",
        "I need a PMP exam-style question with choices, correct answer, and explanation in JSON.",
        "Write a PMP question with 4 answer choices and an explanation in JSON format."
    ]
    selected_prompt = random.choice(prompt_variants)
    final_prompt = f"{selected_prompt} The topic is: {topic}" if topic else selected_prompt

    try:
        res = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {os.getenv('GROQ_API_KEY')}",
                "Content-Type": "application/json"
            },
            json={
                "model": "llama3-70b-8192",
                "messages": [
                    {"role": "user", "content": final_prompt}
                ],
                "temperature": 0.9  # adds randomness
            }
        )
        res.raise_for_status()
        raw = res.json()['choices'][0]['message']['content']

        # Extract JSON from raw text using regex (or fallback to first {...})
        try:
            first_brace = raw.index('{')
            last_brace = raw.rindex('}') + 1
            json_text = raw[first_brace:last_brace]
            question_data = json.loads(json_text)
        except:
            st.error("Sorry, something went wrong parsing the question.")
            st.stop()

        question = question_data.get("question", "")
        choices = question_data.get("choices", {})
        correct = question_data.get("correct", "")
        explanation = question_data.get("explanation", "")

        st.markdown(f"### {question}")
        selected = st.radio("Choose your answer:", list(choices.values()), index=-1, key=random.randint(0, 1000000))

        if selected:
            st.session_state.total += 1
            selected_key = next((k for k, v in choices.items() if v == selected), None)
            if selected_key == correct:
                st.session_state.score += 1
                st.success("\u2705 Correct!")
            else:
                st.error(f"\u274C Incorrect. Correct answer is {correct}.")
            st.info(f"**Explanation:** {explanation}")
            st.markdown(f"---\n**Session Score:** {st.session_state.score} out of {st.session_state.total} correct")

    except Exception as e:
        st.error(f"Error: {str(e)}")