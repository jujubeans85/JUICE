#!/usr/bin/env python3
"""Read-only portfolio evidence -> versioned snapshot -> exception report. Stdlib only.

No GitHub write method, shell execution, checkout of audited repositories or
execution of their code. Public output is allowlisted; raw responses stay local.
"""
from __future__ import annotations

import argparse
import base64
import concurrent.futures
import datetime as dt
import hashlib
import html
import io
import json
import os
from pathlib import Path
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parent
API_ROOT = "https://api.github.com/"
LIMIT = 12 * 1024 * 1024


def utcnow():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def error_status(value):
    if not isinstance(value, dict) or "error" not in value:
        return None
    return value.get("status") or next((n for n in (401, 403, 404, 409, 422, 429, 500, 502, 503) if str(n) in str(value["error"])), 0)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None  # Never forward an Authorization header to another host.


class API:
    def __init__(self, token="", recorded_dir=None):
        self.token = token
        self.recorded = None
        self.opener = urllib.request.build_opener(NoRedirect)
        if recorded_dir:
            self.recorded = {}
            for path in sorted(Path(recorded_dir).glob("*.json")):
                self.recorded.update(json.loads(path.read_text()))

    def get(self, path):
        if path.startswith("/") or "://" in path or ".." in path.split("?")[0].split("/"):
            raise ValueError("Only relative GitHub API paths are accepted")
        if self.recorded is not None:
            if path in self.recorded:
                return self.recorded[path]
            # Connector capture pinned a default-branch tree/content to the same
            # verified branch head. This fallback is fixture-only, never live.
            alias = re.sub(r"/git/trees/[0-9a-f]{40}(?=\?)", "/git/trees/main", path)
            alias = re.sub(r"([?&]ref=)[0-9a-f]{40}(?=&|$)", r"\g<1>main", alias)
            return self.recorded.get(alias, {"error": "Not captured", "status": 0})
        req = urllib.request.Request(API_ROOT + path, method="GET", headers={
            "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "JUICE-read-only-maintenance/1",
            **({"Authorization": "Bearer " + self.token} if self.token else {}),
        })
        for attempt in range(3):
            try:
                with self.opener.open(req, timeout=30) as response:
                    raw = response.read(LIMIT + 1)
                    if len(raw) > LIMIT:
                        return {"error": "Response exceeds audit bound", "status": 0}
                    return json.loads(raw)
            except urllib.error.HTTPError as exc:
                if exc.code in (429, 500, 502, 503, 504) and attempt < 2:
                    time.sleep(min(15, max(1, int(exc.headers.get("Retry-After", "2")))))
                    continue
                # Do not put arbitrary server bodies, credentials or URLs in logs.
                return {"error": "GitHub HTTP " + str(exc.code), "status": exc.code}
            except (OSError, ValueError) as exc:
                if attempt < 2:
                    time.sleep(1 + attempt)
                    continue
                return {"error": type(exc).__name__, "status": 0}

    def pages(self, path, key=None):
        items = []
        for page in range(1, 101):
            value = self.get(path + ("&" if "?" in path else "?") + f"per_page=100&page={page}")
            if error_status(value) is not None:
                return items, False
            batch = value.get(key) if key and isinstance(value, dict) else value
            if not isinstance(batch, list):
                return items, False
            items.extend(batch)
            if len(batch) < 100:
                return items, True
        return items, False


def text_content(value):
    if not isinstance(value, dict) or error_status(value) is not None:
        return None
    try:
        content = value.get("content", "")
        return base64.b64decode(content, validate=False).decode("utf-8") if value.get("encoding") == "base64" else content
    except (ValueError, UnicodeError):
        return None


def safe_url(value):
    try:
        p = urllib.parse.urlsplit(value or "")
        if p.scheme == "https" and p.netloc and p.username is None and p.password is None:
            return urllib.parse.urlunsplit((p.scheme, p.netloc, p.path, "", ""))
    except ValueError:
        pass
    return None


def run_view(run):
    return {k: run.get(k) for k in ("id", "name", "workflow_id", "event", "head_sha", "head_branch", "status", "conclusion", "created_at", "html_url")}


def collect_repo(api, repo, now):
    name, full = repo["name"], repo["full_name"]
    p = "repos/" + full
    branches, branches_ok = api.pages(p + "/branches")
    pulls, pulls_ok = api.pages(p + "/pulls?state=open")
    branch = repo.get("default_branch")
    head = next((b.get("commit", {}).get("sha") for b in branches if b["name"] == branch), None)
    tree = api.get(p + "/git/trees/" + (head or urllib.parse.quote(branch or "HEAD", safe="")) + "?recursive=1")
    empty = error_status(tree) == 409 and branches_ok and not branches
    tree_ok = empty or (isinstance(tree.get("tree"), list) and not tree.get("truncated"))
    files = tree.get("tree", [])
    paths = {x["path"]: x for x in files}
    workflow_states, workflow_ok = api.pages(p + "/actions/workflows", "workflows")
    runs = api.get(p + "/actions/runs?per_page=50&page=1")
    runs_ok = isinstance(runs.get("workflow_runs"), list)
    recent_runs = runs.get("workflow_runs", [])
    configs = []
    workflow_files = []
    for path in sorted(paths):
        is_workflow = bool(re.fullmatch(r"\.github/workflows/[^/]+\.ya?ml", path))
        if not is_workflow and path not in {"netlify.toml", "vercel.json", "CNAME", ".gitmodules"}:
            continue
        entry = {"path": path, "sha": paths[path]["sha"], "source_url": "https://github.com/" + full + "/blob/" + (head or branch or "HEAD") + "/" + path}
        # Historical credential gate: inventory paths and hashes, never body.
        content = None if name == "NICEDAYTODAY" else text_content(api.get(p + "/contents/" + path + "?ref=" + (head or branch or "HEAD")))
        entry["inspection"] = "withheld: credential gate" if name == "NICEDAYTODAY" else ("read" if content is not None else "unavailable")
        if is_workflow:
            entry.update({
                "scheduled": bool(re.search(r"\bcron\s*:", content or "")),
                "deployment_hint": bool(re.search(r"netlify|deploy-pages|vercel|gh-pages|pages-build", content or "", re.I)),
                "actions": sorted(set(re.findall(r"uses:\s*([^\s#]+)", content or ""))),
            })
            workflow_files.append(entry)
        else:
            entry["provider"] = {"netlify.toml": "Netlify", "vercel.json": "Vercel", "CNAME": "Pages/custom domain", ".gitmodules": "Git submodules"}[path]
            configs.append(entry)
    bs = []
    for b in branches:
        view = {"name": b["name"], "sha": b.get("commit", {}).get("sha"), "protected": b.get("protected"), "preserve": b["name"].startswith("rollback/")}
        if b["name"] != branch and not view["preserve"] and head:
            if name == "NICEDAYTODAY":
                view["comparison"] = "withheld: credential gate"
            else:
                compare = api.get(p + "/compare/" + head + "..." + view["sha"])
                view.update({"comparison": compare.get("status", "unavailable"), "ahead_by": compare.get("ahead_by"), "behind_by": compare.get("behind_by")})
        bs.append(view)
    prs = []
    for pr in pulls:
        sha = pr["head"]["sha"]
        combined = api.get(p + "/commits/" + sha + "/status")
        associated = [r for r in recent_runs if r.get("head_sha") == sha or any(x.get("number") == pr["number"] and x.get("head", {}).get("sha") == sha for x in r.get("pull_requests", []))]
        # Most recent attempt per workflow AND event. Push success must not hide
        # a failing PR merge-check run on the same source head.
        latest = {}
        for r in associated:
            key = (r.get("workflow_id"), r.get("event"))
            if key not in latest or (r.get("created_at", ""), r.get("run_attempt", 0), r.get("id", 0)) > (latest[key].get("created_at", ""), latest[key].get("run_attempt", 0), latest[key].get("id", 0)):
                latest[key] = r
        prs.append({"number": pr["number"], "title": pr["title"], "draft": pr.get("draft", False), "url": pr["html_url"], "head_sha": sha, "head_branch": pr["head"]["ref"], "base_sha": pr["base"]["sha"], "updated_at": pr.get("updated_at"), "runs": [run_view(r) for r in latest.values()],
                    "commit_statuses": {"available": isinstance(combined.get("statuses"), list), "state": combined.get("state"), "checks": [{"context": x.get("context"), "state": x.get("state"), "url": safe_url(x.get("target_url"))} for x in combined.get("statuses", [])]}})
    cutoff = dt.datetime.fromisoformat(now.replace("Z", "+00:00")) - dt.timedelta(days=90)
    pushed = repo.get("pushed_at")
    recent = bool(pushed and dt.datetime.fromisoformat(pushed.replace("Z", "+00:00")) >= cutoff)
    unique = [b for b in bs if (b.get("ahead_by") or 0) > 0]
    # Activity is observational, never a KEEP/obsolete verdict.
    activity = "open development" if prs or unique else ("recent push" if recent else "no recent push observed")
    return {
        "id": repo["id"], "name": name, "full_name": full, "url": repo["html_url"],
        "visibility": "public", "archived": repo.get("archived", False), "disabled": repo.get("disabled", False),
        "default_branch": branch, "default_sha": head, "pushed_at": pushed, "size_kb": repo.get("size"),
        "activity": activity, "empty_git_repository": empty, "branches": bs, "pull_requests": prs,
        "tree_fingerprint": digest(sorted((x["path"], x.get("mode"), x["sha"]) for x in files)) if files and tree_ok else None,
        "tracked_files": sum(x.get("type") == "blob" for x in files), "gitlinks": [x["path"] for x in files if x.get("mode") == "160000"],
        "workflow_files": workflow_files,
        "workflow_states": [{k: w.get(k) for k in ("id", "name", "path", "state")} for w in workflow_states],
        "runs": [run_view(r) for r in recent_runs], "run_window": {"inspected": len(recent_runs), "total": runs.get("total_count"), "bound": 50},
        "deployment": {"has_pages": repo.get("has_pages"), "homepage": safe_url(repo.get("homepage")), "configs": configs, "runtime": "uninspected"},
        "coverage": {"branches": branches_ok, "pull_requests": pulls_ok, "tree": tree_ok, "workflow_states": workflow_ok, "runs": runs_ok,
                     "comparisons": all(b.get("comparison") != "unavailable" for b in bs),
                     "commit_statuses": all(p["commit_statuses"]["available"] for p in prs),
                     "config_bodies": all(c["inspection"] != "unavailable" for c in configs + workflow_files)},
    }


def collect(api, policy, now, registry_file=None):
    repos, complete = api.pages("users/" + policy["owner"] + "/repos?type=owner")
    # Ignore private and foreign-owner objects even if a credential unexpectedly
    # causes the public endpoint to expose them. Never serialize raw responses.
    public = [r for r in repos if r.get("owner", {}).get("login", "").casefold() == policy["owner"].casefold() and not r.get("private", True) and r.get("visibility", "public") == "public"]
    registry_sha = None
    if registry_file:
        registry = json.loads(Path(registry_file).read_text())
    else:
        value = api.get("repos/" + policy["registry_repository"] + "/contents/" + policy["registry_path"] + "?ref=main")
        registry_sha = value.get("sha")
        content = text_content(value)
        registry = json.loads(content) if content is not None else {"repositories": [], "unavailable": True}
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        observations = list(pool.map(lambda r: collect_repo(api, r, now), public))
    return {"schema_version": 1, "captured_at": now, "owner": policy["owner"], "scope": "public GitHub; restricted coverage delegated to private monthly record",
            "enumeration_complete": complete, "restricted_repository_count": policy["restricted_repository_count"],
            "registry": {"url": "https://github.com/" + policy["registry_repository"] + "/blob/main/" + policy["registry_path"],
                         "blob_sha": registry_sha, "digest": digest(registry), "rows": len(registry.get("repositories", [])), "unavailable": registry.get("unavailable", False),
                         "public_names": sorted(r["name"] for r in registry.get("repositories", []) if r.get("name") and r.get("visibility") != "restricted")},
            "repositories": sorted(observations, key=lambda r: r["name"].casefold()), "boundaries": policy["boundaries"]}


def findings(snapshot, policy):
    result = []

    def add(fid, observation, recommendation, evidence, state="review"):
        result.append({"id": fid, "state": state, "observation": observation, "recommendation": recommendation, "evidence": evidence})

    names = {r["name"] for r in snapshot["repositories"]}
    missing = sorted(names - set(snapshot["registry"]["public_names"]))
    if missing or snapshot["registry"]["unavailable"]:
        add("GIT-001", "Registry missing observed public repositories: " + ", ".join(missing) if missing else "Registry unavailable", "Update evidence in the existing registry through review; retain earlier decisions and rollback records.", snapshot["registry"]["url"])
    if len(names) != policy["expected_public_repositories"] or not snapshot["enumeration_complete"]:
        add("AUDIT-INVENTORY", f"Observed {len(names)} public repositories; expected baseline {policy['expected_public_repositories']}. Enumeration complete: {snapshot['enumeration_complete']}.", "Reconcile additions, visibility changes or lost access; do not interpret disappearance as deletion.", "https://github.com/" + policy["owner"] + "?tab=repositories")
    gaps = {}
    for r in snapshot["repositories"]:
        for key, ok in r["coverage"].items():
            if not ok:
                gaps.setdefault(key, []).append(r["name"])
        if any((b.get("ahead_by") or 0) > 0 for b in r["branches"]):
            branches = [b["name"] for b in r["branches"] if (b.get("ahead_by") or 0) > 0]
            add("BRANCH-" + str(r["id"]), r["name"] + " has unique commits on: " + ", ".join(branches), "Preserve branch heads. Review intent and changes before any consolidation; an ahead count is not proof the feature is missing from main.", r["url"] + "/branches", "preserve")
        for pr in r["pull_requests"]:
            failed = [x for x in pr["runs"] if x["conclusion"] in {"failure", "timed_out", "action_required", "startup_failure"}]
            failed_statuses = [x for x in pr["commit_statuses"]["checks"] if x["state"] in {"failure", "error"}]
            if failed or failed_statuses:
                fid = "GIT-003" if r["name"] == "JUICE" and pr["number"] == 9 else f"PR-CI-{r['id']}-{pr['number']}"
                labels = {str(x['name']) + ' (' + str(x['event']) + ')' for x in failed} | {str(x['context']) for x in failed_statuses}
                add(fid, f"{r['name']} #{pr['number']} has failing check evidence: " + ", ".join(sorted(labels)), "Reconcile with current main and restore the failing checks before considering merge. Preserve the draft and source work.", pr["url"])
        for w in r["workflow_states"]:
            if w.get("state", "").startswith("disabled"):
                add(f"WORKFLOW-{r['id']}-{w['id']}", r["name"] + ": " + str(w.get("name")) + " is " + w["state"], "Verify intent before re-enabling; public scheduled workflows may be disabled after 60 days without activity.", r["url"] + "/actions")
    for kind, repos in sorted(gaps.items()):
        add("COVERAGE-" + kind.upper(), kind + " evidence unavailable for: " + ", ".join(sorted(repos)), "Carry the gap as unknown. Retry through supported read access; do not treat missing data as a pass.", snapshot["registry"]["url"], "uninspected")
    fingerprints = {}
    for r in snapshot["repositories"]:
        if r["tree_fingerprint"]:
            fingerprints.setdefault(r["tree_fingerprint"], []).append(r["name"])
    for fingerprint, group in fingerprints.items():
        if len(group) > 1:
            add("TREE-" + fingerprint[:12], "Identical default-tree file manifests: " + ", ".join(sorted(group)), "Review history, branches, consumers and live routes. Matching trees alone do not authorize retirement.", snapshot["registry"]["url"])
    for gate in policy["manual_gates"]:
        if gate["repository"] in names:
            add(gate["id"], gate["observation"], gate["recommendation"], gate["evidence"], "blocked")
    return sorted(result, key=lambda f: f["id"])


def reconcile(current, previous, now, complete=True, resolved_ids=None):
    """Stable history; failed collection never silently resolves previous findings."""
    old = {f["id"]: f for f in previous.get("findings", [])}
    result = []
    for f in current:
        prior = old.pop(f["id"], None)
        signature = digest({k: f[k] for k in ("id", "state", "observation", "recommendation", "evidence")})
        change = "new" if not prior else ("reopened" if prior.get("state") == "resolved" else ("unchanged" if prior.get("signature") == signature else "changed"))
        result.append({**f, "signature": signature, "change": change,
                       "first_seen": prior.get("first_seen", now) if prior else now,
                       "last_changed": prior["last_changed"] if prior and change == "unchanged" else now})
    for prior in old.values():
        if prior.get("state") == "resolved":
            result.append({**prior, "change": "unchanged"})
        elif complete or prior['id'] in (resolved_ids or set()):
            result.append({**prior, "state": "resolved", "change": "resolved", "last_changed": now})
        else:
            result.append({**prior, "change": "unverified", "verification": "Current coverage incomplete; prior finding retained."})
    return sorted(result, key=lambda f: f["id"])


def repo_delta(current, previous):
    old = {r["id"]: r for r in previous.get("repositories", [])}
    changes = []
    for r in current:
        prior = old.pop(r["id"], None)
        if prior is None:
            changes.append({"repository": r["name"], "changes": ["first observation"]})
            continue
        keys = ["name", "default_sha", "archived", "disabled", "tree_fingerprint"]
        fields = [k for k in keys if r.get(k) != prior.get(k)]
        for field in ("branches", "pull_requests", "workflow_files", "workflow_states", "deployment"):
            def stable(value):
                if field == "pull_requests":
                    return [{k: x.get(k) for k in ("number", "head_sha", "draft")} for x in value]
                return value
            if digest(stable(r.get(field, []))) != digest(stable(prior.get(field, []))):
                fields.append(field)
        if fields:
            changes.append({"repository": r["name"], "changes": fields})
    for r in old.values():
        changes.append({"repository": r["name"], "changes": ["no longer observed; visibility/access/deletion unresolved"]})
    return changes


def finish(snapshot, policy, previous=None):
    previous = previous or {}
    complete = snapshot["enumeration_complete"] and all(all(r["coverage"].values()) for r in snapshot["repositories"])
    # An unrelated optional gap must not keep a repaired registry/branch/PR
    # permanently open. Resolve only where this finding's own evidence is known.
    resolved_ids = set()
    if snapshot['enumeration_complete'] and not snapshot['registry']['unavailable']:
        resolved_ids.add('GIT-001')
    for f in previous.get('findings', []):
        for r in snapshot['repositories']:
            if f.get('evidence') == r['url'] + '/branches' and r['coverage']['branches'] and r['coverage']['comparisons']:
                resolved_ids.add(f['id'])
            if f.get('evidence', '').startswith(r['url'] + '/pull/') and r['coverage']['pull_requests']:
                number = f['evidence'].rsplit('/', 1)[-1]
                pr = next((p for p in r['pull_requests'] if str(p['number']) == number), None)
                if pr is None:
                    resolved_ids.add(f['id'])
                elif r['coverage']['runs'] and pr['commit_statuses']['available']:
                    checks = pr['runs']
                    statuses = pr['commit_statuses']['checks']
                    if (checks or statuses) and all(x['conclusion'] in {'success','skipped','neutral'} for x in checks) and all(x['state']=='success' for x in statuses):
                        resolved_ids.add(f['id'])
        if f['id'].startswith('COVERAGE-'):
            key = f['id'][len('COVERAGE-'):].lower()
            if all(r['coverage'].get(key, False) for r in snapshot['repositories']):
                resolved_ids.add(f['id'])
    snapshot["findings"] = reconcile(findings(snapshot, policy), previous, snapshot["captured_at"], complete, resolved_ids)
    snapshot["changes"] = repo_delta(snapshot["repositories"], previous)
    snapshot["previous_captured_at"] = previous.get("captured_at")
    snapshot["approved_changes"] = []
    snapshot["collection_complete"] = complete
    snapshot["source_mode"] = "public GET only"
    return snapshot


def markdown(s):
    def cell(v):
        return str(v).replace("|", "\\|").replace("\n", " ")
    repos = s["repositories"]
    prs = sum(len(r["pull_requests"]) for r in repos)
    branches = sum(sum((b.get("ahead_by") or 0) > 0 for b in r["branches"]) for r in repos)
    changed = [f for f in s["findings"] if f["change"] in {"new", "changed", "reopened", "resolved"}]
    active = [f for f in s["findings"] if f["state"] != "resolved"]
    lines = ["# JUICE GitHub maintenance", "", "Captured: " + s["captured_at"], "",
             f"{len(repos)} public repositories inspected; {s['restricted_repository_count']} restricted repository tracked privately. {prs} open PRs; {branches} non-rollback branches contain commits ahead of main.", "",
             "Coverage: " + ("complete for the defined GitHub source checks" if s["collection_complete"] else "partial; gaps below are unknown, not passes") + ". Deployment/provider state and devices are not runtime-tested.", "",
             "Registry: " + s["registry"]["url"], "", "## Changes and exceptions", ""]
    if not s["previous_captured_at"]:
        lines += ["Initial baseline. First-observation findings establish history; they are not new cleanup approvals.", ""]
    elif not s["changes"] and not changed:
        lines += ["No material change since " + s["previous_captured_at"] + ".", ""]
    for c in s["changes"]:
        if s["previous_captured_at"]:
            lines.append("- " + cell(c["repository"]) + ": " + ", ".join(c["changes"]))
    for f in changed:
        lines += [f"- **{f['id']} · {f['change']} · {f['state']}** — {cell(f['observation'])} [Evidence]({safe_url(f['evidence']) or '#'})", f"  Recommendation: {cell(f['recommendation'])}"]
    lines += ["", f"## Carried findings ({len(active)} unresolved)", "", "| ID | State | Change |", "|---|---|---|"]
    for f in active:
        lines.append(f"| {f['id']} | {f['state']} | {f['change']} |")
    lines += ["", "Unchanged findings retain their original evidence and recommendation in snapshot.json; they are not regenerated tasks.", "", "## Observations", "", "| Repository | Activity evidence | Main | PRs | Unique branches | Deploy evidence |", "|---|---|---|---|---|---|"]
    for r in repos:
        hints = [c["provider"] for c in r["deployment"]["configs"]]
        if r["deployment"]["has_pages"]:
            hints.append("Pages enabled")
        main_label = r['default_sha'][:12] if r['default_sha'] else ('empty' if r['empty_git_repository'] else 'unknown')
        lines.append(f"| [{cell(r['name'])}]({r['url']}) | {r['activity']} | {main_label} | {len(r['pull_requests'])} | {sum((b.get('ahead_by') or 0) > 0 for b in r['branches'])} | {cell(', '.join(hints) or 'no configured provider observed')} |")
    lines += ["", "## Boundaries", ""]
    lines += ["- **" + k + "**: " + v for k, v in s["boundaries"].items()]
    lines += ["", "## Approved changes", "", "None. This report records observations and recommendations. It does not delete, archive, merge, deploy or rewrite source.", ""]
    return "\n".join(lines)


def report_html(s, md):
    # No scripts, network assets or unescaped repository content.
    e = lambda value: html.escape(str(value), quote=True)
    repos = s['repositories']
    active = [f for f in s['findings'] if f['state'] != 'resolved']
    changed = [f for f in s['findings'] if f['change'] in {'new', 'changed', 'reopened', 'resolved'}]
    cards = []
    for f in changed:
        cards.append(f'<article><small>{e(f["id"])} · {e(f["change"])} · {e(f["state"])}</small><p>{e(f["observation"])}</p><p><b>Recommendation:</b> {e(f["recommendation"])}</p><a href="{e(safe_url(f["evidence"]) or "#")}">Evidence ↗</a></article>')
    carried = ''.join(f'<details><summary>{e(f["id"])} · {e(f["state"])} · {e(f["change"])}</summary><p>{e(f["observation"])}</p><p>{e(f["recommendation"])}</p><p>First seen {e(f["first_seen"])}</p></details>' for f in active)
    rows = []
    for r in repos:
        branches = ''.join(f'<li>{e(b["name"])} · ahead {e(b.get("ahead_by", "?"))} / behind {e(b.get("behind_by", "?"))}</li>' for b in r['branches'] if (b.get('ahead_by') or 0) > 0)
        prs = ''.join(f'<li><a href="{e(safe_url(p["url"]) or "#")}">#{p["number"]} {e(p["title"])}</a> · {"draft" if p["draft"] else "open"}</li>' for p in r['pull_requests'])
        rows.append(f'<details><summary>{e(r["name"])} <small>· {e(r["activity"])} · {len(r["pull_requests"])} PRs</small></summary><p>Main: <code>{e(r["default_sha"] or "empty/unknown")}</code></p><ul>{prs}{branches}</ul><p>Deployment runtime: uninspected. Source config and workflow details are in snapshot.json.</p><a href="{e(r["url"])}">Repository ↗</a></details>')
    boundaries = ''.join(f'<li><b>{e(k.replace("_", " "))}:</b> {e(v)}</li>' for k,v in s['boundaries'].items())
    return f'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'"><title>JUICE maintenance</title>
<style>body{{font:16px/1.55 system-ui;background:#101619;color:#e5f0ec;margin:0;padding:24px}}main{{max-width:1000px;margin:auto}}h1,a{{color:#c7ef79}}h1{{font-size:clamp(28px,5vw,50px);line-height:1.1}}small,p{{overflow-wrap:anywhere}}small,.muted{{color:#aec3bd}}article,details,.stats{{background:#182326;border:1px solid #31474a;border-radius:14px;padding:18px;margin:12px 0}}summary{{cursor:pointer;font-weight:650}}code{{overflow-wrap:anywhere}}.stats{{font-size:22px}}a{{text-underline-offset:3px}}h2{{margin-top:32px}}</style>
<main><small>JUICE / MAINTENANCE / READ ONLY</small><h1>Keep the work.<br>Catch the drift.</h1><p class="muted">Captured {e(s['captured_at'])}. Public GitHub evidence; private coverage is tracked separately.</p>
<div class="stats">{len(repos)} public + {s['restricted_repository_count']} restricted · {sum(len(r['pull_requests']) for r in repos)} open PRs · {len(active)} carried findings</div>
<p><b>Coverage: {"complete for defined source checks" if s['collection_complete'] else "partial — see evidence gaps"}.</b> No approved changes. Runtime deployments and physical devices remain separate checks.</p>
<p><a href="{e(s['registry']['url'])}">Canonical registry ↗</a> · <a href="https://github.com/{e(s['owner'])}/JUICE/actions/workflows/portfolio-audit.yml">Audit history ↗</a></p>
<h2>Changes and exceptions</h2>{''.join(cards) or '<p>No new or changed findings. Existing gates remain below.</p>'}
<h2>Carried findings</h2>{carried}<h2>Repository evidence</h2>{''.join(rows)}
<h2>Integration boundaries</h2><ul>{boundaries}</ul><h2>Approved changes</h2><p>None. Observations and recommendations require their own reviewed implementation. Original files, branches, research and catalogue history stay preserved.</p></main></html>\n'''


def brief(s):
    changes = [f for f in s['findings'] if f['change'] in {'new', 'changed', 'reopened', 'resolved'}]
    unresolved = [f for f in s['findings'] if f['state'] != 'resolved']
    counts = f"{len(s['repositories'])} public repositories; {s['restricted_repository_count']} restricted tracked privately; {sum(len(r['pull_requests']) for r in s['repositories'])} open PRs."
    lines = ['# JUICE monthly maintenance', '', s['captured_at'], '', counts, '',
             'Source coverage: '+('complete for the defined checks.' if s['collection_complete'] else 'partial; unknowns remain explicit.'), '',
             f"{len(s['changes'])} repositories changed; {len(changes)} findings new/changed/resolved; {len(unresolved)} unresolved carried forward.", '']
    if s.get('previous_captured_at') and not s['changes'] and not changes:
        lines += ['No material change. Existing findings retain their previous recommendations.', '']
    else:
        priority = {'GIT-003':0, 'DEP-002':1, 'GIT-001':2, 'GIT-004':3}
        selected = sorted(changes, key=lambda f:(priority.get(f['id'],4), f['state']=='preserve',f['id']))[:3]
        lines += ['Top changes requiring review:', '']
        for f in selected:
            lines.append(f"- **{f['id']} · {f['change']}** — {f['observation']} [Evidence]({safe_url(f['evidence']) or '#'})")
    lines += ['', 'Deployment bindings/routes, private repositories, chats/projects and Mac/device state have separate evidence boundaries. No deletion, archival, merge or deployment was performed.', '', 'Full observations, recommendations, branch heads and provenance: report.html and snapshot.json in this run’s artifact.', '']
    return '\n'.join(lines)


def previous_artifact(api, repository, default_branch="main"):
    """Only trusted default-branch state artifacts; PR artifacts have another name."""
    artifacts, ok = api.pages("repos/" + repository + "/actions/artifacts?name=portfolio-state", "artifacts")
    if not ok:
        return None, "Previous artifact listing unavailable; using reviewed baseline"
    for artifact in sorted(artifacts, key=lambda a: a.get("created_at", ""), reverse=True):
        if artifact.get("expired") or artifact.get("name") != "portfolio-state" or artifact.get("workflow_run", {}).get("head_branch") != default_branch:
            continue
        path = "repos/" + repository + "/actions/artifacts/" + str(artifact["id"]) + "/zip"
        req = urllib.request.Request(API_ROOT + path, headers={"Authorization": "Bearer " + api.token, "User-Agent": "JUICE-maintenance"})
        try:
            try:
                response = api.opener.open(req, timeout=30)
            except urllib.error.HTTPError as exc:
                if exc.code != 302:
                    continue
                url = exc.headers.get("Location", "")
                if urllib.parse.urlsplit(url).scheme != "https":
                    continue
                # Explicit new request WITHOUT credentials after the API redirect.
                response = urllib.request.urlopen(urllib.request.Request(url), timeout=30)
            with response:
                raw = response.read(LIMIT + 1)
            if len(raw) > LIMIT:
                continue
            with zipfile.ZipFile(io.BytesIO(raw)) as z:
                infos = [x for x in z.infolist() if x.filename == "snapshot.json" and x.file_size <= LIMIT]
                if len(infos) != 1:
                    continue
                state = json.loads(z.read(infos[0]))
                if state.get("schema_version") == 1 and state.get("owner") == repository.split("/")[0] and isinstance(state.get("repositories"), list) and state.get("collection_complete") is True:
                    return state, "Previous default-branch artifact restored"
        except (OSError, ValueError, zipfile.BadZipFile):
            continue
    return None, "No usable previous artifact; using reviewed baseline"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--policy", type=Path, default=ROOT / "policy.json")
    parser.add_argument("--recorded-dir", type=Path, help="Replay connector evidence; never makes network requests")
    parser.add_argument("--registry-file", type=Path, help="Review a proposed canonical registry without publishing it")
    parser.add_argument("--previous", type=Path, default=ROOT / "baseline" / "snapshot.json")
    parser.add_argument("--previous-from-actions", action="store_true")
    parser.add_argument("--output", type=Path, default=ROOT / "output")
    args = parser.parse_args(argv)
    policy = json.loads(args.policy.read_text())
    api = API(os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN", ""), args.recorded_dir)
    previous = json.loads(args.previous.read_text()) if args.previous.exists() else None
    state_source = "Reviewed baseline" if previous else "First observation"
    if args.previous_from_actions:
        restored, state_source = previous_artifact(api, policy["owner"] + "/JUICE")
        previous = restored or previous
    snapshot = finish(collect(api, policy, utcnow(), args.registry_file), policy, previous)
    snapshot['source_mode'] = 'recorded connector GET responses' if args.recorded_dir else 'live public GitHub GET requests'
    snapshot["state_source"] = state_source
    md = markdown(snapshot)
    args.output.mkdir(parents=True, exist_ok=True)
    for name, body in {"snapshot.json": json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", "report.md": md, "report.html": report_html(snapshot, md), "summary.md": brief(snapshot)}.items():
        temp = args.output / (name + ".tmp")
        temp.write_text(body)
        temp.replace(args.output / name)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a") as f:
            f.write(brief(snapshot))
    if os.environ.get('GITHUB_OUTPUT'):
        with open(os.environ['GITHUB_OUTPUT'], 'a') as f:
            f.write('complete='+str(snapshot['collection_complete']).lower()+'\n')
    print(f"Audited {len(snapshot['repositories'])} public repositories; full coverage: {snapshot['collection_complete']}; output: {args.output}")
    return 0 if snapshot["enumeration_complete"] and not snapshot["registry"]["unavailable"] and all(all(r["coverage"][k] for k in ("branches", "pull_requests", "tree")) for r in snapshot["repositories"]) else 2


if __name__ == "__main__":
    raise SystemExit(main())
