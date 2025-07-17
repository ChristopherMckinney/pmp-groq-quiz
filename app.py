import streamlit as st
import requests
import os

st.set_page_config(page_title="PMP AI Quiz Generator")
st.title("PMP AI Quiz Generator")
st.subheader("Powered by Groq & LLaMA 3")

api_key = os.getenv("GROQ_API_KEY")
if not api_key:
    st.error("API key not set. Please set the GROQ_API_KEY environment variable.")
    st.stop()

prompt = st.text_input("Enter a PMP topic or leave blank for a random question:")

if st.button("Generate Question"):
    with st.spinner("Generating..."):
        response = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer " + api_key,
                "Content-Type": "application/json"
            },
            json={
                "model": "llama3-70b-8192",
                "messages": [
                    {
                        "role": "system",
                        "content": "You are a PMP exam question generator. Generate a single multiple-choice PMP exam question. Format answers with A, B, C, D. No explanations."
                    },
                    {
                        "role": "user",
                        "content": prompt or "Generate a random PMP question"
                    }
                ]
            }
        )
        if response.ok:
            question = response.json()["choices"][0]["message"]["content"]
            st.markdown(f"**{question}**")
        else:
            st.error("Failed to generate question. Check your API key or request format.")
