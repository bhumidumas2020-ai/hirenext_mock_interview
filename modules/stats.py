# stats.py
# ---------------------------------------------------------------------------
# This is a small "shared memory" for the whole app.
#
# Why we need it:
#   Module 5 (Mock Coding Round) and Module 4 (Answer Evaluation) each
#   produce a score. Module 6 (Dashboard) needs to show totals like
#   "Interviews Taken", "Coding Rounds", "Overall Score" etc.
#   Instead of a real database (overkill for a college mini-project),
#   we just keep everything in a Python dictionary that lives in the
#   server's memory while it is running.
#
# NOTE: Because this is plain RAM (not a database/file), all numbers
# reset to zero every time you restart the Flask server. That is
# perfectly fine for a demo/mini-project.
# ---------------------------------------------------------------------------

from datetime import datetime
import json
import os
import sqlite3

_REPORT_DB = os.path.join(os.path.dirname(os.path.dirname(__file__)), "users.db")


def save_evaluation(report, user_id):
    """Persist the latest complete interview report for this account."""
    conn = sqlite3.connect(_REPORT_DB)
    try:
        conn.execute("CREATE TABLE IF NOT EXISTS evaluation_reports (user_key TEXT PRIMARY KEY, report_json TEXT NOT NULL, created_at TEXT NOT NULL)")
        conn.execute("INSERT INTO evaluation_reports (user_key, report_json, created_at) VALUES (?, ?, ?) ON CONFLICT(user_key) DO UPDATE SET report_json=excluded.report_json, created_at=excluded.created_at",
                     (str(user_id) if user_id is not None else "anonymous", json.dumps(report), datetime.now().isoformat(timespec="seconds")))
        conn.commit()
    finally:
        conn.close()


def latest_evaluation(user_id):
    conn = sqlite3.connect(_REPORT_DB)
    try:
        conn.execute("CREATE TABLE IF NOT EXISTS evaluation_reports (user_key TEXT PRIMARY KEY, report_json TEXT NOT NULL, created_at TEXT NOT NULL)")
        row = conn.execute("SELECT report_json, created_at FROM evaluation_reports WHERE user_key = ?",
                           (str(user_id) if user_id is not None else "anonymous",)).fetchone()
        if not row:
            return None
        report = json.loads(row[0])
        report["created_at"] = row[1]
        return report
    finally:
        conn.close()


def save_coding_attempt(attempt, user_id):
    """Persist the latest mock-coding submission for this account."""
    conn = sqlite3.connect(_REPORT_DB)
    try:
        conn.execute("CREATE TABLE IF NOT EXISTS coding_attempts (user_key TEXT PRIMARY KEY, attempt_json TEXT NOT NULL, created_at TEXT NOT NULL)")
        conn.execute("INSERT INTO coding_attempts (user_key, attempt_json, created_at) VALUES (?, ?, ?) ON CONFLICT(user_key) DO UPDATE SET attempt_json=excluded.attempt_json, created_at=excluded.created_at",
                     (str(user_id) if user_id is not None else "anonymous", json.dumps(attempt), datetime.now().isoformat(timespec="seconds")))
        conn.commit()
    finally:
        conn.close()


def latest_coding_attempt(user_id):
    conn = sqlite3.connect(_REPORT_DB)
    try:
        conn.execute("CREATE TABLE IF NOT EXISTS coding_attempts (user_key TEXT PRIMARY KEY, attempt_json TEXT NOT NULL, created_at TEXT NOT NULL)")
        row = conn.execute("SELECT attempt_json, created_at FROM coding_attempts WHERE user_key = ?",
                           (str(user_id) if user_id is not None else "anonymous",)).fetchone()
        if not row:
            return None
        attempt = json.loads(row[0])
        attempt["created_at"] = row[1]
        return attempt
    finally:
        conn.close()


# The "database" — just a dictionary sitting in memory
_stats = {
    "interviews_taken": 0,      # how many AI interviews were evaluated
    "coding_rounds": 0,         # how many coding rounds were submitted
    "interview_scores": [],     # list of % scores from Module 4
    "coding_scores": [],        # list of % scores from Module 5
    "recent_activity": [],      # last few activities, newest first
}


def record_interview(score):
    """
    Call this once, right after Module 4 (Answer Evaluation) finishes
    scoring an interview. `score` should be a number 0-100.
    """
    _stats["interviews_taken"] += 1
    _stats["interview_scores"].append(score)
    _add_activity("AI Interview evaluated", score)


def record_coding(score):
    """
    Call this once, right after Module 5 (Mock Coding Round) is submitted.
    `score` should be a number 0-100.
    """
    _stats["coding_rounds"] += 1
    _stats["coding_scores"].append(score)
    _add_activity("Coding Round submitted", score)


def _add_activity(title, score):
    """Internal helper: keeps only the 5 most recent activities."""
    _stats["recent_activity"].insert(0, {
        "title": title,
        "score": score,
        "time": datetime.now().strftime("%d %b, %I:%M %p"),
    })
    _stats["recent_activity"] = _stats["recent_activity"][:5]


def get_summary():
    """
    Used by Module 6 (Dashboard) to build the whole page in one call.
    Returns a plain dictionary of everything the dashboard needs.
    """
    all_scores = _stats["interview_scores"] + _stats["coding_scores"]
    avg_score = round(sum(all_scores) / len(all_scores)) if all_scores else 0

    # "Overall Score" = average of the most recent interview score and
    # the most recent coding score (falls back to 0 if none yet).
    latest_scores = []
    if _stats["interview_scores"]:
        latest_scores.append(_stats["interview_scores"][-1])
    if _stats["coding_scores"]:
        latest_scores.append(_stats["coding_scores"][-1])
    overall_score = round(sum(latest_scores) / len(latest_scores)) if latest_scores else 0

    return {
        "interviews_taken": _stats["interviews_taken"],
        "coding_rounds": _stats["coding_rounds"],
        "overall_score": overall_score,
        "avg_score": avg_score,
        "recent_activity": _stats["recent_activity"],
    }
