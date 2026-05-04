import os
import fitz  # PyMuPDF
import io
from flask import Flask, request, jsonify, render_template, Response, stream_with_context, send_file, session, redirect, url_for
from dotenv import load_dotenv
from groq import Groq
from tavily import TavilyClient
import json
import secrets

load_dotenv()

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB limit
app.secret_key = secrets.token_hex(16)  # For session management

# Login credentials from .env
LOGIN_USERNAME = os.environ.get("LOGIN_USERNAME", "admin")
LOGIN_PASSWORD = os.environ.get("LOGIN_PASSWORD", "kia2025")

# AI Brain
api_key = os.environ.get("GROQ_API_KEY")
client = Groq(api_key=api_key)

# Search Tool — optional
tavily_key = os.environ.get("TAVILY_API_KEY")
tavily = TavilyClient(api_key=tavily_key) if tavily_key else None

# Kia's Memory
conversation_history = []

# Uploaded file storage
uploaded_file_content = ""
uploaded_file_name = ""
uploaded_file_bytes = None

def login_required(f):
    """
    This is a decorator — it protects routes.
    If user is not logged in, redirect to login page.
    """
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated_function

def should_search(message):
    search_keywords = [
        "today", "latest", "current", "now", "recent",
        "news", "weather", "price", "score", "update",
        "what happened", "right now", "this week",
        "this month", "this year", "2024", "2025", "2026"
    ]
    message_lower = message.lower()
    return any(keyword in message_lower for keyword in search_keywords)

def search_web(query):
    if not tavily:
        return ""
    try:
        results = tavily.search(query=query, max_results=3)
        search_summary = ""
        for result in results["results"]:
            search_summary += f"Source: {result['url']}\n"
            search_summary += f"Info: {result['content']}\n\n"
        return search_summary
    except Exception as e:
        return ""

def extract_pdf_text_from_bytes(pdf_bytes):
    try:
        pdf_document = fitz.open(stream=pdf_bytes, filetype="pdf")
        full_text = ""
        for page_num in range(len(pdf_document)):
            page = pdf_document.load_page(page_num)
            full_text += f"\n--- Page {page_num + 1} ---\n"
            full_text += page.get_text()
        pdf_document.close()
        return full_text
    except Exception as e:
        return ""

# ── LOGIN ROUTES ──

@app.route("/login", methods=["GET", "POST"])
def login():
    """
    GET  → Show login page
    POST → Check credentials
    """
    error = None

    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")

        if username == LOGIN_USERNAME and password == LOGIN_PASSWORD:
            # Save login state in session
            session["logged_in"] = True
            session["username"] = username
            return redirect(url_for("home"))
        else:
            error = "Wrong username or password. Try again!"

    return render_template("login.html", error=error)

@app.route("/logout")
def logout():
    """Clears session and redirects to login"""
    session.clear()
    return redirect(url_for("login"))

# ── MAIN ROUTES ──

@app.route("/")
@login_required
def home():
    return render_template("index.html",
        username=session.get("username"))

@app.route("/upload", methods=["POST"])
@login_required
def upload():
    global uploaded_file_content, uploaded_file_name, uploaded_file_bytes

    if "file" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400

    file = request.files["file"]

    if file.filename == "":
        return jsonify({"error": "No file selected"}), 400

    if file.filename.endswith(".pdf"):
        file_bytes = file.read()
        uploaded_file_bytes = file_bytes
        uploaded_file_content = extract_pdf_text_from_bytes(file_bytes)
    elif file.filename.endswith(".txt"):
        uploaded_file_content = file.read().decode("utf-8")
        uploaded_file_bytes = None
    else:
        return jsonify({"error": "Please upload a PDF or TXT file"}), 400

    if not uploaded_file_content:
        return jsonify({"error": "Could not read file"}), 400

    uploaded_file_name = file.filename

    word_count = len(uploaded_file_content.split())
    page_count = uploaded_file_content.count("--- Page ")
    if page_count == 0:
        page_count = 1

    return jsonify({
        "success": True,
        "message": f"📄 Got it! I've finished reading '{file.filename}' — {page_count} page(s) and {word_count} words.\n\nYou can ask me to:\n• Summarise the document\n• Answer specific questions\n• Pull out key details\n\nWhat would you like to know? 😊"
    })

@app.route("/download-file", methods=["GET"])
@login_required
def download_file():
    global uploaded_file_bytes, uploaded_file_name
    if not uploaded_file_bytes:
        return "No file uploaded", 404
    return send_file(
        io.BytesIO(uploaded_file_bytes),
        mimetype="application/pdf",
        as_attachment=False,
        download_name=uploaded_file_name
    )

@app.route("/clear-file", methods=["POST"])
@login_required
def clear_file():
    global uploaded_file_content, uploaded_file_name, uploaded_file_bytes
    uploaded_file_content = ""
    uploaded_file_name = ""
    uploaded_file_bytes = None
    return jsonify({"status": "File cleared!"})

@app.route("/chat", methods=["POST"])
@login_required
def chat():
    global uploaded_file_content, uploaded_file_name

    user_message = request.json.get("message")

    conversation_history.append({
        "role": "user",
        "content": user_message
    })

    system_message = "You are Kia, a friendly assistant who answers general questions simply and clearly. Keep answers short and conversational."

    if uploaded_file_content:
        system_message += f"""

The user has uploaded a document called "{uploaded_file_name}".
Here is the full content:

{uploaded_file_content[:8000]}

Rules for answering:
- Answer naturally and conversationally in 1-2 lines
- NEVER say "as mentioned in the document" or "according to the document"
- NEVER reference section names or page numbers
- Just answer directly and confidently
- At the end of every answer add a new line with exactly this: 📄 Source: {uploaded_file_name} → /download-file
- If the answer is not in the document say "I could not find that in your document"
- Keep answers short and friendly
"""

    elif should_search(user_message):
        search_results = search_web(user_message)
        if search_results:
            system_message += f"""

Here is some current information from the web:

{search_results}

Use this naturally. Do NOT say you searched the web.
"""

    def generate():
        full_reply = ""

        stream = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {
                    "role": "system",
                    "content": system_message
                }
            ] + conversation_history,
            stream=True
        )

        for chunk in stream:
            delta = chunk.choices[0].delta.content
            if delta:
                full_reply += delta
                yield f"data: {json.dumps({'token': delta})}\n\n"

        conversation_history.append({
            "role": "assistant",
            "content": full_reply
        })

        yield f"data: {json.dumps({'done': True})}\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream"
    )

@app.route("/clear", methods=["POST"])
@login_required
def clear():
    conversation_history.clear()
    return jsonify({"status": "Memory cleared!"})

if __name__ == "__main__":
    app.run(debug=True, port=8080)