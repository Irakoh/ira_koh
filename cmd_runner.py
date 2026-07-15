#!/usr/bin/env python3
"""Git Relay command runner.

Polls cmds/pending.json in this GitHub repo every few seconds. When a new
command id shows up, runs "cmd" as a shell command and pushes the result to
cmds/result.json via the GitHub Contents API. See README.md > "Git Relay"
for the full mechanism and JSON format.
"""

import base64
import json
import os
import subprocess
import time
import urllib.error
import urllib.request

POLL_INTERVAL = 5
CMD_TIMEOUT = 120
STDOUT_TAIL = 3000

REPO = os.environ.get("GIT_RELAY_REPO", "irakoh/ira_koh")
BRANCH = os.environ.get("GIT_RELAY_BRANCH", "main")
PENDING_PATH = "cmds/pending.json"
RESULT_PATH = "cmds/result.json"

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.path.join(SCRIPT_DIR, ".cmd_runner_state")
ENV_FILE = os.path.join(SCRIPT_DIR, ".env")

API_ROOT = "https://api.github.com"


def load_token():
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        return token
    if os.path.exists(ENV_FILE):
        with open(ENV_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                if key.strip() == "GITHUB_TOKEN":
                    return value.strip().strip('"').strip("'")
    raise RuntimeError("GITHUB_TOKEN not found in environment or .env")


def _request(url, token, method="GET", body=None):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"token {token}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("User-Agent", "git-relay-cmd-runner")
    if data is not None:
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def get_file(path, token):
    url = f"{API_ROOT}/repos/{REPO}/contents/{path}?ref={BRANCH}"
    try:
        data = _request(url, token)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None, None
        raise
    content = base64.b64decode(data["content"]).decode("utf-8")
    return json.loads(content), data["sha"]


def put_file(path, token, obj, sha):
    url = f"{API_ROOT}/repos/{REPO}/contents/{path}"
    body = {
        "message": f"Git Relay: update {path}",
        "content": base64.b64encode(json.dumps(obj, indent=2).encode("utf-8")).decode("ascii"),
        "branch": BRANCH,
    }
    if sha:
        body["sha"] = sha
    return _request(url, token, method="PUT", body=body)


def read_last_cmd_id():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return f.read().strip()
    return None


def write_last_cmd_id(cmd_id):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        f.write(cmd_id)


def run_command(cmd):
    try:
        proc = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=CMD_TIMEOUT,
        )
        stdout, stderr, returncode = proc.stdout, proc.stderr, proc.returncode
    except subprocess.TimeoutExpired as e:
        stdout = e.stdout or ""
        stderr = (e.stderr or "") + f"\n[timed out after {CMD_TIMEOUT}s]"
        returncode = -1
    return stdout[-STDOUT_TAIL:], stderr[-STDOUT_TAIL:], returncode


def main():
    token = load_token()
    last_cmd_id = read_last_cmd_id()
    print(f"[git-relay] starting, repo={REPO} branch={BRANCH} last_cmd_id={last_cmd_id}")

    while True:
        try:
            pending, _ = get_file(PENDING_PATH, token)
            if pending and pending.get("id") and pending["id"] != last_cmd_id:
                cmd_id = pending["id"]
                cmd = pending.get("cmd", "")
                print(f"[git-relay] running id={cmd_id!r} cmd={cmd!r}")
                stdout, stderr, returncode = run_command(cmd)
                result = {
                    "id": cmd_id,
                    "cmd": cmd,
                    "stdout": stdout,
                    "stderr": stderr,
                    "returncode": returncode,
                    "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                }
                _, result_sha = get_file(RESULT_PATH, token)
                put_file(RESULT_PATH, token, result, result_sha)
                last_cmd_id = cmd_id
                write_last_cmd_id(last_cmd_id)
                print(f"[git-relay] done id={cmd_id!r} returncode={returncode}")
        except Exception as e:
            print(f"[git-relay] error: {e}")
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
