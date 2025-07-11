# ... same imports as before ...
from fastapi import FastAPI, Request, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBasic, HTTPBasicCredentials
import json
from datetime import datetime
import ollama
import smtplib
from email.message import EmailMessage
import sqlite3
import secrets
from apscheduler.schedulers.background import BackgroundScheduler
from collections import defaultdict
from fastapi.responses import JSONResponse

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["POST", "GET"],
    allow_headers=["*"],
)

security = HTTPBasic()
ADMIN_USERNAME = "Tribalconversions"
ADMIN_PASSWORD = "FnbbG@.123"

def authenticate(credentials: HTTPBasicCredentials = Depends(security)):
    if not (
        secrets.compare_digest(credentials.username, ADMIN_USERNAME) and
        secrets.compare_digest(credentials.password, ADMIN_PASSWORD)
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Basic"},
        )

DB_PATH = "leads.db"

def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS leads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                name TEXT,
                email TEXT,
                phone TEXT,
                budget TEXT,
                timeline TEXT,
                interest TEXT,
                property_type TEXT,
                down_payment TEXT,
                credit_score TEXT,
                has_agent TEXT,
                notes TEXT,
                zip TEXT,
                living_in_property TEXT,
                ownership TEXT,
                condition TEXT,
                motivation TEXT,
                score INTEGER,
                message TEXT
            )
        ''')
init_db()

def init_followup_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS followups (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                lead_email TEXT,
                followup_day INTEGER,
                sent INTEGER DEFAULT 0,
                message TEXT
            )
        ''')
init_followup_db()

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
- Has Agent: {data.get("has_agent")}
- Notes: {data.get("notes", "N/A")}
- ZIP: {data.get("zip")}
- Living In Property: {data.get("living_in_property")}
- Ownership: {data.get("ownership")}
- Condition: {data.get("condition")}
- Motivation: {data.get("motivation")}

Give a motivation score between 0 and 100 based on how serious and qualified this lead seems. Only return the number.
"""
    try:
        response = ollama.chat(
            model='gemma:2b',
            options={"temperature": 0},
            messages=[{"role": "user", "content": prompt}]
        )
        content = response['message']['content']
        score = int(''.join(filter(str.isdigit, content)))
        return score
    except Exception as e:
        print("Gemma scoring failed. Using fallback rules.", e)
        return calculate_score(data)

def calculate_score(data):
    score = 0
    budget_map = {"<100k": 10, "100k-500k": 30, "500k+": 50}
    timeline_map = {"6+": 10, "1-3": 25, "asap": 40}
    interest_map = {"low": 10, "medium": 25, "high": 40}
    credit_score_map = {"poor": 0, "fair": 10, "good": 25, "excellent": 40}
    down_payment_map = {"<5%": 0, "5-10%": 10, "10-20%": 25, "20%+": 40}
    motivation_map = {"low": 0, "medium": 20, "high": 40}
    condition_map = {"bad": 0, "average": 10, "good": 20, "excellent": 30}
    living_map = {"yes": 10, "no": 5}

    score += budget_map.get(data.get("budget"), 0)
    score += timeline_map.get(data.get("timeline"), 0)
    score += interest_map.get(data.get("interest"), 0)
    score += credit_score_map.get(data.get("credit_score"), 0)
    score += down_payment_map.get(data.get("down_payment"), 0)
    score += motivation_map.get(data.get("motivation"), 0)
    score += condition_map.get(data.get("condition"), 0)
    score += living_map.get(data.get("living_in_property"), 0)

    if data.get("has_agent") == "no":
        score += 10

    return score

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
- ZIP: {data.get("zip")}
- Living In Property: {data.get("living_in_property")}
- Ownership: {data.get("ownership")}
- Condition: {data.get("condition")}
- Motivation: {data.get("motivation")}

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
        base_message = response['message']['content'].strip()
    except Exception as e:
        print("Gemma message generation failed.", e)
        base_message = "Thanks for reaching out! We'll be in touch with next steps shortly."

    return base_message + "\n\n🗓️ You can book a time that works for you here:\nhttps://calendly.com/tribalconversions/30min"

def send_email(to_email: str, subject: str, body: str):
    gmail_user = "tribalconversions@gmail.com"
    gmail_app_password = "htloooadpajkrxvy"

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

@app.post("/submit")
async def submit(request: Request):
    data = await request.json()
    score = gpt_score_lead(data)
    message = gpt_followup_message(data)
    timestamp = datetime.utcnow().isoformat()
    recipient_email = data.get("email")

    with sqlite3.connect(DB_PATH) as conn:
        conn.execute('''
            INSERT INTO leads (
                timestamp, name, email, phone, budget, timeline, interest, property_type,
                down_payment, credit_score, has_agent, notes, zip, living_in_property,
                ownership, condition, motivation, score, message
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            timestamp,
            data.get("name"),
            data.get("email"),
            data.get("phone"),
            data.get("budget"),
            data.get("timeline"),
            data.get("interest"),
            data.get("property_type"),
            data.get("down_payment"),
            data.get("credit_score"),
            data.get("has_agent"),
            data.get("notes"),
            data.get("zip"),
            data.get("living_in_property"),
            data.get("ownership"),
            data.get("condition"),
            data.get("motivation"),
            score,
            message
        ))

        for day in [1, 3, 7]:
            conn.execute('''
                INSERT INTO followups (lead_email, followup_day, message)
                VALUES (?, ?, ?)
            ''', (recipient_email, day, message))
        conn.commit()

    email_sent = False
    if recipient_email:
        email_sent = send_email(recipient_email, "Thanks for reaching out! Here's the next step", message)

    return {
        "message": "Lead received!",
        "score": score,
        "followup": message,
        "email_sent": email_sent
    }

@app.get("/leads")
def get_leads(credentials: HTTPBasicCredentials = Depends(authenticate)):
    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute('''
            SELECT timestamp, name, email, phone, budget, timeline, interest,
                   property_type, down_payment, credit_score, has_agent, notes,
                   zip, living_in_property, ownership, condition, motivation,
                   score, message
            FROM leads
            ORDER BY score DESC
        ''').fetchall()

    return [
        {
            "timestamp": row[0],
            "name": row[1],
            "email": row[2],
            "phone": row[3],
            "budget": row[4],
            "timeline": row[5],
            "interest": row[6],
            "property_type": row[7],
            "down_payment": row[8],
            "credit_score": row[9],
            "has_agent": row[10],
            "notes": row[11],
            "zip": row[12],
            "living_in_property": row[13],
            "ownership": row[14],
            "condition": row[15],
            "motivation": row[16],
            "score": row[17],
            "message": row[18],
        } for row in rows
    ]

def send_scheduled_followups():
    today = datetime.utcnow()
    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute('''
            SELECT id, lead_email, message, followup_day
            FROM followups
            WHERE sent = 0
        ''').fetchall()

        for row in rows:
            fid, email, message, day = row
            lead_row = conn.execute('SELECT timestamp FROM leads WHERE email = ?', (email,)).fetchone()
            if not lead_row:
                continue
            lead_time = datetime.fromisoformat(lead_row[0])
            if (today - lead_time).days >= day:
                sent = send_email(email, f"Follow-up Day {day}", message)
                if sent:
                    conn.execute('UPDATE followups SET sent = 1 WHERE id = ?', (fid,))
                    print(f"Follow-up email sent to {email} for Day {day}")

scheduler = BackgroundScheduler()
scheduler.add_job(send_scheduled_followups, 'interval', hours=24)
scheduler.start()

@app.get("/analytics/summary")
def analytics_summary(credentials: HTTPBasicCredentials = Depends(authenticate)):
    with sqlite3.connect(DB_PATH) as conn:
        total_leads = conn.execute("SELECT COUNT(*) FROM leads").fetchone()[0]
        avg_score = conn.execute("SELECT AVG(score) FROM leads").fetchone()[0] or 0
        leads_this_month = conn.execute("SELECT COUNT(*) FROM leads WHERE strftime('%Y-%m', timestamp) = strftime('%Y-%m', 'now')").fetchone()[0]

    return {
        "total_leads": total_leads,
        "average_score": round(avg_score, 1),
        "leads_this_month": leads_this_month
    }

@app.get("/analytics/timeline")
def analytics_timeline(credentials: HTTPBasicCredentials = Depends(authenticate)):
    timeline = defaultdict(int)
    with sqlite3.connect(DB_PATH) as conn:
        for row in conn.execute('SELECT timestamp FROM leads'):
            day = row[0][:10]
            timeline[day] += 1

    return JSONResponse([
        {"date": date, "count": count}
        for date, count in sorted(timeline.items(), reverse=True)[:30][::-1]
    ])
# ✅ License Verification API (Simple in-memory for now)
from pydantic import BaseModel

# Store license keys in memory for now (migrate to DB later)
licenses = {
    "client_abc": "LICENSE123",
    "client_xyz": "LICENSE456",
}

class LicenseCheckRequest(BaseModel):
    client_id: str
    license_key: str

@app.post("/verify-license")
async def verify_license(data: LicenseCheckRequest):
    expected_key = licenses.get(data.client_id)
    if expected_key and expected_key == data.license_key:
        return {"status": "valid"}
    else:
        return {"status": "invalid"}

from license_server import app as license_app
app.mount("/license", license_app)
