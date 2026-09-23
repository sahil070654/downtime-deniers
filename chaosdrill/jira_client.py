import os
import requests
from requests.auth import HTTPBasicAuth

JIRA_URL = os.environ["JIRA_URL"]
JIRA_EMAIL = os.environ["JIRA_EMAIL"]
JIRA_API_TOKEN = os.environ["JIRA_API_TOKEN"]
JIRA_PROJECT_KEY = os.environ["JIRA_PROJECT_KEY"]

auth = HTTPBasicAuth(JIRA_EMAIL, JIRA_API_TOKEN)
headers = {"Accept": "application/json", "Content-Type": "application/json"}

BLOCKER_LABEL = "chaosdrill-blocker"


def _doc_text(text):
    return {
        "type": "doc",
        "version": 1,
        "content": [{"type": "paragraph", "content": [{"type": "text", "text": text}]}]
    }


def _search(jql, max_results=1):
    """Jira Cloud search; tries classic endpoint then newer /search/jql."""
    for url in (f"{JIRA_URL}/rest/api/3/search",
                f"{JIRA_URL}/rest/api/3/search/jql"):
        try:
            r = requests.get(
                url,
                params={"jql": jql, "maxResults": max_results, "fields": "key"},
                headers=headers, auth=auth, timeout=20,
            )
            if r.status_code == 200:
                return r.json().get("issues", [])
        except Exception as e:
            print(f"[Jira] search error on {url}: {e}")
    print(f"[Jira] search failed for jql: {jql}")
    return []


def find_open_blocker():
    jql = (f'project={JIRA_PROJECT_KEY} AND labels="{BLOCKER_LABEL}" '
           f'AND statusCategory != Done ORDER BY created DESC')
    issues = _search(jql, max_results=1)
    return issues[0]["key"] if issues else None


def find_open_issue_for_experiment(experiment_name):
    jql = (f'project={JIRA_PROJECT_KEY} '
           f'AND labels="{experiment_name}" AND labels="{BLOCKER_LABEL}" '
           f'AND statusCategory != Done ORDER BY created DESC')
    issues = _search(jql, max_results=1)
    return issues[0]["key"] if issues else None


def create_incident_ticket(report):
    exp = report["experiment"]
    verdict = report["verdict"]

    violations_text = "\n".join(f"- {v}" for v in verdict["violations"])
    description = (
        f"Chaos experiment '{exp}' ({report['kind']}) breached SLO thresholds.\n\n"
        f"Service: {report.get('service', 'unknown')}\n"
        f"Hypothesis: {report['hypothesis']}\n\n"
        f"Violations:\n{violations_text}\n\n"
        f"Max error rate: {verdict['max_error_rate']:.2%}\n"
        f"Max P99 latency: {verdict['max_p99_latency_seconds']:.2f}s\n"
        f"Circuit breaker opened: {verdict['circuit_breaker_opened']}\n\n"
        f"Suggested remedy: {report.get('remedy', 'N/A')}\n\n"
        f"Prometheus evidence queries:\n{report.get('prometheus_evidence', 'N/A')}\n\n"
        f"Started: {report['started_at']}\n"
        f"Finished: {report['finished_at']}"
    )

    payload = {
        "fields": {
            "project": {"key": JIRA_PROJECT_KEY},
            "summary": f"[ChaosDrill] SLO breach: {exp}",
            "description": _doc_text(description),
            "issuetype": {"name": "Task"},
            "labels": ["chaosdrill", "automated", BLOCKER_LABEL, exp]
        }
    }

    response = requests.post(f"{JIRA_URL}/rest/api/3/issue", json=payload,
                             headers=headers, auth=auth)
    if response.status_code == 201:
        key = response.json()["key"]
        print(f"[ChaosDrill] Jira ticket created: {key}")
        return key
    print(f"[ChaosDrill] Failed to create Jira ticket: {response.status_code} {response.text}")
    return None


def add_comment(ticket_key, text):
    r = requests.post(
        f"{JIRA_URL}/rest/api/3/issue/{ticket_key}/comment",
        json={"body": _doc_text(text)}, headers=headers, auth=auth
    )
    return r.status_code == 201


def attach_file(ticket_key, file_path):
    try:
        with open(file_path, "rb") as f:
            r = requests.post(
                f"{JIRA_URL}/rest/api/3/issue/{ticket_key}/attachments",
                files={"file": (os.path.basename(file_path), f)},
                headers={"X-Atlassian-Token": "no-check"},
                auth=auth, timeout=30,
            )
        if r.status_code in (200, 201):
            print(f"[Jira] Attached {os.path.basename(file_path)} to {ticket_key}")
            return True
        print(f"[Jira] attach failed: {r.status_code} {r.text}")
        return False
    except Exception as e:
        print(f"[Jira] attach error: {e}")
        return False


def transition_ticket(ticket_key, transition_name):
    r = requests.get(f"{JIRA_URL}/rest/api/3/issue/{ticket_key}/transitions",
                     headers=headers, auth=auth)
    transitions = r.json().get("transitions", [])
    target = next((t for t in transitions if t["name"].lower() == transition_name.lower()), None)
    if not target:
        print(f"[Jira] Transition '{transition_name}' unavailable. Options: {[t['name'] for t in transitions]}")
        return False
    resp = requests.post(
        f"{JIRA_URL}/rest/api/3/issue/{ticket_key}/transitions",
        json={"transition": {"id": target["id"]}}, headers=headers, auth=auth
    )
    return resp.status_code == 204


def resolve_ticket(ticket_key):
    """Try common transitions until one works."""
    for name in ("Done", "Resolve", "Resolved", "Close", "Closed"):
        if transition_ticket(ticket_key, name):
            print(f"[Jira] {ticket_key} resolved via transition '{name}'")
            return True
    return False
