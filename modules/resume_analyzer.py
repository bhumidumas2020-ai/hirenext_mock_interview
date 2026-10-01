# modules/resume_analyzer.py
# ---------------------------------------------------------------------------
# MODULE 2 : RESUME ANALYSER (RAG)
# ---------------------------------------------------------------------------
# - Reads the resume uploaded in Module 1 (PDF/DOCX)
# - Splits it into small text chunks
# - RETRIEVAL: scores chunks by keyword overlap with the question, picks the
#   top matches (no vector DB — keeps this a simple college project)
# - GENERATION: sends only those retrieved chunks + the question to Groq,
#   so answers stay grounded in the actual resume, not made up
# - Same fallback philosophy as ai_interview.py: works without a Groq key too
# ---------------------------------------------------------------------------

import os
import re
import json
from flask import Blueprint, render_template, request, jsonify, session, redirect, url_for
from groq import Groq
from modules.user_management import get_current_user, UPLOAD_FOLDER

resume_bp = Blueprint("resume_analyzer", __name__)

GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None
CHUNK_SIZE = 600   # characters per chunk
TOP_K = 3          # chunks retrieved per question


def extract_text(filepath):
    ext = filepath.rsplit(".", 1)[-1].lower()
    if ext == "pdf":
        from pypdf import PdfReader
        reader = PdfReader(filepath)
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    if ext == "docx":
        import docx
        doc = docx.Document(filepath)
        return "\n".join(p.text for p in doc.paragraphs)
    return ""


def chunk_text(text):
    text = re.sub(r"\s+", " ", text).strip()
    return [text[i:i + CHUNK_SIZE] for i in range(0, len(text), CHUNK_SIZE)] or [""]


def retrieve_chunks(query, chunks, top_k=TOP_K):
    """RETRIEVAL step: keyword-overlap scoring instead of embeddings."""
    query_words = set(re.findall(r"\w+", query.lower()))
    scored = [(len(query_words & set(re.findall(r"\w+", c.lower()))), c) for c in chunks]
    scored.sort(key=lambda x: x[0], reverse=True)
    top = [c for score, c in scored[:top_k] if score > 0]
    return top or chunks[:top_k]


def ask_groq(prompt):
    if not client:
        return None
    reply = client.chat.completions.create(
        model="openai/gpt-oss-20b",
        messages=[{"role": "user", "content": prompt}],
    )
    return reply.choices[0].message.content.strip()


def get_resume_text():
    user = get_current_user()
    if not user or not user["resume_filename"]:
        return None
    filepath = os.path.join(UPLOAD_FOLDER, user["resume_filename"])
    if not os.path.exists(filepath):
        return None
    return extract_text(filepath)

def get_resume_context(max_chars=1500):
    """
    Returns a short slice of the logged-in user's resume text, for other
    modules (AI Interview, Mock Coding) to personalize their prompts.
    Returns None if no resume is available yet — callers must handle that
    and fall back to a generic question set.
    """
    text = get_resume_text()
    if not text:
        return None
    text = re.sub(r"\s+", " ", text).strip()
    return text[:max_chars]


@resume_bp.route("/resume-analyser")
def resume_analyser_page():
    if "user_id" not in session:
        return redirect(url_for("user_management.login"))
    return render_template("resume_analyzer.html", active="resume")


@resume_bp.route("/api/resume/analyze", methods=["POST"])
def analyze_resume():
    text = get_resume_text()
    if text is None:
        return jsonify({"error": "No resume found. Upload one from the Register page."}), 400

    chunks = chunk_text(text)
    context = "\n---\n".join(chunks[:6])

    prompt = f"""
    Candidate's resume content:
    {context}

    Based ONLY on this resume, reply ONLY with JSON in this exact shape:
    {{"skills": ["skill1"], "strengths": ["strength1"], "improvements": ["suggestion1"]}}
    """

    raw = ask_groq(prompt)
    if raw:
        try:
            cleaned = raw.replace("```json", "").replace("```", "").strip()
            return jsonify(json.loads(cleaned))
        except json.JSONDecodeError:
            pass

    # Fallback: no Groq key or parse failed — basic keyword scan
    common_skills = ["python", "java", "sql", "flask", "react", "machine learning",
                      "communication", "leadership", "html", "css", "javascript"]
    found = [s for s in common_skills if s in text.lower()]
    return jsonify({
        "skills": found or ["Not detected — add clearer skill keywords to your resume"],
        "strengths": ["Resume uploaded and readable."],
        "improvements": ["Set a GROQ_API_KEY for detailed AI-based analysis."]
    })


@resume_bp.route("/api/resume/ask", methods=["POST"])
def ask_about_resume():
    question = request.json.get("question", "").strip()
    if not question:
        return jsonify({"error": "Question is required."}), 400

    text = get_resume_text()
    if text is None:
        return jsonify({"error": "No resume found. Upload one first."}), 400

    chunks = chunk_text(text)
    retrieved = retrieve_chunks(question, chunks)
    context = "\n---\n".join(retrieved)

    prompt = f"""
    Answer using ONLY the resume excerpts below. If it's not in there, say so
    instead of guessing.

    Resume excerpts:
    {context}

    Question: {question}
    """

    answer = ask_groq(prompt)
    if not answer:
        answer = "AI answering needs a GROQ_API_KEY. Closest matching part of your resume:\n\n" + context[:400]

    return jsonify({"answer": answer, "sources_used": len(retrieved)})
