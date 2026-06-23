import os, re, smtplib, ssl, datetime
from email.message import EmailMessage
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://avaspizzakit.com", "https://www.avaspizzakit.com"],
    allow_methods=["POST", "OPTIONS"], allow_headers=["*"],
)

EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
NOTIFY = os.environ.get("NOTIFY_EMAIL", "kim.tjsitaliancafe@gmail.com")
GUSER  = os.environ.get("GMAIL_USER", "")
GPASS  = os.environ.get("GMAIL_APP_PASSWORD", "")

@app.get("/")
def health():
    return {"ok": True, "service": "avapizzakit-signup"}

@app.post("/signup")
async def signup(req: Request):
    try:
        data = await req.json()
    except Exception:
        data = {}
    if (data.get("company") or "").strip():   # honeypot -> silently accept bots
        return JSONResponse({"ok": True})
    email = (data.get("email") or "").strip()
    if not EMAIL_RE.match(email):
        return JSONResponse({"ok": False, "error": "invalid email"}, status_code=400)
    msg = EmailMessage()
    msg["Subject"] = "New Ava's Pizza Kit waitlist signup"
    msg["From"], msg["To"] = GUSER, NOTIFY
    msg["Reply-To"] = email
    ts = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    msg.set_content(f"New Ava's Pizza Kit waitlist signup:\n\n  {email}\n\nReceived: {ts}\nvia avaspizzakit.com")
    try:
        ctx = ssl.create_default_context()
        with smtplib.SMTP("smtp.gmail.com", 587, timeout=20) as s:
            s.starttls(context=ctx); s.login(GUSER, GPASS); s.send_message(msg)
    except Exception as e:
        return JSONResponse({"ok": False, "error": "send_failed"}, status_code=502)
    return {"ok": True}
