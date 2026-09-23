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
ZIP_RE = re.compile(r"^\d{5}(-\d{4})?$")
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
    # optional profile fields (frontend collects since 2026-07-03; older cached pages send email only)
    first = (data.get("firstName") or "").strip()[:80]
    last = (data.get("lastName") or "").strip()[:80]
    zip_code = (data.get("zip") or "").strip()[:10]
    if zip_code and not ZIP_RE.match(zip_code): zip_code = ""
    # dedupe by email — but a repeat signup MERGES new info into the existing row
    rows = []
    if STORE.exists():
        for line in STORE.open():
            try: rows.append(json.loads(line))
            except Exception: pass
    match = next((r for r in rows if r.get("email") == email), None)
    if match:
        updated = False
        for field, val in (("first_name", first), ("last_name", last), ("zip", zip_code)):
            if val and val != match.get(field, ""):
                match[field] = val; updated = True
        if updated:  # keep original signed-up ts; rewrite store with merged row
            with STORE.open("w") as f:
                for r in rows: f.write(json.dumps(r)+"\n")
    else:
        with STORE.open("a") as f:
            f.write(json.dumps({"email": email, "first_name": first, "last_name": last,
                                "zip": zip_code, "ts": datetime.datetime.utcnow().isoformat()+"Z"})+"\n")
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
    out = ["first_name,last_name,email,zip,signed_up"]
    if STORE.exists():
        for line in STORE.open():
            try:
                r = json.loads(line); out.append('%s,%s,%s,%s,%s' % (r.get("first_name",""), r.get("last_name",""), r.get("email",""), r.get("zip",""), r.get("ts","")))
            except Exception: pass
    return PlainTextResponse("\n".join(out) + "\n",
        headers={"Content-Disposition": "attachment; filename=avapizzakit-waitlist.csv"})

@app.post("/delete")
async def delete_signup(req: Request):
    # 2026-09-23 (Sherman): remove test signups from the list page. Key-gated; the row is
    # appended to signups.deleted.jsonl so a mistaken delete can be put back by hand.
    try: data = await req.json()
    except Exception: data = {}
    if not EXPORT_KEY or data.get("key") != EXPORT_KEY:
        return JSONResponse({"ok": False, "error": "unauthorized"}, status_code=401)
    email = (data.get("email") or "").strip().lower()
    rows, removed = [], []
    if STORE.exists():
        for line in STORE.open():
            try: r = json.loads(line)
            except Exception: continue
            (removed if r.get("email") == email else rows).append(r)
    if not removed:
        return JSONResponse({"ok": False, "error": "not found"}, status_code=404)
    with STORE.open("w") as f:
        for r in rows: f.write(json.dumps(r)+"\n")
    with (DATA / "signups.deleted.jsonl").open("a") as f:
        for r in removed:
            r["deleted_ts"] = datetime.datetime.utcnow().isoformat()+"Z"; f.write(json.dumps(r)+"\n")
    return {"ok": True, "count": len(rows)}

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
    esc = lambda s: (s or "").replace("&","&amp;").replace("<","&lt;").replace(">","&gt;").replace('"',"&quot;")
    trs = "".join("<tr data-email=\"%s\"><td>%d</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td class=act><button class=del title=\"Delete this signup\" aria-label=\"Delete\">&#128465;</button></td></tr>" % (esc(r.get("email","")), i+1, (esc(" ".join(x for x in (r.get("first_name",""), r.get("last_name","")) if x)) or "&mdash;"), esc(r.get("email","")), (esc(r.get("zip","")) or "&mdash;"), (r.get("ts","")[:16].replace("T"," ")+" UTC")) for i,r in enumerate(rows))
    if not trs: trs = "<tr><td colspan=6 style='text-align:center;color:#888;padding:24px'>No signups yet</td></tr>"
    plural = "" if len(rows)==1 else "s"
    tmpl = """<!doctype html><html><head><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>Ava's Pizza Kit - Waitlist</title>
<style>body{font-family:-apple-system,system-ui,sans-serif;background:#FBF8F1;color:#1C2B36;margin:0;padding:24px}
.wrap{max-width:760px;margin:0 auto}h1{font-size:22px;margin:0 0 4px}.sub{color:#7a7468;margin:0 0 20px;font-size:14px}
.dl{display:inline-block;background:#B4520F;color:#fff;text-decoration:none;padding:10px 18px;border-radius:8px;font-weight:600;margin-bottom:18px}
table{width:100PCT;border-collapse:collapse;background:#fff;border-radius:10px;overflow:hidden;box-shadow:0 1px 4px rgba(0,0,0,.08)}
th,td{text-align:left;padding:11px 14px;border-bottom:1px solid #eee;font-size:14px}th{background:#F4EEE0;font-size:12px;text-transform:uppercase;letter-spacing:.04em}
td:first-child,th:first-child{width:40px;color:#999}
td.act,th.act{width:44px;text-align:right;padding-right:10px}
button.del{background:none;border:0;cursor:pointer;font-size:16px;opacity:.55;padding:4px 6px;border-radius:6px}button.del:hover{opacity:1;background:#F4EEE0}
tr.confirm td{background:#FFF4EC}
.cf{display:flex;gap:8px;align-items:center;flex-wrap:wrap}.cf span{font-weight:600}
.cf button{font:inherit;font-size:13px;padding:6px 12px;border-radius:6px;border:1px solid #ccc;background:#fff;cursor:pointer}
.cf button.yes{background:#B4520F;border-color:#B4520F;color:#fff;font-weight:600}
.msg{color:#7a7468;font-size:13px;min-height:18px;margin:10px 0 0}</style></head>
<body><div class=wrap><h1>&#127829; Ava's Pizza Kit - Waitlist</h1>
<p class=sub><span id=count>__COUNT__ signup__PLURAL__</span> &middot; bookmark this page</p>
<a class=dl href="/export.csv?key=__KEY__">&#11015; Download CSV</a>
<table id=t><tr><th>#</th><th>Name</th><th>Email</th><th>ZIP</th><th>Signed up</th><th class=act></th></tr>__ROWS__</table>
<p class=msg id=msg></p></div>
<script>
(function(){
  var KEY = "__KEY__", t = document.getElementById("t"), msg = document.getElementById("msg");
  function renumber(){ var n=0; t.querySelectorAll("tr[data-email]").forEach(function(tr){ tr.cells[0].textContent = ++n; });
    document.getElementById("count").textContent = n + " signup" + (n===1?"":"s"); }
  t.addEventListener("click", function(e){
    var b = e.target.closest("button.del"); if(!b) return;
    var tr = b.closest("tr"); if(tr.classList.contains("confirm")) return;
    var email = tr.getAttribute("data-email"), name = tr.cells[1].textContent, saved = tr.cells[5].innerHTML;
    tr.classList.add("confirm");
    tr.cells[5].colSpan = 1; tr.cells[5].style.textAlign = "left"; tr.cells[5].style.width = "auto";
    tr.cells[5].innerHTML = '<div class=cf><span>Delete ' + (name === "—" ? email : name) + '?</span><button class=yes>Yes, delete</button><button class=no>Cancel</button></div>';
    tr.querySelector("button.no").onclick = function(){ tr.classList.remove("confirm"); tr.cells[5].innerHTML = saved; tr.cells[5].style.textAlign=""; tr.cells[5].style.width=""; };
    tr.querySelector("button.yes").onclick = function(){
      this.disabled = true; this.textContent = "Deleting…";
      fetch("/delete", {method:"POST", headers:{"Content-Type":"application/json"}, body: JSON.stringify({key: KEY, email: email})})
        .then(function(r){ return r.json(); })
        .then(function(d){ if(d.ok){ tr.remove(); renumber(); msg.textContent = "Deleted " + email + "."; }
                           else { msg.textContent = "Could not delete: " + (d.error || "unknown error"); tr.querySelector("button.no").click(); } })
        .catch(function(){ msg.textContent = "Could not reach the server. Reload and try again."; tr.querySelector("button.no").click(); });
    };
  });
})();
</script></body></html>"""
    html = (tmpl.replace("100PCT","100%").replace("__COUNT__",str(len(rows)))
                .replace("__PLURAL__",plural).replace("__KEY__",key).replace("__ROWS__",trs))
    return HTMLResponse(html)
