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

It also notes where the repo stood, and when the turn ends sends what the turn changed: each file, its
lines added and removed, and the functions, classes or sections the changes sit in, from git. Names and
counts only, never the code. Git only reads the repo: the snapshots it compares are written through a
copy of the index into a folder in the temp folder, so the repo's index, objects and refs stay as they were.

A send that fails is tried once more when there's time. One that still fails, and a run cut off before
it finished, are noted in a small file in the temp folder and reported with the next send that goes
out, a prompt's note included, so the server can list the turn as one that never arrived.

Everything it sends is gzip-compressed: the firewall in front of a hosted server (Cloudflare, on Render)
refuses a body whose text looks like an attack, such as `; curl -s` in a command the agent ran, and it
doesn't look inside a compressed one. The server needs to take compressed bodies (Night Order does from
2026-11-26).

It never gets in the way: it prints nothing (Claude Code reads a Stop hook's stdout as
decisions), gives up within Claude Code's time limit, and always exits 0. Standard library only.

CALLMEIF_URL    the server's address, such as https://night-order.example.com. Unset: do nothing.
CALLMEIF_TOKEN  optional bearer token. In a cloud session leave it unset and store the token as
                a network secret on the environment, so the session never sees it.
"""

from __future__ import annotations

import glob
import gzip
import hashlib
import json
import os
import re
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


# --- What the turn changed in the code ----------------------------------------------------------------
# When the prompt comes, the working tree is written as a git tree; when the turn ends, again; git compares
# the two and names the function or class each change sits in. Both trees go through a copy of the index
# into a folder of the hook's own, objects included, so the repo's index, objects and refs are only read.
# Changes made before the prompt aren't counted, and neither is how they were made: an edit, a script, a
# formatter. What's sent is names and counts: paths under the repo's top, function, class and section
# names, and lines added and removed. Never the code.
GIT_SECONDS = 3  # each git command; a repo too big to snapshot in this sends no code changes
PROMPT_GIT_SECONDS = 2.5  # all of it when a prompt comes, which waits for the hook
STOP_GIT_SECONDS = 4  # all of it when the turn ends, leaving time to send
MAX_CHANGED = 60  # files listed
MAX_NAMES = 12  # names per file, of each kind
SNAPSHOT_DAYS = 2  # a snapshot left from a session that ended is cleared after this
NO_FILTERS = ("-c", "filter.lfs.clean=", "-c", "filter.lfs.smudge=", "-c", "filter.lfs.process=", "-c", "filter.lfs.required=false")
# Git's own function-context rules, picked by file name. JavaScript and TypeScript have none built in, so
# they get one here; lines that open a block with a keyword aren't functions.
DRIVERS = {"py": "python", "pyi": "python", "go": "golang", "rs": "rust", "java": "java", "kt": "kotlin", "kts": "kotlin",
           "cs": "csharp", "c": "cpp", "h": "cpp", "cc": "cpp", "cpp": "cpp", "cxx": "cpp", "hpp": "cpp", "m": "objc",
           "mm": "objc", "rb": "ruby", "php": "php", "pl": "perl", "pm": "perl", "sh": "bash", "bash": "bash", "ex": "elixir",
           "exs": "elixir", "css": "css", "scss": "css", "html": "html", "md": "markdown", "markdown": "markdown",
           "js": "nightorder-js", "jsx": "nightorder-js", "mjs": "nightorder-js", "cjs": "nightorder-js",
           "ts": "nightorder-js", "tsx": "nightorder-js", "mts": "nightorder-js", "cts": "nightorder-js"}
_ID = "[A-Za-z_$][A-Za-z0-9_$]*"
JS_FUNCNAME = "\n".join([
    "!^[[:blank:]]*(if|else|for|while|do|switch|catch|try|return|with|new|await|typeof)([[:blank:](]|$)",
    "^[[:blank:]]*(((export|default|async|abstract)[[:blank:]]+)*(function[[:blank:]*]*" + _ID + "|class[[:blank:]]+" + _ID + ")"
    "|(export[[:blank:]]+)?(const|let|var)[[:blank:]]+" + _ID + "[[:blank:]]*=[[:blank:]]*(async[[:blank:]]*)?(function|\\(|" + _ID + "[[:blank:]]*=>)"
    "|((public|private|protected|static|async|get|set|readonly|override)[[:blank:]]+)*" + _ID + "[[:blank:]]*\\([^)]*\\)[[:blank:]]*(:[^{]*)?\\{).*$",
])
# A definition, read from a hunk's heading or from a line the turn added or removed: (pattern, kind).
DEFINITIONS = [
    (r"^\s*(?:async\s+)?def\s+(?:self\.)?([A-Za-z_]\w*[?!=]?)", "function"),  # Python, Ruby
    (r"^\s*(?:(?:export|default|abstract|final|sealed|data|public|private|protected|internal|static|open)\s+)*"
     r"(?:class|struct|enum|trait|interface|module|protocol|object|record)\s+([A-Za-z_$][\w$]*)", "class"),
    (r"^\s*(?:(?:export|default|async|public|private|protected|static|final|abstract)\s+)*function\s*\*?\s*([A-Za-z_$][\w$]*)", "function"),
    (r"^func\s+(?:\([^)]*\)\s*)?([A-Za-z_]\w*)", "function"),  # Go
    (r"^\s*(?:pub(?:\([^)]*\))?\s+)?(?:const\s+)?(?:async\s+)?(?:unsafe\s+)?fn\s+([A-Za-z_]\w*)", "function"),  # Rust
    (r"^\s*(?:(?:public|private|protected|internal|override|open|suspend|inline|operator)\s+)*fun\s+(?:<[^>]*>\s*)?(?:[\w.]+\.)?([A-Za-z_]\w*)", "function"),
    (r"^\s*(?:export\s+)?(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?(?:function\b|\([^)]*\)\s*(?::[^=]*)?=>|[A-Za-z_$][\w$]*\s*=>)", "function"),
    (r"^\s*(?:(?:public|private|protected|static|async|get|set|readonly|override)\s+)*([A-Za-z_$][\w$]*)\s*(?:<[^>]*>)?\s*\([^)]*\)\s*(?::[^{=;]*)?\{\s*$", "function"),
    (r"^\s*(?:(?:public|private|protected|internal|static|final|abstract|override|virtual|synchronized|async|unsafe|extern|inline|constexpr)\s+)+"
     r"[\w<>\[\],.?*& ]+?\s+[*&]*([A-Za-z_]\w*)\s*\(", "function"),  # Java, C#, C++ with a modifier
    (r"^\s*(?:function\s+)?([A-Za-z_][\w-]*)\s*\(\)\s*\{?\s*$", "function"),  # shell
]
C_LIKE = {"cpp", "csharp", "java", "objc", "kotlin", "php", "golang", "rust"}
KEYWORDS = frozenset("if elif else for foreach while do switch case catch except try return with new await typeof sizeof match when".split())
HUNK = r"^@@ -\d+(?:,(\d+))? \+\d+(?:,(\d+))? @@ ?(.*)$"


_until = [None]  # when the git work under way must be done by


def git(root, *args, env=None):
    """A git command's output, or None if it failed or took too long. It never prompts, and takes no lock it can skip."""
    limit = GIT_SECONDS if _until[0] is None else min(GIT_SECONDS, _until[0] - time.monotonic())
    if limit <= 0:
        return None
    try:
        done = subprocess.run(["git", "--no-optional-locks", "-C", root, *args], capture_output=True, encoding="utf-8",
                              errors="replace", timeout=limit, env=env, stdin=subprocess.DEVNULL)
    except (OSError, ValueError, subprocess.SubprocessError):
        return None
    return done.stdout if done.returncode == 0 else None


def repo_paths(root):
    """The repo's object folder and index file, absolute (a worktree has its own index and shares the objects)."""
    out = git(root, "rev-parse", "--path-format=absolute", "--git-path", "objects", "--git-path", "index")
    if out is None:
        out = git(root, "rev-parse", "--git-path", "objects", "--git-path", "index")
    lines = (out or "").splitlines()
    if len(lines) != 2:
        return None
    return tuple(os.path.join(root, p) for p in lines)


def snapshot_env(root, store):
    paths = repo_paths(root)
    if not paths:
        return None
    os.makedirs(os.path.join(store, "objects"), exist_ok=True)
    return dict(os.environ, GIT_INDEX_FILE=os.path.join(store, "index"), GIT_OBJECT_DIRECTORY=os.path.join(store, "objects"),
                GIT_ALTERNATE_OBJECT_DIRECTORIES=paths[0], GIT_TERMINAL_PROMPT="0"), paths[1]


def snapshot(root, store):
    """The working tree as a git tree: tracked files as they are now, and untracked ones git doesn't ignore,
    written through a copy of the index into `store`. None if it can't be done in time."""
    found = snapshot_env(root, store)
    if not found:
        return None
    env, index = found
    if os.path.isfile(index):
        shutil.copyfile(index, env["GIT_INDEX_FILE"])  # its file stamps spare git re-reading unchanged files
    elif os.path.exists(env["GIT_INDEX_FILE"]):
        os.remove(env["GIT_INDEX_FILE"])
    if git(root, *NO_FILTERS, "add", "-A", env=env) is None:
        return None
    tree = (git(root, "write-tree", env=env) or "").strip()
    return tree or None


def snapshot_store(session):
    return os.path.join(tempfile.gettempdir(), "night-order-snapshots", hashlib.sha256(str(session).encode()).hexdigest()[:16])


def start_snapshot(payload):
    """When a prompt comes: where the repo stood, to compare the turn's end with. None outside a git repo."""
    _until[0] = time.monotonic() + PROMPT_GIT_SECONDS
    root = (git(payload.get("cwd") or os.getcwd(), "rev-parse", "--show-toplevel") or "").strip()
    if not root:
        return None
    store = snapshot_store(payload.get("session_id"))
    shutil.rmtree(store, ignore_errors=True)  # the session's last snapshot: its turn is over
    tree = snapshot(root, store)
    if not tree:
        shutil.rmtree(store, ignore_errors=True)
        return None
    return {"root": root, "tree": tree, "store": store, "at": time.time()}


def keep_snapshot(state, session, start):
    """Note the session's snapshot, and clear those of sessions that have gone quiet."""
    snapshots = state.get("snapshots") if isinstance(state.get("snapshots"), dict) else {}
    for key, old in list(snapshots.items()):
        if not isinstance(old, dict) or time.time() - float(old.get("at") or 0) > SNAPSHOT_DAYS * 86400:
            if isinstance(old, dict) and old.get("store"):
                shutil.rmtree(old["store"], ignore_errors=True)
            del snapshots[key]
    if start:
        snapshots[str(session)] = start
    else:
        old = snapshots.pop(str(session), None)
        if isinstance(old, dict) and old.get("store"):
            shutil.rmtree(old["store"], ignore_errors=True)
    state["snapshots"] = snapshots


def _name(line, driver, heading=False):
    """(name as shown, kind) for a line that defines something, or None."""
    text = line.strip()
    if driver == "markdown":
        found = re.match(r"^#{1,6}\s+(.+?)\s*#*$", text)
        return (found.group(1)[:80], "section") if found else None
    for pattern, kind in DEFINITIONS:
        found = re.match(pattern, line)
        if found and found.group(1) not in KEYWORDS:
            return (found.group(1) + ("()" if kind == "function" else ""), kind)
    if heading and driver in C_LIKE:  # a function's heading in C and its kin: the name just before the first bracket
        found = re.search(r"([A-Za-z_~]\w*)\s*\(", line)
        if found and found.group(1) not in KEYWORDS:
            return (found.group(1) + "()", "function")
    return None


def _add(names, name):
    if name and name not in names:
        names.append(name)


def _path(text, prefix):
    text = text.strip()
    if text.startswith('"') and text.endswith('"'):
        text = text[1:-1]
    return text[len(prefix):] if text.startswith(prefix) else text


def parse_diff(text):
    """[{path, status, added, removed, changed, new, gone, kind}] from `git diff -U0` between two trees."""
    files, current, hunk, left = [], None, None, [0, 0]

    def close_hunk():
        if current is None or hunk is None:
            return
        driver = DRIVERS.get(current["path"].rsplit(".", 1)[-1].lower()) if current.get("path") else None
        heading = _name(hunk["heading"], driver, heading=True) if hunk["heading"] and driver else None
        added = [_name(line, driver) for line in hunk["plus"]] if driver else []
        removed = [_name(line, driver) for line in hunk["minus"]] if driver else []
        added_names = [n[0] for n in added if n]
        removed_names = [n[0] for n in removed if n]
        for name in added_names:
            (_add(current["changed"], name) if name in removed_names else _add(current["new"], name))
        for name in removed_names:
            if name not in added_names:
                _add(current["gone"], name)
        # Git names the definition before the hunk. A hunk that starts where a definition starts (adding,
        # removing or replacing whole ones) didn't change that one: its changes are the definitions themselves.
        asides = ("<!--",) if driver == "markdown" else ("@", "#", "//", "/*", "*")  # decorators and comments before one

        def first(lines):
            return next((line for line in lines if line.strip() and not line.strip().startswith(asides)), None)

        def outside(line):  # at the left margin, so not inside the body of the definition before it
            return driver not in ("markdown", "css", "html") and line[:1] not in (" ", "\t", "}", ")", "]")

        starts = [line for line in (first(hunk["minus"]), first(hunk["plus"])) if line is not None]
        at_boundary = bool(starts) and bool(driver) and all(_name(line, driver) is not None or outside(line) for line in starts)
        if heading and not at_boundary and heading[0] not in current["new"]:
            _add(current["changed"], heading[0])
        kinds = {n[1] for n in [heading] + added + removed if n}
        if kinds:
            current["kind"] = "section" if kinds == {"section"} else "code"

    for line in text.splitlines():
        if hunk is not None and (left[0] > 0 or left[1] > 0):
            if line.startswith("-") and left[0] > 0:
                left[0] -= 1
                current["removed"] += 1
                hunk["minus"].append(line[1:])
                continue
            if line.startswith("+") and left[1] > 0:
                left[1] -= 1
                current["added"] += 1
                hunk["plus"].append(line[1:])
                continue
            if line.startswith("\\"):
                continue
        if line.startswith("diff --git "):
            close_hunk()
            hunk = None
            current = {"path": None, "status": "modified", "added": 0, "removed": 0, "changed": [], "new": [], "gone": [],
                       "_header": line[len("diff --git "):]}
            files.append(current)
        elif current is None or line.startswith("\\"):
            continue
        elif line.startswith("@@"):
            close_hunk()
            found = re.match(HUNK, line)
            if not found:
                hunk = None
                continue
            left = [int(found.group(1) if found.group(1) is not None else 1), int(found.group(2) if found.group(2) is not None else 1)]
            hunk = {"heading": found.group(3), "plus": [], "minus": []}
        elif line.startswith("new file mode"):
            current["status"] = "added"
        elif line.startswith("deleted file mode"):
            current["status"] = "deleted"
        elif line.startswith("rename from "):
            current["status"], current["from"] = "renamed", _path(line[len("rename from "):], "")
        elif line.startswith("rename to "):
            current["path"] = _path(line[len("rename to "):], "")
        elif line.startswith("--- ") and line[4:].strip() != "/dev/null":
            current.setdefault("old", _path(line[4:], "a/"))
        elif line.startswith("+++ ") and line[4:].strip() != "/dev/null":
            current["path"] = current["path"] or _path(line[4:], "b/")
        elif line.startswith("Binary files "):
            current["binary"] = True
    close_hunk()
    out = []
    for f in files:
        header = f.pop("_header")
        if not f["path"]:  # a binary file: "a/<path> b/<path>"
            f["path"] = f.get("old") or (header[2:2 + (len(header) - 5) // 2] if header.startswith("a/") else header)
        f.pop("old", None)
        f.setdefault("kind", None)
        for key in ("changed", "new", "gone"):
            if len(f[key]) > MAX_NAMES:
                f[key + "_more"] = len(f[key]) - MAX_NAMES
                f[key] = f[key][:MAX_NAMES]
        out.append(f)
    return out


def turn_changes(start):
    """What the turn changed in the repo, from the snapshot its prompt left: {root, files, more}. None without one."""
    if not isinstance(start, dict):
        return None
    root, store, before = start.get("root"), start.get("store"), start.get("tree")
    if not (root and store and before and os.path.isdir(store)):
        return None
    _until[0] = time.monotonic() + STOP_GIT_SECONDS
    after = snapshot(root, store)
    if not after:
        return None
    if after == before:
        return {"root": root, "files": [], "more": 0}
    attributes = os.path.join(store, "attributes")
    with open(attributes, "w", encoding="utf-8") as fh:
        fh.write("".join(f"*.{ext} diff={driver}\n" for ext, driver in DRIVERS.items()))
    env, _ = snapshot_env(root, store) or (None, None)
    if env is None:
        return None
    env.pop("GIT_INDEX_FILE", None)
    out = git(root, "-c", "core.attributesFile=" + attributes, "-c", "diff.nightorder-js.xfuncname=" + JS_FUNCNAME,
              "-c", "core.quotePath=false", "diff", "--no-color", "--no-ext-diff", "--no-textconv", "--src-prefix=a/",
              "--dst-prefix=b/", "-U0", "--find-renames", before, after, env=env)
    if out is None:
        return None
    files = parse_diff(out)
    return {"root": root, "files": files[:MAX_CHANGED], "more": max(0, len(files) - MAX_CHANGED)}


def blocked_by_firewall(status, text):
    """Whether a refusal came from the firewall in front of the server rather than from Night Order."""
    return status == "403" and ("<title>Blocked</title>" in text or "cloudflare" in text.lower())


def post(url, body, seconds=SEND_SECONDS):
    """Send the body once, compressed. Returns (the server's answer as a dict, None), or (None, why it didn't get through)."""
    token = os.environ.get("CALLMEIF_TOKEN", "")
    seconds = max(1.0, float(seconds))
    body = gzip.compress(body, compresslevel=6)
    curl = shutil.which("curl")
    try:
        if curl:  # curl follows the machine's proxy and certificate settings, which a cloud session relies on
            command = [curl, "-sS", "-w", "\n%{http_code}", "--max-time", f"{seconds:.1f}", "-H", "Content-Type: application/json",
                       "-H", "Content-Encoding: gzip", "--data-binary", "@-", url]
            if token:
                command[1:1] = ["-H", f"Authorization: Bearer {token}"]
            done = subprocess.run(command, input=body, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=seconds + 2)
            text, _, status = done.stdout.decode("utf-8", errors="replace").rpartition("\n")
            if done.returncode != 0:
                said = done.stderr.decode("utf-8", errors="replace").strip().splitlines()
                return None, f"curl exit {done.returncode}" + (f": {said[-1][:200]}" if said else "")
        else:
            headers = {"Content-Type": "application/json", "Content-Encoding": "gzip"}
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
    if blocked_by_firewall(status, text):
        return None, "HTTP 403: refused by the firewall in front of the server (Cloudflare), before it reached Night Order"
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
    try:
        start = start_snapshot(payload)
    except Exception:  # noqa: BLE001 - the turn's card goes without its code changes
        start = None

    def noted(state):
        keep_snapshot(state, payload.get("session_id"), start)
        return unreported(state)

    report = change_state(url, noted)
    if report:
        note["hook_report"] = report
    curl = shutil.which("curl")
    if not curl:
        return
    command = [curl, "-s", "-o", os.devnull, "--max-time", str(SEND_SECONDS), "-H", "Content-Type: application/json",
               "-H", "Content-Encoding: gzip", "--data-binary", "@-", url + "/v1/connectors/claude-code"]
    token = os.environ.get("CALLMEIF_TOKEN", "")
    if token:
        command[1:1] = ["-H", f"Authorization: Bearer {token}"]
    started = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    started.stdin.write(gzip.compress(json.dumps(note).encode("utf-8")))
    started.stdin.close()  # curl sends it and is left to finish on its own


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
        snapshots = state.get("snapshots")
        return report, (snapshots.get(str(payload.get("session_id"))) if isinstance(snapshots, dict) else None)

    report, start = change_state(url, begin) or ([], None)
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
        if payload.get("hook_event_name") == "Stop" and deadline - time.monotonic() > STOP_GIT_SECONDS + SEND_SECONDS + 1:
            try:
                changes = turn_changes(start)
                if changes is not None:
                    payload["code_changes"] = changes
            except Exception:  # noqa: BLE001 - the card goes without its code changes
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
