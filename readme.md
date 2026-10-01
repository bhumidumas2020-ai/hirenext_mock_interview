Step 1: Open PowerShell

Open PowerShell and move to the project folder:


Step 2: Create Virtual Environment

python -m venv venv

Step 3: Activate Virtual Environment

venv\Scripts\Activate.ps1

If PowerShell shows an execution-policy error, run:
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
Then run activation again:
venv\Scripts\Activate.ps1

Step 4: Install Required Libraries

pip install -r requirements.txt
or
python -m pip install -r requirements.txt

Step 5 : check java in terminal 

javac -version
java -version

if not there then install , in terminal:
winget install EclipseAdoptium.Temurin.21.JDK

Step 6: Optional Groq AI API Setup

The project works without a Groq API key because fallback questions and coding problems are available.
For live AI-generated content, set your Groq API key:
$env:GROQ_API_KEY="your_groq_api_key_here"

Step 7: Start the Flask Application

python app.py

Step 8: Open the Website

Open Google Chrome and enter:
http://127.0.0.1:5000/filename
