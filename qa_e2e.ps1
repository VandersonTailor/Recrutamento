param(
    [string]$ApiBase = "http://127.0.0.1:8091/api/v1",
    [string]$Username = "recrutamento.carris",
    [string]$Password = "CHANGE_ME_STRONG_PASSWORD"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$pythonExe = "C:\Users\vanderson.pinheiro\AppData\Local\Programs\Python\Python312\python.exe"
if (-not (Test-Path $pythonExe)) {
    $pythonExe = "python"
}

$script = @'
import json
import sys
from datetime import datetime
import requests

API = sys.argv[1].rstrip("/")
USERNAME = sys.argv[2]
PASSWORD = sys.argv[3]

s = requests.Session()
report = []
ctx = {}

def check(name, fn):
    try:
        data = fn()
        report.append({"test": name, "ok": True, "data": data})
    except Exception as exc:
        report.append({"test": name, "ok": False, "error": str(exc)})

def req(method, path, expected=(200,), **kwargs):
    r = s.request(method, f"{API}{path}", timeout=45, **kwargs)
    if r.status_code not in expected:
        raise RuntimeError(f"status={r.status_code} body={r.text[:300]}")
    ctype = r.headers.get("content-type", "")
    if "application/json" in ctype:
        return r.json()
    return r.text

check("health", lambda: requests.get(API.replace("/api/v1", "/healthz"), timeout=20).json())
check("login", lambda: req("POST", "/auth/login", expected=(200,), json={"username": USERNAME, "password": PASSWORD}))
check("auth_me", lambda: req("GET", "/auth/me"))

def _resumes():
    rows = req("GET", "/resumes?limit=10")
    if not rows:
        raise RuntimeError("Sem curriculos para testar")
    ctx["resume_id"] = rows[0]["id"]
    ctx["candidate_id"] = rows[0]["candidate_id"]
    return {"count": len(rows), "resume_id": ctx["resume_id"]}
check("resumes_list", _resumes)
check("resume_detail", lambda: req("GET", f"/resumes/{ctx['resume_id']}"))
check("resume_reanalyze", lambda: req("POST", f"/resumes/{ctx['resume_id']}/reanalyze"))
check("resume_download", lambda: {"ok": bool(req("GET", f"/resumes/{ctx['resume_id']}/download"))})

def _create_job():
    suffix = datetime.now().strftime("%Y%m%d%H%M%S")
    payload = {
        "title": f"QA_AUTO_{suffix}",
        "department": "motorista",
        "description": "Vaga criada por qa_e2e.ps1",
        "requirements": "CNH D",
        "is_active": True,
    }
    job = req("POST", "/jobs", expected=(200, 201), json=payload)
    ctx["job_id"] = job["id"]
    return {"job_id": ctx["job_id"]}
check("job_create", _create_job)
check("job_ranking", lambda: req("GET", f"/jobs/{ctx['job_id']}/ranking?limit=20"))
check("job_profile_get", lambda: req("GET", f"/jobs/{ctx['job_id']}/ranking-profile"))

def _application():
    ranked = req("GET", f"/jobs/{ctx['job_id']}/ranking?limit=20")
    items = ranked.get("items", [])
    cand_id = items[0]["candidate_id"] if items else ctx.get("candidate_id")
    if not cand_id:
        return {"skipped": True, "reason": "Sem candidato elegível para criar candidatura"}
    try:
        app = req("POST", "/applications", expected=(200, 201), json={"candidate_id": cand_id, "job_id": ctx["job_id"]})
    except RuntimeError as exc:
        if "status=409" not in str(exc):
            raise
        rows = req("GET", f"/applications?job_id={ctx['job_id']}&candidate_id={cand_id}")
        if not rows:
            raise RuntimeError("Conflito sem candidatura existente")
        app = rows[0]
    ctx["application_id"] = app["id"]
    return {"application_id": ctx["application_id"]}
check("application_create_or_get", _application)

def _advance():
    if "application_id" not in ctx:
        return {"skipped": True, "reason": "Sem candidatura para avançar"}
    return req("POST", f"/applications/{ctx['application_id']}/advance")

def _talent_pool():
    if "application_id" not in ctx:
        return {"skipped": True, "reason": "Sem candidatura para mover ao banco"}
    return req("POST", f"/applications/{ctx['application_id']}/talent-pool")

def _approve():
    if "application_id" not in ctx:
        return {"skipped": True, "reason": "Sem candidatura para aprovar"}
    return req("POST", f"/applications/{ctx['application_id']}/approve")

check("application_advance", _advance)
check("application_talent_pool", _talent_pool)
check("application_approve", _approve)

check("dashboard", lambda: req("GET", "/dashboard"))
check("dashboard_diagnostics", lambda: req("GET", "/dashboard/diagnostics"))
check("processing_logs", lambda: req("GET", "/processing_logs?limit=10"))
check("audit", lambda: req("GET", "/audit?limit=20"))

def _template_flow():
    suffix = datetime.now().strftime("%H%M%S")
    tpl = req("POST", "/templates", expected=(200, 201), json={
        "channel": "email",
        "name": f"QA_TEMPLATE_{suffix}",
        "subject": "Oi {nome}",
        "body": "Corpo {nome}",
    })
    req("POST", f"/templates/{tpl['id']}/approve", json={"approved_by": "qa.script"})
    rendered = req("POST", "/templates/render", json={"subject": "Oi {nome}", "body": "Corpo {nome}", "variables": {"nome": "QA"}})
    return {"template_id": tpl["id"], "rendered": rendered}
check("templates_flow", _template_flow)

check("ingestion_queue_enqueue", lambda: req("POST", "/ingestion/scan/queue", json={"force_reanalyze": False}))

check("job_cleanup_delete", lambda: req("POST", f"/jobs/{ctx['job_id']}/delete?reason=qa_e2e_cleanup"))

passed = sum(1 for row in report if row["ok"])
failed = sum(1 for row in report if not row["ok"])

print(json.dumps({
    "api_base": API,
    "passed": passed,
    "failed": failed,
    "results": report,
}, ensure_ascii=False, indent=2))

sys.exit(1 if failed else 0)
'@

& $pythonExe -c $script $ApiBase $Username $Password
