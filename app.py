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
        <h1 style='color:#222; font-size:2rem; font-weight:700; margin:0;'>PMP AI Quiz Generator</h1>
    </div>
""", unsafe_allow_html=True)

st.markdown("### Powered by Groq & LLaMA 3")
st.markdown("Enter a PMP topic or leave blank for a random question:")

topic = st.text_input("")

# === API CALL ===
def call_openrouter(prompt):
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {os.getenv('GROQ_API_KEY')}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "llama3-70b-8192",
        "messages": [
            {
                "role": "user",
                "content": f"Generate a PMP multiple choice exam question in JSON format with the following fields: question, choices (with A, B, C, D), correct, explanation. Topic: {prompt if prompt else 'any'}"
            }
        ],
        "temperature": 0.7
    }
    response = requests.post(url, headers=headers, json=payload)
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"]

# === JSON PARSER ===
def extract_json(raw):
    try:
        match = re.search(r'{.*}', raw, re.DOTALL)
        return json.loads(match.group()) if match else None
    except Exception:
        return None

# === UI ===
if st.button("Generate Question"):
    with st.spinner("Generating question..."):
        try:
            raw = call_openrouter(topic)
            st.code(raw, language="json")  # Show raw output for debug
            data = extract_json(raw)
            if not data:
                st.error("❌ Could not parse a valid question. Try again.")
            else:
                st.markdown(f"**{data['question']}**")
                options = [f"{key}: {value}" for key, value in data['choices'].items()]
                selected = st.radio("Choose your answer:", options)

                if selected:
                    selected_key = selected.split(":")[0]
                    if selected_key == data['correct']:
                        st.success("✅ Correct!")
                    else:
                        st.error(f"❌ Incorrect. Correct answer is {data['correct']}.")
                    st.info(f"**Explanation:** {data['explanation']}")
        except Exception as e:
            st.error(f"Error generating question: {e}")
