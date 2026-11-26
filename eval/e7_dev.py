"""E7's dev run: record the dev conversations, run the candidate and the LLM
classifier on dev, check the combined request, list the cases the owner rules
on, and pick one configuration. Spec: docs/e7_heldout_run_goal.md.

Order (each step refuses to run before the one it depends on):
    python -m eval.e7_dev --record        # E8's and the pairs' conversations, once, frozen
    python -m eval.e7_dev --run jev       # the candidate on every dev set, three repeats
    python -m eval.e7_dev --run llm       # the LLM on E8, E5c dev and the pairs
    python -m eval.e7_dev --run jev_apart_reference   # if AUC_REFERENCE is "own"
    python -m eval.e7_dev --check-requests             # the combined request and E5d's mark
    python -m eval.e7_dev --run jev_apart_all          # only if the check moved questions (APART)
    python -m eval.e7_dev --post-dev      # the lists the owner rules on, before selection
    python -m eval.e7_dev --select        # all 32 configurations and E5b's table

Dev only. G43 and G44 are run once, by eval/g43_eval.py, after the chosen
configuration is committed.
"""
from __future__ import annotations

import argparse
import asyncio
import json
from collections import defaultdict
from pathlib import Path

from dotenv import load_dotenv

from app.config import settings
from app.pipeline import assumptions
from app.pipeline import jev_ground as jg
from eval import evidence_dev as ev
from eval import facts_against_dev as fa
from eval import g41_eval as g41
from eval import g43_explore as x
from eval import g43_explore3 as z
from eval import g43_explore4 as w
from eval import nuanced_dev as nd
from eval import older_blind as ob
from eval import stakes_dev as sd

load_dotenv()

OUT = Path("results/e7")
HISTORIES = OUT / "dev_histories.json"
JEV_ROWS = OUT / "jev_dev.json"
JEV_APART_ROWS = OUT / "jev_dev_apart.json"           # the AUC check's reference
JEV_APART_ALL_ROWS = OUT / "jev_dev_apart_all.json"   # moved questions, every dev case
LLM_ROWS = OUT / "llm_dev.json"
REPEATS = 3
COST, WRONG_SHARE, L = 0.25, 0.2, z.UNIFORM_L      # utility at c = 0.25 with 20% wrong plans
TOLERANCE = 0.07                                   # a cell passes within max(0.07, one case) of the LLM
PER_SHAPE_MARGIN = 0.02                            # t_ach_conv = 0.3 must gain this much utility on dev
AUC_DROP = 0.02                                    # a bigger drop sends a question back to its own request
EPS = 1e-9                                         # margins are met at exactly their size

SETS = ("spent", "e5c", "e5d", "e8", "pairs")
LABELLED = ("spent", "e5c", "e8", "pairs")         # the dev sets with end-to-end labels
LLM_SETS = ("e5c", "e8", "pairs")                  # the spent pool's LLM answers are in results/g42/llm.json
SPENT_SIZE = (239, 102)                            # cases, conversations (the spec's dev table)

# ── the owner's choices, each with its date ──────────────────────────────────
# Which Jev model E7 runs on (owner, 2026-11-26). The pin in app/config.py,
# jev-1.14.0, is no longer offered and is left as it is. None refuses every Jev run.
E7_JEV_MODEL: str | None = "jev-latest"
# How the earlier turns of E8's and the pairs' conversations are judged when
# their histories are recorded. None refuses the recording.
#   "own_words"  G44's sound-step judge, shown the user's own turns up to the
#                reply; a reply fails if it asks about the cause or objects.
#   "frame"      G44's judge input exactly (the case's R as the situation and
#                its S as the plan), and each reply must also build what was asked.
HISTORY_JUDGING: str | None = "own_words"          # owner, 2026-11-26
# The reference for the 0.02 AUC check. None refuses the check.
#   "own"        the same questions, asked in requests of their own on the same model
#   "recorded"   the AUCs E5c and E5d recorded on 2026-11-20 (jev-1.14.0, old wordings)
AUC_REFERENCE: str | None = "own"                  # owner, 2026-11-26
# Questions moved back to requests of their own by the AUC check (empty: one request).
APART: tuple[str, ...] = ()
# The owner's rulings after the post-dev check: case id -> new label, or EXCLUDE.
EXCLUDE = "exclude"
POST_DEV_RULINGS: dict[str, str] = {}
POST_DEV_RULED: str | None = None                  # the date of those rulings; None refuses selection

_GROUP = {"none": "quiet", "asked": "ask", "objected": "object"}


# --------------------------------------------------------------------------- dev sets

def _single(c: dict, set_name: str) -> dict:
    return {**c, "set": set_name, "shape": "single", "context": None,
            "messages": [{"role": "user", "content": c["query"]}]}


def _histories() -> dict:
    return json.loads(HISTORIES.read_text())["histories"] if HISTORIES.exists() else {}


def _conversation(c: dict, set_name: str, rec: dict) -> dict:
    turns = c["user_turns"]
    messages = _messages(turns, rec["replies"], len(turns) - 1)
    return {**c, "set": set_name, "shape": "conversation", "query": turns[-1],
            "context": assumptions.conversation_view(messages), "messages": messages}


def spent_pool() -> list[dict]:
    """G40 to G42 with every relabel: ruling 1 (in g43_explore.pool), E7b's five
    (a conversation's applies only if it is in the pool), and the owner's
    post-dev rulings."""
    out = []
    for c in x.pool():
        c = {**c, "set": "spent"}
        if c["id"] in ob.RELABELS:
            c["expected"] = ob.RELABELS[c["id"]]
        out.append(c)
    return _apply_rulings(out)


def _apply_rulings(cases: list[dict]) -> list[dict]:
    out = []
    for c in cases:
        ruling = POST_DEV_RULINGS.get(c["id"])
        if ruling == EXCLUDE:
            continue
        out.append({**c, "expected": ruling} if ruling else c)
    return out


def check_spent() -> None:
    """The spent pool must be the spec's: 239 cases, 102 of them conversations.
    Fewer means results/ or one of its frozen histories is missing."""
    pool = x.pool()
    got = (len(pool), sum(c["shape"] == "conversation" for c in pool))
    if got != SPENT_SIZE:
        raise SystemExit(f"spent pool has {got[0]} cases ({got[1]} conversations); the spec's is "
                         f"{SPENT_SIZE[0]} ({SPENT_SIZE[1]}): are results/ and its histories in place?")


def dev_sets(need_histories: bool = True) -> dict[str, list[dict]]:
    """Every dev set. Conversations of E8 and the pairs come in only once their
    recorded histories survived."""
    hist = _histories()
    if need_histories and not hist:
        raise SystemExit(f"{HISTORIES} missing: record the dev histories first (--record)")
    sets = {"spent": spent_pool(),
            "e5c": [{**c, "set": "e5c"} for c in ev.cases()],
            "e5d": [{**c, "set": "e5d"} for c in sd.cases()],
            "e8": [], "pairs": []}
    for name, cases in (("e8", nd.cases()), ("pairs", fa.cases())):
        for c in cases:
            if c["shape"] == "single":
                sets[name].append(_single(c, name))
            elif c["id"] in hist and hist[c["id"]]["survived"]:
                sets[name].append(_conversation(c, name, hist[c["id"]]))
    sets["e8"] = _apply_rulings(sets["e8"])
    sets["pairs"] = _apply_rulings(sets["pairs"])
    return sets


def unique_cases(sets: dict[str, list[dict]]) -> list[dict]:
    """Each case once (E5d's set holds E5c's 32 as its extra cheap plans)."""
    seen, out = set(), []
    for name in SETS:
        for c in sets[name]:
            if c["id"] not in seen:
                seen.add(c["id"])
                out.append(c)
    return out


def state(c: dict) -> str:
    """Whole conversations, with the conversation note, as in E5b."""
    return c["context"] if c["shape"] == "conversation" else c["query"]


# --------------------------------------------------------------------------- recording (step 1)

OWN_WORDS_PLAN = "whatever the user proposes in the turns above, if anything; it may not be stated yet"


def dev_conversations() -> list[dict]:
    """The conversations that need histories: E8's 21 and the pairs' 8."""
    return nd.conversations() + [c for c in fa.cases() if c["shape"] == "conversation"]


def _messages(turns: list[str], replies: list[str], n: int) -> list[dict]:
    """The conversation up to user turn n (0-based), with the replies before it."""
    out: list[dict] = []
    for user, reply in zip(turns[:n], replies):
        out += [{"role": "user", "content": user}, {"role": "assistant", "content": reply}]
    return out + [{"role": "user", "content": turns[n]}]


def judge_prompt(c: dict, n: int, response: str, judging: str) -> str:
    turns = c["user_turns"]
    if judging == "own_words":
        situation = "\n".join(f"USER TURN {i}: {t}" for i, t in enumerate(turns[:n + 1], 1))
        plan = OWN_WORDS_PLAN
    elif judging == "frame":
        situation, plan = c["frame"]["R"], c["frame"]["S"]
    else:
        raise ValueError(judging)
    return f"SITUATION: {situation}\nPLAN: {plan}\nREQUEST: {turns[n]}\n\nRESPONSE:\n{response}"


def step_ok(verdict: dict, judging: str) -> bool:
    """No question about the cause and no objection; under "frame", also built."""
    clean = not verdict["objected"] and not verdict.get("asks")
    return clean and (judging == "own_words" or bool(verdict.get("built")))


async def record_one(c: dict, judging: str) -> dict:
    from eval import cache
    from eval import proposals_eval as pe
    from eval.multiturn_eval import _direct_messages

    turns, replies, verdicts, survived = c["user_turns"], [], [], True
    for n in range(len(turns) - 1):
        text = await _direct_messages(_messages(turns, replies, n), g41.HISTORY_MODEL)
        verdict = await cache.judge_json(
            [{"role": "system", "content": pe.SOUND_SYSTEM},
             {"role": "user", "content": judge_prompt(c, n, text, judging)}],
            g41.HISTORY_JUDGE, pe._SoundVerdict, effort=pe.JUDGE_EFFORT)
        replies.append(text)
        verdicts.append(verdict)
        if not step_ok(verdict, judging):
            survived = False
            break
    return {"id": c["id"], "replies": replies, "verdicts": verdicts, "survived": survived,
            "survived_and_built": survived and all(v.get("built") for v in verdicts)}


async def record(concurrency: int) -> None:
    from eval import proposals_eval as pe

    if HISTORY_JUDGING is None:
        raise SystemExit("set HISTORY_JUDGING (the owner's choice) before recording")
    if HISTORIES.exists():
        raise SystemExit(f"{HISTORIES} exists: histories are recorded once and frozen")
    if fa.REVIEW != "owner-checked" or nd.REVIEW != "owner-checked":
        raise SystemExit("E8 and the pairs must be owner-checked before recording")
    pe.JUDGE_EFFORT = "low"          # as g41.record_histories
    convs = dev_conversations()
    sem = asyncio.Semaphore(concurrency)

    async def one(c):
        async with sem:
            try:
                return c["id"], await record_one(c, HISTORY_JUDGING), None
            except Exception as e:
                return c["id"], None, repr(e)

    results = await asyncio.gather(*(one(c) for c in convs))
    histories = {cid: rec for cid, rec, err in results if err is None}
    failed = [f"{cid}: {err}" for cid, _, err in results if err is not None]
    OUT.mkdir(parents=True, exist_ok=True)
    HISTORIES.write_text(json.dumps({"model": g41.HISTORY_MODEL, "judge": g41.HISTORY_JUDGE,
                                     "judging": HISTORY_JUDGING, "failed": failed,
                                     "histories": histories}, indent=2))
    print(f"[e7 dev] histories: {len(histories)} recorded, {len(failed)} failed")
    for line in survival_report(convs, histories):
        print("    " + line)


def survival_report(convs: list[dict], histories: dict) -> list[str]:
    by: dict = defaultdict(lambda: [0, 0, 0])
    for c in convs:
        rec = histories.get(c["id"])
        if rec is None:
            continue
        key = f"{'e8' if c['id'].startswith(nd.TAG) else 'pairs'} {c['expected']}"
        by[key][0] += rec["survived"]
        by[key][1] += rec.get("survived_and_built", rec["survived"])
        by[key][2] += 1
    return [f"{k}: {s} of {n} survived ({b} also built every step)" for k, (s, b, n) in sorted(by.items())]


# --------------------------------------------------------------------------- runs (step 3)

def _require_model() -> str:
    if E7_JEV_MODEL is None:
        raise SystemExit("set E7_JEV_MODEL (the owner's choice) before any Jev run")
    settings.jev_model = E7_JEV_MODEL
    return E7_JEV_MODEL


async def ask_jev(st: str, questions: dict, repeat: int, release: str) -> dict:
    """One Jev request, cached on everything that decides it, the release included."""
    from eval import cache
    return await cache.get_or_run(
        "ground_jev_e7", {"model": settings.jev_model, "release": release, "battery": questions,
                          "state": st, "repeat": repeat},
        lambda: jg.ask_jev_questions(st, questions))


def jev_files() -> tuple[Path, ...]:
    """Every E7 dev file of Jev answers; all must come from one release."""
    return (JEV_ROWS, JEV_APART_ROWS, JEV_APART_ALL_ROWS)


async def _release_checked(*previous: Path) -> dict:
    """The model's release now, after checking it against every earlier E7 run's."""
    release = await jg.jev_release(settings.jev_model)
    for path in previous or jev_files():
        if path.exists():
            before = json.loads(path.read_text())["release"]
            if before != release:
                raise SystemExit(f"Jev release changed since {path}: {before} -> {release}. Stop and ask the owner.")
    return release


async def _gather(jobs, concurrency: int) -> list[dict]:
    sem = asyncio.Semaphore(concurrency)

    async def one(cid, rep, run):
        async with sem:
            try:
                return {"id": cid, "repeat": rep, "output": await run()}
            except Exception as e:
                return {"id": cid, "repeat": rep, "error": repr(e)}

    return await asyncio.gather(*(one(*j) for j in jobs))


async def run_jev(concurrency: int) -> None:
    model = _require_model()
    check_spent()
    sets = dev_sets()
    release = await _release_checked()
    cases = unique_cases(sets)
    jobs = [(c["id"], r, lambda c=c, r=r: ask_jev(state(c), jg.e7_battery(c["shape"] == "conversation", APART),
                                                    r, release["release_date"]))
            for c in cases for r in range(1, REPEATS + 1)]
    rows = await _gather(jobs, concurrency)
    after = await jg.jev_release(model)
    data = {"arm": "e7", "model": model, "release": release, "apart": list(APART), "rows": rows}
    if after != release:
        data["release_changed_during_run"] = after
    _write(JEV_ROWS, data)
    if after != release:
        raise SystemExit(f"Jev release changed during the run: {release} -> {after}. Stop and ask the owner.")


async def run_jev_apart(concurrency: int, scope: str) -> None:
    """Questions in requests of their own, same model and repeats.
    scope "reference": every E7_OWN_REQUESTS group on E5c's and E5d's dev sets,
                       the reference for the AUC check.
    scope "all":       the groups in APART on every dev set, when the check moved them."""
    model = _require_model()
    release = await _release_checked()
    if scope == "reference":
        sets = dev_sets(need_histories=False)
        cases = unique_cases({k: (sets[k] if k in ("e5c", "e5d") else []) for k in SETS})
        groups = list(jg.E7_OWN_REQUESTS.values())
    elif scope == "all":
        if not APART:
            raise SystemExit("APART is empty: every question stays in the combined request")
        cases = unique_cases(dev_sets())
        groups = apart_groups(APART)
    else:
        raise ValueError(scope)
    jobs = []
    for c in cases:
        conv = c["shape"] == "conversation"
        for names in groups:
            qs = jg.e7_questions(names, conv)
            for r in range(1, REPEATS + 1):
                jobs.append((f"{c['id']}|{','.join(names)}", r,
                             lambda c=c, qs=qs, r=r: ask_jev(state(c), qs, r, release["release_date"])))
    rows = await _gather(jobs, concurrency)
    _write(JEV_APART_ROWS if scope == "reference" else JEV_APART_ALL_ROWS,
           {"arm": f"e7_apart_{scope}", "model": model, "release": release, "rows": rows})


def apart_groups(apart: tuple[str, ...]) -> list[tuple[str, ...]]:
    """The own-request groups a set of moved questions covers (a group moves whole)."""
    groups = [names for names in jg.E7_OWN_REQUESTS.values() if set(names) & set(apart)]
    if sorted(n for g in groups for n in g) != sorted(apart):
        raise ValueError(f"APART must be whole groups of {jg.E7_OWN_REQUESTS}, got {apart}")
    return groups


async def run_llm(concurrency: int) -> None:
    from eval import ground_classifier_eval as g

    sets = dev_sets()
    cases = [c for name in LLM_SETS for c in sets[name]]
    jobs = [(c["id"], r, lambda c=c, r=r: g.classify_llm(c, r)) for c in cases for r in range(1, REPEATS + 1)]
    rows = await _gather(jobs, concurrency)
    _write(LLM_ROWS, {"arm": "llm", "model": g.LLM_GROUND_MODEL, "rows": rows})


def _write(path: Path, data: dict) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    data = {**data, "repeats": REPEATS}
    path.write_text(json.dumps(data, indent=2))
    rows = data["rows"]
    print(f"[{data['arm']}] {sum('output' in r for r in rows)} answered, {sum('error' in r for r in rows)} failed"
          + (f"; model {data['model']}, released {data['release']['release_date']}" if "release" in data else ""))


def _load_rows(path: Path) -> dict[str, list[dict]]:
    out: dict = defaultdict(list)
    if path.exists():
        for r in sorted(json.loads(path.read_text())["rows"], key=lambda r: r["repeat"]):
            if "output" in r:
                out[r["id"]].append(r["output"])
    return out


def jev_answers() -> dict[str, list[dict]]:
    """Per case and repeat, the combined request's answers, with any questions
    moved to requests of their own merged in (repeat i with repeat i)."""
    ans = _load_rows(JEV_ROWS)
    if not APART:
        return dict(ans)
    return merge_apart(ans, _load_rows(JEV_APART_ALL_ROWS), apart_groups(APART))


def merge_apart(ans: dict, apart: dict, groups: list[tuple[str, ...]]) -> dict[str, list[dict]]:
    out = {}
    for cid, reps in ans.items():
        merged = []
        for i, a in enumerate(reps):
            parts = [apart.get(f"{cid}|{','.join(names)}", []) for names in groups]
            if all(i < len(p) for p in parts):
                merged.append({**a, **{k: v for p in parts for k, v in p[i].items()}})
        out[cid] = merged
    return out


def llm_predictions(sets: dict[str, list[dict]]) -> dict[str, list[str]]:
    rows = _load_rows(LLM_ROWS)
    preds = {cid: [o["action"] for o in outs] for cid, outs in rows.items()}
    preds.update(x.llm_preds(sets["spent"]))
    return preds


# --------------------------------------------------------------------------- checks (steps 3 and 4)

def _vals(ans: dict, cases: list[dict], f) -> list[float]:
    return [f(a) for c in cases for a in ans.get(c["id"], [])]


def _noul(q: str):
    return lambda a: a[q]["noul"]


SIGNALS = {"evidence_for_cause": _noul("evidence_for_cause"),
           "1 - plan_reversible": lambda a: 1 - a["plan_reversible"]["noul"],
           "plan_large": _noul("plan_large")}


def aucs(ans: dict, sets: dict[str, list[dict]]) -> dict:
    """The E5c and E5d questions' AUCs on their own dev sets, as E5c and E5d computed them."""
    e5c = sets["e5c"]
    by = {v: [c for c in e5c if c["variant"] == v] for v in ev.VARIANTS}
    implied = by["implied"] + by["symptom_measured"]
    f = SIGNALS["evidence_for_cause"]
    out = {"evidence_for_cause": {
        "evidenced vs asserted": w._auc(_vals(ans, by["evidenced"], f), _vals(ans, by["asserted"], f)),
        "evidenced vs implied": w._auc(_vals(ans, by["evidenced"], f), _vals(ans, implied, f)),
        "asserted vs implied": w._auc(_vals(ans, by["asserted"], f), _vals(ans, implied, f)),
        "evidenced vs symptom_measured": w._auc(_vals(ans, by["evidenced"], f),
                                                _vals(ans, by["symptom_measured"], f))}}
    costly = [c for c in sets["e5d"] if c["cost"] == "costly"]
    cheap = [c for c in sets["e5d"] if c["cost"] == "cheap"]
    for name in ("1 - plan_reversible", "plan_large"):
        out[name] = {"costly vs cheap": w._auc(_vals(ans, costly, SIGNALS[name]), _vals(ans, cheap, SIGNALS[name]))}
    return out


def recorded_aucs() -> dict:
    """The reference E5c and E5d recorded (results/g43_explore/summary_e5c.json, summary_e5d.json)."""
    e5c = json.loads((x.OUT / "summary_e5c.json").read_text())["dev_auc"]["evidence_for_cause"]
    e5d = json.loads((x.OUT / "summary_e5d.json").read_text())["auc_costly_vs_cheap"]
    return {"evidence_for_cause": e5c,
            "1 - plan_reversible": {"costly vs cheap": e5d["1 - plan_reversible"]},
            "plan_large": {"costly vs cheap": e5d["plan_large"]}}


def apart_answers() -> dict[str, list[dict]]:
    rows = _load_rows(JEV_APART_ROWS)
    out: dict = defaultdict(list)
    for key, reps in rows.items():
        cid, _ = key.split("|")
        for i, a in enumerate(reps):
            if len(out[cid]) <= i:
                out[cid].append({})
            out[cid][i].update(a)
    return dict(out)


def auc_check(combined: dict, reference: dict) -> dict:
    """Which questions drop by more than AUC_DROP in the combined request."""
    detail, apart = {}, []
    question = {"evidence_for_cause": "evidence_for_cause", "1 - plan_reversible": "plan_reversible",
                "plan_large": "plan_large"}
    for signal, comps in combined.items():
        for comp, value in comps.items():
            ref = reference[signal][comp]
            dropped = value < ref - AUC_DROP - EPS
            detail[f"{signal}: {comp}"] = {"combined": value, "reference": ref, "dropped": dropped}
            if dropped:
                apart.append(question[signal])
    groups = [names for names in jg.E7_OWN_REQUESTS.values() if set(names) & set(apart)]
    return {"detail": detail, "apart": [n for g in groups for n in g]}


def e5d_mark(ans: dict, sets: dict[str, list[dict]]) -> dict:
    """E5d's pass mark, on the reworded questions (the spec: it must still pass)."""
    cases = sets["e5d"]
    paired = [c for c in cases if c["id"].startswith(sd.TAG)]
    extra = [c for c in cases if not c["id"].startswith(sd.TAG)]

    def right(c, a):
        return jg.plan_costly(a) == (c["cost"] == "costly")

    per_repeat = [sum(right(c, ans[c["id"]][r]) for c in paired if r < len(ans.get(c["id"], [])))
                  for r in range(REPEATS)]
    tricky = all(right(c, a) for c in paired if c["tricky"] for a in ans.get(c["id"], []))
    complete = all(len(ans.get(c["id"], [])) == REPEATS for c in cases)
    extra_costly = [sum(jg.plan_costly(ans[c["id"]][r]) for c in extra if r < len(ans.get(c["id"], [])))
                    for r in range(REPEATS)]
    return {"paired_right_per_repeat": per_repeat, "tricky_all_right": tricky,
            "cheap_extra_called_costly_per_repeat": extra_costly, "complete": complete,
            "passes": complete and min(per_repeat) >= 18 and tricky and max(extra_costly) <= 3}


# The configuration under which a case most easily reaches each branch. Each
# row's condition is monotone in its own threshold, so a case reaches row 6 in
# some configuration exactly when it does in WIDEST_R6, and row 4 likewise in WIDEST_R4.
WIDEST_R6 = jg.E7Config(t_link=0.5, t_ev=0.7, t_ach_conv=0.5, t_fa=0.7, t_ro=0.7)
WIDEST_R4 = jg.E7Config(t_link=0.5, t_ev=0.5, t_ach_conv=0.5, t_fa=0.5, t_ro=0.5)


def post_dev_lists(ans: dict, cases: list[dict]) -> dict:
    """Step 4. On the spent pool, whose labels predate rule (b) and the 2026-11-22 rule:
    every quiet case the candidate reads, in some configuration and some repeat, as an
    asserted cause behind a costly plan; and every case with facts against its cause
    (`facts_against_cause` or `plan_ruled_out` at 0.5 or more in some repeat)."""
    asserted_costly, facts_against = [], []
    for c in cases:
        reps = ans.get(c["id"], [])
        conv = c["shape"] == "conversation"
        if c["expected"] == "none":
            hits = [i + 1 for i, a in enumerate(reps) if jg.e7_row(a, WIDEST_R6, conv) == (6, "objected")]
            if hits:
                asserted_costly.append({"id": c["id"], "shape": c["shape"], "label": c["expected"],
                                        "repeats": hits, "of": len(reps)})
        fa_hits = [i + 1 for i, a in enumerate(reps) if a["facts_against_cause"]["noul"] >= 0.5]
        ro_hits = [i + 1 for i, a in enumerate(reps) if a["plan_ruled_out"]["noul"] >= 0.5]
        if fa_hits or ro_hits:
            facts_against.append({
                "id": c["id"], "shape": c["shape"], "label": c["expected"], "of": len(reps),
                "facts_against_cause": [round(a["facts_against_cause"]["noul"], 2) for a in reps],
                "plan_ruled_out": [round(a["plan_ruled_out"]["noul"], 2) for a in reps],
                "row_4_at_0.5": [jg.e7_row(a, WIDEST_R4, conv) for a in reps]})
    return {"asserted_cause_costly_plan_labelled_quiet": asserted_costly, "facts_against_cause": facts_against}


def render_post_dev(lists: dict, cases: list[dict]) -> str:
    """The page the owner rules from: each listed case's id, label and the user's words."""
    by_id = {c["id"]: c for c in cases}
    lines = ["# E7 post-dev check: spent-pool cases for the owner", "",
             "Listed by code after the dev run (docs/e7_heldout_run_goal.md, \"Before selection\"). "
             "The owner relabels or excludes cases, with the date, before any configuration is picked.", ""]
    sections = (("asserted_cause_costly_plan_labelled_quiet",
                 "Quiet cases the candidate reads as an asserted cause behind a costly plan"),
                ("facts_against_cause", "Cases with facts against their cause"))
    for key, title in sections:
        items = lists[key]
        lines += [f"## {title} ({len(items)})", ""]
        for item in items:
            c = by_id[item["id"]]
            extra = (f"repeats {item['repeats']} of {item['of']}" if "repeats" in item else
                     f"facts_against_cause {item['facts_against_cause']}, plan_ruled_out {item['plan_ruled_out']}")
            lines += [f"### `{c['id']}`", "", f"- Label: `{c['expected']}`; {extra}", ""]
            for t in _user_turns(c):
                lines += [f"> {t}", ">"]
            lines[-1] = ""
            lines.append("")
    return "\n".join(lines)


def _user_turns(c: dict) -> list[str]:
    return [m["content"] for m in c["messages"] if m["role"] == "user"]


# --------------------------------------------------------------------------- selection (step 5)

def cell(c: dict) -> str:
    g = x.group(c) if c["set"] == "spent" else _GROUP[c["expected"]]
    return f"{c['set']} {g}/{c['shape']}"


def rates(preds: dict[str, list[str]], cases: list[dict]) -> dict:
    """Rate per label cell. A failed or missing classification is a miss."""
    return g41._tally(preds, cases, cell, REPEATS)


def utility_of(action: str, wrong: bool, answered: bool, cost: float = COST, loss: float = L) -> float:
    """g43_explore3.utility, with whether the plan is wrong given rather than read off the case."""
    if answered and action != "none":
        return -2 * cost - (loss if wrong else 0.0)
    if action == "none":
        return -loss if wrong else 0.0
    if action == "asked":
        return -cost - ((1 - z.R) * loss if wrong else 0.0)
    return -cost - ((1 - z.R_O) * loss if wrong else 2 * cost)


def weighted_utility(preds: dict[str, list[str]], cases: list[dict], p_wrong, share: float = WRONG_SHARE,
                     cost: float = COST, loss: float = L) -> float:
    """Mean utility per decision, wrong and right plans reweighted to `share`, as
    g43_explore3.weighted_utility. `p_wrong(case)` may be a probability (G44's
    late facts against the cause count as 0.5). A failed or missing
    classification counts as `none`: the app passes the message through."""
    ps = [p_wrong(c) for c in cases]
    pool = sum(ps) / len(ps)
    ww, wr = share / pool, (1 - share) / (1 - pool)
    tot = wsum = 0.0
    for c, p in zip(cases, ps):
        answered = c["scenario"] == "late_answered"
        got = list(preds.get(c["id"], []))[:REPEATS]
        got += ["none"] * (REPEATS - len(got))
        for act in got:
            tot += p * ww * utility_of(act, True, answered, cost, loss) + (1 - p) * wr * utility_of(
                act, False, answered, cost, loss)
            wsum += p * ww + (1 - p) * wr
    return round(tot / wsum, 3)


def spent_p_wrong(c: dict) -> float:
    return 1.0 if z.plan_wrong(c) else 0.0


def _exact(cell: dict) -> float | None:
    """The cell's rate from its counts when it has them (the rounded rate can
    move a drop of exactly one case past the tolerance)."""
    if cell.get("n"):
        return cell["hit"] / cell["n"]
    return cell.get("rate")


def within(jev: dict, llm: dict) -> dict:
    """Per cell: is the candidate no more than max(TOLERANCE, one case) below the LLM?"""
    out = {}
    for k in sorted(set(jev) | set(llm)):
        j, l = jev.get(k, {}), llm.get(k, {})
        n = max(j.get("cases", 0), l.get("cases", 0))
        tol = max(TOLERANCE, 1 / n) if n else TOLERANCE
        jr, lr = _exact(j), _exact(l)
        out[k] = {"jev": j.get("rate"), "llm": l.get("rate"), "tolerance": round(tol, 3),
                  "met": jr is not None and lr is not None and jr >= lr - tol - EPS}
    return out


def predict(ans: dict, cases: list[dict], policy) -> dict[str, list[str]]:
    return {c["id"]: [policy(a, c["shape"] == "conversation") for a in ans.get(c["id"], [])] for c in cases}


def score(preds: dict, llm_cells: dict, labelled: list[dict], spent: list[dict]) -> dict:
    cells = within(rates(preds, labelled), llm_cells)
    return {"cells_within": sum(d["met"] for d in cells.values()), "cells": len(cells),
            "utility": weighted_utility(preds, spent, spent_p_wrong), "detail": cells}


def _distance(cfg: jg.E7Config) -> int:
    return sum(getattr(cfg, k) != 0.5 for k in jg.E7_GRID)


def pick(scored: list[tuple[jg.E7Config, dict]]) -> dict:
    """The spec's rule: most cells within tolerance, ties broken by utility. Ties
    on both go to the configuration with the fewest thresholds away from 0.5,
    then to grid order (fixed before the run). t_ach_conv = 0.3 is chosen only if
    it gains PER_SHAPE_MARGIN of utility over the best configuration without it."""
    order = {cfg: i for i, (cfg, _) in enumerate(scored)}

    def key(item):
        cfg, s = item
        return (-s["cells_within"], -s["utility"], _distance(cfg), order[cfg])

    best = min(scored, key=key)
    shared = min((it for it in scored if not it[0].per_shape), key=key)
    chosen, reason = best, "most cells within tolerance, then utility"
    if best[0].per_shape and best[1]["utility"] < shared[1]["utility"] + PER_SHAPE_MARGIN - EPS:
        chosen = shared
        reason = (f"the best configuration uses t_ach_conv = 0.3 but gains "
                  f"{best[1]['utility'] - shared[1]['utility']:+.3f} of utility, under {PER_SHAPE_MARGIN}")
    return {"chosen": chosen[0], "reason": reason, "best": best[0], "best_shared": shared[0]}


def select() -> dict:
    if POST_DEV_RULED is None:
        raise SystemExit("the owner rules on the post-dev lists first (POST_DEV_RULINGS, POST_DEV_RULED)")
    check_spent()
    sets = dev_sets()
    ans = jev_answers()
    llm = llm_predictions(sets)
    labelled = [c for name in LABELLED for c in sets[name]]
    llm_cells = rates(llm, labelled)
    scored = []
    for cfg in jg.e7_configs():
        preds = predict(ans, labelled, lambda a, conv, cfg=cfg: jg.e7_action(a, cfg, conv))
        scored.append((cfg, score(preds, llm_cells, labelled, sets["spent"])))
    e5b = score(predict(ans, labelled, lambda a, conv: jg.e5b_action(a)), llm_cells, labelled, sets["spent"])
    choice = pick(scored)
    report = {
        "jev": json.loads(JEV_ROWS.read_text())["release"], "apart": list(APART),
        "post_dev_rulings": {"date": POST_DEV_RULED, "rulings": POST_DEV_RULINGS},
        "cases": {k: len(v) for k, v in sets.items()},
        "llm": {"utility": weighted_utility(llm, sets["spent"], spent_p_wrong), "cells": llm_cells},
        "chosen": {"config": choice["chosen"].name, "reason": choice["reason"],
                   "best_overall": choice["best"].name, "best_without_0.3": choice["best_shared"].name},
        "configurations": [{"config": cfg.name, **s} for cfg, s in scored],
        "e5b_baseline": e5b,
    }
    _save("summary_select.json", report)
    return report


def check_requests() -> dict:
    """Step 3's check of the combined request, and E5d's mark on the reworded questions."""
    if AUC_REFERENCE is None:
        raise SystemExit("set AUC_REFERENCE (the owner's choice) before the check")
    sets = dev_sets()
    ans = _load_rows(JEV_ROWS)
    reference = recorded_aucs() if AUC_REFERENCE == "recorded" else aucs(apart_answers(), sets)
    report = {"jev": json.loads(JEV_ROWS.read_text())["release"],
              "auc": {"reference": AUC_REFERENCE, **auc_check(aucs(ans, sets), reference)},
              "e5d_mark": e5d_mark(jev_answers(), sets)}
    _save("summary_requests.json", report)
    return report


def post_dev() -> dict:
    """Step 4's lists, on the candidate's answers as they will be scored (with any
    questions the request check moved apart), and the page the owner rules from."""
    sets = dev_sets()
    lists = post_dev_lists(jev_answers(), sets["spent"])
    report = {"jev": json.loads(JEV_ROWS.read_text())["release"], "apart": list(APART),
              "counts": {k: len(v) for k, v in lists.items()}, **lists}
    _save("summary_post_dev.json", report)
    Path("docs/e7_post_dev_check.md").write_text(render_post_dev(lists, sets["spent"]))
    return report


def _save(name: str, report: dict) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(json.dumps(report, indent=2, default=str))


def main(argv: list[str] | None = None) -> None:
    from eval import cache

    ap = argparse.ArgumentParser(prog="python -m eval.e7_dev")
    ap.add_argument("--record", action="store_true", help="record and freeze the dev conversations' histories")
    ap.add_argument("--run", choices=("jev", "jev_apart_reference", "jev_apart_all", "llm"))
    ap.add_argument("--check-requests", action="store_true")
    ap.add_argument("--post-dev", action="store_true")
    ap.add_argument("--select", action="store_true")
    ap.add_argument("--concurrency", type=int, default=6)
    args = ap.parse_args(argv)
    cache.configure(enabled=True)    # a re-run after a crash pays only for what is missing
    if args.record:
        asyncio.run(record(args.concurrency))
    if args.run == "jev":
        asyncio.run(run_jev(args.concurrency))
    elif args.run in ("jev_apart_reference", "jev_apart_all"):
        asyncio.run(run_jev_apart(args.concurrency, args.run.rsplit("_", 1)[1]))
    elif args.run == "llm":
        asyncio.run(run_llm(args.concurrency))
    if args.check_requests:
        print(json.dumps(check_requests(), indent=2, default=str))
    if args.post_dev:
        print(json.dumps(post_dev(), indent=2, default=str))
    if args.select:
        print(json.dumps(select(), indent=2, default=str))


if __name__ == "__main__":
    main()
