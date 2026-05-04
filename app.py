import os
from flask import Flask, request, jsonify, render_template, Response, stream_with_context
from dotenv import load_dotenv
from groq import Groq
from tavily import TavilyClient
import json

load_dotenv()

app = Flask(__name__)

# AI Brain
api_key = os.environ.get("GROQ_API_KEY")
client = Groq(api_key=api_key)

# Search Tool
tavily = TavilyClient(api_key=os.environ.get("TAVILY_API_KEY"))

# Kia's Memory
conversation_history = []

def should_search(message):
    search_keywords = [
        "today", "latest", "current", "now", "recent",
        "news", "weather", "price", "score", "update",
        "what happened", "right now", "this week",
        "this month", "this year", "2024", "2025"
    ]
    message_lower = message.lower()
    return any(keyword in message_lower for keyword in search_keywords)

def search_web(query):
    try:
        results = tavily.search(query=query, max_results=3)
        search_summary = ""
        for result in results["results"]:
            search_summary += f"Source: {result['url']}\n"
            search_summary += f"Info: {result['content']}\n\n"
        return search_summary
    except Exception as e:
        return ""

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/chat", methods=["POST"])
def chat():
    user_message = request.json.get("message")

    # Add user message to memory
    conversation_history.append({
        "role": "user",
        "content": user_message
    })

    # Build system message
    system_message = "You are Kia, a friendly assistant who answers general questions simply and clearly. Keep answers short and conversational."

    if should_search(user_message):
        search_results = search_web(user_message)
        if search_results:
            system_message += f"""

Here is some current information from the web to help you answer:

{search_results}

Use this information naturally in your answer.
Do NOT say "I searched the web" or "Based on search results".
Just answer naturally like you already knew this information.
Keep your answer short, friendly and conversational.
"""

    def generate():
        # Stream response word by word
        full_reply = ""

        stream = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {
                    "role": "system",
                    "content": system_message
                }
            ] + conversation_history,
            stream=True  # This enables streaming!
        )

        for chunk in stream:
            # Get each word/piece as it arrives
            delta = chunk.choices[0].delta.content
            if delta:
                full_reply += delta
                # Send each piece to browser immediately
                yield f"data: {json.dumps({'token': delta})}\n\n"

        # Save full reply to memory after streaming
        conversation_history.append({
            "role": "assistant",
            "content": full_reply
        })

        # Tell browser streaming is done
        yield f"data: {json.dumps({'done': True})}\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream"
    )

@app.route("/clear", methods=["POST"])
def clear():
    conversation_history.clear()
    return jsonify({"status": "Memory cleared!"})

if __name__ == "__main__":
    app.run(debug=True, port=8080)