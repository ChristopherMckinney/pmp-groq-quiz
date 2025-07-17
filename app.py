import os
import streamlit as st
import requests

# Read Groq API Key from environment
API_KEY = os.getenv("GROQ_API_KEY")

# Streamlit UI
st.title("PMP AI Quiz Generator")
st.subheader("Powered by Groq & LLaMA 3")

topic = st.text_input("Enter a PMP topic or leave blank for a random question:")

if st.button("Generate Question"):
    if not API_KEY:
        st.error("API key is missing. Please check your Render environment variables.")
    else:
        headers = {
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json"
        }

        payload = {
            "model": "llama3-8b-8192",
            "messages": [
                {
                    "role": "user",
                    "content": f"Generate a PMP exam-style question about {topic or 'any topic'}, and give four answer choices. Do not label the choices with letters."
                }
            ]
        }

        try:
            response = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers=headers,
                json=payload,
                timeout=20
            )
            data = response.json()

            if "choices" in data:
                question = data["choices"][0]["message"]["content"]
                st.success("Question Generated:")
                st.write(question)
            else:
                st.error(f"Error from API: {data.get('error', {}).get('message', 'Unknown error')}")

        except Exception as e:
            st.error(f"Request failed: {str(e)}")
