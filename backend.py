from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
import json
from datetime import datetime
import ollama  # Using Gemma 2B via Ollama
import smtplib
from email.message import EmailMessage

app = FastAPI()

# Allow frontend to connect
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # For dev only — restrict in prod
    allow_methods=["POST"],
    allow_headers=["*"],
)

# --- GPT scoring using Gemma with all fields ---
def gpt_score_lead(data):
    prompt = f"""
You are an AI assistant helping qualify real estate leads.

Here is the lead's information:
- Name: {data.get("name")}
- Email: {data.get("email")}
- Phone: {data.get("phone")}
- Budget: {data.get("budget")}
- Timeline: {data.get("timeline")}
- Interest: {data.get("interest")}
- Property Type: {data.get("property_type")}
- Down Payment: {data.get("down_payment")}
- Credit Score: {data.get("credit_score")}
- Working with Agent: {data.get("has_agent")}
- Notes: {data.get("notes", "N/A")}

Give a motivation score between 0 and 100 based on how serious and qualified this lead seems. Only return the number.
"""

    try:
        response = ollama.chat(
            model='gemma:2b',
            options={"temperature": 0},  # Enforce deterministic output if supported
            messages=[{"role": "user", "content": prompt}]
        )
        content = response['message']['content']
        score = int(''.join(filter(str.isdigit, content)))
        return score
    except Exception as e:
        print("Gemma scoring failed. Using fallback rules.", e)
        return calculate_score(data)

# --- Fallback deterministic rules-based scoring ---
def calculate_score(data):
    score = 0

    budget_map = {
        "<100k": 10,
        "100k-500k": 30,
        "500k+": 50
    }
    timeline_map = {
        "6+": 10,
        "1-3": 25,
        "asap": 40
    }
    interest_map = {
        "low": 10,
        "medium": 25,
        "high": 40
    }
    credit_score_map = {
        "poor": 0,
        "fair": 10,
        "good": 25,
        "excellent": 40
    }
    down_payment_map = {
        "<5%": 0,
        "5-10%": 10,
        "10-20%": 25,
        "20%+": 40
    }

    score += budget_map.get(data.get("budget"), 0)
    score += timeline_map.get(data.get("timeline"), 0)
    score += interest_map.get(data.get("interest"), 0)
    score += credit_score_map.get(data.get("credit_score"), 0)
    score += down_payment_map.get(data.get("down_payment"), 0)

    if data.get("has_agent") == "no":
        score += 10  # bonus if they’re not locked in with another agent

    return score

# --- GPT follow-up message using Gemma ---
def gpt_followup_message(data):
    prompt = f"""
You're a real estate assistant AI. Create a personalized follow-up message to a lead based on their info.

Lead info:
- Name: {data.get("name")}
- Email: {data.get("email")}
- Phone: {data.get("phone")}
- Budget: {data.get("budget")}
- Timeline: {data.get("timeline")}
- Interest: {data.get("interest")}
- Property Type: {data.get("property_type")}
- Down Payment: {data.get("down_payment")}
- Credit Score: {data.get("credit_score")}
- Has Agent: {data.get("has_agent")}
- Notes: {data.get("notes", "N/A")}

Tone: Friendly, professional, and helpful. Mention the timeline, suggest scheduling a call, and thank them for reaching out.
Sign off as "Temple from Tribal Conversions".
Make it sound natural — like a text or email.
"""
    try:
        response = ollama.chat(
            model='gemma:2b',
            options={"temperature": 0},
            messages=[{"role": "user", "content": prompt}]
        )
        return response['message']['content'].strip()
    except Exception as e:
        print("Gemma message generation failed.", e)
        return "Thanks for reaching out! We'll be in touch with next steps shortly."

# --- NEW: Send email helper function ---
def send_email(to_email: str, subject: str, body: str):
    # Your Gmail credentials
    gmail_user = "tribalconversions@gmail.com"
    gmail_app_password = "htloooadpajkrxvy"  # no spaces

    msg = EmailMessage()
    msg["From"] = gmail_user
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.set_content(body)

    try:
        with smtplib.SMTP("smtp.gmail.com", 587) as smtp:
            smtp.starttls()
            smtp.login(gmail_user, gmail_app_password)
            smtp.send_message(msg)
        print(f"Email sent successfully to {to_email}")
        return True
    except Exception as e:
        print(f"Failed to send email to {to_email}: {e}")
        return False

# --- Submit lead + score + message + send email ---
@app.post("/submit")
async def submit(request: Request):
    data = await request.json()

    score = gpt_score_lead(data)
    message = gpt_followup_message(data)

    # Save lead info + score + message
    lead_entry = {
        "timestamp": datetime.utcnow().isoformat(),
        **data,
        "score": score,
        "message": message
    }

    with open("leads.txt", "a") as f:
        f.write(json.dumps(lead_entry) + "\n")

    # --- Send AI follow-up email ---
    recipient_email = data.get("email")
    email_subject = "Thanks for reaching out! Here's the next step"
    email_sent = False
    if recipient_email:
        email_sent = send_email(recipient_email, email_subject, message)

    return {
        "message": "Lead received!",
        "score": score,
        "followup": message,
        "email_sent": email_sent
    }

# --- Dashboard: Get sorted leads ---
@app.get("/leads")
def get_leads():
    leads = []
    try:
        with open("leads.txt", "r") as f:
            for line in f:
                leads.append(json.loads(line.strip()))
    except FileNotFoundError:
        pass

    leads.sort(key=lambda x: x.get("score", 0), reverse=True)
    return leads
