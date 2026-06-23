import os, re, json, datetime, pathlib
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://avaspizzakit.com","https://www.avaspizzakit.com","http://avaspizzakit.com","http://www.avaspizzakit.com"],
    allow_methods=["POST", "OPTIONS"], allow_headers=["*"],
)
EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
DATA = pathlib.Path(os.environ.get("DATA_DIR", "/data")); DATA.mkdir(parents=True, exist_ok=True)
STORE = DATA / "signups.jsonl"
EXPORT_KEY = os.environ.get("EXPORT_KEY", "")

@app.get("/")
def health():
    n = sum(1 for _ in STORE.open()) if STORE.exists() else 0
    return {"ok": True, "service": "avapizzakit-signup", "count": n}

@app.post("/signup")
async def signup(req: Request):
    try: data = await req.json()
    except Exception: data = {}
    if (data.get("company") or "").strip():        # honeypot
        return JSONResponse({"ok": True})
    email = (data.get("email") or "").strip().lower()
    if not EMAIL_RE.match(email):
        return JSONResponse({"ok": False, "error": "invalid email"}, status_code=400)
    # dedupe
    existing = set()
    if STORE.exists():
        for line in STORE.open():
            try: existing.add(json.loads(line).get("email"))
            except Exception: pass
    if email not in existing:
        with STORE.open("a") as f:
            f.write(json.dumps({"email": email, "ts": datetime.datetime.utcnow().isoformat()+"Z"})+"\n")
    return {"ok": True}

@app.get("/export")
def export(key: str = "", since: str = ""):
    if not EXPORT_KEY or key != EXPORT_KEY:
        return JSONResponse({"ok": False, "error": "unauthorized"}, status_code=401)
    rows = []
    if STORE.exists():
        for line in STORE.open():
            try:
                r = json.loads(line)
                if not since or r.get("ts","") >= since: rows.append(r)
            except Exception: pass
    return {"ok": True, "count": len(rows), "signups": rows}
