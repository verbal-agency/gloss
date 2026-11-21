#!/usr/bin/env python3
"""Night Order hook for Claude Code (Stop and SubagentStop) that sends the turn itself.

For sessions whose transcript Night Order can't read from disk: a cloud session, or any machine
other than the one Night Order runs on. It posts the hook's payload with the current turn's own
transcript entries (the prompt, the tool calls and their results, the reply), so the server can
store them as a transcript of its own. When the project's own writing changes (its README,
instructions, plans and other Markdown), it sends those files too, so cards can be written with
the project's context and in its own words.

It never gets in the way: it prints nothing (Claude Code reads a Stop hook's stdout as
decisions), gives up after a few seconds, and always exits 0. Standard library only.

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
import urllib.request

SEND_SECONDS = 8
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


def post(url, body):
    """Send the body. Returns the server's answer as a dict, or None when it didn't take it."""
    token = os.environ.get("CALLMEIF_TOKEN", "")
    curl = shutil.which("curl")
    if curl:  # curl follows the machine's proxy and certificate settings, which a cloud session relies on
        command = [curl, "-s", "-w", "\n%{http_code}", "--max-time", str(SEND_SECONDS), "-H", "Content-Type: application/json",
                   "--data-binary", "@-", url]
        if token:
            command[1:1] = ["-H", f"Authorization: Bearer {token}"]
        done = subprocess.run(command, input=body, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=SEND_SECONDS + 2)
        text, _, status = done.stdout.decode("utf-8", errors="replace").rpartition("\n")
    else:
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        with urllib.request.urlopen(urllib.request.Request(url, data=body, headers=headers), timeout=SEND_SECONDS) as answer:
            text, status = answer.read().decode("utf-8", errors="replace"), str(answer.status)
    if not status.startswith("2"):
        return None
    try:
        answer = json.loads(text)
    except ValueError:
        return {}
    return answer if isinstance(answer, dict) else {}


def main():
    url = os.environ.get("CALLMEIF_URL", "").strip().rstrip("/")
    if not url:
        return
    payload = json.load(sys.stdin)
    if not isinstance(payload, dict):
        return
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
    stamp = None
    try:
        project, stamp = the_project(payload, url)
        if project:
            payload["project"] = project
    except Exception:
        pass
    answer = post(url + "/v1/connectors/claude-code", json.dumps(payload).encode("utf-8"))
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
