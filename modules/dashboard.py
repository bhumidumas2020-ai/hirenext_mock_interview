# modules/dashboard.py
# ---------------------------------------------------------------------------
# MODULE 6 : DASHBOARD
# ---------------------------------------------------------------------------
# What this module does:
#   Shows a summary page pulling together numbers from the other modules:
#     - Interviews Taken   (from Module 4, via stats.py)
#     - Coding Rounds      (from Module 5, via stats.py)
#     - Overall Score / Avg Score (calculated in stats.py)
#     - Recent Activity feed
#     - A few static "AI improvement tips" (kept simple — no AI call
#       needed just to show generic study tips)
#
# This module does NOT talk to the AI at all — it just reads whatever
# Module 4 and Module 5 have already saved into stats.py and displays it.
# ---------------------------------------------------------------------------

from flask import Blueprint, render_template, jsonify, session
from modules import stats

dashboard_bp = Blueprint("dashboard", __name__)


@dashboard_bp.route("/dashboard")
def dashboard_page():
    """Shows the Dashboard page (module 6's main page)."""
    return render_template("dashboard.html", active="dashboard")


@dashboard_bp.route("/api/dashboard")
def dashboard_data():
    """
    Returns all the numbers the dashboard page needs, as JSON.
    The webpage calls this once when it loads.
    """
    summary = stats.get_summary()
    report = stats.latest_evaluation(session.get("user_id"))

    # Static, generic tips — feel free to make these dynamic later
    # (e.g. generate them with the AI based on weak topics).
    tips = [
        "Practice a few coding problems every day to build speed.",
        "Review the topics you scored lowest on in your last interview.",
        "Speak slowly and clearly during the mock interview for a better score.",
        "Re-attempt any coding round you scored under 60% on.",
    ]

    return jsonify({
        "interviews_taken": summary["interviews_taken"],
        "coding_rounds": summary["coding_rounds"],
        "overall_score": summary["overall_score"],
        "avg_score": summary["avg_score"],
        "recent_activity": summary["recent_activity"],
        "tips": tips,
        "latest_report": report,
    })
