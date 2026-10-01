# modules/user_management.py
# ---------------------------------------------------------------------------
# MODULE 1 : USER REGISTRATION + RESUME UPLOAD
# ---------------------------------------------------------------------------
# - Registers a candidate (name, email, password) + resume (PDF/DOCX) in one step
# - Stores everything in a SQLite db (users.db) so it survives server restarts
#   (unlike stats.py, which is plain in-memory)
# - Login/logout via Flask session. Module 2 (Resume Analyser) reads the
#   logged-in user's resume through get_current_user() below.
# ---------------------------------------------------------------------------

import os
import sqlite3
from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

user_bp = Blueprint("user_management", __name__)

BASE_DIR = os.path.dirname(os.path.dirname(__file__))
DB_PATH = os.path.join(BASE_DIR, "users.db")
UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads", "resumes")
ALLOWED_EXTENSIONS = {"pdf", "docx"}

os.makedirs(UPLOAD_FOLDER, exist_ok=True)


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            resume_filename TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()


init_db()


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


@user_bp.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        resume = request.files.get("resume")

        if not name or not email or not password:
            flash("Name, email and password are required.")
            return redirect(url_for("user_management.register"))

        resume_filename = None
        if resume and resume.filename:
            if not allowed_file(resume.filename):
                flash("Resume must be a PDF or DOCX file.")
                return redirect(url_for("user_management.register"))
            resume_filename = f"{email.replace('@', '_at_')}_{secure_filename(resume.filename)}"
            resume.save(os.path.join(UPLOAD_FOLDER, resume_filename))

        conn = get_db()
        try:
            conn.execute(
                "INSERT INTO users (name, email, password_hash, resume_filename) VALUES (?, ?, ?, ?)",
                (name, email, generate_password_hash(password), resume_filename),
            )
            conn.commit()
        except sqlite3.IntegrityError:
            flash("An account with that email already exists.")
            return redirect(url_for("user_management.register"))
        finally:
            conn.close()

        flash("Registration successful. Please log in.")
        return redirect(url_for("user_management.login"))

    return render_template("register.html", active="register")


@user_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        conn = get_db()
        user = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        conn.close()

        if user and check_password_hash(user["password_hash"], password):
            session["user_id"] = user["id"]
            session["user_name"] = user["name"]
            return redirect(url_for("resume_analyzer.resume_analyser_page"))

        flash("Invalid email or password.")
        return redirect(url_for("user_management.login"))

    return render_template("login.html", active="login")


@user_bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("user_management.login"))


def get_current_user():
    """Other modules (e.g. Resume Analyser) import this to find out
    who's logged in and where their resume file lives."""
    if "user_id" not in session:
        return None
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE id = ?", (session["user_id"],)).fetchone()
    conn.close()
    return user
