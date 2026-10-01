from flask import Blueprint, render_template, request, jsonify
from groq import Groq
import json
import os

from modules.resume_analyzer import get_resume_context

ai_interview_bp = Blueprint("ai_interview", __name__)
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None

# Only used if no resume has been uploaded yet — keeps the interview
# working for a brand-new user too.
fallback_skills = ["Python", "SQL", "Machine Learning", "Communication"]

state = {"questions": [], "answers": [], "current": 0}


def ask_groq(prompt, temperature=None):
    if not client:
        return None
    kwargs = {}
    if temperature is not None:
        kwargs["temperature"] = temperature
    reply = client.chat.completions.create(
        model="openai/gpt-oss-20b",
        messages=[{"role": "user", "content": prompt}],
        **kwargs,
    )
    text = reply.choices[0].message.content
    return text.replace("```json", "").replace("```", "").strip()


@ai_interview_bp.route("/ai-interview")
def interview_page():
    return render_template("interview.html", active="interview")


@ai_interview_bp.route("/api/start", methods=["POST"])
def start_interview():
    resume_context = get_resume_context()

    if resume_context:
        candidate_info = f"Here is the candidate's actual resume content:\n{resume_context}"
    else:
        candidate_info = f"The candidate knows: {fallback_skills} (no resume uploaded yet)."

    prompt = f"""
    {candidate_info}

    Create 5 spoken mock-interview questions for this student/fresher
    candidate, based on the skills, projects and experience shown above.

    Rules:
    - This is a VERBAL interview, not a coding test — do not ask to "write code."
    - Base the questions on what's actually in the resume content above
      (specific projects, tools, skills mentioned) wherever possible.
    - Keep questions conceptual and explain-in-your-own-words style, appropriate
      for a fresher/entry-level candidate, not senior-level trick questions.
    - Mix: 3 easy/conceptual, 1 medium, 1 slightly challenging — nothing beyond
      fresher level.
    - Include at least 1 general/behavioral question (e.g. "tell me about a
      project you're proud of"), not only technical ones.

    Reply ONLY with a JSON list like this, nothing else:
    ["question 1", "question 2", "question 3"]
    """

    raw = ask_groq(prompt)
    questions = None
    if raw:
        try:
            questions = json.loads(raw)
        except json.JSONDecodeError:
            questions = None

    if not questions:
        # Fallback: no Groq key set, or the AI reply failed to parse
        questions = [
            "Tell me about a project you're proud of.",
            "What is the difference between a list and a tuple in Python?",
            "How would you explain SQL joins to someone new to databases?",
            "Describe a time you had to learn something new quickly for a project.",
            "What's one machine learning concept you find interesting, and why?",
        ]

    state["questions"] = questions
    state["answers"] = []
    state["current"] = 0
    return jsonify({"question": questions[0], "index": 1, "total": len(questions)})


@ai_interview_bp.route("/api/answer", methods=["POST"])
def submit_answer():
    answer_text = request.json.get("answer", "")
    q_index = state["current"]
    question = state["questions"][q_index]
    state["answers"].append({"question": question, "answer": answer_text})
    state["current"] += 1

    if state["current"] < len(state["questions"]):
        next_q = state["questions"][state["current"]]
        return jsonify({"done": False, "question": next_q,
                         "index": state["current"] + 1, "total": len(state["questions"])})
    return jsonify({"done": True})


def get_state():
    return state
