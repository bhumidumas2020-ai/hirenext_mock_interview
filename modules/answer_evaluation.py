from flask import Blueprint, render_template, jsonify, session
from modules.ai_interview import get_state, ask_groq
from modules import stats
import json
import re

answer_eval_bp = Blueprint("answer_evaluation", __name__)

# Each criterion has a consistent 0–100 definition included in the evaluator prompt.
CRITERIA = {
    "technical_accuracy": "Correctness and depth of relevant technical knowledge",
    "communication": "Clarity, logical structure, and directness of the explanation",
    "problem_solving": "Reasoning, trade-offs, and a sound approach to the problem",
    "relevance": "How directly the response addresses the question",
    "specificity": "Use of concrete examples, details, or evidence",
    "grammar": "Readable sentence construction and professional language",
}


@answer_eval_bp.route("/answer-evaluation")
def answer_evaluation_page():
    return render_template("evaluation.html", active="eval")


def parse_json(raw):
    """Grab the outermost { ... } block from the AI reply and parse it."""
    match = re.search(r"\{.*\}", raw.strip(), re.DOTALL)
    if not match:
        raise ValueError("No JSON found in AI reply")
    return json.loads(match.group(0))


def score_answer(question, answer_text, rubric):
    """
    Asks the AI to score ONE answer. Tries twice. Returns a dict of
    per-criterion results, or None if both attempts failed (so the
    caller can leave this answer out of the averages instead of
    counting a failed API call as a score of 0).

    NOTE: temporary debug prints below (RAW GROQ REPLY / EVAL ERROR)
    show exactly why an answer failed to score. Remove them once the
    cause is confirmed and fixed.
    """
    shape = {
        key: {"score": 0, "evidence": "...", "improvement": "..."}
        for key in CRITERIA
    }

    prompt = f"""Assess this fresher/student interview answer fairly and specifically.

IMPORTANT CONTEXT: This is a VERBAL mock interview. The answer was captured
with speech-to-text, so it has NO punctuation or capitalization and may
contain misheard words (for example "mosquito" for Mockito, "cic" for CI/CD,
"refractor" for refactor, "login" for logging, "Microsoft detector" for
microservices architecture). First work out what the candidate most likely
meant, then judge THAT.
- Do NOT lower any score for missing punctuation, capitalization, or words
  that look like speech-to-text mistakes.
- The "grammar" score should only reflect genuinely unclear phrasing, filler
  words, or unprofessional wording — not transcription noise.
- If the candidate names correct concepts or tools, give credit even if they
  don't elaborate; reserve very low technical scores for answers that are
  wrong or say nothing relevant.

Question: {question}
Answer: {answer_text}

Score each criterion from 0 to 100 using the rubric. Cite a short, exact
observation from the answer as evidence (do not invent details), and give one
specific improvement action that is NOT something the candidate already did.
Be encouraging but honest.
{rubric}

Return only JSON with this shape: {json.dumps(shape)}"""

    for attempt in range(2):   # one retry
        try:
            raw = ask_groq(prompt, temperature=0)
            print(f"RAW GROQ REPLY (attempt {attempt + 1}):", raw)
            if not raw:
                print("EVAL ERROR: ask_groq returned empty/None (no Groq key or API call failed)")
                return None   # no Groq key / service unavailable
            parsed = parse_json(raw)
            result = {}
            for key in CRITERIA:
                value = parsed[key]
                score = max(0, min(100, int(value["score"])))
                result[key] = {
                    "score": score,
                    "evidence": str(value.get("evidence", "No evidence supplied.")),
                    "improvement": str(value.get("improvement", "Review this area and practise a clearer answer.")),
                }
            return result
        except Exception as e:
            print(f"EVAL ERROR (attempt {attempt + 1}):", repr(e))
            continue
    return None


@answer_eval_bp.route("/api/evaluate", methods=["POST"])
def evaluate():
    state = get_state()
    if not state.get("answers"):
        return jsonify({"error": "Complete an interview before requesting an evaluation."}), 400

    results = []
    rubric = "\n".join(
        f"- {key}: {description}. 0 = absent/incorrect, 50 = partial, 100 = excellent."
        for key, description in CRITERIA.items()
    )

    for item in state["answers"]:
        answer_text = item.get("answer", "").strip()

        # Genuinely empty / too-short answers really do score 0.
        if len(answer_text) < 15:
            result = {key: {"score": 0, "evidence": "The response was empty or too short to assess.", "improvement": "Give a direct answer, explain your reasoning, and include a relevant example."} for key in CRITERIA}
            result.update(overall=0, question=item["question"], answer=answer_text, failed=False,
                          note="Insufficient response for a meaningful assessment.")
            results.append(result)
            continue

        scored = score_answer(item["question"], answer_text, rubric)

        if scored is None:
            # The AI call failed. Show 0s on screen, but flag it so it is
            # excluded from the averages below.
            result = {key: {"score": 0, "evidence": "A detailed assessment could not be produced for this answer.", "improvement": "Retry the evaluation when the assessment service is available."} for key in CRITERIA}
            result.update(question=item["question"], answer=answer_text, overall=0, failed=True,
                          note="Evaluation unavailable; this answer was not scored and is left out of your final score.")
        else:
            result = scored
            result.update(question=item["question"], answer=answer_text, failed=False)
            result["overall"] = round(sum(result[key]["score"] for key in CRITERIA) / len(CRITERIA))
        results.append(result)

    # Only answers that were actually scored count towards the averages.
    counted = [r for r in results if not r.get("failed")] or results
    averages = {key: round(sum(row[key]["score"] for row in counted) / len(counted)) for key in CRITERIA}
    final_score = round(sum(averages.values()) / len(averages))

    strengths = sorted(({"criterion": CRITERIA[k], "score": v} for k, v in averages.items()), key=lambda row: row["score"], reverse=True)[:3]
    improvements = sorted(({"criterion": CRITERIA[k], "score": v} for k, v in averages.items()), key=lambda row: row["score"])[:3]
    report = {"final_score": final_score, "averages": averages, "criteria": CRITERIA, "details": results,
              "strengths": strengths, "improvements": improvements,
              "unscored": sum(1 for r in results if r.get("failed")),
              "candidate": session.get("user_name", "Candidate")}
    stats.record_interview(final_score)
    stats.save_evaluation(report, session.get("user_id"))
    return jsonify(report)


@answer_eval_bp.route("/report/download")
def download_report():
    report = stats.latest_evaluation(session.get("user_id"))
    coding = stats.latest_coding_attempt(session.get("user_id"))
    if not report and not coding:
        return "No completed evaluation report is available yet.", 404
    return render_template("report_download.html", report=report, coding=coding), 200, {
        "Content-Type": "text/html; charset=utf-8",
        "Content-Disposition": "attachment; filename=hirenext-performance-report.html",
    }
