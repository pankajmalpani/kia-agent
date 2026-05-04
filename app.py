import os
from flask import Flask, request, jsonify, render_template
from dotenv import load_dotenv
from groq import Groq

load_dotenv()

app = Flask(__name__)
api_key = os.environ.get("GROQ_API_KEY")
client = Groq(api_key=api_key)

# This is Kia's MEMORY — an empty notebook
# It stores the entire conversation history
conversation_history = []

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/chat", methods=["POST"])
def chat():
    user_message = request.json.get("message")

    # Step 1 — Write user message in notebook
    conversation_history.append({
        "role": "user",
        "content": user_message
    })

    # Step 2 — Send entire notebook to AI
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {
                "role": "system",
                "content": "You are Kia, a friendly assistant who answers general questions simply and clearly."
            }
        ] + conversation_history  # Full history sent here!
    )

    # Step 3 — Get Kia's reply
    reply = response.choices[0].message.content

    # Step 4 — Write Kia's reply in notebook too
    conversation_history.append({
        "role": "assistant",
        "content": reply
    })

    return jsonify({"reply": reply})

@app.route("/clear", methods=["POST"])
def clear():
    # This clears the memory — fresh start!
    conversation_history.clear()
    return jsonify({"status": "Memory cleared!"})

if __name__ == "__main__":
    app.run(debug=True, port=8080)