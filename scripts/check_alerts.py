import subprocess
import json

gh_path = r"C:\Program Files\GitHub CLI\gh.exe"
res = subprocess.run(
    [gh_path, "api", "repos/aryansinghnagar/AnonyMus/code-scanning/alerts"],
    capture_output=True,
    text=True,
)
alerts = json.loads(res.stdout)

print("=== OPEN CODE SCANNING ALERTS ===")
for a in alerts:
    if a.get("state") == "open":
        loc = a.get("most_recent_instance", {}).get("location", {})
        msg = a.get("most_recent_instance", {}).get("message", {}).get("text", "")
        print(
            f"Alert #{a['number']} | Rule: {a['rule']['id']} | File: {loc.get('path')}:{loc.get('start_line')} | Msg: {msg}"
        )

res_dep = subprocess.run(
    [gh_path, "api", "repos/aryansinghnagar/AnonyMus/dependabot/alerts"],
    capture_output=True,
    text=True,
)
dep_alerts = json.loads(res_dep.stdout)

print("\n=== OPEN DEPENDABOT ALERTS ===")
for d in dep_alerts:
    if d.get("state") == "open":
        vuln = d.get("security_vulnerability", {})
        pkg = vuln.get("package", {}).get("name")
        adv = d.get("security_advisory", {}).get("summary")
        print(
            f"Dependabot Alert #{d['number']} | Pkg: {pkg} | Severity: {vuln.get('severity')} | Summary: {adv}"
        )
