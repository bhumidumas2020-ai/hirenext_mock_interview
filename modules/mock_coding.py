# modules/mock_coding.py
# ---------------------------------------------------------------------------
# MODULE 5 : MOCK CODING ROUND
# ---------------------------------------------------------------------------
# What this module does:
#   1. Reads the candidate's resume (Module 2) and picks the coding
#      language to practise in (Java or Python, based on which one the
#      resume mentions more; Python if neither / no resume).
#   2. Asks the AI (Groq) to invent one simple beginner-level problem +
#      input -> expected_output test cases, to be solved in THAT language.
#   3. "Run Code"    -> runs the student's code against a CUSTOM input.
#   4. "Submit Code" -> runs the code against ALL official test cases,
#      calculates a score and shows feedback.
#   5. Saves that score into modules/stats.py for the Dashboard, and
#      saves the full attempt (problem, results, submitted code) so the
#      downloadable report can include it.
#
# HOW THE CODE IS ACTUALLY RUN:
#   Python: save to a temp .py file and run it with the same interpreter.
#   Java:   save to a temp folder as <ClassName>.java, compile with
#           `javac`, then run with `java` (needs a JDK installed).
#   In both cases the test's "input" is fed as stdin and whatever is
#   printed on stdout is compared to the expected output.
#
#   IMPORTANT: this is a BATCH judge, not a live terminal. Student code
#   must NOT print prompt text before reading input, e.g. use
#   input() / sc.nextLine() with no "Enter a number:" prompt.
#
#   ERROR MESSAGES: raw tracebacks contain temp file paths. clean_error()
#   and clean_java_error() trim them to "ErrorType: message (line N)".
#
#   SECURITY NOTE: local practice use only. Never expose an endpoint like
#   this to the public internet without proper sandboxing.
# ---------------------------------------------------------------------------

import json
import re
import shutil
import subprocess
import sys
import tempfile
import os

from flask import Blueprint, render_template, request, jsonify, session

# We reuse the same Groq client/helper that Module 3 (AI Interview) already
# set up, instead of creating a second one.
from modules.ai_interview import ask_groq
from modules.resume_analyzer import get_resume_context, get_resume_text
from modules import stats

mock_coding_bp = Blueprint("mock_coding", __name__)

# Simple in-memory state, just like Module 3 does with its `state` dict.
# It remembers the current problem + test cases between requests.
coding_state = {
    "language": "python",   # "python" or "java" — set when a round starts
    "title": "",
    "problem": "",
    "sample_input": "",
    "sample_output": "",
    "test_cases": [],       # list of {"input": ..., "output": ...}
}

# Everything language-specific lives here, so adding another language
# later means adding one entry + one runner function.
LANGUAGES = {
    "python": {
        "label": "Python",
        "read_hint": "input() with NO prompt text inside it (just input(), not input(\"Enter a number: \"))",
        "print_hint": "print()",
        "starter": (
            "# Write your solution below.\n"
            "# Read input with input() — do NOT put prompt text inside input()\n"
            "# e.g. use:  num = int(input())   NOT   num = int(input(\"Enter number: \"))\n"
            "# Print ONLY your final answer with print()\n\n"
            "text = input()\n"
            "# TODO: solve the problem here\n"
        ),
    },
    "java": {
        "label": "Java",
        "read_hint": "a Scanner on System.in, e.g. sc.nextLine(), with NO prompt text printed before reading",
        "print_hint": "System.out.println()",
        "starter": (
            "import java.util.*;\n\n"
            "// Keep the class name as Main.\n"
            "// Read input with the Scanner — do NOT print any prompt text.\n"
            "// Print ONLY your final answer with System.out.println()\n"
            "public class Main {\n"
            "    public static void main(String[] args) {\n"
            "        Scanner sc = new Scanner(System.in);\n"
            "        String text = sc.nextLine();\n"
            "        // TODO: solve the problem here\n"
            "    }\n"
            "}\n"
        ),
    },
}

# Used only when the AI call fails or no Groq key is set — fulfils the
# readme's "works without a Groq key" promise for this module too.
# (Language-neutral, so it works for Python and Java.)
fallback_problem = {
    "title": "Reverse a String",
    "problem": "Read a single line of text and print it reversed.",
    "sample_input": "hello",
    "sample_output": "olleh",
    "test_cases": [
        {"input": "hello", "output": "olleh"},
        {"input": "python", "output": "nohtyp"},
    ],
}


def detect_language():
    """
    Picks the practice language from the resume: whichever of Java /
    Python is mentioned more often. Falls back to Python when there is
    no resume or neither is mentioned.
    \\b makes sure "JavaScript" is NOT counted as "Java".
    """
    text = get_resume_text()
    if not text:
        return "python"

    text = text.lower()
    counts = {
        "python": len(re.findall(r"\bpython\b", text)),
        "java": len(re.findall(r"\bjava\b", text)),
    }
    best = max(counts, key=counts.get)
    return best if counts[best] > 0 else "python"


def clean_json_response(raw_text):
    """
    Groq sometimes wraps its JSON reply in ```json ... ``` markdown fences,
    or adds stray text before/after the JSON object. This strips that off
    so json.loads() doesn't blow up.
    """
    text = raw_text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        text = match.group(0)
    return text.strip()


def clean_error(stderr):
    """
    PYTHON: turns a raw traceback into a short student-friendly message.
        SyntaxError: '(' was never closed (line 3)
    Keeps only the last line (error type + message) and the line number;
    the temp file path is dropped.
    """
    if not stderr:
        return ""

    lines = [l for l in stderr.replace("\r", "").split("\n") if l.strip()]
    if not lines:
        return ""

    last_line = lines[-1].strip()
    line_numbers = re.findall(r"line (\d+)", stderr)
    where = f" (line {line_numbers[-1]})" if line_numbers else ""
    return last_line + where


def clean_java_error(stderr):
    """
    JAVA: shortens javac compile errors and runtime exceptions.
        Compile error: ';' expected (line 5)
        java.lang.ArithmeticException: / by zero (line 7)
    """
    if not stderr:
        return ""

    text = stderr.replace("\r", "")

    # Compile error:  C:\...\Main.java:5: error: ';' expected
    match = re.search(r"\.java:(\d+): error: (.+)", text)
    if match:
        return f"Compile error: {match.group(2).strip()} (line {match.group(1)})"

    # Runtime exception:  Exception in thread "main" java.lang.X: message
    lines = [l for l in text.split("\n") if l.strip()]
    if not lines:
        return ""
    first = lines[0].replace('Exception in thread "main" ', "").strip()
    match = re.search(r"\(\w+\.java:(\d+)\)", text)
    where = f" (line {match.group(1)})" if match else ""
    return first + where


def run_python_code(code, input_text, timeout=5):
    """
    Runs Python `code` in a separate process, feeding `input_text` on
    stdin. Returns (output_text, error_text); error_text is "" on
    success and is already cleaned (no temp file paths).
    """
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as f:
        f.write(code)
        temp_path = f.name

    try:
        result = subprocess.run(
            [sys.executable, temp_path],
            input=input_text or "",
            capture_output=True,
            text=True,
            timeout=timeout,               # stop infinite loops after 5 seconds
        )
        output = result.stdout.strip()
        error = clean_error(result.stderr.strip())
        return output, error
    except subprocess.TimeoutExpired:
        return "", "Your code took too long to run (possible infinite loop)."
    finally:
        os.remove(temp_path)


def run_java_code(code, input_text, timeout=5):
    """
    Compiles then runs Java `code`. Same return shape as run_python_code:
    (output_text, error_text). Needs a JDK (javac + java) on the PATH.
    The file is named after the student's public class (default: Main),
    because Java requires the file name to match the public class name.
    """
    match = re.search(r"public\s+class\s+(\w+)", code)
    class_name = match.group(1) if match else "Main"

    folder = tempfile.mkdtemp()
    java_file = os.path.join(folder, class_name + ".java")

    try:
        with open(java_file, "w", encoding="utf-8") as f:
            f.write(code)

        # Step 1: compile
        try:
            compiled = subprocess.run(
                ["javac", java_file],
                capture_output=True,
                text=True,
                timeout=20,
            )
        except FileNotFoundError:
            return "", "Java (JDK) is not installed on this computer, so Java code can't be run."

        if compiled.returncode != 0:
            return "", clean_java_error(compiled.stderr.strip())

        # Step 2: run
        result = subprocess.run(
            ["java", "-cp", folder, class_name],
            input=input_text or "",
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        output = result.stdout.strip()
        error = clean_java_error(result.stderr.strip())
        return output, error

    except subprocess.TimeoutExpired:
        return "", "Your code took too long to run (possible infinite loop)."
    finally:
        shutil.rmtree(folder, ignore_errors=True)   # always clean up


def run_code_in_language(code, input_text, language):
    """Sends the code to the right runner for the chosen language."""
    if language == "java":
        return run_java_code(code, input_text)
    return run_python_code(code, input_text)


@mock_coding_bp.route("/mock-coding")
def mock_coding_page():
    """Shows the Mock Coding Round page (module 5's main page)."""
    return render_template("mock_coding.html", active="coding")


@mock_coding_bp.route("/api/coding/start", methods=["POST"])
def start_coding_round():
    """
    Picks the language from the resume, then asks the AI to generate ONE
    beginner coding problem + test cases for that language.
    """
    language = detect_language()
    lang = LANGUAGES[language]
    coding_state["language"] = language

    resume_context = get_resume_context()
    if resume_context:
        skill_hint = (
            "The candidate's resume shows this background:\n"
            f"{resume_context}\n"
            "Pick a problem related to a skill/tool actually mentioned above "
            f"where possible. The solution itself must be written in {lang['label']}."
        )
    else:
        skill_hint = (
            "No resume on file yet — pick any classic beginner problem. "
            f"The solution must be written in {lang['label']}."
        )

    prompt = f"""
    {skill_hint}

    Invent ONE simple beginner-level coding problem, suitable for a
    student practicing for a coding round (examples: reverse a string,
    check if a word is a palindrome, count vowels, find the largest
    number in a list, sum of digits of a number). Pick a different one
    each time, chosen randomly.

    The solution program (in {lang['label']}) should:
    - Read ONE line of input using {lang['read_hint']}
    - Print ONLY the final answer using {lang['print_hint']}, nothing else

    Reply ONLY with JSON in exactly this format, nothing else, no markdown,
    no code fences, no extra commentary:
    {{
      "title": "short title",
      "problem": "2-3 sentence problem statement",
      "sample_input": "example input",
      "sample_output": "expected output for that example",
      "test_cases": [
        {{"input": "value1", "output": "expected1"}},
        {{"input": "value2", "output": "expected2"}}
      ]
    }}
    """

    raw = ask_groq(prompt)
    data = None
    if raw:
        try:
            data = json.loads(clean_json_response(raw))
        except json.JSONDecodeError:
            data = None

    if not data:
        # No Groq key set, or the AI reply didn't parse — use the fallback
        data = fallback_problem

    coding_state["title"] = data["title"]
    coding_state["problem"] = data["problem"]
    coding_state["sample_input"] = data["sample_input"]
    coding_state["sample_output"] = data["sample_output"]
    coding_state["test_cases"] = data["test_cases"]

    return jsonify({
        "title": data["title"],
        "problem": data["problem"],
        "sample_input": data["sample_input"],
        "sample_output": data["sample_output"],
        "starter_code": lang["starter"],
        "language": lang["label"],
    })


@mock_coding_bp.route("/api/coding/run", methods=["POST"])
def run_code():
    """
    "Run Code" button — runs the student's code against whatever is in
    the CUSTOM INPUT box on the page (defaults to the sample input, but
    the student can edit or clear it). Does NOT save a score.
    """
    req = request.json or {}
    code = req.get("code", "")

    # Use the student-provided custom input if they sent one (even an
    # empty string counts as "they cleared it on purpose"). Only fall
    # back to the stored sample_input if the key is missing entirely.
    if "custom_input" in req:
        input_text = req.get("custom_input", "")
    else:
        input_text = coding_state["sample_input"]

    output, error = run_code_in_language(code, input_text, coding_state["language"])

    return jsonify({
        "output": output if output else "(no output)",
        "error": error,
    })


@mock_coding_bp.route("/api/coding/submit", methods=["POST"])
def submit_code():
    """
    "Submit Code" button — runs the student's code against EVERY official
    test case, works out a score, and records it in stats.py for the
    Dashboard. Also saves the full attempt (problem, results, submitted
    code) so the downloadable report can include the Mock Coding Round.
    """
    code = request.json.get("code", "")
    test_cases = coding_state["test_cases"]

    if not test_cases:
        return jsonify({"error": "No active question — refresh the page and try again."}), 400

    results = []
    passed_count = 0

    for case in test_cases:
        output, error = run_code_in_language(code, case["input"], coding_state["language"])
        passed = (output.strip() == str(case["output"]).strip()) and not error
        if passed:
            passed_count += 1
        results.append({
            "input": case["input"],
            "expected": case["output"],
            "got": output if output else error,
            "error": error,
            "passed": passed,
        })

    total = len(test_cases) if test_cases else 1
    score = round((passed_count / total) * 100)

    # Simple rule-based feedback (no extra AI call needed — fast & free).
    # The icon is part of each message, so the frontend adds none.
    feedback = []
    if score == 100:
        feedback.append("✅ Correct output for all test cases. Great job!")
    elif score >= 50:
        feedback.append(f"⚠️ Passed {passed_count} out of {total} test cases — good attempt.")
    else:
        feedback.append(f"❌ Only {passed_count} out of {total} test cases passed — check your logic again.")

    if any(r["error"] for r in results if not r["passed"]):
        feedback.append("⚠️ There were errors in your code — check the output details below.")
    else:
        feedback.append("✅ No runtime errors — nice, clean execution.")

    # Save this attempt's score so the Dashboard can show it
    stats.record_coding(score)

    # Save the full attempt so /report/download can show the Mock
    # Coding Round alongside the AI Interview round.
    stats.save_coding_attempt({
        "title": coding_state["title"],
        "problem": coding_state["problem"],
        "language": LANGUAGES[coding_state["language"]]["label"],
        "score": score,
        "passed_count": passed_count,
        "total": total,
        "results": results,
        "code": code,
    }, session.get("user_id"))

    return jsonify({
        "score": score,
        "passed_count": passed_count,
        "total": total,
        "results": results,
        "feedback": feedback,
    })
