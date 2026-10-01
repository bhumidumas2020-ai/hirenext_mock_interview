from pathlib import Path
from dotenv import load_dotenv

# Load the project-local .env before importing feature modules: they create
# their Groq clients from GROQ_API_KEY during import.
load_dotenv(Path(__file__).resolve().parent / ".env")

from flask import Flask
from modules.ai_interview import ai_interview_bp
from modules.answer_evaluation import answer_eval_bp
from modules.mock_coding import mock_coding_bp
from modules.dashboard import dashboard_bp
from modules.user_management import user_bp
from modules.resume_analyzer import resume_bp

app = Flask(__name__)
app.secret_key = "dev-secret-change-this"

app.register_blueprint(ai_interview_bp)
app.register_blueprint(answer_eval_bp)
app.register_blueprint(mock_coding_bp)
app.register_blueprint(dashboard_bp)
app.register_blueprint(user_bp)
app.register_blueprint(resume_bp)

if __name__ == "__main__":
    app.run(debug=True, port=5000)
