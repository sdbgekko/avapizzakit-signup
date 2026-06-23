import os, re, json, datetime, pathlib
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse, HTMLResponse

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


@app.get("/export.csv", response_class=PlainTextResponse)
def export_csv(key: str = ""):
    if not EXPORT_KEY or key != EXPORT_KEY:
        return PlainTextResponse("unauthorized", status_code=401)
    out = ["email,signed_up"]
    if STORE.exists():
        for line in STORE.open():
            try:
                r = json.loads(line); out.append('%s,%s' % (r.get("email",""), r.get("ts","")))
            except Exception: pass
    return PlainTextResponse("\n".join(out) + "\n",
        headers={"Content-Disposition": "attachment; filename=avapizzakit-waitlist.csv"})

@app.get("/list", response_class=HTMLResponse)
def list_view(key: str = ""):
    if not EXPORT_KEY or key != EXPORT_KEY:
        return HTMLResponse("<h1>Not authorized</h1>", status_code=401)
    rows = []
    if STORE.exists():
        for line in STORE.open():
            try: rows.append(json.loads(line))
            except Exception: pass
    rows.sort(key=lambda r: r.get("ts",""))
    trs = "".join("<tr><td>%d</td><td>%s</td><td>%s</td></tr>" % (i+1, r.get("email",""), (r.get("ts","")[:16].replace("T"," ")+" UTC")) for i,r in enumerate(rows))
    if not trs: trs = "<tr><td colspan=3 style='text-align:center;color:#888;padding:24px'>No signups yet</td></tr>"
    plural = "" if len(rows)==1 else "s"
    tmpl = """<!doctype html><html><head><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>Ava's Pizza Kit - Waitlist</title><meta http-equiv=refresh content=60>
<style>body{font-family:-apple-system,system-ui,sans-serif;background:#FBF8F1;color:#1C2B36;margin:0;padding:24px}
.wrap{max-width:680px;margin:0 auto}h1{font-size:22px;margin:0 0 4px}.sub{color:#7a7468;margin:0 0 20px;font-size:14px}
.dl{display:inline-block;background:#B4520F;color:#fff;text-decoration:none;padding:10px 18px;border-radius:8px;font-weight:600;margin-bottom:18px}
table{width:100PCT;border-collapse:collapse;background:#fff;border-radius:10px;overflow:hidden;box-shadow:0 1px 4px rgba(0,0,0,.08)}
th,td{text-align:left;padding:11px 14px;border-bottom:1px solid #eee;font-size:14px}th{background:#F4EEE0;font-size:12px;text-transform:uppercase;letter-spacing:.04em}
td:first-child,th:first-child{width:40px;color:#999}</style></head>
<body><div class=wrap><h1>&#127829; Ava's Pizza Kit - Waitlist</h1>
<p class=sub>__COUNT__ signup__PLURAL__ &middot; updates automatically &middot; bookmark this page</p>
<a class=dl href="/export.csv?key=__KEY__">&#11015; Download CSV</a>
<table><tr><th>#</th><th>Email</th><th>Signed up</th></tr>__ROWS__</table></div></body></html>"""
    html = (tmpl.replace("100PCT","100%").replace("__COUNT__",str(len(rows)))
                .replace("__PLURAL__",plural).replace("__KEY__",key).replace("__ROWS__",trs))
    return HTMLResponse(html)
