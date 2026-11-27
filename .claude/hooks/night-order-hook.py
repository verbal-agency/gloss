#!/usr/bin/env python3
"""Night Order hook for Claude Code (Stop, SubagentStop and UserPromptSubmit) that sends the turn itself.

For sessions whose transcript Night Order can't read from disk: a cloud session, or any machine
other than the one Night Order runs on. It posts the hook's payload with the current turn's own
transcript entries (the prompt, the tool calls and their results, the reply), so the server can
store them as a transcript of its own. When the project's own writing changes (its README,
instructions, plans and other Markdown), it sends those files too, so cards can be written with
the project's context and in its own words, and with them the names its code defines (functions and
classes, each with the first sentence of its docstring or comment), for the glossary.

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

What stays on the machine, set per repo in `.claude/night-order.json` (each part optional):
    {"send": false}                      send nothing from this repo, not even that a prompt came
    {"private": ["customers", "*.sql"]}  files whose contents are never sent, added to the built-in list
                                         (.env files, keys and certificates, .ssh, .aws, secrets/ and the like);
                                         a pattern matches a path's end, and covers a folder of that name
    {"redact": ["ACME-[0-9]{6}"]}         the repo's own secret patterns, redacted with the built-in ones
A call that names a private file (a file tool given one, or a command with one among its words or as a
quoted path, `open('.env')`) is sent without its output, keeping only how it ended, and without what it
wrote: an edit's text, a command's here-documents and quoted strings. Other output loses the lines it
printed from a private file under that file's name: a search's `.env:3:…` and a diff of one. Private
files are left out of the project's writing, its names and the turn's code changes. A private file's
name can leave. Not caught: what a program prints from a private file the command doesn't name, and what
the agent itself says about one. Everything sent is redacted first with the server's own patterns (keys,
tokens, passwords in URLs and assignments), gitleaks' 221 rules for providers' key formats (MIT; generated
into this file and the server by Night Order's ops/secret_rules.py), and the repo's own. A settings file the
hook can't read sends nothing: it fails closed.

It never gets in the way: it prints nothing (Claude Code reads a Stop hook's stdout as
decisions), gives up within Claude Code's time limit, and always exits 0. Standard library only.

CALLMEIF_URL    the server's address, such as https://night-order.example.com. Unset: do nothing.
CALLMEIF_TOKEN  optional bearer token. In a cloud session leave it unset and store the token as
                a network secret on the environment, so the session never sees it.
"""

from __future__ import annotations

import fnmatch
import glob
import gzip
import hashlib
import json
import math
import os
import re
import shlex
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


def project_files(root, private=()):
    """{path under the root: text} for the project's README, instructions, plans and other Markdown, but
    for the files the repo keeps private."""
    names = [n for n in NAMED_FILES if os.path.isfile(os.path.join(root, n)) and not is_private(n, private)]
    for pattern in DOC_PATTERNS:
        for path in sorted(glob.glob(os.path.join(root, pattern), recursive=True)):
            name = os.path.relpath(path, root).replace(os.sep, "/")
            if os.path.isfile(path) and name not in names and not is_private(name, private):
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


def the_project(payload, url, private=()):
    """The project's root and a hash of its writing, with the files themselves when the server hasn't
    been sent this version from this machine. Returns (what to send, the stamp to write once it arrives)."""
    root = project_root(payload)
    files = project_files(root, private)
    names = project_names(root, private)
    if not files and not names:
        return None, None
    writing = {"files": files, "names": names} if names else files  # the files alone hash as before
    digest = hashlib.sha256(json.dumps(writing, sort_keys=True).encode("utf-8")).hexdigest()[:16]
    project = {"root": root, "hash": digest}
    stamp = stamp_file(root, url)
    try:
        with open(stamp, encoding="utf-8") as fh:
            sent = fh.read().strip()
    except OSError:
        sent = ""
    if sent != digest:
        project["files"] = files
        if names:
            project["names"] = names
    return project, (stamp, digest)


# --- Secret rules: generated by ops/secret_rules.py from gitleaks' rules (MIT); don't edit by hand ---
# gitleaks 5f6ec56cfa6f8c67648d863582c7ae2f206d5c1c 2026-10-23: 221 rules.
# (id, pattern, keywords, entropy floor, secret group, allowlists, length of the lazy name prefix taken off)
SECRET_RULES = [
    ('1password-secret-key', '\\bA3-[A-Z0-9]{6}-(?:(?:[A-Z0-9]{11})|(?:[A-Z0-9]{6}-[A-Z0-9]{5}))-[A-Z0-9]{5}-[A-Z0-9]{5}-[A-Z0-9]{5}\\b', ('a3-',), 3.8, 0, (), 0),
    ('1password-service-account-token', 'ops_eyJ[a-zA-Z0-9+/]{250,}={0,3}', ('ops_',), 4.0, 0, (), 0),
    ('adafruit-api-key', '(?i)(?:adafruit)(?:[ \\t\\w.-]{0,20})[\\s\'"]{0,3}(?:=|>|:{1,3}=|\\|\\||:|=>|\\?=|,)[\\x60\'"\\s=]{0,5}([a-z0-9_-]{32})(?:[\\x60\'"\\s;]|\\\\[nr]|$)', ('adafruit',), 0.0, 0, (), 50),
    ('adobe-client-id', '(?i)(?:adobe)(?:[ \\t\\w.-]{0,20})[\\s\'"]{0,3}(?:=|>|:{1,3}=|\\|\\||:|=>|\\?=|,)[\\x60\'"\\s=]{0,5}([a-f0-9]{32})(?:[\\x60\'"\\s;]|\\\\[nr]|$)', ('adobe',), 2.0, 0, (), 50),
    ('adobe-client-secret', '\\b(p8e-(?i:[a-z0-9]{32}))(?:[\\x60\'"\\s;]|\\\\[nr]|$)', ('p8e-',), 2.0, 0, (), 0),
    ('age-secret-key', 'AGE-SECRET-KEY-1[QPZRY9X8GF2TVDW0S3JN54KHCE6MUA7L]{58}', ('age-secret-key-1',), 0.0, 0, (), 0),
    ('airtable-api-key', '(?i)(?:airtable)(?:[ \\t\\w.-]{0,20})[\\s\'"]{0,3}(?:=|>|:{1,3}=|\\|\\||:|=>|\\?=|,)[\\x60\'"\\s=]{0,5}([a-z0-9]{17})(?:[\\x60\'"\\s;]|\\\\[nr]|$)', ('airtable',), 0.0, 0, (), 50),
    ('airtable-personnal-access-token', '\\b(pat[a-zA-Z0-9]{14}\\.[a-f0-9]{64})\\b', ('airtable',), 0.0, 0, (), 0),
    ('algolia-api-key', '(?i)(?:algolia)(?:[ \\t\\w.-]{0,20})[\\s\'"]{0,3}(?:=|>|:{1,3}=|\\|\\||:|=>|\\?=|,)[\\x60\'"\\s=]{0,5}([a-z0-9]{32})(?:[\\x60\'"\\s;]|\\\\[nr]|$)', ('algolia',), 0.0, 0, (), 50),
    ('alibaba-access-key-id', '\\b(LTAI(?i:[a-z0-9]{20}))(?:[\\x60\'"\\s;]|\\\\[nr]|$)', ('ltai',), 2.0, 0, (), 0),
    ('alibaba-secret-key', '(?i)(?:alibaba)(?:[ \\t\\w.-]{0,20})[\\s\'"]{0,3}(?:=|>|:{1,3}=|\\|\\||:|=>|\\?=|,)[\\x60\'"\\s=]{0,5}([a-z0-9]{30})(?:[\\x60\'"\\s;]|\\\\[nr]|$)', ('alibaba',), 2.0, 0, (), 50),
    ('anthropic-admin-api-key', '\\b(sk-ant-admin01-[a-zA-Z0-9_\\-]{93}AA)(?:[\\x60\'"\\s;]|\\\\[nr]|$)', ('sk-ant-admin01',), 0.0, 0, (), 0),
    ('anthropic-api-key', '\\b(sk-ant-api03-[a-zA-Z0-9_\\-]{93}AA)(?:[\\x60\'"\\s;]|\\\\[nr]|$)', ('sk-ant-api03',), 0.0, 0, (), 0),
    ('artifactory-api-key', '\\bAKCp[A-Za-z0-9]{69}\\b', ('akcp',), 4.5, 0, (), 0),
    ('artifactory-reference-token', '\\bcmVmd[A-Za-z0-9]{59}\\b', ('cmvmd',), 4.5, 0, (), 0),
    ('asana-client-id', '(?i)(?:asana)(?:[ \\t\\w.-]{0,20})[\\s\'"]{0,3}(?:=|>|:{1,3}=|\\|\\||:|=>|\\?=|,)[\\x60\'"\\s=]{0,5}([0-9]{16})(?:[\\x60\'"\\s;]|\\\\[nr]|$)', ('asana',), 0.0, 0, (), 50),
    ('asana-client-secret', '(?i)(?:asana)(?:[ \\t\\w.-]{0,20})[\\s\'"]{0,3}(?:=|>|:{1,3}=|\\|\\||:|=>|\\?=|,)[\\x60\'"\\s=]{0,5}([a-z0-9]{32})(?:[\\x60\'"\\s;]|\\\\[nr]|$)', ('asana',), 0.0, 0, (), 50),
    ('atlassian-api-token', '(?i)(?:(?-i:ATLASSIAN|[Aa]tlassian)|(?-i:CONFLUENCE|[Cc]onfluence)|(?-i:JIRA|[Jj]ira))(?:[ \\t\\w.-]{0,20})[\\s\'"]{0,3}(?:=|>|:{1,3}=|\\|\\||:|=>|\\?=|,)[\\x60\'"\\s=]{0,5}([a-z0-9]{20}[a-f0-9]{4})(?:[\\x60\'"\\s;]|\\\\[nr]|$)|\\b(ATATT3[A-Za-z0-9_\\-=]{186})(?:[\\x60\'"\\s;]|\\\\[nr]|$)', ('atatt3', 'atlassian', 'confluence', 'jira'), 3.5, 0, (), 50),
    ('authress-service-client-access-key', '\\b((?:sc|ext|scauth|authress)_(?i:[a-z0-9]{5,30}\\.[a-z0-9]{4,6}\\.(?-i:acc)[_-][a-z0-9-]{10,32}\\.[a-z0-9+/_=-]{30,120}))(?:[\\x60\'"\\s;]|\\\\[nr]|$)', ('authress_', 'ext_', 'sc_', 'scauth_'), 2.0, 0, (), 0),
    ('aws-access-token', '\\b((?:A3T[A-Z0-9]|AKIA|ASIA|ABIA|ACCA)[A-Z2-7]{16})\\b', ('a3t', 'abia', 'acca', 'akia', 'asia'), 3.0, 0, (('secret', ('.+EXAMPLE$',), (), False, False),), 0),
    ('aws-amazon-bedrock-api-key-long-lived', '\\b(ABSK[A-Za-z0-9+/]{109,269}={0,2})(?:[\\x60\'"\\s;]|\\\\[nr]|$)', ('absk',), 3.0, 0, (), 0),
    ('aws-amazon-bedrock-api-key-short-lived', 'bedrock-api-key-YmVkcm9jay5hbWF6b25hd3MuY29t', ('bedrock-api-key-',), 3.0, 0, (), 0),
    ('azure-ad-client-secret', '(?:^|[\\\\\'"\\x60\\s>=:(,)])([a-zA-Z0-9_~.]{3}\\dQ~[a-zA-Z0-9_~.-]{31,34})(?:$|[\\\\\'"\\x60\\s<),])', ('q~',), 3.0, 0, (), 0),
    ('beamer-api-token', '(?i)(?:beamer)(?:[ \\t\\w.-]{0,20})[\\s\'"]{0,3}(?:=|>|:{1,3}=|\\|\\||:|=>|\\?=|,)[\\x60\'"\\s=]{0,5}(b_[a-z0-9=_\\-]{44})(?:[\\x60\'"\\s;]|\\\\[nr]|$)', ('beamer',), 0.0, 0, (), 50),
    ('bitbucket-client-id', '(?i)(?:bitbucket)(?:[ \\t\\w.-]{0,20})[\\s\'"]{0,3}(?:=|>|:{1,3}=|\\|\\||:|=>|\\?=|,)[\\x60\'"\\s=]{0,5}([a-z0-9]{32})(?:[\\x60\'"\\s;]|\\\\[nr]|$)', ('bitbucket',), 0.0, 0, (), 50),
    ('bitbucket-client-secret', '(?i)(?:bitbucket)(?:[ \\t\\w.-]{0,20})[\\s\'"]{0,3}(?:=|>|:{1,3}=|\\|\\||:|=>|\\?=|,)[\\x60\'"\\s=]{0,5}([a-z0-9=_\\-]{64})(?:[\\x60\'"\\s;]|\\\\[nr]|$)', ('bitbucket',), 0.0, 0, (), 50),
    ('bittrex-access-key', '(?i)(?:bittrex)(?:[ \\t\\w.-]{0,20})[\\s\'"]{0,3}(?:=|>|:{1,3}=|\\|\\||:|=>|\\?=|,)[\\x60\'"\\s=]{0,5}([a-z0-9]{32})(?:[\\x60\'"\\s;]|\\\\[nr]|$)', ('bittrex',), 0.0, 0, (), 50),
    ('bittrex-secret-key', '(?i)(?:bittrex)(?:[ \\t\\w.-]{0,20})[\\s\'"]{0,3}(?:=|>|:{1,3}=|\\|\\||:|=>|\\?=|,)[\\x60\'"\\s=]{0,5}([a-z0-9]{32})(?:[\\x60\'"\\s;]|\\\\[nr]|$)', ('bittrex',), 0.0, 0, (), 50),
    ('cisco-meraki-api-key', '(?i:[\\w.-]{0,50}?(?:(?-i:[Mm]eraki|MERAKI))(?:[ \\t\\w.-]{0,20})[\\s\'"]{0,3})(?:=|>|:{1,3}=|\\|\\||:|=>|\\?=|,)[\\x60\'"\\s=]{0,5}([0-9a-f]{40})(?:[\\x60\'"\\s;]|\\\\[nr]|$)', ('meraki',), 3.0, 0, (), 50),
    ('clickhouse-cloud-api-secret-key', '\\b(4b1d[A-Za-z0-9]{38})\\b', ('4b1d',), 3.0, 0, (), 0),
    ('clojars-api-token', '(?i)CLOJARS_[a-z0-9]{60}', ('clojars_',), 2.0, 0, (), 0),
    ('cloudflare-api-key', '(?i)(?:cloudflare)(?:[ \\t\\w.-]{0,20})[\\s\'"]{0,3}(?:=|>|:{1,3}=|\\|\\||:|=>|\\?=|,)[\\x60\'"\\s=]{0,5}([a-z0-9_-]{40})(?:[\\x60\'"\\s;]|\\\\[nr]|$)', ('cloudflare',), 2.0, 0, (), 50),
    ('cloudflare-global-api-key', '(?i)(?:cloudflare)(?:[ \\t\\w.-]{0,20})[\\s\'"]{0,3}(?:=|>|:{1,3}=|\\|\\||:|=>|\\?=|,)[\\x60\'"\\s=]{0,5}([a-f0-9]{37})(?:[\\x60\'"\\s;]|\\\\[nr]|$)', ('cloudflare',), 2.0, 0, (), 50),
    ('cloudflare-origin-ca-key', '\\b(v1\\.0-[a-f0-9]{24}-[a-f0-9]{146})(?:[\\x60\'"\\s;]|\\\\[nr]|$)', ('cloudflare', 'v1.0-'), 2.0, 0, (), 0),
    ('codecov-access-token', '(?i)(?:codecov)(?:[ \\t\\w.-]{0,20})[\\s\'"]{0,3}(?:=|>|:{1,3}=|\\|\\||:|=>|\\?=|,)[\\x60\'"\\s=]{0,5}([a-z0-9]{32})(?:[\\x60\'"\\s;]|\\\\[nr]|$)', ('codecov',), 0.0, 0, (), 50),
    ('cohere-api-token', '(?i:[\\w.-]{0,50}?(?:cohere|CO_API_KEY)(?:[ \\t\\w.-]{0,20})[\\s\'"]{0,3})(?:=|>|:{1,3}=|\\|\\||:|=>|\\?=|,)[\\x60\'"\\s=]{0,5}([a-zA-Z0-9]{40})(?:[\\x60\'"\\s;]|\\\\[nr]|$)', ('co_api_key', 'cohere'), 4.0, 0, (), 50),
    ('coinbase-access-token', '(?i)(?:coinbase)(?:[ \\t\\w.-]{0,20})[\\s\'"]{0,3}(?:=|>|:{1,3}=|\\|\\||:|=>|\\?=|,)[\\x60\'"\\s=]{0,5}([a-z0-9_-]{64})(?:[\\x60\'"\\s;]|\\\\[nr]|$)', ('coinbase',), 0.0, 0, (), 50),
    ('confluent-access-token', '(?i)(?:confluent)(?:[ \\t\\w.-]{0,20})[\\s\'"]{0,3}(?:=|>|:{1,3}=|\\|\\||:|=>|\\?=|,)[\\x60\'"\\s=]{0,5}([a-z0-9]{16})(?:[\\x60\'"\\s;]|\\\\[nr]|$)', ('confluent',), 0.0, 0, (), 50),
    ('confluent-secret-key', '(?i)(?:confluent)(?:[ \\t\\w.-]{0,20})[\\s\'"]{0,3}(?:=|>|:{1,3}=|\\|\\||:|=>|\\?=|,)[\\x60\'"\\s=]{0,5}([a-z0-9]{64})(?:[\\x60\'"\\s;]|\\\\[nr]|$)', ('confluent',), 0.0, 0, (), 50),
    ('contentful-delivery-api-token', '(?i)(?:contentful)(?:[ \\t\\w.-]{0,20})[\\s\'"]{0,3}(?:=|>|:{1,3}=|\\|\\||:|=>|\\?=|,)[\\x60\'"\\s=]{0,5}([a-z0-9=_\\-]{43})(?:[\\x60\'"\\s;]|\\\\[nr]|$)', ('contentful',), 0.0, 0, (), 50),
    ('curl-auth-header', '\\bcurl\\b(?:.*?|.*?(?:[\\r\\n]{1,2}.*?){1,5})[ \\t\\n\\r](?:-H|--header)(?:=|[ \\t]{0,5})(?:"(?i:(?:Authorization:[ \\t]{0,5}(?:Basic[ \\t]([a-z0-9+/]{8,}={0,3})|(?:Bearer|(?:Api-)?Token)[ \\t]([\\w=~@.+/-]{8,})|([\\w=~@.+/-]{8,}))|(?:(?:X-(?:[a-z]+-)?)?(?:Api-?)?(?:Key|Token)):[ \\t]{0,5}([\\w=~@.+/-]{8,}))")|(?i:\'(?i:(?:Authorization:[ \\t]{0,5}(?:Basic[ \\t]([a-z0-9+/]{8,}={0,3})|(?:Bearer|(?:Api-)?Token)[ \\t]([\\w=~@.+/-]{8,})|([\\w=~@.+/-]{8,}))|(?:(?:X-(?:[a-z]+-)?)?(?:Api-?)?(?:Key|Token)):[ \\t]{0,5}([\\w=~@.+/-]{8,}))\')))(?:\\B|\\s|\\Z)', ('curl',), 2.75, 0, (), 0),
    ('curl-auth-user', '\\bcurl\\b(?:.*|.*(?:[\\r\\n]{1,2}.*){1,5})[ \\t\\n\\r](?:-u|--user)(?:=|[ \\t]{0,5})("(:[^"]{3,}|[^:"]{3,}:|[^:"]{3,}:[^"]{3,})"|\'([^:\']{3,}:[^\']{3,})\'|((?:"[^"]{3,}"|\'[^\']{3,}\'|[\\w$@.-]+):(?:"[^"]{3,}"|\'[^\']{3,}\'|[\\w${}@.-]+)))(?:\\s|\\Z)', ('curl',), 2.0, 0, (('secret', ('[^:]+:(?:change(?:it|me)|pass(?:word)?|pwd|test|token|\\*+|x+)', '[\'"]?<[^>]+>[\'"]?:[\'"]?<[^>]+>|<[^:]+:[^>]+>[\'"]?', '[^:]+:\\[[^]]+]', '[\'"]?[^:]+[\'"]?:[\'"]?\\$(?:\\d|\\w+|\\{(?:\\d|\\w+)})[\'"]?', '\\$\\([^)]+\\):\\$\\([^)]+\\)', '[\'"]?\\$?{{[^}]+}}[\'"]?:[\'"]?\\$?{{[^}]+}}[\'"]?'), (), False, False),), 0),
    ('databricks-api-token', '\\b(dapi[a-f0-9]{32}(?:-\\d)?)(?:[\\x60\'"\\s;]|\\\\[nr]|$)', ('dapi',), 3.0, 0, (), 0),
    ('datadog-access-token', '(?i)(?:datadog)(?:[ \\t\\w.-]{0,20})[\\s\'"]{0,3}(?:=|>|:{1,3}=|\\|\\||:|=>|\\?=|,)[\\x60\'"\\s=]{0,5}([a-z0-9]{40})(?:[\\x60\'"\\s;]|\\\\[nr]|$)', ('datadog',), 0.0, 0, (), 50),
    ('defined-networking-api-token', '(?i)(?:dnkey)(?:[ \\t\\w.-]{0,20})[\\s\'"]{0,3}(?:=|>|:{1,3}=|\\|\\||:|=>|\\?=|,)[\\x60\'"\\s=]{0,5}(dnkey-[a-z0-9=_\\-]{26}-[a-z0-9=_\\-]{52})(?:[\\x60\'"\\s;]|\\\\[nr]|$)', ('dnkey',), 0.0, 0, (), 50),
    ('digitalocean-access-token', '\\b(doo_v1_[a-f0-9]{64})(?:[\\x60\'"\\s;]|\\\\[nr]|$)', ('doo_v1_',), 3.0, 0, (), 0),
    ('digitalocean-pat', '\\b(dop_v1_[a-f0-9]{64})(?:[\\x60\'"\\s;]|\\\\[nr]|$)', ('dop_v1_',), 3.0, 0, (), 0),
    ('digitalocean-refresh-token', '(?i)\\b(dor_v1_[a-f0-9]{64})(?:[\\x60\'"\\s;]|\\\\[nr]|$)', ('dor_v1_',), 0.0, 0, (), 0),
    ('discord-api-token', '(?i)(?:discord)(?:[ \\t\\w.-]{0,20})[\\s\'"]{0,3}(?:=|>|:{1,3}=|\\|\\||:|=>|\\?=|,)[\\x60\'"\\s=]{0,5}([a-f0-9]{64})(?:[\\x60\'"\\s;]|\\\\[nr]|$)', ('discord',), 0.0, 0, (), 50),
    ('discord-client-id', '(?i)(?:discord)(?:[ \\t\\w.-]{0,20})[\\s\'"]{0,3}(?:=|>|:{1,3}=|\\|\\||:|=>|\\?=|,)[\\x60\'"\\s=]{0,5}([0-9]{18})(?:[\\x60\'"\\s;]|\\\\[nr]|$)', ('discord',), 2.0, 0, (), 50),
    ('discord-client-secret', '(?i)(?:discord)(?:[ \\t\\w.-]{0,20})[\\s\'"]{0,3}(?:=|>|:{1,3}=|\\|\\||:|=>|\\?=|,)[\\x60\'"\\s=]{0,5}([a-z0-9=_\\-]{32})(?:[\\x60\'"\\s;]|\\\\[nr]|$)', ('discord',), 2.0, 0, (), 50),
    ('doppler-api-token', 'dp\\.pt\\.(?i:[a-z0-9]{43})', ('dp.pt.',), 2.0, 0, (), 0),
    ('droneci-access-token', '(?i)(?:droneci)(?:[ \\t\\w.-]{0,20})[\\s\'"]{0,3}(?:=|>|:{1,3}=|\\|\\||:|=>|\\?=|,)[\\x60\'"\\s=]{0,5}([a-z0-9]{32})(?:[\\x60\'"\\s;]|\\\\[nr]|$)', ('droneci',), 0.0, 0, (), 50),
    ('dropbox-api-token', '(?i)(?:dropbox)(?:[ \\t\\w.-]{0,20})[\\s\'"]{0,3}(?:=|>|:{1,3}=|\\|\\||:|=>|\\?=|,)[\\x60\'"\\s=]{0,5}([a-z0-9]{15})(?:[\\x60\'"\\s;]|\\\\[nr]|$)', ('dropbox',), 0.0, 0, (), 50),
    ('dropbox-long-lived-api-token', '(?i)(?:dropbox)(?:[ \\t\\w.-]{0,20})[\\s\'"]{0,3}(?:=|>|:{1,3}=|\\|\\||:|=>|\\?=|,)[\\x60\'"\\s=]{0,5}([a-z0-9]{11}(AAAAAAAAAA)[a-z0-9\\-_=]{43})(?:[\\x60\'"\\s;]|\\\\[nr]|$)', ('dropbox',), 0.0, 0, (), 50),
    ('dropbox-short-lived-api-token', '(?i)(?:dropbox)(?:[ \\t\\w.-]{0,20})[\\s\'"]{0,3}(?:=|>|:{1,3}=|\\|\\||:|=>|\\?=|,)[\\x60\'"\\s=]{0,5}(sl\\.[a-z0-9\\-=_]{135})(?:[\\x60\'"\\s;]|\\\\[nr]|$)', ('dropbox',), 0.0, 0, (), 50),
    ('duffel-api-token', 'duffel_(?:test|live)_(?i:[a-z0-9_\\-=]{43})', ('duffel_',), 2.0, 0, (), 0),
    ('dynatrace-api-token', 'dt0c01\\.(?i:[a-z0-9]{24}\\.[a-z0-9]{64})', ('dt0c01.',), 4.0, 0, (), 0),
    ('easypost-api-token', '\\bEZAK(?i:[a-z0-9]{54}\\b)', ('ezak',), 2.0, 0, (), 0),
    ('easypost-test-api-token', '\\bEZTK(?i:[a-z0-9]{54}\\b)', ('eztk',), 2.0, 0, (), 0),
    ('etsy-access-token', '(?i)(?:(?-i:ETSY|[Ee]tsy))(?:[ \\t\\w.-]{0,20})[\\s\'"]{0,3}(?:=|>|:{1,3}=|\\|\\||:|=>|\\?=|,)[\\x60\'"\\s=]{0,5}([a-z0-9]{24})(?:[\\x60\'"\\s;]|\\\\[nr]|$)', ('etsy',), 3.0, 0, (), 50),
    ('facebook-access-token', '(?i)\\b(\\d{15,16}(\\||%)[0-9a-z\\-_]{27,40})(?:[\\x60\'"\\s;]|\\\\[nr]|$)', ('facebook',), 3.0, 0, (), 0),
    ('facebook-page-access-token', '\\b(EAA[MC](?i:[a-z0-9]{100,}))(?:[\\x60\'"\\s;]|\\\\[nr]|$)', ('eaac', 'eaam'), 4.0, 0, (), 0),
    ('facebook-secret', '(?i)(?:facebook)(?:[ \\t\\w.-]{0,20})[\\s\'"]{0,3}(?:=|>|:{1,3}=|\\|\\||:|=>|\\?=|,)[\\x60\'"\\s=]{0,5}([a-f0-9]{32})(?:[\\x60\'"\\s;]|\\\\[nr]|$)', ('facebook',), 3.0, 0, (), 50),
    ('fastly-api-token', '(?i)(?:fastly)(?:[ \\t\\w.-]{0,20})[\\s\'"]{0,3}(?:=|>|:{1,3}=|\\|\\||:|=>|\\?=|,)[\\x60\'"\\s=]{0,5}([a-z0-9=_\\-]{32})(?:[\\x60\'"\\s;]|\\\\[nr]|$)', ('fastly',), 0.0, 0, (), 50),
    ('finicity-api-token', '(?i)(?:finicity)(?:[ \\t\\w.-]{0,20})[\\s\'"]{0,3}(?:=|>|:{1,3}=|\\|\\||:|=>|\\?=|,)[\\x60\'"\\s=]{0,5}([a-f0-9]{32})(?:[\\x60\'"\\s;]|\\\\[nr]|$)', ('finicity',), 0.0, 0, (), 50),
    ('finicity-client-secret', '(?i)(?:finicity)(?:[ \\t\\w.-]{0,20})[\\s\'"]{0,3}(?:=|>|:{1,3}=|\\|\\||:|=>|\\?=|,)[\\x60\'"\\s=]{0,5}([a-z0-9]{20})(?:[\\x60\'"\\s;]|\\\\[nr]|$)', ('finicity',), 0.0, 0, (), 50),
    ('finnhub-access-token', '(?i)(?:finnhub)(?:[ \\t\\w.-]{0,20})[\\s\'"]{0,3}(?:=|>|:{1,3}=|\\|\\||:|=>|\\?=|,)[\\x60\'"\\s=]{0,5}([a-z0-9]{20})(?:[\\x60\'"\\s;]|\\\\[nr]|$)', ('finnhub',), 0.0, 0, (), 50),
    ('flickr-access-token', '(?i)(?:flickr)(?:[ \\t\\w.-]{0,20})[\\s\'"]{0,3}(?:=|>|:{1,3}=|\\|\\||:|=>|\\?=|,)[\\x60\'"\\s=]{0,5}([a-z0-9]{32})(?:[\\x60\'"\\s;]|\\\\[nr]|$)', ('flickr',), 0.0, 0, (), 50),
    ('flutterwave-encryption-key', 'FLWSECK_TEST-(?i:[a-h0-9]{12})', ('flwseck_test',), 2.0, 0, (), 0),
    ('flutterwave-public-key', 'FLWPUBK_TEST-(?i:[a-h0-9]{32}-X)', ('flwpubk_test',), 2.0, 0, (), 0),
    ('flutterwave-secret-key', 'FLWSECK_TEST-(?i:[a-h0-9]{32}-X)', ('flwseck_test',), 2.0, 0, (), 0),
    ('flyio-access-token', '\\b((?:fo1_[\\w-]{43}|fm1[ar]_[a-zA-Z0-9+\\/]{100,}={0,3}|fm2_[a-zA-Z0-9+\\/]{100,}={0,3}))(?:[\\x60\'"\\s;]|\\\\[nr]|$)', ('fm1', 'fm2_', 'fo1_'), 4.0, 0, (), 0),
    ('frameio-api-token', 'fio-u-(?i:[a-z0-9\\-_=]{64})', ('fio-u-',), 0.0, 0, (), 0),
    ('freemius-secret-key', '(?i)["\']secret_key["\']\\s*=>\\s*["\'](sk_[\\S]{29})["\']', ('secret_key',), 0.0, 0, (), 0),
    ('freshbooks-access-token', '(?i)(?:freshbooks)(?:[ \\t\\w.-]{0,20})[\\s\'"]{0,3}(?:=|>|:{1,3}=|\\|\\||:|=>|\\?=|,)[\\x60\'"\\s=]{0,5}([a-z0-9]{64})(?:[\\x60\'"\\s;]|\\\\[nr]|$)', ('freshbooks',), 0.0, 0, (), 50),
    ('gcp-api-key', '\\b(AIza[\\w-]{35})(?:[\\x60\'"\\s;]|\\\\[nr]|$)', ('aiza',), 4.0, 0, (('secret', ('AIzaSyabcdefghijklmnopqrstuvwxyz1234567', 'AIzaSyAnLA7NfeLquW1tJFpx_eQCxoX-oo6YyIs', 'AIzaSyCkEhVjf3pduRDt6d1yKOMitrUEke8agEM', 'AIzaSyDMAScliyLx7F0NPDEJi1QmyCgHIAODrlU', 'AIzaSyD3asb-2pEZVqMkmL6M9N6nHZRR_znhrh0', 'AIzayDNSXIbFmlXbIE6mCzDLQAqITYefhixbX4A', 'AIzaSyAdOS2zB6NCsk1pCdZ4-P6GBdi_UUPwX7c', 'AIzaSyASWm6HmTMdYWpgMnjRBjxcQ9CKctWmLd4', 'AIzaSyANUvH9H9BsUccjsu2pCmEkOPjjaXeDQgY', 'AIzaSyA5_iVawFQ8ABuTZNUdcwERLJv_a_p4wtM', 'AIzaSyA4UrcGxgwQFTfaI3no3t7Lt1sjmdnP5sQ', 'AIzaSyDSb51JiIcB6OJpwwMicseKRhhrOq1cS7g', 'AIzaSyBF2RrAIm4a0mO64EShQfqfd2AFnzAvvuU', 'AIzaSyBcE-OOIbhjyR83gm4r2MFCu4MJmprNXsw', 'AIzaSyB8qGxt4ec15vitgn44duC5ucxaOi4FmqE', 'AIzaSyA8vmApnrHNFE0bApF4hoZ11srVL_n0nvY'), (), False, False),), 0),
    ('generic-api-key', '(?i)(?:access|auth|(?-i:[Aa]pi|API)|credential|creds|key|passw(?:or)?d|secret|token)(?:[ \\t\\w.-]{0,20})[\\s\'"]{0,3}(?:=|>|:{1,3}=|\\|\\||:|=>|\\?=|,)[\\x60\'"\\s=]{0,5}([\\w.=-]{10,150}|[a-z0-9][a-z0-9+/]{11,}={0,3})(?:[\\x60\'"\\s;]|\\\\[nr]|$)', ('access', 'api', 'auth', 'credential', 'creds', 'key', 'passwd', 'password', 'secret', 'token'), 3.5, 0, (('secret', ('^[a-zA-Z_.-]+$',), (), False, False), ('match', ('(?i)(?:access(?:ibility|or)|access[_.-]?id|random[_.-]?access|api[_.-]?(?:id|name|version)|rapid|capital|[a-z0-9-]*?api[a-z0-9-]*?:jar:|author|X-MS-Exchange-Organization-Auth|Authentication-Results|(?:credentials?[_.-]?id|withCredentials)|(?:bucket|foreign|hot|idx|natural|primary|pub(?:lic)?|schema|sequence)[_.-]?key|(?:turkey)|key[_.-]?(?:alias|board|code|frame|id|length|mesh|name|pair|press(?:ed)?|ring|selector|signature|size|stone|storetype|word|up|down|left|right)|key[_.-]?vault[_.-]?(?:id|name)|keyVaultToStoreSecrets|key(?:store|tab)[_.-]?(?:file|path)|issuerkeyhash|(?-i:[DdMm]onkey|[DM]ONKEY)|keying|(?:secret)[_.-]?(?:length|name|size)|UserSecretsId|(?:csrf)[_.-]?token|(?:io\\.jsonwebtoken[ \\t]?:[ \\t]?[\\w-]+)|(?:api|credentials|token)[_.-]?(?:endpoint|ur[il])|public[_.-]?token|(?:key|token)[_.-]?file|(?-i:(?:[A-Z_]+=\\n[A-Z_]+=|[a-z_]+=\\n[a-z_]+=)(?:\\n|\\Z))|(?-i:(?:[A-Z.]+=\\n[A-Z.]+=|[a-z.]+=\\n[a-z.]+=)(?:\\n|\\Z)))',), ('000000', '6fe4476ee5a1832882e326b506d14126', '_ec2_', 'aaaaaa', 'about', 'abstract', 'academy', 'acces', 'account', 'act-', 'act.', 'act_', 'action', 'active', 'actively', 'activity', 'adapter', 'add-', 'add-on', 'add.', 'add_', 'addon', 'addres', 'admin', 'adobe', 'advanced', 'adventure', 'agent', 'agile', 'air-', 'air.', 'air_', 'ajax', 'akka', 'alert', 'alfred', 'algorithm', 'all-', 'all.', 'all_', 'alloy', 'alpha', 'amazon', 'amqp', 'analysi', 'analytic', 'analyzer', 'android', 'angular', 'angularj', 'animate', 'animation', 'another', 'ansible', 'answer', 'ant-', 'ant.', 'ant_', 'any-', 'any.', 'any_', 'apache', 'app-', 'app.', 'app_', 'apple', 'arch', 'archive', 'archived', 'arduino', 'array', 'art-', 'art.', 'art_', 'article', 'asp-', 'asp.', 'asp_', 'asset', 'async', 'atom', 'attention', 'audio', 'audit', 'aura', 'auth', 'author', 'authorize', 'auto', 'automated', 'automatic', 'awesome', 'aws_', 'azure', 'back', 'backbone', 'backend', 'backup', 'bar-', 'bar.', 'bar_', 'base', 'based', 'bash', 'basic', 'batch', 'been', 'beer', 'behavior', 'being', 'benchmark', 'best', 'beta', 'better', 'big-', 'big.', 'big_', 'binary', 'binding', 'bit-', 'bit.', 'bit_', 'bitcoin', 'block', 'blog', 'board', 'book', 'bookmark', 'boost', 'boot', 'bootstrap', 'bosh', 'bot-', 'bot.', 'bot_', 'bower', 'box-', 'box.', 'box_', 'boxen', 'bracket', 'branch', 'bridge', 'browser', 'brunch', 'buffer', 'bug-', 'bug.', 'bug_', 'build', 'builder', 'building', 'buildout', 'buildpack', 'built', 'bundle', 'busines', 'but-', 'but.', 'but_', 'button', 'cache', 'caching', 'cakephp', 'calendar', 'call', 'camera', 'campfire', 'can-', 'can.', 'can_', 'canva', 'captcha', 'capture', 'card', 'carousel', 'case', 'cassandra', 'cat-', 'cat.', 'cat_', 'category', 'center', 'cento', 'challenge', 'change', 'changelog', 'channel', 'chart', 'chat', 'cheat', 'check', 'checker', 'chef', 'ches', 'chinese', 'chosen', 'chrome', 'ckeditor', 'clas', 'classe', 'classic', 'clean', 'cli-', 'cli.', 'cli_', 'client', 'clojure', 'clone', 'closure', 'cloud', 'club', 'cluster', 'cms-', 'cms_', 'coco', 'code', 'coding', 'coffee', 'color', 'combination', 'combo', 'command', 'commander', 'comment', 'commit', 'common', 'community', 'compas', 'compiler', 'complete', 'component', 'composer', 'computer', 'computing', 'con-', 'con.', 'con_', 'concept', 'conf', 'config', 'connect', 'connector', 'console', 'contact', 'container', 'contao', 'content', 'contest', 'context', 'control', 'convert', 'converter', "conway'", 'cookbook', 'cookie', 'cool', 'copy', 'cordova', 'core', 'couchbase', 'couchdb', 'countdown', 'counter', 'course', 'craft', 'crawler', 'create', 'creating', 'creator', 'credential', 'crm-', 'crm.', 'crm_', 'cros', 'crud', 'csv-', 'csv.', 'csv_', 'cube', 'cucumber', 'cuda', 'current', 'currently', 'custom', 'daemon', 'dark', 'dart', 'dash', 'dashboard', 'data', 'database', 'date', 'day-', 'day.', 'day_', 'dead', 'debian', 'debug', 'debugger', 'deck', 'define', 'del-', 'del.', 'del_', 'delete', 'demo', 'deploy', 'design', 'designer', 'desktop', 'detection', 'detector', 'dev-', 'dev.', 'dev_', 'develop', 'developer', 'device', 'devise', 'diff', 'digital', 'directive', 'directory', 'discovery', 'display', 'django', 'dns-', 'dns_', 'doc-', 'doc.', 'doc_', 'docker', 'docpad', 'doctrine', 'document', 'doe-', 'doe.', 'doe_', 'dojo', 'dom-', 'dom.', 'dom_', 'domain', "don't", 'done', 'dot-', 'dot.', 'dot_', 'dotfile', 'download', 'draft', 'drag', 'drill', 'drive', 'driven', 'driver', 'drop', 'dropbox', 'drupal', 'dsl-', 'dsl.', 'dsl_', 'dynamic', 'easy', 'ecdsa', 'eclipse', 'edit', 'editing', 'edition', 'editor', 'element', 'emac', 'email', 'embed', 'embedded', 'ember', 'emitter', 'emulator', 'encoding', 'endpoint', 'engine', 'english', 'enhanced', 'entity', 'entry', 'env_', 'episode', 'erlang', 'error', 'espresso', 'event', 'evented', 'example', 'exchange', 'exercise', 'experiment', 'expire', 'exploit', 'explorer', 'export', 'exporter', 'expres', 'ext-', 'ext.', 'ext_', 'extended', 'extension', 'external', 'extra', 'extractor', 'fabric', 'facebook', 'factory', 'fake', 'fast', 'feature', 'feed', 'fewfwef', 'ffmpeg', 'field', 'file', 'filter', 'find', 'finder', 'firefox', 'firmware', 'first', 'fish', 'fix-', 'fix_', 'flash', 'flask', 'flat', 'flex', 'flexible', 'flickr', 'flow', 'fluent', 'fluentd', 'fluid', 'folder', 'font', 'force', 'foreman', 'fork', 'form', 'format', 'formatter', 'forum', 'foundry', 'framework', 'free', 'friend', 'friendly', 'front-end', 'frontend', 'ftp-', 'ftp.', 'ftp_', 'fuel', 'full', 'fun-', 'fun.', 'fun_', 'func', 'future', 'gaia', 'gallery', 'game', 'gateway', 'gem-', 'gem.', 'gem_', 'gen-', 'gen.', 'gen_', 'general', 'generator', 'generic', 'genetic', 'get-', 'get.', 'get_', 'getenv', 'getting', 'ghost', 'gist', 'git-', 'git.', 'git_', 'github', 'gitignore', 'gitlab', 'glas', 'gmail', 'gnome', 'gnu-', 'gnu.', 'gnu_', 'goal', 'golang', 'gollum', 'good', 'google', 'gpu-', 'gpu.', 'gpu_', 'gradle', 'grail', 'graph', 'graphic', 'great', 'grid', 'groovy', 'group', 'grunt', 'guard', 'gui-', 'gui.', 'gui_', 'guide', 'guideline', 'gulp', 'gwt-', 'gwt.', 'gwt_', 'hack', 'hackathon', 'hacker', 'hacking', 'hadoop', 'haml', 'handler', 'hardware', 'has-', 'has_', 'hash', 'haskell', 'have', 'haxe', 'hello', 'help', 'helper', 'here', 'hero', 'heroku', 'high', 'hipchat', 'history', 'home', 'homebrew', 'homepage', 'hook', 'host', 'hosting', 'hot-', 'hot.', 'hot_', 'house', 'how-', 'how.', 'how_', 'html', 'http', 'hub-', 'hub.', 'hub_', 'hubot', 'human', 'icon', 'ide-', 'ide.', 'ide_', 'idea', 'identity', 'idiomatic', 'image', 'impact', 'import', 'important', 'importer', 'impres', 'index', 'infinite', 'info', 'injection', 'inline', 'input', 'inside', 'inspector', 'instagram', 'install', 'installer', 'instant', 'intellij', 'interface', 'internet', 'interview', 'into', 'intro', 'ionic', 'iphone', 'ipython', 'irc-', 'irc_', 'iso-', 'iso.', 'iso_', 'issue', 'jade', 'jasmine', 'java', 'jbos', 'jekyll', 'jenkin', 'jetbrains', 'job-', 'job.', 'job_', 'joomla', 'jpa-', 'jpa.', 'jpa_', 'jquery', 'json', 'just', 'kafka', 'karma', 'kata', 'kernel', 'keyboard', 'kindle', 'kit-', 'kit.', 'kit_', 'kitchen', 'knife', 'koan', 'kohana', 'lab-', 'lab.', 'lab_', 'lambda', 'lamp', 'language', 'laravel', 'last', 'latest', 'latex', 'launcher', 'layer', 'layout', 'lazy', 'ldap', 'leaflet', 'league', 'learn', 'learning', 'led-', 'led.', 'led_', 'leetcode', 'les-', 'les.', 'les_', 'level', 'leveldb', 'lib-', 'lib.', 'lib_', 'librarie', 'library', 'license', 'life', 'liferay', 'light', 'lightbox', 'like', 'line', 'link', 'linked', 'linkedin', 'linux', 'lisp', 'list', 'lite', 'little', 'load', 'loader', 'local', 'location', 'lock', 'log-', 'log.', 'log_', 'logger', 'logging', 'logic', 'login', 'logstash', 'longer', 'look', 'love', 'lua-', 'lua.', 'lua_', 'mac-', 'mac.', 'mac_', 'machine', 'made', 'magento', 'magic', 'mail', 'make', 'maker', 'making', 'man-', 'man.', 'man_', 'manage', 'manager', 'manifest', 'manual', 'map-', 'map.', 'map_', 'mapper', 'mapping', 'markdown', 'markup', 'master', 'math', 'matrix', 'maven', 'md5', 'mean', 'media', 'mediawiki', 'meetup', 'memcached', 'memory', 'menu', 'merchant', 'message', 'messaging', 'meta', 'metadata', 'meteor', 'method', 'metric', 'micro', 'middleman', 'migration', 'minecraft', 'miner', 'mini', 'minimal', 'mirror', 'mit-', 'mit.', 'mit_', 'mobile', 'mocha', 'mock', 'mod-', 'mod.', 'mod_', 'mode', 'model', 'modern', 'modular', 'module', 'modx', 'money', 'mongo', 'mongodb', 'mongoid', 'mongoose', 'monitor', 'monkey', 'more', 'motion', 'moved', 'movie', 'mozilla', 'mqtt', 'mule', 'multi', 'multiple', 'music', 'mustache', 'mvc-', 'mvc.', 'mvc_', 'mysql', 'nagio', 'name', 'native', 'need', 'neo-', 'neo.', 'neo_', 'nest', 'nested', 'net-', 'net.', 'net_', 'nette', 'network', 'new-', 'new.', 'new_', 'next', 'nginx', 'ninja', 'nlp-', 'nlp.', 'nlp_', 'node', 'nodej', 'nosql', 'not-', 'not.', 'not_', 'note', 'notebook', 'notepad', 'notice', 'notifier', 'now-', 'now.', 'now_', 'number', 'oauth', 'object', 'objective', 'obsolete', 'ocaml', 'octopres', 'official', 'old-', 'old.', 'old_', 'onboard', 'online', 'only', 'open', 'opencv', 'opengl', 'openshift', 'openwrt', 'option', 'oracle', 'org-', 'org.', 'org_', 'origin', 'original', 'orm-', 'orm.', 'orm_', 'osx-', 'osx_', 'our-', 'our.', 'our_', 'out-', 'out.', 'out_', 'output', 'over', 'overview', 'own-', 'own.', 'own_', 'pack', 'package', 'packet', 'page', 'panel', 'paper', 'paperclip', 'para', 'parallax', 'parallel', 'parse', 'parser', 'parsing', 'particle', 'party', 'password', 'patch', 'path', 'pattern', 'payment', 'paypal', 'pdf-', 'pdf.', 'pdf_', 'pebble', 'people', 'perl', 'personal', 'phalcon', 'phoenix', 'phone', 'phonegap', 'photo', 'php-', 'php.', 'php_', 'physic', 'picker', 'pipeline', 'platform', 'play', 'player', 'please', 'plu-', 'plu.', 'plu_', 'plug-in', 'plugin', 'plupload', 'png-', 'png.', 'png_', 'poker', 'polyfill', 'polymer', 'pool', 'pop-', 'pop.', 'pop_', 'popcorn', 'popup', 'port', 'portable', 'portal', 'portfolio', 'post', 'power', 'powered', 'powerful', 'prelude', 'pretty', 'preview', 'principle', 'print', 'pro-', 'pro.', 'pro_', 'problem', 'proc', 'product', 'profile', 'profiler', 'program', 'progres', 'project', 'protocol', 'prototype', 'provider', 'proxy', 'public', 'pull', 'puppet', 'pure', 'purpose', 'push', 'pusher', 'pyramid', 'python', 'quality', 'query', 'queue', 'quick', 'rabbitmq', 'rack', 'radio', 'rail', 'railscast', 'random', 'range', 'raspberry', 'rdf-', 'rdf.', 'rdf_', 'react', 'reactive', 'read', 'reader', 'readme', 'ready', 'real', 'real-time', 'reality', 'realtime', 'recipe', 'recorder', 'red-', 'red.', 'red_', 'reddit', 'redi', 'redmine', 'reference', 'refinery', 'refresh', 'registry', 'related', 'release', 'remote', 'rendering', 'repo', 'report', 'request', 'require', 'required', 'requirej', 'research', 'resource', 'response', 'resque', 'rest', 'restful', 'resume', 'reveal', 'reverse', 'review', 'riak', 'rich', 'right', 'ring', 'robot', 'role', 'room', 'router', 'routing', 'rpc-', 'rpc.', 'rpc_', 'rpg-', 'rpg.', 'rpg_', 'rspec', 'ruby-', 'ruby.', 'ruby_', 'rule', 'run-', 'run.', 'run_', 'runner', 'running', 'runtime', 'rust', 'rvm-', 'rvm.', 'rvm_', 'salt', 'sample', 'sandbox', 'sas-', 'sas.', 'sas_', 'sbt-', 'sbt.', 'sbt_', 'scala', 'scalable', 'scanner', 'schema', 'scheme', 'school', 'science', 'scraper', 'scratch', 'screen', 'script', 'scroll', 'scs-', 'scs.', 'scs_', 'sdk-', 'sdk.', 'sdk_', 'sdl-', 'sdl.', 'sdl_', 'search', 'secure', 'security', 'see-', 'see.', 'see_', 'seed', 'select', 'selector', 'selenium', 'semantic', 'sencha', 'send', 'sentiment', 'serie', 'server', 'service', 'session', 'set-', 'set.', 'set_', 'setting', 'setup', 'sha1', 'sha2', 'sha256', 'share', 'shared', 'sharing', 'sheet', 'shell', 'shield', 'shipping', 'shop', 'shopify', 'shortener', 'should', 'show', 'showcase', 'side', 'silex', 'simple', 'simulator', 'single', 'site', 'skeleton', 'sketch', 'skin', 'slack', 'slide', 'slider', 'slim', 'small', 'smart', 'smtp', 'snake', 'snapshot', 'snippet', 'soap', 'social', 'socket', 'software', 'solarized', 'solr', 'solution', 'solver', 'some', 'soon', 'source', 'space', 'spark', 'spatial', 'spec', 'sphinx', 'spine', 'spotify', 'spree', 'spring', 'sprite', 'sql-', 'sql.', 'sql_', 'sqlite', 'ssh-', 'ssh.', 'ssh_', 'stack', 'staging', 'standard', 'stanford', 'start', 'started', 'starter', 'startup', 'stat', 'statamic', 'state', 'static', 'statistic', 'statsd', 'statu', 'steam', 'step', 'still', 'stm-', 'stm.', 'stm_', 'storage', 'store', 'storm', 'story', 'strategy', 'stream', 'streaming', 'string', 'stripe', 'structure', 'studio', 'study', 'stuff', 'style', 'sublime', 'sugar', 'suite', 'summary', 'super', 'support', 'supported', 'svg-', 'svg.', 'svg_', 'svn-', 'svn.', 'svn_', 'swagger', 'swift', 'switch', 'switcher', 'symfony', 'symphony', 'sync', 'synopsi', 'syntax', 'system', 'tab-', 'tab.', 'tab_', 'table', 'tag-', 'tag.', 'tag_', 'talk', 'target', 'task', 'tcp-', 'tcp.', 'tcp_', 'tdd-', 'tdd.', 'tdd_', 'team', 'tech', 'template', 'term', 'terminal', 'testing', 'tetri', 'text', 'textmate', 'theme', 'theory', 'three', 'thrift', 'time', 'timeline', 'timer', 'tiny', 'tinymce', 'tip-', 'tip.', 'tip_', 'title', 'todo', 'todomvc', 'token', 'tool', 'toolbox', 'toolkit', 'top-', 'top.', 'top_', 'tornado', 'touch', 'tower', 'tracker', 'tracking', 'traffic', 'training', 'transfer', 'translate', 'transport', 'tree', 'trello', 'try-', 'try.', 'try_', 'tumblr', 'tut-', 'tut.', 'tut_', 'tutorial', 'tweet', 'twig', 'twitter', 'type', 'typo', 'ubuntu', 'uiview', 'ultimate', 'under', 'unit', 'unity', 'universal', 'unix', 'update', 'updated', 'upgrade', 'upload', 'uploader', 'uri-', 'uri.', 'uri_', 'url-', 'url.', 'url_', 'usage', 'usb-', 'usb.', 'usb_', 'use-', 'use.', 'use_', 'used', 'useful', 'user', 'using', 'util', 'utilitie', 'utility', 'vagrant', 'validator', 'value', 'variou', 'varnish', 'version', 'via-', 'via.', 'via_', 'video', 'view', 'viewer', 'vim-', 'vim.', 'vim_', 'vimrc', 'virtual', 'vision', 'visual', 'vpn', 'want', 'warning', 'watch', 'watcher', 'wave', 'way-', 'way.', 'way_', 'weather', 'web-', 'web_', 'webapp', 'webgl', 'webhook', 'webkit', 'webrtc', 'website', 'websocket', 'welcome', 'what', "what'", 'when', 'where', 'which', 'why-', 'why.', 'why_', 'widget', 'wifi', 'wiki', 'win-', 'win.', 'win_', 'window', 'wip-', 'wip.', 'wip_', 'within', 'without', 'wizard', 'word', 'wordpres', 'work', 'worker', 'workflow', 'working', 'workshop', 'world', 'wrapper', 'write', 'writer', 'writing', 'written', 'www-', 'www.', 'www_', 'xamarin', 'xcode', 'xml-', 'xml.', 'xml_', 'xmpp', 'xxxxxx', 'yahoo', 'yaml', 'yandex', 'yeoman', 'yet-', 'yet.', 'yet_', 'yii-', 'yii.', 'yii_', 'youtube', 'yui-', 'yui.', 'yui_', 'zend', 'zero', 'zip-', 'zip.', 'zip_', 'zsh-', 'zsh.', 'zsh_'), False, False), ('line', ('--mount=type=secret,', 'import[ \\t]+{[ \\t\\w,]+}[ \\t]+from[ \\t]+[\'"][^\'"]+[\'"]'), (), False, False), ('line', ('LICENSE[^=]*=\\s*"[^"]+', 'LIC_FILES_CHKSUM[^=]*=\\s*"[^"]+', 'SRC[^=]*=\\s*"[a-zA-Z0-9]+'), (), True, True)), 50),
    ('github-app-token', '(?:ghu|ghs)_[0-9a-zA-Z]{36}', ('ghs_', 'ghu_'), 3.0, 0, (('secret', (), (), False, True),), 0),
    ('github-fine-grained-pat', 'github_pat_\\w{82}', ('github_pat_',), 3.0, 0, (), 0),
    ('github-oauth', 'gho_[0-9a-zA-Z]{36}', ('gho_',), 3.0, 0, (), 0),
    ('github-pat', 'ghp_[0-9a-zA-Z]{36}', ('ghp_',), 3.0, 0, (('secret', (), (), False, True),), 0),
    ('github-refresh-token', 'ghr_[0-9a-zA-Z]{36}', ('ghr_',), 3.0, 0, (), 0),
    ('gitlab-cicd-job-token', 'glcbt-[0-9a-zA-Z]{1,5}_[0-9a-zA-Z_-]{20}', ('glcbt-',), 3.0, 0, (), 0),
    ('gitlab-deploy-token', 'gldt-[0-9a-zA-Z_\\-]{20}', ('gldt-',), 3.0, 0, (), 0),
    ('gitlab-feature-flag-client-token', 'glffct-[0-9a-zA-Z_\\-]{20}', ('glffct-',), 3.0, 0, (), 0),
    ('gitlab-feed-token', 'glft-[0-9a-zA-Z_\\-]{20}', ('glft-',), 3.0, 0, (), 0),
    ('gitlab-incoming-mail-token', 'glimt-[0-9a-zA-Z_\\-]{25}', ('glimt-',), 3.0, 0, (), 0),
    ('gitlab-kubernetes-agent-token', 'glagent-[0-9a-zA-Z_\\-]{50}', ('glagent-',), 3.0, 0, (), 0),
    ('gitlab-oauth-app-secret', 'gloas-[0-9a-zA-Z_\\-]{64}', ('gloas-',), 3.0, 0, (), 0),
    ('gitlab-pat', 'glpat-[\\w-]{20}', ('glpat-',), 3.0, 0, (), 0),
    ('gitlab-pat-routable', '\\bglpat-[0-9a-zA-Z_-]{27,300}\\.[0-9a-z]{2}[0-9a-z]{7}\\b', ('glpat-',), 4.0, 0, (), 0),
    ('gitlab-ptt', 'glptt-[0-9a-f]{40}', ('glptt-',), 3.0, 0, (), 0),
    ('gitlab-rrt', 'GR1348941[\\w-]{20}', ('gr1348941',), 3.0, 0, (), 0),
    ('gitlab-runner-authentication-token', 'glrt-[0-9a-zA-Z_\\-]{20}', ('glrt-',), 3.0, 0, (), 0),
    ('gitlab-runner-authentication-token-routable', '\\bglrt-t\\d_[0-9a-zA-Z_\\-]{27,300}\\.[0-9a-z]{2}[0-9a-z]{7}\\b', ('glrt-',), 4.0, 0, (), 0),
    ('gitlab-scim-token', 'glsoat-[0-9a-zA-Z_\\-]{20}', ('glsoat-',), 3.0, 0, (), 0),
    ('gitlab-session-cookie', '_gitlab_session=[0-9a-z]{32}', ('_gitlab_session=',), 3.0, 0, (), 0),
    ('gitter-access-token', '(?i)(?:gitter)(?:[ \\t\\w.-]{0,20})[\\s\'"]{0,3}(?:=|>|:{1,3}=|\\|\\||:|=>|\\?=|,)[\\x60\'"\\s=]{0,5}([a-z0-9_-]{40})(?:[\\x60\'"\\s;]|\\\\[nr]|$)', ('gitter',), 0.0, 0, (), 50),
    ('gocardless-api-token', '(?i)(?:gocardless)(?:[ \\t\\w.-]{0,20})[\\s\'"]{0,3}(?:=|>|:{1,3}=|\\|\\||:|=>|\\?=|,)[\\x60\'"\\s=]{0,5}(live_(?i:[a-z0-9\\-_=]{40}))(?:[\\x60\'"\\s;]|\\\\[nr]|$)', ('gocardless', 'live_'), 0.0, 0, (), 50),
    ('grafana-api-key', '(?i)\\b(eyJrIjoi[A-Za-z0-9]{70,400}={0,3})(?:[\\x60\'"\\s;]|\\\\[nr]|$)', ('eyjrijoi',), 3.0, 0, (), 0),
    ('grafana-cloud-api-token', '(?i)\\b(glc_[A-Za-z0-9+/]{32,400}={0,3})(?:[\\x60\'"\\s;]|\\\\[nr]|$)', ('glc_',), 3.0, 0, (), 0),
    ('grafana-service-account-token', '(?i)\\b(glsa_[A-Za-z0-9]{32}_[A-Fa-f0-9]{8})(?:[\\x60\'"\\s;]|\\\\[nr]|$)', ('glsa_',), 3.0, 0, (), 0),
    ('harness-api-key', '(?:pat|sat)\\.[a-zA-Z0-9_-]{22}\\.[a-zA-Z0-9]{24}\\.[a-zA-Z0-9]{20}', ('pat.', 'sat.'), 0.0, 0, (), 0),
    ('hashicorp-tf-api-token', '(?i)[a-z0-9]{14}\\.(?-i:atlasv1)\\.[a-z0-9\\-_=]{60,70}', ('atlasv1',), 3.5, 0, (), 0),
    ('hashicorp-tf-password', '(?i)(?:administrator_login_password|password)(?:[ \\t\\w.-]{0,20})[\\s\'"]{0,3}(?:=|>|:{1,3}=|\\|\\||:|=>|\\?=|,)[\\x60\'"\\s=]{0,5}("[a-z0-9=_\\-]{8,20}")(?:[\\x60\'"\\s;]|\\\\[nr]|$)', ('administrator_login_password', 'password'), 2.0, 0, (), 50),
    ('heroku-api-key', '(?i)(?:heroku)(?:[ \\t\\w.-]{0,20})[\\s\'"]{0,3}(?:=|>|:{1,3}=|\\|\\||:|=>|\\?=|,)[\\x60\'"\\s=]{0,5}([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})(?:[\\x60\'"\\s;]|\\\\[nr]|$)', ('heroku',), 0.0, 0, (), 50),
    ('heroku-api-key-v2', '\\b((HRKU-AA[0-9a-zA-Z_-]{58}))(?:[\\x60\'"\\s;]|\\\\[nr]|$)', ('hrku-aa',), 4.0, 0, (), 0),
    ('hubspot-api-key', '(?i)(?:hubspot)(?:[ \\t\\w.-]{0,20})[\\s\'"]{0,3}(?:=|>|:{1,3}=|\\|\\||:|=>|\\?=|,)[\\x60\'"\\s=]{0,5}([0-9A-F]{8}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{12})(?:[\\x60\'"\\s;]|\\\\[nr]|$)', ('hubspot',), 0.0, 0, (), 50),
    ('huggingface-access-token', '\\b(hf_(?i:[a-z]{34}))(?:[\\x60\'"\\s;]|\\\\[nr]|$)', ('hf_',), 2.0, 0, (), 0),
    ('huggingface-organization-api-token', '\\b(api_org_(?i:[a-z]{34}))(?:[\\x60\'"\\s;]|\\\\[nr]|$)', ('api_org_',), 2.0, 0, (), 0),
    ('infracost-api-token', '\\b(ico-[a-zA-Z0-9]{32})(?:[\\x60\'"\\s;]|\\\\[nr]|$)', ('ico-',), 3.0, 0, (), 0),
    ('intercom-api-key', '(?i)(?:intercom)(?:[ \\t\\w.-]{0,20})[\\s\'"]{0,3}(?:=|>|:{1,3}=|\\|\\||:|=>|\\?=|,)[\\x60\'"\\s=]{0,5}([a-z0-9=_\\-]{60})(?:[\\x60\'"\\s;]|\\\\[nr]|$)', ('intercom',), 0.0, 0, (), 50),
    ('intra42-client-secret', '\\b(s-s4t2(?:ud|af)-(?i:[abcdef0123456789]{64}))(?:[\\x60\'"\\s;]|\\\\[nr]|$)', ('intra', 's-s4t2af-', 's-s4t2ud-'), 3.0, 0, (), 0),
    ('jfrog-api-key', '(?i)(?:jfrog|artifactory|bintray|xray)(?:[ \\t\\w.-]{0,20})[\\s\'"]{0,3}(?:=|>|:{1,3}=|\\|\\||:|=>|\\?=|,)[\\x60\'"\\s=]{0,5}([a-z0-9]{73})(?:[\\x60\'"\\s;]|\\\\[nr]|$)', ('artifactory', 'bintray', 'jfrog', 'xray'), 0.0, 0, (), 50),
    ('jfrog-identity-token', '(?i)(?:jfrog|artifactory|bintray|xray)(?:[ \\t\\w.-]{0,20})[\\s\'"]{0,3}(?:=|>|:{1,3}=|\\|\\||:|=>|\\?=|,)[\\x60\'"\\s=]{0,5}([a-z0-9]{64})(?:[\\x60\'"\\s;]|\\\\[nr]|$)', ('artifactory', 'bintray', 'jfrog', 'xray'), 0.0, 0, (), 50),
    ('jwt', '\\b(ey[a-zA-Z0-9]{17,}\\.ey[a-zA-Z0-9\\/\\\\_-]{17,}\\.(?:[a-zA-Z0-9\\/\\\\_-]{10,}={0,2})?)(?:[\\x60\'"\\s;]|\\\\[nr]|$)', ('ey',), 3.0, 0, (), 0),
    ('jwt-base64', '\\bZXlK(?:(?P<alg>aGJHY2lPaU)|(?P<apu>aGNIVWlPaU)|(?P<apv>aGNIWWlPaU)|(?P<aud>aGRXUWlPaU)|(?P<b64>aU5qUWlP)|(?P<crit>amNtbDBJanBi)|(?P<cty>amRIa2lPaU)|(?P<epk>bGNHc2lPbn)|(?P<enc>bGJtTWlPaU)|(?P<jku>cWEzVWlPaU)|(?P<jwk>cWQyc2lPb)|(?P<iss>cGMzTWlPaU)|(?P<iv>cGRpSTZJ)|(?P<kid>cmFXUWlP)|(?P<key_ops>clpYbGZiM0J6SWpwY)|(?P<kty>cmRIa2lPaUp)|(?P<nonce>dWIyNWpaU0k2)|(?P<p2c>d01tTWlP)|(?P<p2s>d01uTWlPaU)|(?P<ppt>d2NIUWlPaU)|(?P<sub>emRXSWlPaU)|(?P<svt>emRuUWlP)|(?P<tag>MFlXY2lPaU)|(?P<typ>MGVYQWlPaUp)|(?P<url>MWNtd2l)|(?P<use>MWMyVWlPaUp)|(?P<ver>MlpYSWlPaU)|(?P<version>MlpYSnphVzl1SWpv)|(?P<x>NElqb2)|(?P<x5c>NE5XTWlP)|(?P<x5t>NE5YUWlPaU)|(?P<x5ts256>NE5YUWpVekkxTmlJNkl)|(?P<x5u>NE5YVWlPaU)|(?P<zip>NmFYQWlPaU))[a-zA-Z0-9\\/\\\\_+\\-\\r\\n]{40,}={0,2}', ('zxlk',), 2.0, 0, (), 0),
    ('kraken-access-token', '(?i)(?:kraken)(?:[ \\t\\w.-]{0,20})[\\s\'"]{0,3}(?:=|>|:{1,3}=|\\|\\||:|=>|\\?=|,)[\\x60\'"\\s=]{0,5}([a-z0-9\\/=_\\+\\-]{80,90})(?:[\\x60\'"\\s;]|\\\\[nr]|$)', ('kraken',), 0.0, 0, (), 50),
    ('kubernetes-secret-yaml', '(?i)(?:\\bkind:[ \\t]*["\']?\\bsecret\\b["\']?(?s:.){0,200}?\\bdata:(?s:.){0,100}?\\s+([\\w.-]+:(?:[ \\t]*(?:\\||>[-+]?)\\s+)?[ \\t]*(?:["\']?[a-z0-9+/]{10,}={0,3}["\']?|\\{\\{[ \\t\\w"|$:=,.-]+}}|""|\'\'))|\\bdata:(?s:.){0,100}?\\s+([\\w.-]+:(?:[ \\t]*(?:\\||>[-+]?)\\s+)?[ \\t]*(?:["\']?[a-z0-9+/]{10,}={0,3}["\']?|\\{\\{[ \\t\\w"|$:=,.-]+}}|""|\'\'))(?s:.){0,200}?\\bkind:[ \\t]*["\']?\\bsecret\\b["\']?)', ('secret',), 0.0, 0, (('secret', ('[\\w.-]+:(?:[ \\t]*(?:\\||>[-+]?)\\s+)?[ \\t]*(?:\\{\\{[ \\t\\w"|$:=,.-]+}}|""|\'\')',), (), False, False), ('match', ('(kind:(?s:.)+\\n---\\n(?s:.)+\\bdata:|data:(?s:.)+\\n---\\n(?s:.)+\\bkind:)',), (), False, False)), 0),
    ('kucoin-access-token', '(?i)(?:kucoin)(?:[ \\t\\w.-]{0,20})[\\s\'"]{0,3}(?:=|>|:{1,3}=|\\|\\||:|=>|\\?=|,)[\\x60\'"\\s=]{0,5}([a-f0-9]{24})(?:[\\x60\'"\\s;]|\\\\[nr]|$)', ('kucoin',), 0.0, 0, (), 50),
    ('kucoin-secret-key', '(?i)(?:kucoin)(?:[ \\t\\w.-]{0,20})[\\s\'"]{0,3}(?:=|>|:{1,3}=|\\|\\||:|=>|\\?=|,)[\\x60\'"\\s=]{0,5}([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})(?:[\\x60\'"\\s;]|\\\\[nr]|$)', ('kucoin',), 0.0, 0, (), 50),
    ('launchdarkly-access-token', '(?i)(?:launchdarkly)(?:[ \\t\\w.-]{0,20})[\\s\'"]{0,3}(?:=|>|:{1,3}=|\\|\\||:|=>|\\?=|,)[\\x60\'"\\s=]{0,5}([a-z0-9=_\\-]{40})(?:[\\x60\'"\\s;]|\\\\[nr]|$)', ('launchdarkly',), 0.0, 0, (), 50),
    ('linear-api-key', 'lin_api_(?i:[a-z0-9]{40})', ('lin_api_',), 2.0, 0, (), 0),
    ('linear-client-secret', '(?i)(?:linear)(?:[ \\t\\w.-]{0,20})[\\s\'"]{0,3}(?:=|>|:{1,3}=|\\|\\||:|=>|\\?=|,)[\\x60\'"\\s=]{0,5}([a-f0-9]{32})(?:[\\x60\'"\\s;]|\\\\[nr]|$)', ('linear',), 2.0, 0, (), 50),
    ('linkedin-client-id', '(?i)(?:linked[_-]?in)(?:[ \\t\\w.-]{0,20})[\\s\'"]{0,3}(?:=|>|:{1,3}=|\\|\\||:|=>|\\?=|,)[\\x60\'"\\s=]{0,5}([a-z0-9]{14})(?:[\\x60\'"\\s;]|\\\\[nr]|$)', ('linked-in', 'linked_in', 'linkedin'), 2.0, 0, (), 50),
    ('linkedin-client-secret', '(?i)(?:linked[_-]?in)(?:[ \\t\\w.-]{0,20})[\\s\'"]{0,3}(?:=|>|:{1,3}=|\\|\\||:|=>|\\?=|,)[\\x60\'"\\s=]{0,5}([a-z0-9]{16})(?:[\\x60\'"\\s;]|\\\\[nr]|$)', ('linked-in', 'linked_in', 'linkedin'), 2.0, 0, (), 50),
    ('lob-api-key', '(?i)(?:lob)(?:[ \\t\\w.-]{0,20})[\\s\'"]{0,3}(?:=|>|:{1,3}=|\\|\\||:|=>|\\?=|,)[\\x60\'"\\s=]{0,5}((live|test)_[a-f0-9]{35})(?:[\\x60\'"\\s;]|\\\\[nr]|$)', ('live_', 'test_'), 0.0, 0, (), 50),
    ('lob-pub-api-key', '(?i)(?:lob)(?:[ \\t\\w.-]{0,20})[\\s\'"]{0,3}(?:=|>|:{1,3}=|\\|\\||:|=>|\\?=|,)[\\x60\'"\\s=]{0,5}((test|live)_pub_[a-f0-9]{31})(?:[\\x60\'"\\s;]|\\\\[nr]|$)', ('_pub', 'live_pub', 'test_pub'), 0.0, 0, (), 50),
    ('looker-client-id', '(?i)(?:looker)(?:[ \\t\\w.-]{0,20})[\\s\'"]{0,3}(?:=|>|:{1,3}=|\\|\\||:|=>|\\?=|,)[\\x60\'"\\s=]{0,5}([a-z0-9]{20})(?:[\\x60\'"\\s;]|\\\\[nr]|$)', ('looker',), 0.0, 0, (), 50),
    ('looker-client-secret', '(?i)(?:looker)(?:[ \\t\\w.-]{0,20})[\\s\'"]{0,3}(?:=|>|:{1,3}=|\\|\\||:|=>|\\?=|,)[\\x60\'"\\s=]{0,5}([a-z0-9]{24})(?:[\\x60\'"\\s;]|\\\\[nr]|$)', ('looker',), 0.0, 0, (), 50),
    ('mailchimp-api-key', '(?i)(?:MailchimpSDK.initialize|mailchimp)(?:[ \\t\\w.-]{0,20})[\\s\'"]{0,3}(?:=|>|:{1,3}=|\\|\\||:|=>|\\?=|,)[\\x60\'"\\s=]{0,5}([a-f0-9]{32}-us\\d\\d)(?:[\\x60\'"\\s;]|\\\\[nr]|$)', ('mailchimp',), 0.0, 0, (), 50),
    ('mailgun-private-api-token', '(?i)(?:mailgun)(?:[ \\t\\w.-]{0,20})[\\s\'"]{0,3}(?:=|>|:{1,3}=|\\|\\||:|=>|\\?=|,)[\\x60\'"\\s=]{0,5}(key-[a-f0-9]{32})(?:[\\x60\'"\\s;]|\\\\[nr]|$)', ('mailgun',), 0.0, 0, (), 50),
    ('mailgun-pub-key', '(?i)(?:mailgun)(?:[ \\t\\w.-]{0,20})[\\s\'"]{0,3}(?:=|>|:{1,3}=|\\|\\||:|=>|\\?=|,)[\\x60\'"\\s=]{0,5}(pubkey-[a-f0-9]{32})(?:[\\x60\'"\\s;]|\\\\[nr]|$)', ('mailgun',), 0.0, 0, (), 50),
    ('mailgun-signing-key', '(?i)(?:mailgun)(?:[ \\t\\w.-]{0,20})[\\s\'"]{0,3}(?:=|>|:{1,3}=|\\|\\||:|=>|\\?=|,)[\\x60\'"\\s=]{0,5}([a-h0-9]{32}-[a-h0-9]{8}-[a-h0-9]{8})(?:[\\x60\'"\\s;]|\\\\[nr]|$)', ('mailgun',), 0.0, 0, (), 50),
    ('mapbox-api-token', '(?i)(?:mapbox)(?:[ \\t\\w.-]{0,20})[\\s\'"]{0,3}(?:=|>|:{1,3}=|\\|\\||:|=>|\\?=|,)[\\x60\'"\\s=]{0,5}(pk\\.[a-z0-9]{60}\\.[a-z0-9]{22})(?:[\\x60\'"\\s;]|\\\\[nr]|$)', ('mapbox',), 0.0, 0, (), 50),
    ('mattermost-access-token', '(?i)(?:mattermost)(?:[ \\t\\w.-]{0,20})[\\s\'"]{0,3}(?:=|>|:{1,3}=|\\|\\||:|=>|\\?=|,)[\\x60\'"\\s=]{0,5}([a-z0-9]{26})(?:[\\x60\'"\\s;]|\\\\[nr]|$)', ('mattermost',), 0.0, 0, (), 50),
    ('maxmind-license-key', '\\b([A-Za-z0-9]{6}_[A-Za-z0-9]{29}_mmk)(?:[\\x60\'"\\s;]|\\\\[nr]|$)', ('_mmk',), 4.0, 0, (), 0),
    ('messagebird-api-token', '(?i)(?:message[_-]?bird)(?:[ \\t\\w.-]{0,20})[\\s\'"]{0,3}(?:=|>|:{1,3}=|\\|\\||:|=>|\\?=|,)[\\x60\'"\\s=]{0,5}([a-z0-9]{25})(?:[\\x60\'"\\s;]|\\\\[nr]|$)', ('message-bird', 'message_bird', 'messagebird'), 0.0, 0, (), 50),
    ('messagebird-client-id', '(?i)(?:message[_-]?bird)(?:[ \\t\\w.-]{0,20})[\\s\'"]{0,3}(?:=|>|:{1,3}=|\\|\\||:|=>|\\?=|,)[\\x60\'"\\s=]{0,5}([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})(?:[\\x60\'"\\s;]|\\\\[nr]|$)', ('message-bird', 'message_bird', 'messagebird'), 0.0, 0, (), 50),
    ('microsoft-teams-webhook', 'https://[a-z0-9]+\\.webhook\\.office\\.com/webhookb2/[a-z0-9]{8}-([a-z0-9]{4}-){3}[a-z0-9]{12}@[a-z0-9]{8}-([a-z0-9]{4}-){3}[a-z0-9]{12}/IncomingWebhook/[a-z0-9]{32}/[a-z0-9]{8}-([a-z0-9]{4}-){3}[a-z0-9]{12}', ('incomingwebhook', 'webhook.office.com', 'webhookb2'), 0.0, 0, (), 0),
    ('netlify-access-token', '(?i)(?:netlify)(?:[ \\t\\w.-]{0,20})[\\s\'"]{0,3}(?:=|>|:{1,3}=|\\|\\||:|=>|\\?=|,)[\\x60\'"\\s=]{0,5}([a-z0-9=_\\-]{40,46})(?:[\\x60\'"\\s;]|\\\\[nr]|$)', ('netlify',), 0.0, 0, (), 50),
    ('new-relic-browser-api-token', '(?i)(?:new-relic|newrelic|new_relic)(?:[ \\t\\w.-]{0,20})[\\s\'"]{0,3}(?:=|>|:{1,3}=|\\|\\||:|=>|\\?=|,)[\\x60\'"\\s=]{0,5}(NRJS-[a-f0-9]{19})(?:[\\x60\'"\\s;]|\\\\[nr]|$)', ('nrjs-',), 0.0, 0, (), 50),
    ('new-relic-insert-key', '(?i)(?:new-relic|newrelic|new_relic)(?:[ \\t\\w.-]{0,20})[\\s\'"]{0,3}(?:=|>|:{1,3}=|\\|\\||:|=>|\\?=|,)[\\x60\'"\\s=]{0,5}(NRII-[a-z0-9-]{32})(?:[\\x60\'"\\s;]|\\\\[nr]|$)', ('nrii-',), 0.0, 0, (), 50),
    ('new-relic-user-api-id', '(?i)(?:new-relic|newrelic|new_relic)(?:[ \\t\\w.-]{0,20})[\\s\'"]{0,3}(?:=|>|:{1,3}=|\\|\\||:|=>|\\?=|,)[\\x60\'"\\s=]{0,5}([a-z0-9]{64})(?:[\\x60\'"\\s;]|\\\\[nr]|$)', ('new-relic', 'new_relic', 'newrelic'), 0.0, 0, (), 50),
    ('new-relic-user-api-key', '(?i)(?:new-relic|newrelic|new_relic)(?:[ \\t\\w.-]{0,20})[\\s\'"]{0,3}(?:=|>|:{1,3}=|\\|\\||:|=>|\\?=|,)[\\x60\'"\\s=]{0,5}(NRAK-[a-z0-9]{27})(?:[\\x60\'"\\s;]|\\\\[nr]|$)', ('nrak',), 0.0, 0, (), 50),
    ('notion-api-token', '\\b(ntn_[0-9]{11}[A-Za-z0-9]{32}[A-Za-z0-9]{3})(?:[\\x60\'"\\s;]|\\\\[nr]|$)', ('ntn_',), 4.0, 0, (), 0),
    ('npm-access-token', '(?i)\\b(npm_[a-z0-9]{36})(?:[\\x60\'"\\s;]|\\\\[nr]|$)', ('npm_',), 2.0, 0, (), 0),
    ('nuget-config-password', '(?i)<add key=\\"(?:(?:ClearText)?Password)\\"\\s*value=\\"(.{8,})\\"\\s*/>', ('<add key=',), 1.0, 0, (('secret', ('33f!!lloppa', 'hal\\+9ooo_da!sY', '^\\%\\S.*\\%$'), (), False, False),), 0),
    ('nytimes-access-token', '(?i)(?:nytimes|new-york-times,|newyorktimes)(?:[ \\t\\w.-]{0,20})[\\s\'"]{0,3}(?:=|>|:{1,3}=|\\|\\||:|=>|\\?=|,)[\\x60\'"\\s=]{0,5}([a-z0-9=_\\-]{32})(?:[\\x60\'"\\s;]|\\\\[nr]|$)', ('new-york-times', 'newyorktimes', 'nytimes'), 0.0, 0, (), 50),
    ('octopus-deploy-api-key', '\\b(API-[A-Z0-9]{26})(?:[\\x60\'"\\s;]|\\\\[nr]|$)', ('api-',), 3.0, 0, (), 0),
    ('okta-access-token', '(?i:[\\w.-]{0,50}?(?:(?-i:[Oo]kta|OKTA))(?:[ \\t\\w.-]{0,20})[\\s\'"]{0,3})(?:=|>|:{1,3}=|\\|\\||:|=>|\\?=|,)[\\x60\'"\\s=]{0,5}(00[\\w=\\-]{40})(?:[\\x60\'"\\s;]|\\\\[nr]|$)', ('okta',), 4.0, 0, (), 50),
    ('openai-api-key', '\\b(sk-(?:proj|svcacct|admin)-(?:[A-Za-z0-9_-]{74}|[A-Za-z0-9_-]{58})T3BlbkFJ(?:[A-Za-z0-9_-]{74}|[A-Za-z0-9_-]{58})\\b|sk-[a-zA-Z0-9]{20}T3BlbkFJ[a-zA-Z0-9]{20})(?:[\\x60\'"\\s;]|\\\\[nr]|$)', ('t3blbkfj',), 3.0, 0, (), 0),
    ('openshift-user-token', '\\b(sha256~[\\w-]{43})(?:[^\\w-]|\\Z)', ('sha256~',), 3.5, 0, (), 0),
    ('perplexity-api-key', '\\b(pplx-[a-zA-Z0-9]{48})(?:[\\x60\'"\\s;]|\\\\[nr]|$|\\b)', ('pplx-',), 4.0, 0, (), 0),
    ('plaid-api-token', '(?i)(?:plaid)(?:[ \\t\\w.-]{0,20})[\\s\'"]{0,3}(?:=|>|:{1,3}=|\\|\\||:|=>|\\?=|,)[\\x60\'"\\s=]{0,5}(access-(?:sandbox|development|production)-[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})(?:[\\x60\'"\\s;]|\\\\[nr]|$)', ('plaid',), 0.0, 0, (), 50),
    ('plaid-client-id', '(?i)(?:plaid)(?:[ \\t\\w.-]{0,20})[\\s\'"]{0,3}(?:=|>|:{1,3}=|\\|\\||:|=>|\\?=|,)[\\x60\'"\\s=]{0,5}([a-z0-9]{24})(?:[\\x60\'"\\s;]|\\\\[nr]|$)', ('plaid',), 3.5, 0, (), 50),
    ('plaid-secret-key', '(?i)(?:plaid)(?:[ \\t\\w.-]{0,20})[\\s\'"]{0,3}(?:=|>|:{1,3}=|\\|\\||:|=>|\\?=|,)[\\x60\'"\\s=]{0,5}([a-z0-9]{30})(?:[\\x60\'"\\s;]|\\\\[nr]|$)', ('plaid',), 3.5, 0, (), 50),
    ('planetscale-api-token', '\\b(pscale_tkn_(?i:[\\w=\\.-]{32,64}))(?:[\\x60\'"\\s;]|\\\\[nr]|$)', ('pscale_tkn_',), 3.0, 0, (), 0),
    ('planetscale-oauth-token', '\\b(pscale_oauth_[\\w=\\.-]{32,64})(?:[\\x60\'"\\s;]|\\\\[nr]|$)', ('pscale_oauth_',), 3.0, 0, (), 0),
    ('planetscale-password', '(?i)\\b(pscale_pw_(?i:[\\w=\\.-]{32,64}))(?:[\\x60\'"\\s;]|\\\\[nr]|$)', ('pscale_pw_',), 3.0, 0, (), 0),
    ('postman-api-token', '\\b(PMAK-(?i:[a-f0-9]{24}\\-[a-f0-9]{34}))(?:[\\x60\'"\\s;]|\\\\[nr]|$)', ('pmak-',), 3.0, 0, (), 0),
    ('prefect-api-token', '\\b(pnu_[a-zA-Z0-9]{36})(?:[\\x60\'"\\s;]|\\\\[nr]|$)', ('pnu_',), 2.0, 0, (), 0),
    ('private-key', '(?i)-----BEGIN[ A-Z0-9_-]{0,100}PRIVATE KEY(?: BLOCK)?-----[\\s\\S-]{64,}?KEY(?: BLOCK)?-----', ('-----begin',), 0.0, 0, (), 0),
    ('privateai-api-token', '(?i:[\\w.-]{0,50}?(?:private[_-]?ai)(?:[ \\t\\w.-]{0,20})[\\s\'"]{0,3})(?:=|>|:{1,3}=|\\|\\||:|=>|\\?=|,)[\\x60\'"\\s=]{0,5}([a-z0-9]{32})(?:[\\x60\'"\\s;]|\\\\[nr]|$)', ('private-ai', 'private_ai', 'privateai'), 3.0, 0, (), 50),
    ('pulumi-api-token', '\\b(pul-[a-f0-9]{40})(?:[\\x60\'"\\s;]|\\\\[nr]|$)', ('pul-',), 2.0, 0, (), 0),
    ('pypi-upload-token', 'pypi-AgEIcHlwaS5vcmc[\\w-]{50,1000}', ('pypi-ageichlwas5vcmc',), 3.0, 0, (), 0),
    ('rapidapi-access-token', '(?i)(?:rapidapi)(?:[ \\t\\w.-]{0,20})[\\s\'"]{0,3}(?:=|>|:{1,3}=|\\|\\||:|=>|\\?=|,)[\\x60\'"\\s=]{0,5}([a-z0-9_-]{50})(?:[\\x60\'"\\s;]|\\\\[nr]|$)', ('rapidapi',), 0.0, 0, (), 50),
    ('readme-api-token', '\\b(rdme_[a-z0-9]{70})(?:[\\x60\'"\\s;]|\\\\[nr]|$)', ('rdme_',), 2.0, 0, (), 0),
    ('rubygems-api-token', '\\b(rubygems_[a-f0-9]{48})(?:[\\x60\'"\\s;]|\\\\[nr]|$)', ('rubygems_',), 2.0, 0, (), 0),
    ('scalingo-api-token', '\\b(tk-us-[\\w-]{48})(?:[\\x60\'"\\s;]|\\\\[nr]|$)', ('tk-us-',), 2.0, 0, (), 0),
    ('sendbird-access-id', '(?i)(?:sendbird)(?:[ \\t\\w.-]{0,20})[\\s\'"]{0,3}(?:=|>|:{1,3}=|\\|\\||:|=>|\\?=|,)[\\x60\'"\\s=]{0,5}([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})(?:[\\x60\'"\\s;]|\\\\[nr]|$)', ('sendbird',), 0.0, 0, (), 50),
    ('sendbird-access-token', '(?i)(?:sendbird)(?:[ \\t\\w.-]{0,20})[\\s\'"]{0,3}(?:=|>|:{1,3}=|\\|\\||:|=>|\\?=|,)[\\x60\'"\\s=]{0,5}([a-f0-9]{40})(?:[\\x60\'"\\s;]|\\\\[nr]|$)', ('sendbird',), 0.0, 0, (), 50),
    ('sendgrid-api-token', '\\b(SG\\.(?i:[a-z0-9=_\\-\\.]{66}))(?:[\\x60\'"\\s;]|\\\\[nr]|$)', ('sg.',), 2.0, 0, (), 0),
    ('sendinblue-api-token', '\\b(xkeysib-[a-f0-9]{64}\\-(?i:[a-z0-9]{16}))(?:[\\x60\'"\\s;]|\\\\[nr]|$)', ('xkeysib-',), 2.0, 0, (), 0),
    ('sentry-access-token', '(?i)(?:sentry)(?:[ \\t\\w.-]{0,20})[\\s\'"]{0,3}(?:=|>|:{1,3}=|\\|\\||:|=>|\\?=|,)[\\x60\'"\\s=]{0,5}([a-f0-9]{64})(?:[\\x60\'"\\s;]|\\\\[nr]|$)', ('sentry',), 3.0, 0, (), 50),
    ('sentry-org-token', '\\bsntrys_eyJpYXQiO[a-zA-Z0-9+/]{10,200}(?:LCJyZWdpb25fdXJs|InJlZ2lvbl91cmwi|cmVnaW9uX3VybCI6)[a-zA-Z0-9+/]{10,200}={0,2}_[a-zA-Z0-9+/]{43}(?:[^a-zA-Z0-9+/]|\\Z)', ('sntrys_eyjpyxqio',), 4.5, 0, (), 0),
    ('sentry-user-token', '\\b(sntryu_[a-f0-9]{64})(?:[\\x60\'"\\s;]|\\\\[nr]|$)', ('sntryu_',), 3.5, 0, (), 0),
    ('settlemint-application-access-token', '\\b(sm_aat_[a-zA-Z0-9]{16})(?:[\\x60\'"\\s;]|\\\\[nr]|$)', ('sm_aat',), 3.0, 0, (), 0),
    ('settlemint-personal-access-token', '\\b(sm_pat_[a-zA-Z0-9]{16})(?:[\\x60\'"\\s;]|\\\\[nr]|$)', ('sm_pat',), 3.0, 0, (), 0),
    ('settlemint-service-access-token', '\\b(sm_sat_[a-zA-Z0-9]{16})(?:[\\x60\'"\\s;]|\\\\[nr]|$)', ('sm_sat',), 3.0, 0, (), 0),
    ('shippo-api-token', '\\b(shippo_(?:live|test)_[a-fA-F0-9]{40})(?:[\\x60\'"\\s;]|\\\\[nr]|$)', ('shippo_',), 2.0, 0, (), 0),
    ('shopify-access-token', 'shpat_[a-fA-F0-9]{32}', ('shpat_',), 2.0, 0, (), 0),
    ('shopify-custom-access-token', 'shpca_[a-fA-F0-9]{32}', ('shpca_',), 2.0, 0, (), 0),
    ('shopify-private-app-access-token', 'shppa_[a-fA-F0-9]{32}', ('shppa_',), 2.0, 0, (), 0),
    ('shopify-shared-secret', 'shpss_[a-fA-F0-9]{32}', ('shpss_',), 2.0, 0, (), 0),
    ('sidekiq-secret', '(?i)(?:BUNDLE_ENTERPRISE__CONTRIBSYS__COM|BUNDLE_GEMS__CONTRIBSYS__COM)(?:[ \\t\\w.-]{0,20})[\\s\'"]{0,3}(?:=|>|:{1,3}=|\\|\\||:|=>|\\?=|,)[\\x60\'"\\s=]{0,5}([a-f0-9]{8}:[a-f0-9]{8})(?:[\\x60\'"\\s;]|\\\\[nr]|$)', ('bundle_enterprise__contribsys__com', 'bundle_gems__contribsys__com'), 0.0, 0, (), 50),
    ('sidekiq-sensitive-url', '(?i)\\bhttps?://([a-f0-9]{8}:[a-f0-9]{8})@(?:gems.contribsys.com|enterprise.contribsys.com)(?:[\\/|\\#|\\?|:]|$)', ('enterprise.contribsys.com', 'gems.contribsys.com'), 0.0, 0, (), 0),
    ('slack-app-token', '(?i)xapp-\\d-[A-Z0-9]+-\\d+-[a-z0-9]+', ('xapp',), 2.0, 0, (), 0),
    ('slack-bot-token', 'xoxb-[0-9]{10,13}-[0-9]{10,13}[a-zA-Z0-9-]*', ('xoxb',), 3.0, 0, (), 0),
    ('slack-config-access-token', '(?i)xoxe.xox[bp]-\\d-[A-Z0-9]{163,166}', ('xoxe.xoxb-', 'xoxe.xoxp-'), 2.0, 0, (), 0),
    ('slack-config-refresh-token', '(?i)xoxe-\\d-[A-Z0-9]{146}', ('xoxe-',), 2.0, 0, (), 0),
    ('slack-legacy-bot-token', 'xoxb-[0-9]{8,14}-[a-zA-Z0-9]{18,26}', ('xoxb',), 2.0, 0, (), 0),
    ('slack-legacy-token', 'xox[os]-\\d+-\\d+-\\d+-[a-fA-F\\d]+', ('xoxo', 'xoxs'), 2.0, 0, (), 0),
    ('slack-legacy-workspace-token', 'xox[ar]-(?:\\d-)?[0-9a-zA-Z]{8,48}', ('xoxa', 'xoxr'), 2.0, 0, (), 0),
    ('slack-user-token', 'xox[pe](?:-[0-9]{10,13}){3}-[a-zA-Z0-9-]{28,34}', ('xoxe-', 'xoxp-'), 2.0, 0, (), 0),
    ('slack-webhook-url', '(?:https?://)?hooks.slack.com/(?:services|workflows|triggers)/[A-Za-z0-9+/]{43,56}', ('hooks.slack.com',), 0.0, 0, (), 0),
    ('snyk-api-token', '(?i)(?:snyk[_.-]?(?:(?:api|oauth)[_.-]?)?(?:key|token))(?:[ \\t\\w.-]{0,20})[\\s\'"]{0,3}(?:=|>|:{1,3}=|\\|\\||:|=>|\\?=|,)[\\x60\'"\\s=]{0,5}([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})(?:[\\x60\'"\\s;]|\\\\[nr]|$)', ('snyk',), 0.0, 0, (), 50),
    ('sonar-api-token', '(?i)(?:sonar[_.-]?(login|token))(?:[ \\t\\w.-]{0,20})[\\s\'"]{0,3}(?:=|>|:{1,3}=|\\|\\||:|=>|\\?=|,)[\\x60\'"\\s=]{0,5}((?:squ_|sqp_|sqa_)?[a-z0-9=_\\-]{40})(?:[\\x60\'"\\s;]|\\\\[nr]|$)', ('sonar',), 0.0, 2, (), 50),
    ('sourcegraph-access-token', '(?i)\\b(\\b(sgp_(?:[a-fA-F0-9]{16}|local)_[a-fA-F0-9]{40}|sgp_[a-fA-F0-9]{40}|[a-fA-F0-9]{40})\\b)(?:[\\x60\'"\\s;]|\\\\[nr]|$)', ('sgp_', 'sourcegraph'), 3.0, 0, (), 0),
    ('square-access-token', '\\b((?:EAAA|sq0atp-)[\\w-]{22,60})(?:[\\x60\'"\\s;]|\\\\[nr]|$)', ('eaaa', 'sq0atp-'), 2.0, 0, (), 0),
    ('squarespace-access-token', '(?i)(?:squarespace)(?:[ \\t\\w.-]{0,20})[\\s\'"]{0,3}(?:=|>|:{1,3}=|\\|\\||:|=>|\\?=|,)[\\x60\'"\\s=]{0,5}([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})(?:[\\x60\'"\\s;]|\\\\[nr]|$)', ('squarespace',), 0.0, 0, (), 50),
    ('stripe-access-token', '\\b((?:sk|rk)_(?:test|live|prod)_[a-zA-Z0-9]{10,99})(?:[\\x60\'"\\s;]|\\\\[nr]|$)', ('rk_live', 'rk_prod', 'rk_test', 'sk_live', 'sk_prod', 'sk_test'), 2.0, 0, (), 0),
    ('sumologic-access-id', '(?i:[\\w.-]{0,50}?(?:(?-i:[Ss]umo|SUMO))(?:[ \\t\\w.-]{0,20})[\\s\'"]{0,3})(?:=|>|:{1,3}=|\\|\\||:|=>|\\?=|,)[\\x60\'"\\s=]{0,5}(su[a-zA-Z0-9]{12})(?:[\\x60\'"\\s;]|\\\\[nr]|$)', ('sumo',), 3.0, 0, (), 50),
    ('sumologic-access-token', '(?i)(?:(?-i:[Ss]umo|SUMO))(?:[ \\t\\w.-]{0,20})[\\s\'"]{0,3}(?:=|>|:{1,3}=|\\|\\||:|=>|\\?=|,)[\\x60\'"\\s=]{0,5}([a-z0-9]{64})(?:[\\x60\'"\\s;]|\\\\[nr]|$)', ('sumo',), 3.0, 0, (), 50),
    ('telegram-bot-api-token', '(?i)(?:telegr)(?:[ \\t\\w.-]{0,20})[\\s\'"]{0,3}(?:=|>|:{1,3}=|\\|\\||:|=>|\\?=|,)[\\x60\'"\\s=]{0,5}([0-9]{5,16}:(?-i:A)[a-z0-9_\\-]{34})(?:[\\x60\'"\\s;]|\\\\[nr]|$)', ('telegr',), 0.0, 0, (), 50),
    ('travisci-access-token', '(?i)(?:travis)(?:[ \\t\\w.-]{0,20})[\\s\'"]{0,3}(?:=|>|:{1,3}=|\\|\\||:|=>|\\?=|,)[\\x60\'"\\s=]{0,5}([a-z0-9]{22})(?:[\\x60\'"\\s;]|\\\\[nr]|$)', ('travis',), 0.0, 0, (), 50),
    ('twilio-api-key', 'SK[0-9a-fA-F]{32}', ('sk',), 3.0, 0, (), 0),
    ('twitch-api-token', '(?i)(?:twitch)(?:[ \\t\\w.-]{0,20})[\\s\'"]{0,3}(?:=|>|:{1,3}=|\\|\\||:|=>|\\?=|,)[\\x60\'"\\s=]{0,5}([a-z0-9]{30})(?:[\\x60\'"\\s;]|\\\\[nr]|$)', ('twitch',), 0.0, 0, (), 50),
    ('twitter-access-secret', '(?i)(?:twitter)(?:[ \\t\\w.-]{0,20})[\\s\'"]{0,3}(?:=|>|:{1,3}=|\\|\\||:|=>|\\?=|,)[\\x60\'"\\s=]{0,5}([a-z0-9]{45})(?:[\\x60\'"\\s;]|\\\\[nr]|$)', ('twitter',), 0.0, 0, (), 50),
    ('twitter-access-token', '(?i)(?:twitter)(?:[ \\t\\w.-]{0,20})[\\s\'"]{0,3}(?:=|>|:{1,3}=|\\|\\||:|=>|\\?=|,)[\\x60\'"\\s=]{0,5}([0-9]{15,25}-[a-zA-Z0-9]{20,40})(?:[\\x60\'"\\s;]|\\\\[nr]|$)', ('twitter',), 0.0, 0, (), 50),
    ('twitter-api-key', '(?i)(?:twitter)(?:[ \\t\\w.-]{0,20})[\\s\'"]{0,3}(?:=|>|:{1,3}=|\\|\\||:|=>|\\?=|,)[\\x60\'"\\s=]{0,5}([a-z0-9]{25})(?:[\\x60\'"\\s;]|\\\\[nr]|$)', ('twitter',), 0.0, 0, (), 50),
    ('twitter-api-secret', '(?i)(?:twitter)(?:[ \\t\\w.-]{0,20})[\\s\'"]{0,3}(?:=|>|:{1,3}=|\\|\\||:|=>|\\?=|,)[\\x60\'"\\s=]{0,5}([a-z0-9]{50})(?:[\\x60\'"\\s;]|\\\\[nr]|$)', ('twitter',), 0.0, 0, (), 50),
    ('twitter-bearer-token', '(?i)(?:twitter)(?:[ \\t\\w.-]{0,20})[\\s\'"]{0,3}(?:=|>|:{1,3}=|\\|\\||:|=>|\\?=|,)[\\x60\'"\\s=]{0,5}(A{22}[a-zA-Z0-9%]{80,100})(?:[\\x60\'"\\s;]|\\\\[nr]|$)', ('twitter',), 0.0, 0, (), 50),
    ('typeform-api-token', '(?i)(?:typeform)(?:[ \\t\\w.-]{0,20})[\\s\'"]{0,3}(?:=|>|:{1,3}=|\\|\\||:|=>|\\?=|,)[\\x60\'"\\s=]{0,5}(tfp_[a-z0-9\\-_\\.=]{59})(?:[\\x60\'"\\s;]|\\\\[nr]|$)', ('tfp_',), 0.0, 0, (), 50),
    ('vault-batch-token', '\\b(hvb\\.[\\w-]{138,300})(?:[\\x60\'"\\s;]|\\\\[nr]|$)', ('hvb.',), 4.0, 0, (), 0),
    ('vault-service-token', '\\b((?:hvs\\.[\\w-]{90,120}|s\\.(?i:[a-z0-9]{24})))(?:[\\x60\'"\\s;]|\\\\[nr]|$)', ('hvs.', 's.'), 3.5, 0, (('secret', ('s\\.[A-Za-z]{24}',), (), False, False),), 0),
    ('yandex-access-token', '(?i)(?:yandex)(?:[ \\t\\w.-]{0,20})[\\s\'"]{0,3}(?:=|>|:{1,3}=|\\|\\||:|=>|\\?=|,)[\\x60\'"\\s=]{0,5}(t1\\.[A-Z0-9a-z_-]+[=]{0,2}\\.[A-Z0-9a-z_-]{86}[=]{0,2})(?:[\\x60\'"\\s;]|\\\\[nr]|$)', ('yandex',), 0.0, 0, (), 50),
    ('yandex-api-key', '(?i)(?:yandex)(?:[ \\t\\w.-]{0,20})[\\s\'"]{0,3}(?:=|>|:{1,3}=|\\|\\||:|=>|\\?=|,)[\\x60\'"\\s=]{0,5}(AQVN[A-Za-z0-9_\\-]{35,38})(?:[\\x60\'"\\s;]|\\\\[nr]|$)', ('yandex',), 0.0, 0, (), 50),
    ('yandex-aws-access-token', '(?i)(?:yandex)(?:[ \\t\\w.-]{0,20})[\\s\'"]{0,3}(?:=|>|:{1,3}=|\\|\\||:|=>|\\?=|,)[\\x60\'"\\s=]{0,5}(YC[a-zA-Z0-9_\\-]{38})(?:[\\x60\'"\\s;]|\\\\[nr]|$)', ('yandex',), 0.0, 0, (), 50),
    ('zendesk-secret-key', '(?i)(?:zendesk)(?:[ \\t\\w.-]{0,20})[\\s\'"]{0,3}(?:=|>|:{1,3}=|\\|\\||:|=>|\\?=|,)[\\x60\'"\\s=]{0,5}([a-z0-9]{40})(?:[\\x60\'"\\s;]|\\\\[nr]|$)', ('zendesk',), 0.0, 0, (), 50),
]
SECRET_ALLOW = (('secret', ('(?i)^true|false|null$', '^(?i:a+|b+|c+|d+|e+|f+|g+|h+|i+|j+|k+|l+|m+|n+|o+|p+|q+|r+|s+|t+|u+|v+|w+|x+|y+|z+|\\*+|\\.+)$', '^\\$(?:\\d+|{\\d+})$', '^\\$(?:[A-Z_]+|[a-z_]+)$', '^\\${(?:[A-Z_]+|[a-z_]+)}$', '^\\{\\{[ \\t]*[\\w ().|]+[ \\t]*}}$', '^\\$\\{\\{[ \\t]*(?:(?:env|github|secrets|vars)(?:\\.[A-Za-z]\\w+)+[\\w "\'&./=|]*)[ \\t]*}}$', '^%(?:[A-Z_]+|[a-z_]+)%$', '^%[+\\-# 0]?[bcdeEfFgGoOpqstTUvxX]$', '^\\{\\d{0,2}}$', '^@(?:[A-Z_]+|[a-z_]+)@$', '^/Users/(?i:[a-z0-9]+/[\\w .-/]+$)', '^/(?:bin|etc|home|opt|tmp|usr|var)/[\\w ./-]+$'), ('014df517-39d1-4453-b7b3-9930c563627c', 'abcdefghijklmnopqrstuvwxyz'), False, True),)

SECRET_CHUNK = 32_000  # characters read at once, in whole lines, so a rule can span lines as it does in gitleaks
SECRET_OVERLAP = 2_000  # characters of whole lines each piece shares with the next, so a match across a cut is found
SECRET_LINE = 4_000  # a longer line is read in pieces: Python's engine backtracks, and a few rules take seconds on one
_secret_compiled = {}
_SECRET_NAME = re.compile(r"[\w.-]", re.ASCII)


def _secret_rx(pattern):
    found = _secret_compiled.get(pattern)
    if found is None:
        found = _secret_compiled[pattern] = re.compile(pattern, re.ASCII)
    return found


def secret_entropy(text):
    """Shannon entropy in bits a character, as gitleaks reckons it."""
    counts = {}
    for ch in text:
        counts[ch] = counts.get(ch, 0) + 1
    return -sum(n / len(text) * math.log2(n / len(text)) for n in counts.values()) if text else 0.0


def _secret_pieces(text):
    """(offset, piece) for the text: whole lines up to SECRET_CHUNK characters, overlapping, and a line longer than
    SECRET_LINE in overlapping pieces of its own."""
    if len(text) <= SECRET_CHUNK and max(map(len, text.split("\n"))) <= SECRET_LINE:
        yield 0, text
        return
    lines, at = [], 0
    for line in text.split("\n"):
        lines.append((at, line))
        at += len(line) + 1
    piece, size = [], 0
    for at, line in lines:
        if len(line) > SECRET_LINE:
            if piece:
                yield piece[0][0], "\n".join(text for _, text in piece)
                piece, size = [], 0
            for i in range(0, len(line), SECRET_LINE - 256):
                yield at + i, line[i:i + SECRET_LINE]
            continue
        if piece and size + len(line) + 1 > SECRET_CHUNK:
            yield piece[0][0], "\n".join(text for _, text in piece)
            kept, size = [], 0
            for at_, text_ in reversed(piece):
                if size + len(text_) + 1 > SECRET_OVERLAP:
                    break
                kept.insert(0, (at_, text_))
                size += len(text_) + 1
            piece = kept
        piece.append((at, line))
        size += len(line) + 1
    if piece:
        yield piece[0][0], "\n".join(text for _, text in piece)


def _secret_allowed(allowlists, secret, match, line):
    low = secret.lower()
    for target, regexes, stopwords, every, elsewhere in allowlists:
        text = match if target == "match" else line if target == "line" else secret
        by_regex = any(_secret_rx(p).search(text) for p in regexes)
        by_word = any(w in low for w in stopwords)
        if every:
            checks = ([False] if elsewhere else []) + ([by_regex] if regexes else []) + ([by_word] if stopwords else [])
            if checks and all(checks):
                return True
        elif by_regex or by_word:
            return True
    return False


def secret_rules_in(low):
    """The rules worth trying on a lowercased text: those with a keyword in it (gitleaks' own prefilter). Run it once
    over everything about to be redacted, and pass the result to each piece, so a payload of many small strings
    doesn't check every rule's keywords against each of them."""
    return [r for r in SECRET_RULES if not r[2] or any(k in low for k in r[2])]


def secret_spans(text, rules=None):
    """[(start, end, rule id)] for each secret in the text, by gitleaks' rules (or those of them given), earliest
    first, none overlapping."""
    if not text or len(text) < 8:
        return []
    rules = secret_rules_in(text.lower()) if rules is None else rules
    if not rules:
        return []
    found = set()
    for at, piece in _secret_pieces(text):
        piece_low = piece.lower()
        for rule_id, pattern, keywords, floor, group, allowlists, lead in rules:
            if keywords and not any(k in piece_low for k in keywords):
                continue
            done = 0
            for m in _secret_rx(pattern).finditer(piece):
                begin = m.start()
                while lead and begin > done and m.start() - begin < lead and _SECRET_NAME.match(piece, begin - 1):
                    begin -= 1  # gitleaks' lazy name prefix, reached back over from the keyword
                done = m.end()
                g = group or next((i for i in range(1, (m.lastindex or 0) + 1) if m.group(i)), 0)
                secret = m.group(g)
                if not secret or (floor and secret_entropy(secret) <= floor):
                    continue
                start = piece.rfind("\n", 0, begin) + 1
                end = piece.find("\n", m.end())
                line = piece[start:end if end >= 0 else len(piece)]
                match = piece[begin:m.end()]
                if _secret_allowed(SECRET_ALLOW, secret, match, line) or _secret_allowed(allowlists, secret, match, line):
                    continue
                found.add((at + m.start(g), at + m.end(g), rule_id))
    spans = []
    for start, end, rule_id in sorted(found):
        if spans and start < spans[-1][1]:
            spans[-1] = (spans[-1][0], max(end, spans[-1][1]), spans[-1][2])
        else:
            spans.append((start, end, rule_id))
    return spans


def redact_secrets(text, counts=None, rules=None):
    """The text with each secret gitleaks' rules find replaced by [REDACTED:<rule id>]."""
    spans = secret_spans(text, rules)
    if not spans:
        return text
    out, at = [], 0
    for start, end, rule_id in spans:
        out.append(text[at:start] + f"[REDACTED:{rule_id}]")
        at = end
        if counts is not None:
            counts[rule_id] = counts.get(rule_id, 0) + 1
    return "".join(out) + text[at:]
# --- End of the generated secret rules ---


# --- What never leaves the machine ---------------------------------------------------------------------
# Per repo, in `.claude/night-order.json`: whether to send at all, files whose contents are private, and the
# repo's own secret patterns. A private file's contents are left out wherever they'd go; everything sent is
# redacted first, with the server's own patterns (kept the same as `callmeif.redact`, which a test checks).
SETTINGS_FILE = os.path.join(".claude", "night-order.json")
PRIVATE = (".env", ".env.*", "*.env", "*.pem", "*.key", "*.p12", "*.pfx", "*.jks", "*.keystore", "*.kdbx", "id_rsa*", "id_dsa*",
           "id_ecdsa*", "id_ed25519*", ".ssh/*", ".aws/*", ".gnupg/*", ".kube/config", ".docker/config.json", ".netrc", ".npmrc",
           ".pypirc", "*.tfstate", "*.tfstate.*", "secrets/*", "*/secrets/*", "credentials.json", "*credentials*.json",
           "service-account*.json")
LEFT_OUT = "[left out by Night Order's hook: {}]"
FILE_FIELDS = ("file_path", "notebook_path", "path")
WRITTEN_FIELDS = ("content", "new_string", "old_string", "new_source", "edits")
PATTERNS = [
    ("private_key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----")),
    ("anthropic_key", re.compile(r"\bsk-ant-[A-Za-z0-9_\-]{20,}")),
    ("openai_key", re.compile(r"\bsk-(?!ant-)(?:proj-|svcacct-|admin-)?[A-Za-z0-9_\-]{20,}")),
    ("aws_access_key", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("github_token", re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,})\b")),
    ("slack_token", re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}")),
    ("google_api_key", re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b")),
    ("stripe_key", re.compile(r"\b(?:sk|rk|pk)_(?:live|test)_[A-Za-z0-9]{16,}\b")),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}")),
]
_NOT_ALREADY = r"(?!\[REDACTED)"
KEEP_PREFIX = [
    ("url_password", re.compile(rf"(?P<prefix>\b[a-z][a-z0-9+.\-]*://[^/\s:@]+:){_NOT_ALREADY}(?P<secret>[^/\s@]+)(?=@)", re.I)),
    ("bearer_token", re.compile(rf"(?P<prefix>\bBearer[ \t]+){_NOT_ALREADY}(?P<secret>[A-Za-z0-9._\-~+/]{{20,}}=*)", re.I)),
    ("assigned_secret", re.compile(
        r"(?P<prefix>\b[A-Za-z_][A-Za-z0-9_]*(?:api_?key|secret_?key|access_?key|private_?key|token|secret|password|passwd)"
        rf"[\"']?[ \t]*[=:][ \t]*[\"']?){_NOT_ALREADY}(?P<secret>[^\s\"',;]{{8,}})", re.I)),
]


def settings(root):
    """The repo's settings: {send, private, redact}. With no settings file, the defaults; with one the hook can't
    read, or that isn't what it should be, nothing is sent."""
    base = {"send": True, "private": PRIVATE, "redact": []}
    path = os.path.join(root, SETTINGS_FILE)
    if not os.path.exists(path):
        return base
    try:
        with open(path, encoding="utf-8") as fh:
            raw = json.load(fh)
        if not isinstance(raw, dict):
            raise ValueError("not an object")
        send = raw.get("send", True)
        private = raw.get("private", [])
        redact = raw.get("redact", [])
        if not isinstance(send, bool) or not isinstance(private, list) or not isinstance(redact, list) \
                or not all(isinstance(p, str) for p in private + redact):
            raise ValueError("wrong types")
        return {"send": send, "private": PRIVATE + _own_patterns(private), "redact": [re.compile(r) for r in redact]}
    except (OSError, ValueError, TypeError, re.error):
        return {"send": False, "private": PRIVATE, "redact": [], "unreadable": True}


def _own_patterns(raw):
    """A repo's own private patterns, each also covering what's inside a folder of that name (`customers`)."""
    out = []
    for pattern in raw:
        pattern = pattern.strip().lstrip("/").rstrip("/")
        if pattern:
            out.append(pattern)
            if not pattern.endswith("*"):
                out.append(pattern + "/*")
    return tuple(out)


_matchers = {}


def _matcher(private):
    """One regular expression for a list of private patterns, made once."""
    key = tuple(private)
    if key not in _matchers:
        _matchers[key] = re.compile("|".join(f"(?:{fnmatch.translate(p)})" for p in key))
    return _matchers[key]


def is_private(path, private):
    """Whether a path (under the repo's top, or anywhere) is one of the private files: a pattern matches the
    path's end, so `.env` covers `app/.env` and `.aws/*` covers `/home/me/.aws/credentials`."""
    if not path or not private:
        return False
    parts = [p for p in str(path).replace("\\", "/").split("/") if p and p != "."]
    rx = _matcher(private)
    return any(rx.match("/".join(parts[i:])) for i in range(len(parts)))


_HEREDOC = re.compile(r"(?<!<)<<(?!<)(-?)[ \t]*(['\"]?)\\?([A-Za-z_][A-Za-z0-9_]*)\2")
_QUOTED_NAME = re.compile(r"""(['"`])([^'"`\s]{1,300})\1""")
_QUOTED = re.compile(r"""'[^']*'|"(?:[^"\\]|\\.)*\"""")


def split_heredocs(command):
    """A command's text as [(is a here-document body, text)]: each body is the lines between a `<<WORD` and the
    line that ends it, the rest is shell text."""
    parts, lines, i = [], command.split("\n"), 0
    while i < len(lines):
        parts.append((False, lines[i]))
        ends = [(m.group(3), bool(m.group(1))) for m in _HEREDOC.finditer(lines[i])]
        i += 1
        for word, tabs in ends:
            body = []
            while i < len(lines) and (lines[i].lstrip("\t") if tabs else lines[i]) != word:
                body.append(lines[i])
                i += 1
            parts.append((True, "\n".join(body)))
            if i < len(lines):
                parts.append((False, lines[i]))
                i += 1
    return parts


def _paths_in(command):
    """What a command could name as a file: its shell words and their parts after `=` or `:`, and any quoted
    string without spaces, here-documents included (`open('.env')`). A here-document's other text is what the
    command writes or runs, not a name."""
    parts = split_heredocs(command)
    shell = "\n".join(text for body, text in parts if not body)
    try:
        words = shlex.split(shell, posix=True)
    except ValueError:
        words = shell.split()
    found = []
    for word in words:
        for piece in [word] + re.split(r"[=:]", word):
            piece = piece.strip("<>|&;()'\"")
            if piece and not piece.startswith("-"):
                found.append(piece)
    found.extend(m.group(2) for m in _QUOTED_NAME.finditer(command))
    return found


def private_call(name, tool_input, private):
    """Whether a tool call touched a private file: a file tool given one, or a command naming one."""
    if not isinstance(tool_input, dict):
        return False
    if any(is_private(tool_input.get(field), private) for field in FILE_FIELDS):
        return True
    command = tool_input.get("command")
    return isinstance(command, str) and any(is_private(p, private) for p in _paths_in(command))


def quiet(command):
    """A command that named a private file, without what it could carry into one: its here-document bodies and
    quoted strings, over several lines too. What it ran stays readable: its programs, flags and file names."""
    parts = split_heredocs(command)
    shell = "\n".join(f"\x00{i}\x00" if body else text for i, (body, text) in enumerate(parts))
    note = LEFT_OUT.format("a here-document")
    return re.sub(r"\x00\d+\x00", lambda _: note, _QUOTED.sub('"…"', shell))


def _left_out(content):
    """A private call's result: nothing of what it printed, but how it ended (`Exit code 1`)."""
    first = content if isinstance(content, str) else next(
        (str(b.get("text", "")) for b in content or [] if isinstance(b, dict) and b.get("type") == "text"), "")
    note = LEFT_OUT.format("the output of a call that touched a private file")
    head = first.split("\n", 1)[0]
    return f"{head}\n{note}" if re.fullmatch(r"Exit code -?\d+", head.strip()) else note


_DIFF_LINE = (" ", "+", "-", "@@", "\\", "index ", "new file mode", "deleted file mode", "old mode", "new mode",
              "similarity index", "dissimilarity index", "rename from", "rename to", "copy from", "copy to", "Binary files")
_LABEL = re.compile(r":|-\d+-")


def _labelled(line, private):
    """Whether a line of output says it came from a private file: a search's `path:3:…`, `path-3-…` or `path:…`."""
    head = line.strip().split(" ", 1)[0]
    return any(m.start() and is_private(head[: m.start()], private) for m in _LABEL.finditer(head))


def _private_lines(text, private):
    """Output without what it printed from private files under their names: the lines a search labels with one,
    and the lines of a diff of one (`git diff`, `git show`, `git log -p`), whose header stays."""
    kept, dropped, hidden = [], 0, False
    for line in text.split("\n"):
        if line.startswith("diff "):
            hidden = any(is_private(w[2:] if w[:2] in ("a/", "b/") else w, private) for w in line[5:].split() if not w.startswith("-"))
            kept.append(line)
            continue
        if hidden and (not line.strip() or line.startswith(_DIFF_LINE)):
            dropped += 1
            continue
        hidden = False
        if ":" in line or "-" in line:
            if _labelled(line, private):
                dropped += 1
                continue
        kept.append(line)
    return text if not dropped else "\n".join(kept + [LEFT_OUT.format(f"{dropped} line(s) from private files")])


def privatize(entries, private):
    """The turn's entries with private files' contents left out: what a call wrote to one, the output of a call
    that touched one, and what other output printed from one under its name."""
    touched, out = set(), []
    for entry in entries:
        message = entry.get("message")
        if not isinstance(message, dict) or not isinstance(message.get("content"), list):
            out.append(entry)
            continue
        blocks = []
        for block in message["content"]:
            if isinstance(block, dict) and block.get("type") == "tool_use" and private_call(block.get("name"), block.get("input"), private):
                touched.add(block.get("id"))
                tool_input = dict(block.get("input") or {})
                for field in WRITTEN_FIELDS:
                    if field in tool_input:
                        tool_input[field] = LEFT_OUT.format("written to a private file")
                if isinstance(tool_input.get("command"), str):
                    tool_input["command"] = quiet(tool_input["command"])
                block = {**block, "input": tool_input}
            elif isinstance(block, dict) and block.get("type") == "tool_result":
                if block.get("tool_use_id") in touched:
                    block = {**block, "content": _left_out(block.get("content"))}
                elif isinstance(block.get("content"), str):
                    block = {**block, "content": _private_lines(block["content"], private)}
                elif isinstance(block.get("content"), list):
                    block = {**block, "content": [{**b, "text": _private_lines(str(b.get("text", "")), private)}
                                                  if isinstance(b, dict) and b.get("type") == "text" else b for b in block["content"]]}
            blocks.append(block)
        out.append({**entry, "message": {**message, "content": blocks}})
    return out


def _strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for v in value.values():
            yield from _strings(v)
    elif isinstance(value, list):
        for v in value:
            yield from _strings(v)


def redact(value, own=(), rules=None):
    """Every string in the value with secrets redacted: the server's patterns, gitleaks' rules, then the repo's own.
    gitleaks' keywords are looked for once, over all of it."""
    if rules is None:
        rules = secret_rules_in("\n".join(_strings(value)).lower())
    if isinstance(value, dict):
        return {k: redact(v, own, rules) for k, v in value.items()}
    if isinstance(value, list):
        return [redact(v, own, rules) for v in value]
    if not isinstance(value, str):
        return value
    for kind, pattern in PATTERNS:
        value = pattern.sub(f"[REDACTED:{kind}]", value)
    low = value.lower()
    value = redact_secrets(value, rules=[r for r in rules if not r[2] or any(k in low for k in r[2])])
    for kind, pattern in KEEP_PREFIX:
        value = pattern.sub(lambda m, kind=kind: m.group("prefix") + f"[REDACTED:{kind}]", value)
    for pattern in own:
        value = pattern.sub("[REDACTED:repo_pattern]", value)
    return value


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


# --- Names for the glossary --------------------------------------------------------------------------------
# The project's own names (functions and classes, with the first sentence of what each one's docstring or comment
# says) are a source for the glossary that needs no docs: it's how a card can say what `done_by_command()` is.
# A file is read again only when it changed (by its size and time), within a time limit each turn, so a big repo
# is read over a few turns. Private files are left out. Names and first sentences of docs only, never the code.
NAMES_SECONDS = 1.5
MAX_NAME_FILES = 2000
NAME_FILE_CHARS = 200_000
MAX_NAMES = 3000
NAMES_PER_FILE = 200
DOC_CHARS = 160
CODE_DRIVERS = {ext: driver for ext, driver in DRIVERS.items() if driver not in ("markdown", "css", "html")}
_COMMENT = re.compile(r"^\s*(?:///?|#|--|;+|\*|/\*\*?)\s?(.*?)\s*(?:\*/)?\s*$")
_QUOTES = ('"""', "'''")
_INLINE_BODY = re.compile(r"^\s*(?:async\s+)?def\b.*\)\s*(?:->[^:]*)?:\s*[^\s#]|^\s*class\s+\w+(?:\([^)]*\))?\s*:\s*[^\s#]")
_TRAILING_COMMENT = re.compile(r"\s+#[^'\"]*$")


_SENTENCE_END = re.compile(r"(?<=[.!?])\s+(?=[A-Z`(\"'])")


def first_sentence(text):
    """The first sentence of a doc's first paragraph, its lines joined, cut to fit a card."""
    text = " ".join(text.split())
    end = _SENTENCE_END.search(text)
    text = text[: end.start()] if end else text
    return text if len(text) <= DOC_CHARS else text[:DOC_CHARS].rsplit(" ", 1)[0].rstrip(",;:") + "…"


def _docstring(lines, start):
    """The first sentence of a Python docstring that opens at `lines[start]`, or ""."""
    text = lines[start].strip().lstrip("rRuUbB")
    quote, rest, words = text[:3], text[3:], []
    for n in range(start, min(len(lines), start + 15)):
        if n > start:
            rest = lines[n].strip()
        end = rest.find(quote)
        part = (rest if end < 0 else rest[:end]).strip()
        if part:
            words.append(part)
        elif words:
            break  # a blank line ends the first paragraph
        if end >= 0:
            break
    return first_sentence(" ".join(words))


def _doc(lines, at, driver):
    """The first sentence of a definition's docstring (Python) or of the comment above it, or ""."""
    if driver == "python":
        if _INLINE_BODY.search(lines[at]):
            return ""  # `def f(): return 1`
        signature = not _TRAILING_COMMENT.sub("", lines[at]).rstrip().endswith(":")
        for n in range(at + 1, min(len(lines), at + 20)):
            text = lines[n].strip()
            if signature:  # still inside a signature that runs over several lines
                signature = not _TRAILING_COMMENT.sub("", text).endswith(":")
                continue
            if not text:
                continue
            return _docstring(lines, n) if text.lstrip("rRuUbB").startswith(_QUOTES) else ""
        return ""
    above = at - 1
    while above >= 0 and lines[above].strip().startswith("@"):
        above -= 1  # decorators and annotations
    block = []
    while above >= 0 and lines[above].strip() and _COMMENT.match(lines[above]) and not lines[above].strip().startswith("#!"):
        block.append(_COMMENT.match(lines[above]).group(1).strip())
        above -= 1
    words = []
    for text in reversed(block):  # top to bottom: the first paragraph, up to a blank line or a tag
        if text in ("", "/", "*") or text.startswith("@"):
            if words:
                break
            continue
        words.append(text)
    return first_sentence(" ".join(words))


def names_in(text, driver):
    """[(line, kind, name, doc)] for the definitions in a file's text (the line is for reading them, not sent)."""
    lines = text.split("\n")
    out = []
    for at, line in enumerate(lines):
        if len(line) > 300 or not line.strip():
            continue
        found = _name(line, driver)
        if found:
            name, kind = found
            out.append((at + 1, kind, name, _doc(lines, at, driver)))
            if len(out) >= NAMES_PER_FILE:
                break
    return out


def names_cache(root):
    return os.path.join(tempfile.gettempdir(), "night-order-names-" + hashlib.sha256(root.encode()).hexdigest()[:16] + ".json")


def _out_of_time():
    return time.monotonic() > _until[0]


def project_names(root, private=()):
    """[[path, kind, name, its doc's first sentence]] for the repo's code. A file is read again only when its size or time
    changed, for a second and a half a turn; a repo with more to read than that keeps the names it had until the
    reading is done, over the next turns. No line numbers: an edit inside a function changes nothing here, so
    the project isn't sent again for it. None outside a git repo, or before the first reading is done."""
    _until[0] = time.monotonic() + NAMES_SECONDS
    listed = git(root, "ls-files", "-z", "--cached", "--others", "--exclude-standard")
    if listed is None:
        return None
    cache = names_cache(root)
    try:
        with open(cache, encoding="utf-8") as fh:
            kept = json.load(fh)
    except (OSError, ValueError):
        kept = {}
    kept = kept if isinstance(kept, dict) else {}
    before = kept.get("files") if isinstance(kept.get("files"), dict) else {}
    files, done = {}, True
    for path in listed.split("\0"):
        ext = path.rsplit(".", 1)[-1].lower() if "." in path else ""
        if ext not in CODE_DRIVERS or is_private(path, private):
            continue
        try:
            stat = os.stat(os.path.join(root, path))
        except OSError:
            continue
        mark = [stat.st_mtime_ns, stat.st_size]
        old = before.get(path)
        if isinstance(old, list) and len(old) == 3 and old[:2] == mark:
            files[path] = old
        elif _out_of_time():
            done = False  # read on a later turn
        else:
            found = []
            if stat.st_size <= NAME_FILE_CHARS * 4:
                try:
                    with open(os.path.join(root, path), encoding="utf-8", errors="replace") as fh:
                        found = [[kind, name, doc] for _, kind, name, doc in names_in(fh.read(NAME_FILE_CHARS), CODE_DRIVERS[ext])]
                except OSError:
                    pass
            files[path] = mark + [found]
        if len(files) >= MAX_NAME_FILES:
            break
    names = [[path, *found] for path, (_, _, each) in files.items() for found in each][:MAX_NAMES] if done else kept.get("names")
    if files != before or names != kept.get("names"):
        try:
            with open(cache, "w", encoding="utf-8") as fh:
                json.dump({"files": files, "names": names}, fh)
        except OSError:
            pass
    return names


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
    rules = settings(project_root(payload))
    if not rules["send"]:
        return  # this repo sends nothing, not even that a prompt came
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
                turn["entries"] = privatize(turn.get("entries") or [], rules["private"])
                payload["turn"] = turn
        except Exception:  # the payload alone still makes a card, without its tool calls
            pass
        if os.environ.get("CLAUDE_CODE_REMOTE") == "true":
            payload["remote"] = True
        if os.environ.get("CLAUDE_CODE_REMOTE_SESSION_ID"):
            payload["remote_session_id"] = os.environ["CLAUDE_CODE_REMOTE_SESSION_ID"]
        try:
            project, stamp = the_project(payload, url, rules["private"])
            if project:
                payload["project"] = project
        except Exception:
            pass
        if payload.get("hook_event_name") == "Stop" and deadline - time.monotonic() > STOP_GIT_SECONDS + SEND_SECONDS + 1:
            try:
                changes = turn_changes(start)
                if changes is not None:
                    changes["files"] = [f for f in changes.get("files") or [] if not is_private(f.get("path"), rules["private"])]
                    payload["code_changes"] = changes
            except Exception:  # noqa: BLE001 - the card goes without its code changes
                pass
        if report:
            payload["hook_report"] = report
        payload = redact(payload, rules["redact"])  # nothing leaves unredacted
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
