#!/usr/bin/env python3
"""Night Order hook for Claude Code (Stop, SubagentStop and UserPromptSubmit) that sends the turn itself.

For sessions whose transcript Night Order can't read from disk: a cloud session, or any machine
other than the one Night Order runs on. It posts the hook's payload with the current turn's own
transcript entries (the prompt, the tool calls and their results, the reply), so the server can
store them as a transcript of its own. When the project's own writing changes (its README,
instructions, plans and other Markdown), it sends those files too, so cards can be written with
the project's context and in its own words.

When you send a prompt, it tells the server only that the session has moved on (no text), so the
card for the turn before is put away while the next one runs. That send doesn't wait for an answer.

A send that fails is tried once more when there's time. One that still fails, and a run cut off before
it finished, are noted in a small file in the temp folder and reported with the next send that goes
out, a prompt's note included, so the server can list the turn as one that never arrived.

It never gets in the way: it prints nothing (Claude Code reads a Stop hook's stdout as
decisions), gives up within Claude Code's time limit, and always exits 0. Standard library only.

CALLMEIF_URL    the server's address, such as https://night-order.example.com. Unset: do nothing.
CALLMEIF_TOKEN  optional bearer token. In a cloud session leave it unset and store the token as
                a network secret on the environment, so the session never sees it.
"""

from __future__ import annotations

import glob
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import uuid

SEND_SECONDS = 8
HOOK_SECONDS = 17  # the whole run, inside the 20 s Claude Code gives a Stop hook
RETRY_AFTER = 5  # seconds before the one retry, when there's time for it
KEEP_FAILURES = 20  # failed sends remembered until one is reported
STALE_RUN = 60  # seconds: a run noted as under way for longer than this was cut off
TAIL_BYTES = 20_000_000  # how far back to look for the turn's start
BODY_BYTES = 4_000_000  # results are cut shorter until the body fits
RESULT_CHARS = (100_000, 20_000, 4_000)
DROPPED_BLOCKS = ("thinking", "redacted_thinking", "image")  # private or bulky, and never read by the server
FLUSH_TRIES = 5  # the reply can reach the transcript a moment after the hook fires
FLUSH_WAIT = 0.3
# The project's own writing, as the server's project cards and glossary read it.
NAMED_FILES = ("README.md", "AGENTS.md", "CLAUDE.md", "PLAN.md", "ROADMAP.md", "SITE_ROADMAP.md", "BRIEF.md", "docs/roadmap.md",
               "docs/ROADMAP.md", "docs/discovery/board.md", "framework/current-goal.yaml")
DOC_PATTERNS = ("*.md", "docs/**/*.md")
MAX_FILES = 80
FILE_CHARS = 400_000
FILES_BYTES = 3_000_000


def text_of(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n\n".join(b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text")
    return ""


def starts_turn(entry):
    """Whether a user entry is a prompt that starts a turn. Mirrors `prompt_origin` on the server."""
    if entry.get("type") != "user":
        return False
    if entry.get("turnOrigin") == "peer" or (entry.get("origin") or {}).get("kind") == "peer":
        return True
    if entry.get("isMeta"):
        return False
    if entry.get("isCompactSummary") or entry.get("turnOrigin"):
        return True
    content = (entry.get("message") or {}).get("content")
    if isinstance(content, list) and any(isinstance(b, dict) and b.get("type") == "tool_result" for b in content):
        return False
    text = text_of(content).lstrip()
    return bool(text) and not text.startswith(("<local-command", "<command-", "<bash-"))


def read(path):
    """(user and assistant entries from the end of the transcript, the session's latest title)."""
    entries, custom, generated = [], None, None
    with open(path, "rb") as fh:
        size = os.fstat(fh.fileno()).st_size
        if size > TAIL_BYTES:
            fh.seek(size - TAIL_BYTES)
            fh.readline()  # drop the partial first line
        for raw in fh:
            try:
                entry = json.loads(raw)
            except ValueError:
                continue
            if not isinstance(entry, dict):
                continue
            kind = entry.get("type")
            if kind in ("user", "assistant"):
                entries.append(entry)
            elif kind == "custom-title" and entry.get("customTitle"):
                custom = str(entry["customTitle"])
            elif kind == "ai-title" and entry.get("aiTitle"):
                generated = str(entry["aiTitle"])
    return entries, custom or generated


def has_reply(entries, reply):
    """Whether the transcript already ends with the reply the hook reported."""
    want = " ".join(reply.split())[:200]
    if not want:
        return True
    for entry in reversed(entries):
        if entry.get("type") == "assistant":
            said = " ".join(text_of((entry.get("message") or {}).get("content")).split())
            if said:
                return want in said or said in " ".join(reply.split())
    return False


def cut(text, limit):
    if len(text) <= limit:
        return text
    head = int(limit * 0.7)
    return text[:head] + f"\n… [{len(text) - limit} characters left out by the hook] …\n" + text[-(limit - head):]


def slim(entry, limit):
    """The entry without thinking and images, and with long tool results cut to `limit` characters."""
    message = entry.get("message")
    if not isinstance(message, dict) or not isinstance(message.get("content"), list):
        return entry
    blocks = []
    for block in message["content"]:
        if not isinstance(block, dict) or block.get("type") in DROPPED_BLOCKS:
            continue
        if block.get("type") == "tool_result":
            inner = block.get("content")
            if isinstance(inner, str):
                block = {**block, "content": cut(inner, limit)}
            elif isinstance(inner, list):
                block = {**block, "content": [
                    {**b, "text": cut(str(b.get("text", "")), limit)}
                    for b in inner if isinstance(b, dict) and b.get("type") == "text"
                ]}
        blocks.append(block)
    out = {k: v for k, v in entry.items() if k != "toolUseResult"}  # a second copy of the result
    out["message"] = {**message, "content": blocks}
    return out


def the_turn(payload):
    """The current turn's entries, from the prompt that started it. A subagent's whole transcript is one turn."""
    subagent = payload.get("hook_event_name") == "SubagentStop"
    path = payload.get("agent_transcript_path") if subagent else payload.get("transcript_path")
    if not path or not os.path.isfile(path):
        return None
    reply = str(payload.get("last_assistant_message") or "")
    for attempt in range(FLUSH_TRIES):
        entries, title = read(path)
        if has_reply(entries, reply):
            break
        if attempt + 1 < FLUSH_TRIES:
            time.sleep(FLUSH_WAIT)
    if not subagent:
        starts = [i for i, e in enumerate(entries) if starts_turn(e)]
        if starts:
            entries = entries[starts[-1]:]
    turn = {"title": None if subagent else title}
    if subagent:
        try:
            with open(path[: -len(".jsonl")] + ".meta.json", encoding="utf-8") as fh:
                meta = json.load(fh)
            if isinstance(meta, dict):
                turn["agent_meta"] = {k: meta.get(k) for k in ("agentType", "description") if meta.get(k)}
        except (OSError, ValueError):
            pass
    for limit in RESULT_CHARS:
        turn["entries"] = [slim(e, limit) for e in entries]
        if len(json.dumps(turn)) <= BODY_BYTES:
            break
    return turn


def project_root(payload):
    """The repo's top folder: the nearest one at or above the session's folder that has a .git."""
    start = os.environ.get("CLAUDE_PROJECT_DIR") or payload.get("cwd") or os.getcwd()
    folder = os.path.abspath(start)
    while True:
        if os.path.exists(os.path.join(folder, ".git")):
            return folder
        parent = os.path.dirname(folder)
        if parent == folder:
            return os.path.abspath(start)
        folder = parent


def project_files(root):
    """{path under the root: text} for the project's README, instructions, plans and other Markdown."""
    names = [n for n in NAMED_FILES if os.path.isfile(os.path.join(root, n))]
    for pattern in DOC_PATTERNS:
        for path in sorted(glob.glob(os.path.join(root, pattern), recursive=True)):
            name = os.path.relpath(path, root).replace(os.sep, "/")
            if os.path.isfile(path) and name not in names:
                names.append(name)
    files, size = {}, 0
    for name in names[:MAX_FILES]:
        try:
            with open(os.path.join(root, name), encoding="utf-8", errors="replace") as fh:
                text = fh.read(FILE_CHARS)
        except OSError:
            continue
        size += len(text.encode("utf-8"))
        if size > FILES_BYTES:
            break
        files[name] = text
    return files


def stamp_file(root, url):
    return os.path.join(tempfile.gettempdir(), "night-order-" + hashlib.sha256(f"{root}|{url}".encode()).hexdigest()[:16] + ".sent")


def the_project(payload, url):
    """The project's root and a hash of its writing, with the files themselves when the server hasn't
    been sent this version from this machine. Returns (what to send, the stamp to write once it arrives)."""
    root = project_root(payload)
    files = project_files(root)
    if not files:
        return None, None
    digest = hashlib.sha256(json.dumps(files, sort_keys=True).encode("utf-8")).hexdigest()[:16]
    project = {"root": root, "hash": digest}
    stamp = stamp_file(root, url)
    try:
        with open(stamp, encoding="utf-8") as fh:
            sent = fh.read().strip()
    except OSError:
        sent = ""
    if sent != digest:
        project["files"] = files
    return project, (stamp, digest)


def post(url, body, seconds=SEND_SECONDS):
    """Send the body once. Returns (the server's answer as a dict, None), or (None, why it didn't get through)."""
    token = os.environ.get("CALLMEIF_TOKEN", "")
    seconds = max(1.0, float(seconds))
    curl = shutil.which("curl")
    try:
        if curl:  # curl follows the machine's proxy and certificate settings, which a cloud session relies on
            command = [curl, "-sS", "-w", "\n%{http_code}", "--max-time", f"{seconds:.1f}", "-H", "Content-Type: application/json",
                       "--data-binary", "@-", url]
            if token:
                command[1:1] = ["-H", f"Authorization: Bearer {token}"]
            done = subprocess.run(command, input=body, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=seconds + 2)
            text, _, status = done.stdout.decode("utf-8", errors="replace").rpartition("\n")
            if done.returncode != 0:
                said = done.stderr.decode("utf-8", errors="replace").strip().splitlines()
                return None, f"curl exit {done.returncode}" + (f": {said[-1][:200]}" if said else "")
        else:
            headers = {"Content-Type": "application/json"}
            if token:
                headers["Authorization"] = f"Bearer {token}"
            try:
                with urllib.request.urlopen(urllib.request.Request(url, data=body, headers=headers), timeout=seconds) as answer:
                    text, status = answer.read().decode("utf-8", errors="replace"), str(answer.status)
            except urllib.error.HTTPError as exc:
                text, status = exc.read().decode("utf-8", errors="replace"), str(exc.code)
    except subprocess.TimeoutExpired:
        return None, f"no answer within {seconds:.0f} s"
    except Exception as exc:  # noqa: BLE001 - every way of not getting through is worth reporting
        return None, f"{type(exc).__name__}: {exc}"[:240]
    if not status.startswith("2"):
        return None, f"HTTP {status}" + (f": {text.strip()[:120]}" if text.strip() else "")
    try:
        answer = json.loads(text)
    except ValueError:
        return {}, None
    return (answer if isinstance(answer, dict) else {}), None


def send(url, payload, deadline):
    """Post the payload, and once more after a pause if that fails and there's time before `deadline` (a
    time.monotonic() value). Returns (answer, why it failed, tries). A send that got through on the second try
    says so, with why the first failed, so the server can note it."""
    answer, reason = post(url, json.dumps(payload).encode("utf-8"), min(SEND_SECONDS, deadline - time.monotonic()))
    if answer is not None:
        return answer, None, 1
    left = deadline - time.monotonic()
    wait = min(RETRY_AFTER, max(0.0, left - 4))
    if left - wait < 3:  # no time for a real second try
        return None, reason, 1
    time.sleep(wait)
    again, second = post(url, json.dumps({**payload, "hook_retried": reason}).encode("utf-8"),
                         min(SEND_SECONDS, deadline - time.monotonic()))
    if again is not None:
        return again, None, 2
    return None, f"{reason}; tried again {wait:.0f} s later: {second}", 2


# What this machine remembers between runs, per server: sends that failed and haven't been reported yet,
# and runs under way. A turn's Stop and a helper agent's can run at once, so every change is made under a lock.

def state_path(url):
    return os.path.join(tempfile.gettempdir(), "night-order-" + hashlib.sha256(url.encode()).hexdigest()[:16] + ".state.json")


def change_state(url, change):
    """Apply change(state) to the remembered state, under a lock, and return what it returns (None if the file
    can't be used: then nothing is remembered, and nothing else changes)."""
    try:
        import fcntl
    except ImportError:  # not on this system: no lock, which only matters when two runs overlap
        fcntl = None
    try:
        with open(state_path(url), "a+", encoding="utf-8") as fh:
            if fcntl:
                fcntl.flock(fh, fcntl.LOCK_EX)
            fh.seek(0)
            try:
                state = json.loads(fh.read() or "{}")
            except ValueError:
                state = {}
            if not isinstance(state, dict):
                state = {}
            result = change(state)
            fh.seek(0)
            fh.truncate()
            fh.write(json.dumps(state))
            return result
    except Exception:  # noqa: BLE001
        return None


def iso(seconds=None):
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(seconds))


def failure(what, reason, at=None, tries=0):
    """One send that didn't get through, as reported to the server."""
    return {"id": uuid.uuid4().hex, "at": at or iso(),
            "event": what.get("hook_event_name") or what.get("event"), "session_id": str(what.get("session_id") or "")[:200],
            "agent_id": str(what.get("agent_id") or "")[:200] or None, "cwd": str(what.get("cwd") or "")[:500] or None,
            "reason": str(reason)[:500], "tries": tries}


def unreported(state, now=None):
    """The failures still to report, after turning runs that never finished into failures of their own."""
    now = time.time() if now is None else now
    pending = [f for f in state.get("pending") or [] if isinstance(f, dict)]
    running = state.get("running") if isinstance(state.get("running"), dict) else {}
    for run_id, run in list(running.items()):
        started = float(run.get("started", now)) if isinstance(run, dict) else 0.0
        if now - started > STALE_RUN:
            pending.append(failure(run if isinstance(run, dict) else {}, "the hook stopped before it finished: "
                                   "cut off at Claude Code's time limit, or the machine stopped", at=iso(started)))
            del running[run_id]
    state["running"] = running
    state["pending"] = pending[-KEEP_FAILURES:]
    return list(state["pending"])


def note_prompt(url, payload):
    """Tell the server the session got a prompt: its id and nothing of what was said, plus any failed sends
    still to report. Started and left, because a UserPromptSubmit hook holds the prompt back until it returns,
    so the failures stay noted until a turn's send gets through (the server counts each once)."""
    note = {"hook_event_name": "UserPromptSubmit", "session_id": payload.get("session_id")}
    report = change_state(url, unreported)
    if report:
        note["hook_report"] = report
    curl = shutil.which("curl")
    if not curl:
        return
    command = [curl, "-s", "-o", os.devnull, "--max-time", str(SEND_SECONDS), "-H", "Content-Type: application/json",
               "--data-binary", json.dumps(note), url + "/v1/connectors/claude-code"]
    token = os.environ.get("CALLMEIF_TOKEN", "")
    if token:
        command[1:1] = ["-H", f"Authorization: Bearer {token}"]
    subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)


def main():
    deadline = time.monotonic() + HOOK_SECONDS
    url = os.environ.get("CALLMEIF_URL", "").strip().rstrip("/")
    if not url:
        return
    payload = json.load(sys.stdin)
    if not isinstance(payload, dict):
        return
    if payload.get("hook_event_name") == "UserPromptSubmit":
        note_prompt(url, payload)
        return
    run_id = uuid.uuid4().hex
    run = {"started": time.time(), "hook_event_name": payload.get("hook_event_name"), "session_id": payload.get("session_id"),
           "agent_id": payload.get("agent_id"), "cwd": payload.get("cwd")}

    def begin(state):
        report = unreported(state)
        state["running"][run_id] = run
        return report

    report = change_state(url, begin) or []
    answer, reason, tries, stamp = None, "the hook failed before sending", 0, None
    try:
        try:
            turn = the_turn(payload)
            if turn:
                payload["turn"] = turn
        except Exception:  # the payload alone still makes a card, without its tool calls
            pass
        if os.environ.get("CLAUDE_CODE_REMOTE") == "true":
            payload["remote"] = True
        if os.environ.get("CLAUDE_CODE_REMOTE_SESSION_ID"):
            payload["remote_session_id"] = os.environ["CLAUDE_CODE_REMOTE_SESSION_ID"]
        try:
            project, stamp = the_project(payload, url)
            if project:
                payload["project"] = project
        except Exception:
            pass
        if report:
            payload["hook_report"] = report
        answer, reason, tries = send(url + "/v1/connectors/claude-code", payload, deadline)
    except Exception as exc:  # noqa: BLE001 - noted below, and reported with the next send
        reason = f"the hook failed before sending: {type(exc).__name__}: {exc}"
    finally:
        def end(state):
            state.setdefault("running", {}).pop(run_id, None)
            pending = [f for f in state.get("pending") or [] if isinstance(f, dict)]
            if answer is not None:
                delivered = {f.get("id") for f in report}
                pending = [f for f in pending if f.get("id") not in delivered]
            else:
                pending.append(failure(run, reason, at=iso(run["started"]), tries=tries))
            state["pending"] = pending[-KEEP_FAILURES:]

        change_state(url, end)
    if stamp and answer is not None:
        # Remember what the server has, so the files go again only when they change, or when it lost them.
        path, digest = stamp
        if answer.get("project") == "kept":
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(digest)
        elif answer.get("project") == "missing" and os.path.exists(path):
            os.remove(path)


if __name__ == "__main__":
    try:
        main()
    except BaseException:  # never get in the session's way
        pass
    sys.exit(0)
