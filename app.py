import os
import streamlit as st
import requests
import json

st.set_page_config(page_title="PMP AI Quiz Generator", layout="centered")

# --- Banner ---
st.markdown("""
    <div style='width:100%; height:70px; background: linear-gradient(90deg, #D32F2F 0%, #FFFFFF 50%, #1976D2 100%);
    display:flex; align-items:center; justify-content:center; margin-bottom:30px; border-radius:0 0 10px 10px;'>
        <h1 style='color:#222; font-size:2rem; font-weight:700;'>PMP AI Quiz Generator</h1>
    </div>
""", unsafe_allow_html=True)

st.markdown("### Powered by Groq & LLaMA 3")
st.write("Enter a PMP topic or leave blank for a random question:")

topic = st.text_input("")
generate = st.button("Generate Question")

question_data = None
selected_answer = None

def generate_prompt(topic):
    return f"""
You are a PMP exam tutor. Return only a single PMP multiple choice exam question in valid JSON format as shown:

{{
  "question": "What is the primary purpose of a Work Breakdown Structure (WBS)?",
  "choices": {{
    "A": "Identify stakeholders",
    "B": "Break down the project into manageable components",
    "C": "Control project costs",
    "D": "Define quality standards"
  }},
  "correct": "B",
  "explanation": "The WBS helps in decomposing the overall project into smaller, more manageable components."
}}

Only include the JSON. The question must be relevant to PMP exam content. Topic: {topic if topic else "random"}
""".strip()

def parse_question(response_text):
    try:
        # Extract only the JSON block if surrounded by code blocks
        start = response_text.find('{')
        end = response_text.rfind('}') + 1
        json_str = response_text[start:end]
        return json.loads(json_str)
    except Exception as e:
        st.error("Sorry, something went wrong parsing the question.")
        st.caption(f"Error: {e}")
        return None

if generate:
    headers = {
        "Authorization": f"Bearer {os.getenv('GROQ_API_KEY')}"
    }

    payload = {
        "model": "llama3-8b-8192",
        "messages": [
            {"role": "user", "content": generate_prompt(topic)}
        ]
    }

    with st.spinner("Generating your question..."):
        res = requests.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=payload)
        if res.status_code == 200:
            response_text = res.json()["choices"][0]["message"]["content"]
            question_data = parse_question(response_text)
        else:
            st.error("Failed to get a response from Groq API.")
            st.caption(res.text)

if question_data:
    st.subheader(question_data["question"])
    selected_answer = st.radio("Choose your answer:", list(question_data["choices"].items()), format_func=lambda x: f"{x[0]}. {x[1]}")

    if selected_answer:
        if selected_answer[0] == question_data["correct"]:
            st.success(f"✅ Correct! The answer is {selected_answer[0]}.")
        else:
            st.error(f"❌ Incorrect. Correct answer is {question_data['correct']}.")
        st.info(f"Explanation: {question_data['explanation']}")