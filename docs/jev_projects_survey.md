# How other projects build around Jev

**Reviewed 2026-11-27.** Nine public projects that use Jev, or a model shaped like it, read at a fixed commit each.

## Why

E7 found that Jev can't replace the LLM grounding classifier ([v3_spike.md](v3_spike.md), "E7 result"). Most of the gap came from one broad question, `achieves_goal`, over whole conversations. This review asks how other projects split the work between Jev and their own code, and what that suggests for Gloss.

## How

Each project was read at the commit in its note:
- one decision was followed end to end, through the code's own files;
- what the surrounding code owns was listed: candidate generation, thresholds, verification, retries, fallbacks and execution;
- saved replays, fixtures or traces were rerun where the repo has them.

**Evidence labels.** Every result is marked as one of:
- **author-reported:** claimed in the repo, not checked;
- **reproduced from saved artifacts:** rebuilt from files committed in the repo;
- **reproduced with fresh model calls:** new Jev calls, at most 20 per project, with the repo's own example inputs only.

No other model's API was called, so anything that needs OpenAI, OpenRouter, a ROM, a Neo4j database or live websites is marked not reproduced.

**Model versions.** On 2026-11-27, `jev-latest` answered as `jev-1.14.0`. The models list showed only `jev-latest` (released 2026-10-22) and `jev-preview`. Pinned `jev-1.13.0` was still served, although it isn't listed. Each response names the version that answered it, in its `model` field.

## What this suggests for Gloss

These are readings, not results: none was tested on Gloss's data.

- **Every project keeps Jev's questions narrow.** None asks one broad judgment question over a long history:
  - Pokémon, Neo4j and the robot arm ask for one choice among a few options the code supplies;
  - the chat moderator (`jev-firehose`) and the voice browser ask several narrow yes/no questions per state, and combine them in code with fixed, ordered thresholds;
  - the closest match to Gloss, `wechat-jev-assistant` (found through the index), splits one judgment about a whole conversation into about 12 narrow questions in one call.

  This fits E7, where narrow questions held up and `achieves_goal` didn't.
- **The code works out the facts and puts them in the state.**
  - Pokémon gives damage, KO and catch estimates per option; the robot arm gives booleans and signed errors.
  - In Neo4j, naming the node instead of passing its id raised the goal-reached score from about 0.7 to 0.96 (fresh calls, one example).
  - The benchmarking paper found that history in the state isn't used reliably (ALFWorld: 45% of steps repeat).

  For Gloss, that points to pulling the relevant turns or facts out of a conversation before asking, not sending it whole.
- **Abstaining and fallback are the code's job, not Jev's:**
  - `wechat-jev-assistant` shows "cannot judge" below a confidence of 0.35, and every choice has an "insufficient context" option;
  - the voice browser adds `none` to every choice, and lets timing rules overrule `complete`;
  - the browser benchmark's hybrid hands a task to an LLM agent when Jev's result can't be verified. It doesn't say how often.
- **Fallback is not free.** In the browser benchmark's desktop lane, Jev-first cost 38% more than the LLM alone, because Jev failed on most tasks first. Gloss should measure the fallback rate per kind of case before counting on savings.
- **Thresholds should be tuned, not left at 0.5.**
  - The benchmarking paper raised one dataset's F1 from 0.50 to 0.75 by tuning the threshold. Where ranking (AUROC) is weak, tuning didn't help.
  - Its choice probabilities were well calibrated, its yes/no probabilities under-confident.
  - Most projects here use untuned defaults.
- **Confidence carries some signal.**
  - Robot arm: the chosen option's median probability was 0.83 on answers that broke the prompt's rules, and 0.91 on the rest (saved artifacts).
  - Responses also carry a `confidence` field that is not the top probability (0.68 against 0.72 in the index, 0.1 against 0.55 in jevlike).

  It's worth testing which of the two separates Gloss's hard cases better.
- **Record the answering version.**
  - The voice browser pins `jev-1.13.0`, because aliases move on release.
  - E7 checked the release date in the models list, not the `model` field of each response, and Gloss didn't store that field. So E7 can't show which version answered each request. Storing it is a small change.

## Notes

### Pokémon Red (`christianmat/jev-pokemon`)

- Repository and commit:
  - `christianmat/jev-pokemon` at `20cdcb846ff995383fe3da1d48ad5eac6d8d1abd` (HEAD of a shallow clone: "Landing page + README: median decision time").
  - TypeScript and Node. The emulator is serverboy (GameBoy-Online core). Jev is called through the Vercel AI SDK `experimental_evaluate` with model `typesafe-ai/jev` (`ai` 7.0.113 in the lockfile). It does not use `typesafe-sdk`.
  - Entry point: `npm start` / `npm run headless`, both `tsx src/server/main.ts`. The main loop calls `Agent.step()`. The debug scripts `scripts/trace.ts` and `scripts/inspect.ts` load a save and step the agent. All of them need a ROM.
  - No ROM, saves, logs or fixtures are committed. `roms/`, `saves/` and `logs/` are gitignored. So is `src/data/generated.json`, which is built from pret/pokered during setup.

- What the project demonstrates:
  - Jev plays all of Pokémon Red. On every turn the harness reads RAM, lists the legal options as `choice` criteria (a key and a prose "facts" string), and presses the buttons for the option Jev returns.
  - It uses four kinds of Jev question, all single-question `choice` calls: battle, overworld target, intent ("focus"), and generic on-screen menus. A fifth, nickname spelling, picks one letter at a time.
  - The claim is a finished game with no scripted play. The harness does supply story milestones and computes a lot of facts for Jev.

- One decision traced end to end (a battle turn; reconstructed from code, since no logged call exists in the repo):
  1. **Mode detection.** `Agent.mode()` returns `battle` when `wIsInBattle != 0`. `battleStep` calls `decideBattle` only when the FIGHT/RUN main menu is on screen with a cursor (`isMainMenu`).
  2. **Emulator state.** `gs.battle()` reads `wEnemyMon`/`wBattleMon` (species, level, HP, status, types, moves with PP). `stats()` reads atk/def/spd/spc from the battle structs. Party and bag are read from RAM.
  3. **Candidate generation**, all in `decideBattle`:
     - `Use <MOVE>` for each of the active Pokémon's moves. The fact string gives type, power, accuracy, PP, a type-effectiveness word, STAB, and a Gen 1 damage range against the foe's current HP. It adds "likely KO" or "high damage", a hit chance adjusted for accuracy and evasion stages, and recoil or self-faint notes. A move with 0 PP stays in the list, marked "0 PP left, unusable".
     - `Switch to <NICK>` for each living benched Pokémon, with its matchup facts.
     - `Use <POTION…>` only when HP is below max. Revive, status-cure and `Throw <BALL>` options appear only where they are legal. A ball option carries an estimated catch % from the Gen 1 formula.
     - `Run away` only in wild battles, with a speed comparison.
     - Pruning: damaging moves the foe is immune to are removed whenever anything else is possible. After two switches in a row against the same foe, switches are removed. In Pokémon Tower without the SILPH SCOPE, the option texts are rewritten to say the move does nothing and the enemy is hidden.
  4. **Typed question.** `jev.choose('battle', state, "You are in a Pokémon battle. Choose the best action for this battle.", opts)`. This sends `{decision: {type:'choice', instructions, criteria: opts}}`. If there is only one option, Jev is not called. `state` is `situation()` (objective, party, bag, money, losses, recent dialog and actions) plus `battle` (enemy with stats, active Pokémon) plus `currentFocus`.
  5. **Returned scores.** Jev returns `{choice, probabilities}`. The client takes `answers.decision.choice` as given. Battle code throws the probabilities away. No threshold, margin or confidence is checked. `providerMetadata.typesafe.confidence` is stored and never read.
  6. **Button press.** `actions[key]()` runs a closure. For a move it is `select('FIGHT')`, then `cursorTo(moveName)` (UP/DOWN/LEFT/RIGHT until the ▶ cursor sits beside the on-screen label), then `confirmA`. `confirmA` presses A, then watches up to 40 frames for the screen to change, and tries 3 times. If the label isn't found, it presses B.
  7. **Logging.** Every call is appended to `logs/jev-calls.jsonl` with state, questions, answers, picked key and latency.
  - Illustrative option shape, from the template at battle.ts L121 (the values are invented, not from a log): `"Use EMBER": "EMBER: FIRE move, power 40, accuracy 100%, 25 PP left. super effective x2 against BUG. Same-type bonus. Estimated damage 18-22 HP vs enemy's 20 HP left (likely KO)."`

- What the model decides:
  - One option key per decision, from a list the harness has already filtered for legality. That covers the battle action, the overworld target (an exit, NPC, item, grass or boulder push), the 7-way intent (progress, heal, train, catch, shop, explore, team), every menu answer, and nickname letters.
  - All the reasoning about type matchups, damage and catch odds is precomputed as text. Jev weighs those facts. It does not compute them.

- What the surrounding code handles:
  - **Candidate generation and facts:** everything above. In the overworld, `buildCandidates` lists reachable targets. Each one carries facts such as "N areas toward the objective" (reverse BFS over a region graph) and visit history.
  - **Pathfinding:** `findPath` in `world.ts` is a grid search with ledges, spinner tiles, surf, blocked squares, a grass cost and a node cap. The README calls it A*, but it pushes `f = g`, so it is really uniform-cost (Dijkstra) search. `walk()` presses one direction per step and checks each one. It returns `ok`, `blocked`, `moved`, `warped` or `interrupted`.
  - **Verification:** `confirmA` checks the screen changed after a press. `runChosen` checks whether an exit attempt actually changed map or region. If not, it records a `blockedExits` or `blockedEdges` count, saves the NPC text that blocked it, and marks the "trap square" so later paths go around it. Milestone progress is checked against real event flags and badges.
  - **Retries:** the gateway allows 4 attempts with a 10 s timeout each. The client wraps that in 5 attempts with exponential backoff (500 ms × 2^n). Either layer can raise, and the main loop catches any error, logs it, waits 30 frames and steps again. An interrupted overworld walk is resumed up to 3 times.
  - **Loop protection:**
    - Overworld options tried with no progress get "ALREADY TRIED n time(s)" added to their text. After 5 tries they are dropped from the pool, except options that lead toward the objective.
    - If Jev picks an option already tried 3 or more times, the harness samples an alternative from Jev's own probabilities, each with +0.05 added.
    - Menus: after 2 closes in a row, a third close is replaced by a probability-weighted alternative. The harness never forces RELEASE, TOSS, SELL, or an unsafe DEPOSIT. If the same menu comes back 5 times, it backs out with B.
    - Client-level `explore` sampling (mixing Jev's distribution 50/50 with uniform after `STUCK_EXPLORE=30` decisions) looks unreachable. It applies only to purpose `overworld`, and `overworldStep` sets `explore=false` around that exact call.
    - Checkpoint reload is off by default (`STUCK_RELOAD=Infinity`), although the README lists it as the last resort.
  - **Throttling and cache:** at least 300 ms between calls and at most 90 per minute. Identical (state, questions) pairs are answered from an LRU cache of 500 entries.
  - **Execution:** all button presses. The harness never writes game memory.
  - **Mock backend:** `MockJev` scores options by regex keywords in the fact strings, adds noise, and applies a softmax. It is a stand-in for development, not a baseline.

- Reported result and how it was measured:
  - All author-reported (README "Result"): the game was beaten in 37h 40m on a YouTube stream on Sep 25–26, 2026. 16,150 decisions, about 39.2M input tokens, about $1.65 of Jev cost, median decision time about 0.4 s. 16 team wipes, 14 of them at the Elite Four, over 15 Elite Four attempts. The final team is listed.
  - Cost is priced at $0.042 per million input tokens. The stream overlay computes it from `usage.inputTokens` of gateway calls that were not served from cache. Latency is wall-clock time in `Jev.ask` and includes throttle waits. The model is `typesafe-ai/jev` via Vercel AI Gateway. No model version or release date is recorded.
  - This is not a benchmark. It is one run, with no baseline, no repeat runs and no success rate per decision. Success means reaching the Hall of Fame (`currentMilestone(gs).m === null`).
  - The run's logs (`jev-calls.jsonl`, `events.jsonl`) are not published, so none of these numbers can be checked.

- What I reproduced and how:
  - Nothing at the result level. There is no ROM (I did not download one), and there are no saved traces, saves or fixtures.
  - Code reading only: I traced the battle path, the client, the gateway, the overworld loop rules and the pathfinder at the pinned commit.
  - `npm ci` worked. `tsc --noEmit` fails only on the missing gitignored `src/data/generated.json`, which needs `npm run setup` to clone and build pret/pokered.
  - No fresh Jev calls. The repo has no example inputs of its own to send, and building a battle state by hand would have meant making up the input. Its real backend also needs a Vercel AI Gateway key, which I do not have.

- Limitation or open question:
  - There is no published per-decision data. We cannot see how peaked Jev's battle distributions were, how often the loop rules overrode it, or how many of the 16,150 decisions were trivial menu or letter picks.
  - Nothing measures how much of the win comes from the harness (legal-only options, precomputed damage, KO and catch facts, milestone routing, pruning of immune moves and repeat switches) rather than from Jev. No ablation and no mock-versus-Jev comparison was reported.
  - There is no validation of the returned key. A key outside `opts` would throw in `actions[key]()`, and the main loop would just retry. We don't know whether that ever happened.

- Source permalinks:
  - README result and how it works: https://github.com/christianmat/jev-pokemon/blob/20cdcb846ff995383fe3da1d48ad5eac6d8d1abd/README.md#L7-L52
  - README logs and cost: https://github.com/christianmat/jev-pokemon/blob/20cdcb846ff995383fe3da1d48ad5eac6d8d1abd/README.md#L86-L95
  - Mode detection and step dispatch: https://github.com/christianmat/jev-pokemon/blob/20cdcb846ff995383fe3da1d48ad5eac6d8d1abd/src/agent/agent.ts#L25-L48
  - Unstick (explore flag, reload off by default): https://github.com/christianmat/jev-pokemon/blob/20cdcb846ff995383fe3da1d48ad5eac6d8d1abd/src/agent/agent.ts#L10-L12 and https://github.com/christianmat/jev-pokemon/blob/20cdcb846ff995383fe3da1d48ad5eac6d8d1abd/src/agent/agent.ts#L97-L112
  - RAM read of battlers: https://github.com/christianmat/jev-pokemon/blob/20cdcb846ff995383fe3da1d48ad5eac6d8d1abd/src/game/state.ts#L110-L127
  - Damage and catch estimates: https://github.com/christianmat/jev-pokemon/blob/20cdcb846ff995383fe3da1d48ad5eac6d8d1abd/src/agent/battle.ts#L39-L57
  - Battle candidate generation: https://github.com/christianmat/jev-pokemon/blob/20cdcb846ff995383fe3da1d48ad5eac6d8d1abd/src/agent/battle.ts#L63-L194
  - Pruning (immune moves, ghost, switch streak): https://github.com/christianmat/jev-pokemon/blob/20cdcb846ff995383fe3da1d48ad5eac6d8d1abd/src/agent/battle.ts#L196-L234
  - Jev call and execution: https://github.com/christianmat/jev-pokemon/blob/20cdcb846ff995383fe3da1d48ad5eac6d8d1abd/src/agent/battle.ts#L235-L240
  - Battle dispatch: https://github.com/christianmat/jev-pokemon/blob/20cdcb846ff995383fe3da1d48ad5eac6d8d1abd/src/agent/battle.ts#L281-L296
  - Shared state summary sent to Jev: https://github.com/christianmat/jev-pokemon/blob/20cdcb846ff995383fe3da1d48ad5eac6d8d1abd/src/agent/context.ts#L114-L150
  - Cursor and press helpers: https://github.com/christianmat/jev-pokemon/blob/20cdcb846ff995383fe3da1d48ad5eac6d8d1abd/src/agent/menus.ts#L57-L84 and https://github.com/christianmat/jev-pokemon/blob/20cdcb846ff995383fe3da1d48ad5eac6d8d1abd/src/agent/menus.ts#L438-L449
  - Menu loop rules: https://github.com/christianmat/jev-pokemon/blob/20cdcb846ff995383fe3da1d48ad5eac6d8d1abd/src/agent/menus.ts#L361-L403
  - Jev client (throttle, cache, retries, argmax/sample, log): https://github.com/christianmat/jev-pokemon/blob/20cdcb846ff995383fe3da1d48ad5eac6d8d1abd/src/jev/client.ts#L44-L134
  - Gateway backend: https://github.com/christianmat/jev-pokemon/blob/20cdcb846ff995383fe3da1d48ad5eac6d8d1abd/src/jev/gateway.ts#L1-L36
  - Mock backend: https://github.com/christianmat/jev-pokemon/blob/20cdcb846ff995383fe3da1d48ad5eac6d8d1abd/src/jev/mock.ts#L1-L62
  - Overworld decision and loop rule: https://github.com/christianmat/jev-pokemon/blob/20cdcb846ff995383fe3da1d48ad5eac6d8d1abd/src/agent/overworld.ts#L1284-L1387
  - Exit verification and recovery: https://github.com/christianmat/jev-pokemon/blob/20cdcb846ff995383fe3da1d48ad5eac6d8d1abd/src/agent/overworld.ts#L1390-L1445
  - Step-by-step walk: https://github.com/christianmat/jev-pokemon/blob/20cdcb846ff995383fe3da1d48ad5eac6d8d1abd/src/agent/overworld.ts#L899-L937
  - Pathfinder (f = g): https://github.com/christianmat/jev-pokemon/blob/20cdcb846ff995383fe3da1d48ad5eac6d8d1abd/src/game/world.ts#L82-L143
  - Region hop BFS: https://github.com/christianmat/jev-pokemon/blob/20cdcb846ff995383fe3da1d48ad5eac6d8d1abd/src/game/regions.ts#L310-L324
  - Main loop error catch: https://github.com/christianmat/jev-pokemon/blob/20cdcb846ff995383fe3da1d48ad5eac6d8d1abd/src/server/main.ts#L167-L195

### Robot-arm control (`openroboto-ai/jev-robot-control`)

- Repository and commit:
  - `openroboto-ai/jev-robot-control` at `7a4ed8b72c3c17d7aa790678ed9660df67c10dd3`. This is a single commit: "Publish Jev xArm7 simulation control experiment".
  - Offline entry point: `verify_replay.py`. Live entry points: `reproduce.py` and `incremental_run.py`. Those need `OPENROUTER_API_KEY`.
  - Git LFS is not used. `.gitattributes` has no LFS filters. The MP4, STL and JSON files are real binaries and data, and `check_manifest.py` verified all 87 hashes. The replay needs nothing beyond the clone.

- What the project demonstrates:
  - Jev drives a simulated xArm7 in MuJoCo to put one apple on one plate. The comparison controllers are GPT-6 Astra (low reasoning) and GPT-4.1 mini.
  - The model never outputs coordinates or torques. Each cycle makes two sequential Jev calls:
    - an 8-way intent `choice`: approach, grasp, lift, carry, lower, release, withdraw, finish;
    - a motor call with four 3-way `choice` questions in one request: X, Y and Z each pick negative, hold or positive, and the gripper picks open, hold or close.
  - A shared executor turns the chosen signs into one small Cartesian step.
  - Observations are simulator geometry and contacts, not camera images.
  - There is one seed-0 trial per controller. This is a demo, not a benchmark.

- One decision traced end to end (Jev run `20260919-200239-0-jev`, cycle 35, the switch from approach to grasp):
  - Input state (`before`):
    - TCP at [379.3, -121.7, 29.3] mm. The grasp target minus TCP is [0.7, 0.2, -1.5] mm.
    - `alignment.grasp_pose_reached` is true for the first time. The code computes it as XY within 4 mm and Z within 2 mm.
    - The gripper is open, there are no finger contacts, `held` is false, and `previous_intent` is approach.
  - Intent question: one `choice` question. Its instructions are `INTENT_INSTRUCTIONS`. Its criteria are the 8 `INTENTS` strings, each a precondition written in terms of observation fields.
  - Intent answer (Jev `typesafe/jev-1.13-20260917`):
    - grasp 0.94, approach 0.05, withdraw 0.01, all others 0;
    - `confidence` 0.93;
    - latency 0.597 s; cost $0.0000557; 1,327 input and 77 output tokens.
  - Motor question:
    - The same state plus `selected_intent: grasp`.
    - Four questions, each with `MOTOR_INSTRUCTIONS` plus axis-specific numbers: current value, grasp target, release target and signed errors.
  - Motor answer:
    - x: hold 0.95;
    - y: hold 0.96;
    - z: hold 0.55 against negative 0.45 (`confidence` 0.31);
    - gripper: close 0.75.
    - Latency 0.976 s; cost $0.000111.
  - Code checks and execution:
    - `validate_choice` checks that the labels are exact, that the probabilities sum to 1 ± 0.025, and that the choice is the argmax.
    - `env.increment` then applies a requested delta of [0, 0, 0] mm and gripper = 1.0 (a ctrl of 230). It runs a 0.32 s smooth interpolation, which is 160 physics steps at 2 ms.
  - Result (`after`):
    - Bilateral finger contacts, `held` true, `bilateral_contact_seconds` 0.21, `grasp_secured` still false.
    - Cycle 36 picked grasp again with p = 1.0, as the prompt requires, and the grasp became secured (0.53 s of contact).
    - In that cycle Jev chose Z negative at 0.55 against hold at 0.45, although the prompt says "GRASP: HOLD all XYZ". The executor applied the -2 mm step without checking.

- What the model decides:
  - Only argmax picks over fixed labels: one intent per cycle, then one sign per axis and one gripper command.
  - Every decision is narrow and local. The state is precomputed, so most intent preconditions reduce to reading booleans such as `grasp_pose_reached`, `over_plate`, `held`, `grasp_secured` and `at_release_height`. Most motor answers reduce to reading the sign of one supplied error against a stated tolerance.

- What the surrounding code handles:
  - Candidate generation: fixed option sets are hard-coded in `incremental_policy.py`.
  - Features: `observe()` computes the signed target-minus-TCP errors, alignment booleans, contact state, a held flag, a contact timer and stability.
  - Thresholds:
    - None are applied to Jev's probabilities. The code takes the argmax, and the `confidence` field is recorded but never used.
    - Physical thresholds are fixed in code: 4 mm, 2 mm, 6 mm, 0.45 s of contact, 0.4 s of stability, and a TCP height of 145 mm for success.
  - Step magnitude: the executor sets it at 18, 4 or 2 mm, depending on the distance to an intent-specific reference point. It keeps the sign the model chose.
  - Safety and verification:
    - Workspace bounds and fixed-orientation IK are in the code. An out-of-bounds or non-converging step is rejected, the arm holds for 0.32 s, and the next observation feeds back the rejection text.
    - Response validation is `validate_choice`.
    - Nothing checks whether the motor choice fits the selected intent.
  - Retries and fallbacks:
    - There are none. Any HTTP, validation or model error ends the trial with `status: error`.
    - The README says there is "no silent fallback to another model".
  - Termination: `env.success()` ends the loop, not the model. Jev never chose `finish`. The run stopped after the 8th withdraw cycle, once the physical criteria held. There is a budget of 160 cycles.
  - Logging: each cycle records the request, response ID, cost, latency, observation, execution, `qpos` and `qvel`.

- Reported result and how it was measured (author-reported):
  - Seed 0, one trial each, budget of 160 cycles.
  - The table below is from README.md and docs/RESULTS.md.

    | Controller | Outcome | Cycles | API calls | Cost | Wall time |
    |---|---|---:|---:|---:|---:|
    | Jev 1.13 | Placed | 113 | 226 | $0.018825 | 181.8 s |
    | GPT-6 Astra (low reasoning) | Placed | 106 | 212 | $5.93 | 707.3 s |
    | GPT-4.1 mini | Hit the 160-cycle limit | 160 | 320 | $0.29 | 704.3 s |

  - Mini comes from an earlier paired run with the same scene, physics and prompts.
  - Costs are the provider-reported `usage.cost` from OpenRouter. Wall time includes model waits. Jev's model wait was 159.8 s of the 181.8 s.
  - Jev and GPT-6 ran concurrently in one pair.
  - The authors say the probabilities are not calibrated task-success estimates.
  - Model: `typesafe/jev-1.13` was requested and resolved to `typesafe/jev-1.13-20260917`, through the OpenRouter `/api/alpha/decisions` endpoint.

- What I reproduced and how:
  - Reproduced from saved artifacts, with no network:
    - Setup: Python 3.12 venv, pinned `mujoco==3.13.0` and `numpy==2.5.3`, on Linux. The authors' reference run used Windows.
    - `check_manifest.py`: 87 hashes OK.
    - Unit tests: 7 of 7 pass.
    - `verify_replay.py` passed in about 12 s. It rebuilt every recorded question and observation from current code, validated every answer, and re-executed every motor command in MuJoCo.
    - Maximum `qpos` error was 5.6e-10 for Jev, 4.6e-10 for GPT-6 and 1.2e-9 for mini, against a tolerance of 1e-7.
    - Outcomes, cycle counts and cost sums match the table.
    - The archived source snapshots are byte-identical to the current `incremental_*.py` files.
  - My own analysis of the saved answers. The rule oracle is my approximation of the prompt's motor rules (a one-off script, not kept):
    - 48 of Jev's 452 motor answers (10.6%) disagree with the oracle. 38 of the 48 are on the Z axis.
    - Example: cycles 30 to 33 hold all axes during approach while Z is still 3 mm above target. Cycle 36 moves Z during grasp.
    - GPT-6 has 0 of 424 disagreements. Mini has 100 of 640 and stays in approach for 156 cycles.
    - Jev's chosen-option probability is informative but loose. The median is 0.91 when it agrees with the oracle and 0.83 when it disagrees. 27% of disagreements have p < 0.6, against 5% of agreements.
  - Reproduced with fresh model calls: 13 calls to `api.typesafe.ai` through `typesafe-sdk` 0.7.6.
    - `jev-1.13` returned 400 "Unknown model".
    - `models.list()` offers `jev-latest` (released 2026-10-22) and `jev-preview` (2026-10-14). Responses report model `jev-1.14.0`, a newer model than the recording.
    - Cycle 35 intent, 3 repeats: grasp each time, p = 0.94, 0.94 and 0.95. This matches the recording.
    - Cycle 35 motor, 3 repeats: same choices each time. x and y hold (0.93 to 0.98), z hold (0.67 to 0.80), gripper close (0.73 to 0.79).
    - Cycle 36 motor, 3 repeats: z now holds, but narrowly (0.52 to 0.57 against negative). The gripper flips between hold and close (0.54, 0.58, then close 0.52).
    - Latency was 0.14 to 0.18 s per call, called directly. The recording, made through OpenRouter, had a median of 0.66 s. The two runs used different routes and model versions.
    - Input tokens were 1,349 for intent and 2,654 for motor; output tokens were 77 and 144.
  - Not reproduced: a full fresh closed-loop trial, and anything with GPT-6 or mini. Both need an OpenRouter key, which the brief forbids. The 3-column web replay server was not launched.

- Limitation or open question:
  - There is n = 1 per controller and seed 0 only. The `seed` parameter adds only ±12 mm of apple jitter, and no other seed is recorded. The README itself says these are not success rates.
  - The task is broken into very narrow questions whose answers are mostly given in the state. Even so, Jev misreads about 1 in 10 motor channels, and several Z decisions are near 50/50.
  - Success depends on the closed loop absorbing errors. A wrong 2 mm step is cheap and the next observation corrects it.
  - Open question: no layer uses Jev's probabilities or `confidence`, for example to re-ask or to fall back to a rule. Would that close the gap with GPT-6's cycle count?

- Source permalinks:
  - Offline verifier: https://github.com/openroboto-ai/jev-robot-control/blob/7a4ed8b72c3c17d7aa790678ed9660df67c10dd3/verify_replay.py#L17-L53
  - Intent criteria and instructions: https://github.com/openroboto-ai/jev-robot-control/blob/7a4ed8b72c3c17d7aa790678ed9660df67c10dd3/incremental_policy.py#L8-L40
  - Answer validation (labels, sum, argmax): https://github.com/openroboto-ai/jev-robot-control/blob/7a4ed8b72c3c17d7aa790678ed9660df67c10dd3/incremental_policy.py#L43-L58
  - Jev request (OpenRouter decisions endpoint): https://github.com/openroboto-ai/jev-robot-control/blob/7a4ed8b72c3c17d7aa790678ed9660df67c10dd3/incremental_policy.py#L76-L81
  - Intent and per-axis motor question construction: https://github.com/openroboto-ai/jev-robot-control/blob/7a4ed8b72c3c17d7aa790678ed9660df67c10dd3/incremental_policy.py#L130-L151
  - Observation and precomputed alignment booleans: https://github.com/openroboto-ai/jev-robot-control/blob/7a4ed8b72c3c17d7aa790678ed9660df67c10dd3/incremental_env.py#L165-L202
  - Success criterion: https://github.com/openroboto-ai/jev-robot-control/blob/7a4ed8b72c3c17d7aa790678ed9660df67c10dd3/incremental_env.py#L204-L205
  - Executor (magnitude scaling, bounds, IK, interpolation): https://github.com/openroboto-ai/jev-robot-control/blob/7a4ed8b72c3c17d7aa790678ed9660df67c10dd3/incremental_env.py#L207-L251
  - Control loop, logging, success stop, error ending the trial: https://github.com/openroboto-ai/jev-robot-control/blob/7a4ed8b72c3c17d7aa790678ed9660df67c10dd3/incremental_run.py#L64-L98
  - Recorded cycle 35 (intent and motor responses): https://github.com/openroboto-ai/jev-robot-control/blob/7a4ed8b72c3c17d7aa790678ed9660df67c10dd3/incremental-gpt6-comparisons/20260919-200239-715974-0/jev/20260919-200239-0-jev.json#L15620-L15790
  - Recorded cycle 35 execution: https://github.com/openroboto-ai/jev-robot-control/blob/7a4ed8b72c3c17d7aa790678ed9660df67c10dd3/incremental-gpt6-comparisons/20260919-200239-715974-0/jev/20260919-200239-0-jev.json#L15886-L15906
  - Reported results and caveats: https://github.com/openroboto-ai/jev-robot-control/blob/7a4ed8b72c3c17d7aa790678ed9660df67c10dd3/README.md#L15-L28
  - Model configuration and probability caveat: https://github.com/openroboto-ai/jev-robot-control/blob/7a4ed8b72c3c17d7aa790678ed9660df67c10dd3/README.md#L132-L144

### Voice-controlled browser (`moritzkremb/jev-voice-browser`)

- Repository and commit:
  - `moritzkremb/jev-voice-browser` at `198a0764395a666f8398026c0d8abdaf6d1866c5` (shallow clone, single commit: "Send conversation context ... 34/34 integration").
  - Node app. Uses `@typesafe-ai/sdk` 0.6.0 (the JS SDK, not the Python `typesafe-sdk` 0.7.6). Model pinned to `jev-1.13.0` in `src/constants.js`.
  - Entry points: `src/server.js` (live mic + Playwright), `scripts/demo.js` (word-by-word replay against real websites), `test/integration/jev-decisions.test.js` (34 real-API cases on page fixtures), `test/unit/*` (mocked Jev, offline).

- What the project demonstrates:
  - Voice control of a real Chromium window. Each partial transcript from the Web Speech API triggers one Jev request with 9 to 11 typed questions about the same state.
  - The state is the transcript, the page (URL, title, site) and up to 100 page elements as one-line strings (`e03 link "new"`), plus the last 3 executed actions as "context".
  - Questions: `intent` (Choice, 17 options with `{what, not_for, examples}`), `target` (Choice over element ids + `none`), `site` (Choice), `complete`, `is_command`, `destructive` (Noul), `scroll_amount` (Score, 3 levels), `tab_direction` (Choice), and conditionally `text_span`, `url_span` (Choice over regex-extracted spans) and `is_correction` (Noul, only when there is history).
  - Code turns the answers into act / wait / ignore / confirm / disambiguate. Jev never writes text: search queries and URLs are regex candidates that Jev picks and code copies verbatim.

- One decision traced end to end:
  - Input: the repo's `wikipedia-main` fixture (Wikipedia main page, 100 elements, search box `e02`). Transcript fed as partials "search", "search for", "search for alan", "search for alan turing", as `scripts/demo.js` does.
  - Candidates per partial come from `extractTextCandidates` in code. For "search for alan turing" they were `["alan turing", "for alan turing", "search for alan turing"]`; no URL candidates.
  - Fresh-call answers (`jev-1.13.0`, policy run with `silentMs=0`, `isFinal=false` unless noted):
    - "search": intent `search_web` 0.83, `complete` 0.19, `is_command` 0.90. Policy: wait (complete gate).
    - "search for": intent `search_web` 0.98, `complete` 0.03, `text_span` = `none` 0.87. Policy: wait (complete gate).
    - "search for alan": intent `search_web` 1.00, `complete` **0.94**, `text_span` = "alan" 1.00, target `e02` 0.97. The complete gate passes. Policy still waits, because code's `payload_final` gate (free-text intents need a final result or 600 ms silence) fails. Without that code rule the browser would have searched for "alan".
    - "search for alan turing": intent 1.00, `complete` 0.98, `text_span` = "alan turing" 1.00, target `e02` 0.99. With 0 ms silence: wait. With 600 ms silence, or `isFinal`: act.
  - Resulting action, built in code: no site named (`site` = `none` 0.99) and the page has a search box, so `type_into_field e02 "alan turing" + Enter`.
  - What the controller does around this: debounce 200 ms per transcript update; up to 2 requests in flight, older ones aborted; a response for an outdated prefix gets `silentMs=0` and is never final; a "wait" schedules a re-check at 900 ms silence (or the 600 ms payload retry), which calls Jev again.

- What the model decides:
  - Narrow, per-utterance judgments, each as its own typed question: which of 17 intents, which element id, which site, which extracted span, whether the words so far form a complete command, whether they are addressed to the browser, whether the action is destructive, and whether they correct the last action.
  - The model judges an unfinished utterance only as "complete so far". It cannot tell whether more words are coming. "search for alan" scored 0.94 complete.

- What the surrounding code handles:
  - Candidate generation: element snapshot (cap 100, 60 chars, viewport first); regex text spans (≤ 8) and spoken-URL spans (≤ 6); `none` added to every Choice.
  - Thresholds in one object `T`: `is_command ≥ 0.5`, intent confidence ≥ 0.55 and not `none`, `complete ≥ 0.6`, target confidence ≥ 0.45 and top probability ≥ 0.35, span confidence ≥ 0.35, `destructive ≥ 0.5` → confirm, `is_correction ≥ 0.6`.
  - Timing rules that override the model: 900 ms silence or a final recognizer result counts as complete; free-text intents need a final result or 600 ms silence whatever `complete` says.
  - Ordered gates: pending confirm/cancel → correction (reverse last action, or exclude last target) → is_command → intent → complete → payload → build action → destructive.
  - Execution: URL templates and site home pages, search-box fallback, verbatim span copy, Playwright actions, undo by `reverseAction`.
  - Fallbacks: low target confidence shows numbered overlays, and a spoken number is parsed by regex with no model call. Low span confidence falls back to the first heuristic candidate. Unknown destination → wait.
  - Retries: SDK `maxRetries: 1`, 8 s timeout. Stale requests aborted with `AbortSignal`. One action per utterance; extra words (≥ 2) after an executed command become a new command.
  - Memory: Jev is stateless, so code keeps previous page + last 3 actions and sends them in the state.

- Reported result and how it was measured:
  - Author-reported (README, "Sep 2026, from this machine"): integration 34/34 (100%); Jev latency avg ≈ 330 ms, p50 ≈ 300 ms; 3 to 6k input tokens per request; first request of a process ≈ 700 ms (TLS); "last-word→decision ≈ 300 ms including the 200 ms debounce"; whole demo ≈ $0.01. `DEMO.md` still says 27/27. No saved run logs or traces are in the repo.
  - What is timed, from code:
    - "Jev latency" (`latencyMs`) is client wall clock around `client.systemOne(...).withResponse()` in `src/jev.js`. It includes network, proxy, TLS and any SDK retry. There is no server-side timing.
    - "last word→decision" (`decisionLagMs`) is `Date.now() - utterance.updatedAt` at decision time. `updatedAt` is the last transcript update the server received, not when the person spoke. So recognizer delay (Web Speech API, Google) is not counted. It includes the 200 ms debounce, any snapshot refresh (`refreshSnapshot` if > 1.5 s old, a Playwright call before the Jev call) and the Jev round trip.
    - "last word→action done" adds Playwright execution and page load.
  - Benchmark design: 34 hand-written cases on 4 captured page fixtures + 3 inline pages. Expectations on intent, target, decision, text, URL, scroll amount, correction. Pass bar ≥ 90%. Most cases run with `isFinal=true`, so the `complete` gate is bypassed except in 2 partial cases ("go to", "search for"). No baseline model and no repeated runs.
  - Open inconsistency: if the Jev round trip averages 330 ms, a 300 ms last-word→decision that includes a 200 ms debounce is not possible for a decision on the last word. It can only hold if decisions come from requests on earlier partials, or if Jev was faster in that run.

- What I reproduced and how:
  - Reproduced offline: `npm install` then `npm test`. 45/45 unit tests pass (mocked Jev and browser; spans, snapshot, policy, controller, context).
  - Reproduced with fresh model calls: 13 HTTP calls in all (1 `models.list` + 12 `systemOne`) through the repo's own `decide()` and `evaluatePolicy()`, using its fixtures and the inline test pages. The script and raw output were one-off and are not kept.
    - Model reported in every response: `jev-1.13.0`. `models.list` returned only `jev-latest` (release 2026-10-22) and `jev-preview` (2026-10-14); the pinned `jev-1.13.0` is not listed but is accepted.
    - Decisions matched the integration expectations on the overlapping cases: "go to wikipedia" act; "go to" wait (`complete` 0.05); "search for alan turing" on Wikipedia → type into `e02`; chit-chat ignore (`is_command` 0.01); "click place order" → confirm (`destructive` 0.95, target `e05` 1.00); "no not that one" with context → `is_correction` 0.84 → go_back.
    - Latency (client wall clock from a cloud machine, through an HTTPS proxy, `api.typesafe.ai` behind Cloudflare): 143 to 199 ms per call, about half the README figure. About 3.2k input tokens with 1 element (example.com) took 143 to 152 ms. About 6.0k tokens with 100 elements took 166 to 199 ms. A near-empty `GET models` took 139 ms. So a fixed round trip of about 140 ms dominates, and tokens add roughly 10 ms per 1k. The response body arrived within 1 to 2 ms of the headers. No cold-start penalty was seen (147 vs 143 ms).
    - Token floor: the question set alone (intent options with examples, etc.) costs about 3.2k tokens. The 100-element snapshot adds about 2.8k. API-reported output tokens were 444 to 1575 per call; the repo treats output as free and prices input at $0.042/M (a repo constant, not checked against billing).
  - Not reproduced: `scripts/demo.js` and the live server. They need a Playwright Chromium and real websites, and a full demo makes far more than 20 Jev calls. The full 34-case integration run was also skipped (34 calls > limit of 20). So the author's 34/34, the 300 ms last-word→decision and "acted before the sentence ended" are author-reported only.

- Limitation or open question:
  - `complete` is a grammar judgment on the prefix, not a forecast of more speech. The product's "act before you finish" works only for closed-set intents. Free-text commands always wait for 600 ms silence or the final result, a rule owned by code.
  - Thresholds are said to be "calibrated on jev-1.13.0", but there is no calibration data or script in the repo. The cases are few and nearly all score at 0.95 to 1.00, so they do not test the thresholds.
  - The latency claim does not separate fixed network round trip from token-dependent compute, and leaves out recognizer delay. Would the end-to-end number hold with a different network path?

- Source permalinks:
  - Thresholds, timing constants, model pin: https://github.com/moritzkremb/jev-voice-browser/blob/198a0764395a666f8398026c0d8abdaf6d1866c5/src/constants.js#L15-L60
  - `complete` question text: https://github.com/moritzkremb/jev-voice-browser/blob/198a0764395a666f8398026c0d8abdaf6d1866c5/src/constants.js#L232-L249
  - Intent question (judge "words said so far"): https://github.com/moritzkremb/jev-voice-browser/blob/198a0764395a666f8398026c0d8abdaf6d1866c5/src/constants.js#L205-L212
  - State + question fan-out: https://github.com/moritzkremb/jev-voice-browser/blob/198a0764395a666f8398026c0d8abdaf6d1866c5/src/jev.js#L93-L146
  - What "Jev latency" times: https://github.com/moritzkremb/jev-voice-browser/blob/198a0764395a666f8398026c0d8abdaf6d1866c5/src/jev.js#L152-L171
  - SDK client retry and timeout: https://github.com/moritzkremb/jev-voice-browser/blob/198a0764395a666f8398026c0d8abdaf6d1866c5/src/jev.js#L19-L25
  - Policy gates, in order: https://github.com/moritzkremb/jev-voice-browser/blob/198a0764395a666f8398026c0d8abdaf6d1866c5/src/policy.js#L56-L161
  - Payload (free-text) silence gate: https://github.com/moritzkremb/jev-voice-browser/blob/198a0764395a666f8398026c0d8abdaf6d1866c5/src/policy.js#L126-L140
  - Search action built in code: https://github.com/moritzkremb/jev-voice-browser/blob/198a0764395a666f8398026c0d8abdaf6d1866c5/src/policy.js#L202-L216
  - Target gate and disambiguation fallback: https://github.com/moritzkremb/jev-voice-browser/blob/198a0764395a666f8398026c0d8abdaf6d1866c5/src/policy.js#L218-L264
  - Text span candidates (regex): https://github.com/moritzkremb/jev-voice-browser/blob/198a0764395a666f8398026c0d8abdaf6d1866c5/src/spans.js#L55-L86
  - Debounce per transcript update: https://github.com/moritzkremb/jev-voice-browser/blob/198a0764395a666f8398026c0d8abdaf6d1866c5/src/controller.js#L127-L129
  - In-flight cap, abort, snapshot refresh, stale-prefix handling, `decisionLagMs`: https://github.com/moritzkremb/jev-voice-browser/blob/198a0764395a666f8398026c0d8abdaf6d1866c5/src/controller.js#L144-L230
  - Silence re-check: https://github.com/moritzkremb/jev-voice-browser/blob/198a0764395a666f8398026c0d8abdaf6d1866c5/src/controller.js#L274-L281
  - Integration cases and pass bar: https://github.com/moritzkremb/jev-voice-browser/blob/198a0764395a666f8398026c0d8abdaf6d1866c5/test/integration/jev-decisions.test.js#L73-L101 and https://github.com/moritzkremb/jev-voice-browser/blob/198a0764395a666f8398026c0d8abdaf6d1866c5/test/integration/jev-decisions.test.js#L181-L190
  - Demo word-by-word replay: https://github.com/moritzkremb/jev-voice-browser/blob/198a0764395a666f8398026c0d8abdaf6d1866c5/scripts/demo.js#L135-L174
  - README latency claim: https://github.com/moritzkremb/jev-voice-browser/blob/198a0764395a666f8398026c0d8abdaf6d1866c5/README.md#L163-L165

### Neo4j navigation (`jexp/neo4jev`)

- Repository and commit:
  - `jexp/neo4jev` at `d157bbe496eb91813475156942bef1c6badfb342` (2026-09-18, "navigator: include the live graph schema (labels + topology) in every Jev state"). The clone is shallow, so only that one commit is present.
  - Entry points: `notebooks/02_navigator_dry_run.ipynb` (one hop) and `notebooks/03_full_traversal.ipynb` (full beam search, all three goal modes). Both call `src/neo4jev/navigator.py`. `app/streamlit_app.py` wraps the same code.
  - The lockfile pins `typesafe-sdk` 0.6.0, and `pyproject.toml` asks for `>=0.6.0`. I ran everything with 0.7.6.

- What the project demonstrates:
  - Walking a Neo4j knowledge graph (the public "Companies KG", database `companies2`) one hop at a time. At each hop Jev picks the next relationship.
  - Each hop is exactly one `system_one` call with two questions:
    - a `Choice` (`next_edge`) over the capped outgoing edges, keyed `e0..eN`;
    - a `Noul` (`goal_reached`): "has the goal already been reached at the current node?"
  - The code turns Jev's probability distribution into a beam search: top-k plus a cutoff per hop, paths ranked by the sum of log-probabilities, and a goal threshold on the Noul.
  - There are three goal modes: `free_text`, `target_node` and `path_intent`.
  - This is a demo, not a benchmark. There is no task set, no baseline and no success metric beyond "runs end to end".

- One decision traced end to end (notebook 02, saved outputs):
  - Input state: the start node is Apple Inc. (`4:...:4`), found by a fulltext lookup for "Apple". It has 1354 outgoing edges. `get_outgoing_relationships` keeps at most 10 per relationship type, then fills a 60-edge budget round-robin across types in name order. Within a type, edges are ordered by `elementId(r)`, not by relevance. Result: 60 of 1354 edges, with 4 of 26 `HAS_COMPETITOR` edges.
  - State payload (`_node_state`): `current_node` (id, label, properties with long text cut to 200 characters and lists dropped), `path_so_far`, `hop_index` and `goal`. It also gets `graph_schema` when `NavigatorConfig.schema` is set. The notebooks do not set it. The app does.
  - Typed questions:
    - Choice instructions: "Choose the single outgoing relationship that best advances the navigation goal… Goal: move toward an organization that competes with the start organization".
    - Each option's criteria: `relationship_type`, `relationship_properties`, `target_label` and `target_properties`. They do not include the target element id.
    - Noul criteria: the `true` text is the goal text itself, and the `false` text is "The current node does not satisfy the goal description."
  - Returned (saved output): 60 probabilities summing to 1.0.
    - e8 `HAS_COMPETITOR`→Amazon 0.43, e24 `HAS_COMPETITOR`→Microsoft 0.40, e40 `HAS_COMPETITOR`→Samsung 0.14, e55 →Nokia 0.02, e9 `HAS_CUSTOMER`→Microsoft 0.01, all others 0.0.
    - Noul 0.09. Choice confidence 0.41.
  - Resulting action (`_select_branches`, with `top_k=2`, `cutoff=0.05`): keep e8 and e24.
    - The Noul is below `goal_threshold=0.5`, so the search does not stop.
    - Each kept branch adds `ln p` to its score (ln 0.43 = −0.844). Children already visited are skipped.
    - The frontier is cut to `beam_width`.
  - In a full run (notebook 03, `free_text`, "find an organization that competes with Google", `max_depth=2`, `max_calls=6`, `beam_width=2`):
    - The path was Google →`HAS_COMPETITOR` (p=0.88)→ Apple →`HAS_COMPETITOR` (p=0.74)→ Microsoft. Score −0.429. It stopped on `max_depth`, not on `goal_reached`.
    - So the Noul at Apple was below 0.5, even though Apple already satisfies the goal. I infer this from the code path: the Noul check runs before branching.

- What the model decides:
  - A probability over the capped candidate edges at the current node.
  - One Noul per node: has the free-text or path-intent goal been reached?
  - Identity properties (a separate use in `neo4j_access._select_display_properties`): one Choice per label picks which properties name a node (for example `fullName`, `name`). Those properties then lead in the prompt and in captions. The app uses this. The notebooks only use it for rendering.
  - The model never sees the edges the cap left out, and never sees element ids of candidate targets.

- What the surrounding code handles:
  - Candidate generation: a Cypher fetch, capped per type and in total, with deterministic ordering. Properties are trimmed. The API limit of 255 options is enforced as a backstop.
  - Thresholds:
    - `cutoff` (default 0.05) and `top_k` (default 2). If nothing clears the cutoff, the single best edge is kept anyway.
    - `goal_threshold` (default 0.5) on the Noul.
    - `beam_width` (default 4).
  - Verification and stopping:
    - `target_node` stops on an exact element-id match and ignores the Noul.
    - A visited set prevents cycles.
    - Other stopping reasons: `max_depth`, `max_calls` budget and `no_candidates`.
    - A node at `max_depth` is closed without a call, so the last node of a path never gets a Noul check.
  - Scoring: the sum of `ln max(p, 1e-12)`. Choice confidence is shown but deliberately not used.
  - Result selection: the best path, or the top N distinct node sequences for `path_intent`. Path-intent stages are split on the text with "->", ";" and similar separators, one stage per hop.
  - Retries and fallbacks:
    - The navigator has no retry or fallback. `TypeSafeError` propagates.
    - The notebooks then switch to a `KeywordStubClient` that is clearly labelled as not TypeSafe output.
    - Identity derivation falls back to a local ranking.
  - Execution: concurrent `asyncio.gather` per beam level, and rendering with `neo4j-viz`. Nothing is written to the graph.

- Reported result and how it was measured:
  - Saved notebook outputs (from the author's run; the model version is not recorded):
    - Notebook 02 hop as above.
    - Notebook 03:
      - `free_text`: stopped on `max_depth`, score −0.429.
      - `target_node` (target Microsoft `:10`, a direct out-neighbour of Google): failed. It went Google →`HAS_SUBSIDIARY` (0.47)→ YouTube →`HAS_SUBSIDIARY` (0.22)→ a streaming service, then `no_candidates`. The saved check "target element id appears on a returned path" reads False.
      - `path_intent` (article → mentioned organizations → their competitors): 3 distinct paths with scores −0.445, −2.674 and −2.736.
    - No run ended on `goal_reached`.
  - `.plans/progress-graph-navigation-demo.txt` (author-reported): 157 unit and 11 integration tests passed with a live key. The integration tests only check output shape (probabilities exist, the Noul is in [0, 1], chosen p ≥ cutoff), not quality. Timing and cost were not measured.

- What I reproduced and how:
  - Reproduced from saved artifacts:
    - I parsed notebook 02's printed candidate table and probability dict (`neo4jev_work/extract.py`).
    - I replayed them through the real `one_hop` / `navigate` with a scripted client (`replay.py`). The selection matches the saved one (e8, e24). Noul 0.09 means no stop.
    - The sums of `ln p` match every saved notebook 03 score (−0.429, −2.269, −0.445, −2.674, −2.736).
    - I confirmed that a `target_node` element id never appears in the Choice criteria.
    - Small bug found: when the budget is smaller than the frontier (`navigator.py` L613), unexpanded branches are silently dropped, not reported as `budget_exhausted`. With `max_calls=2`, `path_intent` returned only the e8 path. With `max_calls=3` it returned both.
  - Unit tests: 161 passed offline with `typesafe-sdk` 0.7.6, Python 3.12, in a scratch virtualenv.
  - Reproduced with fresh model calls: 7 calls in total (1 `models.list` and 6 `system_one`), all through the repo's own `one_hop`.
    - Model: `jev-latest`, release date 2026-10-22. This is newer than the September 2026 notebook run.
    - Latency per call: 0.16–0.40 s wall clock from a cloud machine, through an HTTPS proxy. Token usage was not captured.
    - The inputs were rebuilt from the saved outputs, so target properties were reduced to 60-character captions. They are approximate, not identical.
    - Notebook 02 hop, run twice: all top 4 are `HAS_COMPETITOR` edges, as in the saved run. The order changed: Samsung 0.56 / 0.46, Amazon 0.23 / 0.30, Microsoft 0.16 / 0.19. The Noul was 0.09 and 0.08, matching the saved 0.09.
    - Notebook 03 `free_text` hop 2 at Apple, rebuilt as the navigator builds it: the Noul was 0.68 and 0.74. Under the default threshold that run would have stopped at Apple. The saved run did not stop there.
    - Variant (my change, not repo code): I put "Google LLC" into `path_so_far.from_node`. The Noul rose to 0.96. The repo's `path_so_far` carries only element ids and relationship types, so the model cannot see what "Google" was.
    - `target_node` toward Microsoft's id from Apple: the top picks were `HAS_SUBSIDIARY`→Apple 0.31 and Beats 0.09. No Microsoft edge reached the top 5. This matches the saved notebook 03 failure.
  - Not reproduced: anything against Neo4j. No database was available, and I was told not to start one. The live notebooks and the Streamlit app were not run.

- Limitation or open question:
  - The stopping rule is fragile. The Noul is asked about the current node with a thin `path_so_far` (ids only). The saved run never fired it. Fresh calls on rebuilt inputs went over 0.5, and naming the start node raised the Noul further. Is the gap down to the model version, or to missing context?
  - `target_node` mode cannot work as designed. The goal is an element id that never appears in any option, so the code's id check is the only thing that can find the target. The author flagged this only as a stub limitation.
  - The final node at `max_depth` is never checked by the Noul.
  - Within a type, the cap keeps the first edges by `elementId`, so the model only ever ranks an arbitrary sample.
  - The notebooks did not pass `schema` and did not record the model name. The HEAD commit's schema feature is therefore not reflected in any saved output.

- Source permalinks:
  - Config defaults (top_k, cutoff, goal_threshold, beam_width): https://github.com/jexp/neo4jev/blob/d157bbe496eb91813475156942bef1c6badfb342/src/neo4jev/navigator.py#L52-L74
  - Option criteria (no target id): https://github.com/jexp/neo4jev/blob/d157bbe496eb91813475156942bef1c6badfb342/src/neo4jev/navigator.py#L178-L195
  - Noul stop rule and target check: https://github.com/jexp/neo4jev/blob/d157bbe496eb91813475156942bef1c6badfb342/src/neo4jev/navigator.py#L245-L251
  - Goal resolution (target goal text is the id): https://github.com/jexp/neo4jev/blob/d157bbe496eb91813475156942bef1c6badfb342/src/neo4jev/navigator.py#L275-L300
  - State payload: https://github.com/jexp/neo4jev/blob/d157bbe496eb91813475156942bef1c6badfb342/src/neo4jev/navigator.py#L303-L339
  - Top-k and cutoff selection: https://github.com/jexp/neo4jev/blob/d157bbe496eb91813475156942bef1c6badfb342/src/neo4jev/navigator.py#L342-L358
  - One call, Choice plus Noul: https://github.com/jexp/neo4jev/blob/d157bbe496eb91813475156942bef1c6badfb342/src/neo4jev/navigator.py#L400-L436
  - Expansion (Noul stop, ln p, visited, target): https://github.com/jexp/neo4jev/blob/d157bbe496eb91813475156942bef1c6badfb342/src/neo4jev/navigator.py#L499-L540
  - Beam loop (depth cap, budget slice, beam width): https://github.com/jexp/neo4jev/blob/d157bbe496eb91813475156942bef1c6badfb342/src/neo4jev/navigator.py#L604-L639
  - Candidate cap (round robin): https://github.com/jexp/neo4jev/blob/d157bbe496eb91813475156942bef1c6badfb342/src/neo4jev/neo4j_access.py#L163-L207
  - Candidate fetch (ordered by elementId): https://github.com/jexp/neo4jev/blob/d157bbe496eb91813475156942bef1c6badfb342/src/neo4jev/neo4j_access.py#L866-L943
  - Identity-property Choice: https://github.com/jexp/neo4jev/blob/d157bbe496eb91813475156942bef1c6badfb342/src/neo4jev/neo4j_access.py#L712-L743
  - Notebook 02 saved cap, hop and probabilities: https://github.com/jexp/neo4jev/blob/d157bbe496eb91813475156942bef1c6badfb342/notebooks/02_navigator_dry_run.ipynb#L206-L250 and https://github.com/jexp/neo4jev/blob/d157bbe496eb91813475156942bef1c6badfb342/notebooks/02_navigator_dry_run.ipynb#L332-L477
  - Notebook 03 saved `free_text` result: https://github.com/jexp/neo4jev/blob/d157bbe496eb91813475156942bef1c6badfb342/notebooks/03_full_traversal.ipynb#L440-L442
  - Notebook 03 saved `target_node` failure: https://github.com/jexp/neo4jev/blob/d157bbe496eb91813475156942bef1c6badfb342/notebooks/03_full_traversal.ipynb#L1774-L1779
  - App passes schema and derives identity: https://github.com/jexp/neo4jev/blob/d157bbe496eb91813475156942bef1c6badfb342/app/streamlit_app.py#L220-L233
  - My scripts and results were one-off (`extract.py`, `replay.py`, `budget.py`, `fresh.py`, `fresh_results.json`) and are not kept.

### Browser automation benchmark (`steve8708/jev-browser-benchmark`)

- Repository and commit:
  - `steve8708/jev-browser-benchmark` at `61588f06c5a0b48ff1ffa9e61176e91bc11cb38e` ("Clarify overall aggregate results", 2026-09-21). This is the only commit in the shallow clone.
  - The repo has 9 files and no code: `README.md`, `RESULTS.md`, `data/results.json`, `report.html`, two report screenshots, `videos/README.md`, `LICENSE`, `.gitignore`.
  - There is no runner, harness, prompt, task list, per-task log or trace. The README says the full runner depends on private accounts, local browser sessions and desktop apps, so only the results are published.
  - The only "entry point" given is `python3 -m json.tool data/results.json` and opening `report.html`.

- What the project demonstrates:
  - A results snapshot (run date 2026-09-21) comparing four systems on three lanes:
    - Jev Browser: a fast Jev browser-action system.
    - Jev Ultrafast: a faster Jev variant.
    - Luna: "Luna-style visual computer use", an LLM computer-use agent. Provider and model version are not named.
    - Hybrid: Jev first, then verification, then fallback to Luna.
  - Task sets (author-reported; the tasks themselves are not published):
    - Simple browser: 42 controlled tasks (navigation, clicking, selecting, scrolling, forms, small edits, state checks).
    - Longer browser: 10 multi-step flows (flight search, restaurant reservation, TodoMVC, Drive, Notion, Figma, mail, other authenticated checkpoints). Jev Ultrafast was run on a separate public 9-flow set instead, so it is not comparable.
    - Native desktop: 5 tasks (Spotify, TextEdit, Pages, Keynote, Numbers). Jev Ultrafast was not run.
  - Sample size is n=1 run per task. No repeats, variance or confidence intervals are reported.
  - Headline claim: Hybrid ties Luna on success in every lane (39/42, 7/10, 5/5; 51/57 overall) and is faster and cheaper per success, except on desktop, where it costs more.

- One decision traced end to end:
  - Not possible from this repo. No Jev input state, typed question, candidate options or returned scores appear anywhere in it.
  - The closest description of the Hybrid decision is one sentence: "Hybrid used Jev when its result could be verified and used Luna when it could not" (RESULTS.md L62). Elsewhere: "try the cheap action path, verify the result, and spend Luna effort only when needed" (L68).
  - `videos/README.md` mentions local clips "showing the Jev attempt and fallback boundary". These are not published.
  - What a Hybrid decision would look like, as far as the text allows:
    - input: a task in a browser or desktop app;
    - Jev proposes and executes an action;
    - an unnamed verifier checks the resulting state;
    - on a failed check, or when no check is possible, Luna takes over.
  - The text does not say what Jev's output is (an action, a target, a probability). It does not say whether a confidence threshold is used.

- What the model decides:
  - Jev: the browser or desktop action, in some form the repo does not show. Its raw success rate falls with task difficulty:
    - 18/42 simple browser;
    - 0/10 longer browser;
    - 1/5 desktop.
  - Luna, the fallback: interprets the screen, types, recovers from drift and "verifies richer state" (RESULTS.md L67).
  - Whether Jev itself scores or gates anything is not stated.

- What the surrounding code handles (as described; no code is available to confirm):
  - Candidate generation: not described.
  - Thresholds: not described. There is no mention of a Jev confidence cutoff.
  - Verification:
    - Hybrid verifies Jev's result before accepting it.
    - The verifier is not described: it could be a DOM or state check, a Luna check, or a scripted assertion. The repo does not say which.
    - "Could not be verified" is ambiguous. It may mean a check that failed, a check that could not be run, or both.
  - Fallback trigger: a failed or missing verification. Fallback target: Luna.
  - Retries: no Jev retries are described.
  - Fallback count: not reported in any file. My inferences, from saved aggregates only, are below.
  - Execution:
    - Local browser and desktop tooling (cost treated as $0).
    - On the longer lane, Hybrid used a "staged recorded fallback rather than one uninterrupted live turn" (RESULTS.md L69, results.json L28). The Jev attempt and the Luna fallback were therefore not one live run, and the stitching is not explained.
  - Success criteria:
    - Longer lane: "the defined checkpoint was reached and verified", stopping before any irreversible purchase, booking or send. Who or what verified it is not stated.
    - Simple and desktop lanes: no success definition is given beyond the task descriptions.
  - Separate capability checks are kept out of the headline numbers:
    - A deterministic browser-tool probe scored 14/14.
    - "Jev plus deterministic replay" scored 42/42.
    - Both are flagged as "not a model score".

- Reported result and how it was measured (all author-reported):
  - Simple browser:
    - Hybrid: 39/42, 25.19 s/task, $0.006922 per success.
    - Luna: 39/42, 32.49 s, $0.010741.
    - Jev Browser: 18/42, 1.77 s, $0.000301.
    - Jev Ultrafast: 18/42, 0.77 s, $0.000453.
  - Longer browser:
    - Hybrid: 7/10, 45.3 s, total $0.1241.
    - Luna: 7/10, 98.7 s, total $0.1876.
    - Jev Browser: 0/10, 11.4 s, total $0.00583.
  - Native desktop (costs are a proxy):
    - Hybrid: 5/5, 36.11 s, $0.012644 per success.
    - Luna: 5/5, 37.82 s, $0.00913.
    - Jev: 1/5, 9.3 s, $0.0227.
  - Overall: Hybrid and Luna 51/57 (89.5%); Jev Browser 19/57 (33.3%); Jev Ultrafast 19/51 (37.3%).
  - Cost measurement:
    - Jev cost is the "recorded API estimate".
    - Luna cost is a "token/action proxy".
    - These are not invoices or provider prices.
  - Timing: "average time" is per task attempted, including failures. I confirmed this from the overall reconstruction below. Hardware and network are not stated.
  - Model versions: none given. "Jev Browser" and "Jev Ultrafast" are product labels, and Luna's provider and version are not given.

- What I reproduced and how:
  - Reproduced from saved artifacts: the overall table from the per-lane rows in `data/results.json`, by recomputing totals with a short Python script.
    - All four overall rows match exactly (51/57, 29.68 s, $0.00897; 51/57, 44.57 s, $0.01279; 19/57, 4.12 s, $0.00179; 19/51, 1.07 s, $0.00118).
    - Overall averages are task-weighted means across lanes. Cost per success is the total cost divided by total successes.
    - The Jev Browser overall row uses the desktop row labelled "Jev".
  - My inference from saved aggregates, on how often Hybrid falls back and what it costs. None of this is reported by the author.
    - Simple lane:
      - Jev failed 24/42 tasks, so at least about 24 fallbacks if every Jev success was verified.
      - Hybrid's total cost minus Jev's total, divided by Luna's mean per-task cost ($0.00997), gives about 26.5 Luna-task equivalents.
      - The time difference gives about 30 Luna-task equivalents.
      - So roughly 24 to 30 of 42 tasks (57 to 71%) needed Luna, and a fallback costs about one full Luna run.
      - Hybrid's success count equals Luna's exactly (39). That fits Luna's 3 failures all falling among Jev's 24 failures, but per-task data would be needed to confirm it.
    - Longer lane:
      - Jev was 0/10, so all 10 tasks fell back.
      - Hybrid still cost 66% of Luna's total and took 46% of its time.
      - So the fallback did not restart Luna from scratch: it resumed from a staged or recorded point. The headline saving here comes from that staging, not from Jev solving anything.
    - Desktop lane:
      - Jev was 1/5, so about 4 fallbacks. The cost implies about 4.4 Luna-task equivalents and the time about 3.5.
      - Hybrid cost 38% more than Luna ($0.0632 vs $0.0457 total), because Jev's $0.0227 of attempts was wasted on top of Luna.
      - This is the one lane where Jev-first costs more than going straight to the LLM.
  - Not reproduced, with fresh calls or otherwise: no runner, tasks, prompts, Jev inputs or credentials for the private accounts are published, and Luna would need a non-Jev API key.
  - I made no Jev calls because the repo contains no example inputs to send.

- Limitation or open question:
  - The fallback rule, the verifier and the fallback counts are not published. Every claim about Hybrid rests on one sentence of prose plus aggregates.
  - The longer-lane Hybrid run is a staged stitch of a Jev attempt and a recorded Luna fallback, not a live run. Its 45.3 s and $0.1241 may understate a real end-to-end handoff.
  - Hybrid ties Luna exactly in every lane. With n=1 per task and no per-task table, it is unclear whether Hybrid's Luna half was scored independently or reused from Luna runs.
  - Success definitions for the simple and desktop lanes are not given, and who verifies the longer-lane checkpoints is not stated.
  - The local-report screenshot (`report/overview-light.png`) ranks Luna above Hybrid in the simple lane. That contradicts the stated tie-break on cost and the published `report.html`, so the published report and the screenshot differ.

- Source permalinks:
  - Lane table and overall aggregate: https://github.com/steve8708/jev-browser-benchmark/blob/61588f06c5a0b48ff1ffa9e61176e91bc11cb38e/README.md#L7-L26
  - Longer-lane success definition: https://github.com/steve8708/jev-browser-benchmark/blob/61588f06c5a0b48ff1ffa9e61176e91bc11cb38e/README.md#L42-L46
  - Browser-tools probe and Jev-plus-replay 42/42: https://github.com/steve8708/jev-browser-benchmark/blob/61588f06c5a0b48ff1ffa9e61176e91bc11cb38e/README.md#L52-L54
  - Cost method and no public runner: https://github.com/steve8708/jev-browser-benchmark/blob/61588f06c5a0b48ff1ffa9e61176e91bc11cb38e/README.md#L56-L69
  - Per-lane table: https://github.com/steve8708/jev-browser-benchmark/blob/61588f06c5a0b48ff1ffa9e61176e91bc11cb38e/RESULTS.md#L18-L27
  - Hybrid fallback rule (desktop): https://github.com/steve8708/jev-browser-benchmark/blob/61588f06c5a0b48ff1ffa9e61176e91bc11cb38e/RESULTS.md#L62
  - Hybrid as "policy plus verification and fallback" and staged recorded fallback: https://github.com/steve8708/jev-browser-benchmark/blob/61588f06c5a0b48ff1ffa9e61176e91bc11cb38e/RESULTS.md#L64-L69
  - Raw lane data, including totals and the staged note: https://github.com/steve8708/jev-browser-benchmark/blob/61588f06c5a0b48ff1ffa9e61176e91bc11cb38e/data/results.json#L15-L43
  - Capability probes marked "not a model score": https://github.com/steve8708/jev-browser-benchmark/blob/61588f06c5a0b48ff1ffa9e61176e91bc11cb38e/data/results.json#L44-L48
  - Unpublished Hybrid "fallback boundary" clips: https://github.com/steve8708/jev-browser-benchmark/blob/61588f06c5a0b48ff1ffa9e61176e91bc11cb38e/videos/README.md#L5-L12

### Jev evaluation across 37 datasets (`AppliedMachineLearning-Lab/jev-benchmarking`)

- Repository and commit:
  - `AppliedMachineLearning-Lab/jev-benchmarking` at `b8e825b44fb8429842b589057258d9af3ab3213f` (2026-11-18, "Add arXiv v2 LaTeX source of the paper").
  - Paper: Deußer, Ramamurthy, Sparrenberg, Sifa, "Evaluating and Benchmarking the System One Model Jev", arXiv:2609.37647. arxiv.org could not be reached from the machine I worked on. I read the paper from the repo's own LaTeX source, `paper/arxiv_v2/_main.tex`.
  - Entry points: `scripts/run.py` (sends requests), `scripts/evaluate.py` (scores them from the cache and never calls the API), `scripts/make_paper_assets.py` (tables, including the tuned thresholds), `scripts/run_sequential.py` (multi-step track).
  - Model pinned to `jev-1.13.0` (`config.py`). Results were recorded 2026-09-24 to 09-27.

- What the project demonstrates:
  - A zero-shot benchmark of Jev on 37 public datasets. It uses one frozen question template per dataset and full eval splits: 346,009 requests for $9.15.
  - Reference models: Qwen3.8-27B and Gemma-4-E4B, scored on identical requests using their exact next-token probabilities over option codes.
  - It covers all three primitives: Choice (22 datasets), Noul (single and multi-label fan-out) and Score (rubrics).
  - It also has a sequential track with five text environments (ALFWorld, TextWorld, BabyAI-Text, Blackjack, FrozenLake). It asks one Choice over legal actions per step, with the full history in the state.
  - The analysis includes calibration (ECE, Brier), selective accuracy by confidence, per-question threshold tuning, memorization probes and cost.

- One decision traced end to end (ToxiGen, the paper's own Figure "fig:request"):
  - Adapter: `ToxiGen.build` puts the row's text in `state = {"text": ...}`. In the same request it asks two questions:
    - a Noul: "Is `text` toxic, offensive or hateful toward a group of people?"
    - a five-level Score: "How offensive is `text` toward the group of people it mentions?", with described levels from "Benign" to "Extremely offensive".
  - Gold: `toxic = toxicity_ai + toxicity_human > 5.5` (the lm-evaluation-harness convention), and `toxicity = toxicity_human - 1`.
  - Candidates: for the Noul there are none, so the model returns P(yes). For the Score, the five levels are written in the code.
  - Harness: `request_key = sha256(model, state, questions)`, with no key sorting because option order matters. On a cache miss, `AsyncTypeSafeClient.system_one(state, questions)` is called. The raw body is stored in SQLite.
  - Decision: `binary_metrics` thresholds `noul >= 0.5`. Score uses the probability-weighted `score`, plus the argmax over level probabilities.
  - Fresh call on the figure's exact state ("having a disability means you can get everything for free"), on `jev-1.13.0`:
    - `toxic.noul = 0.57`, so the code predicts toxic at 0.5;
    - `toxicity.score = 2.33`, with probabilities {0: 0.00, 1: 0.15, 2: 0.40, 3: 0.43, 4: 0.02} and confidence 0.40;
    - 383 input tokens, 0.14 s.
  - The dataset's gold label for this sentence is not in the repo, so I cannot say whether this answer is correct.

- What the model decides:
  - One answer per typed question: a Choice option with a full distribution and a `confidence`, P(yes) for a Noul, or a level distribution for a Score.
  - The model never sees other questions' answers. Each Noul in a fan-out is answered independently.
  - In the sequential track, it picks the next action from the admissible commands. The argmax is executed.

- What the surrounding code handles:
  - Question wording and candidates:
    - The code writes one template per dataset, tested on 20 dev examples and then frozen. It does no tuning on eval data and uses no few-shot examples.
    - Labels become Choice options, with one-sentence descriptions where a bare label is ambiguous (AG News, NLI, FinancialPhraseBank).
    - Multiple-choice answers get letter keys A, B, ... and AA, AB, ... beyond 26 options. The code avoids numeric keys after the key "36" collided with the answer "atomic number 36".
    - Out-of-scope is an explicit option for CLINC150.
    - Multi-label tasks are split into one narrow Noul per label, with a definition for each (moderation, UNFAIR-ToS, GoEmotions).
  - Thresholds:
    - The default is a fixed 0.5.
    - For 4 datasets (GoEmotions, UNFAIR-ToS, AGB-DE, ToxicChat), the code tunes one threshold per question by grid search. The grid runs from 0.02 to 0.98 in steps of 0.01. The objective is F1 on 1,000 dev examples. Ties go to the value closest to 0.5. A question with no positives keeps 0.5.
    - The tuned thresholds are applied unchanged to the eval split, and each model is tuned on its own answers.
  - Calibration and selection: ECE on 15 bins, Brier, selective accuracy at 80% and 50% coverage ranked by the API's `confidence`, and AURC.
  - Retries and errors:
    - SDK `RetryPolicy(max_retries=6)`, a 60 s timeout, and a client rate cap of 1,000 req/min.
    - 401, 402 and 403 are fatal.
    - 413, 422 and 400 `max_tokens_exceeded` are remembered and never resent.
    - The run stops after 25 consecutive failures.
    - Spend caps apply per run and in total.
  - Execution: no fallback model and no verification step. This is a benchmark, so the "action" is only a metric. In the sequential track the harness runs the environment and logs a reference action that is never sent to the model.
  - Benchmark setup:
    - Task set: 37 datasets in 7 families.
    - Baselines: Qwen3.8-27B and Gemma-4-E4B on the same prompts, single forward pass, thinking disabled.
    - Sample size: full eval splits (116 to 109,800 examples).
    - Success criteria: each dataset's usual primary metric, with 500-resample bootstrap 95% CIs.

- Reported result and how it was measured (all author-reported unless marked):
  - Choice calibration is good:
    - Pooled ECE is 0.028 over 22 Choice datasets (279,925 answers). The per-dataset median is 0.028 and the mean is 0.061.
    - Where it misses, it is overconfident: on 20 of 22 datasets the mean top probability is above accuracy.
    - ECE worsens with lower accuracy (Spearman -0.83). Emotion has ECE 0.279 at 58.5% accuracy.
    - Selective prediction works. At 50% coverage, Banking77 rises from 79.7% to 96.3% and ANLI from 73.9% to 86.9%.
  - Binary (Noul) results "rank well but sit badly against 0.5":
    - Single Nouls are slightly under-confident: mean P(yes) is 0.465 against a yes-rate of 0.518 (ECE 0.052).
    - Prompt injection: AUROC 0.982, but at 0.5 it gets precision 1.0 and recall 0.50.
    - Multi-label fan-out over-predicts yes: mean P(yes) is 0.209 against a 0.041 rate (ECE 0.168), because each Noul is answered in isolation.
    - Tuned thresholds raise UNFAIR-ToS micro-F1 from 0.499 to 0.748 and GoEmotions macro-F1 from 0.243 to 0.353. On GoEmotions the tuned thresholds are mostly high (median 0.86), but `neutral` drops to 0.09.
    - ToxicChat jailbreak goes from 0.717 to 0.833 with the threshold at 0.85. ToxicChat toxic barely moves (0.786 to 0.793).
    - AGB-DE (legal voidness) stays at 0.204: 0.5 was already best on dev. The authors read this as weak separation (AUROC 0.784), not a misplaced threshold.
  - Question wording:
    - Only one template per dataset was evaluated, and the authors list this as a limitation. Some weak results (AGB-DE, HelpSteer2) "may partly reflect our wording".
    - Controlled wording tests exist only in the sequential track.
    - FrozenLake, 500 fixed positions:
      - base request: 32.0% accuracy;
      - adding the strategy in words: 37.0%, mostly just lower confidence;
      - rewriting each option to list where the move can land, with holes marked: 62.4%.
    - BabyAI-Text: adding BALROG's instruction prompt, including "don't repeat actions when the observation doesn't change", moves success from 20.8% to 25.6% (McNemar p = 0.065). The loops stay: 94% of forward moves still hit an obstacle.
    - Their takeaway: Jev does well when the right option can be recognized from the request, or when the request states each option's consequence. It does poorly when it must derive the answer from rules.
  - Narrow versus broad judgments:
    - Strong on gist-of-short-text tasks: IMDB 96.5%, SST-2 96.4%, ARC 98.8%, HellaSwag 95.5%, language ID 99.6%, SMS spam F1 0.938.
    - Weakest on fine-grained or noisy labels (Emotion 58.5%, SST-5 57.9%), on legal judgment (AGB-DE F1 0.204), and on rubric judging of generated text:
      - SummEval summary-level Spearman 0.554;
      - HelpSteer2 0.412, where helpfulness (0.399) and correctness (0.369) correlate least.
  - Long inputs:
    - IMDB (long reviews) scores 96.5%. BoolQ passages score 91.3%. Belebele passages average 86.7% over 122 languages.
    - LLM-AggreFact (claim versus document grounding) has a mean balanced accuracy of 0.786. By source it ranges from 0.598 (ExpertQA) to 0.906 (Reveal).
    - BIG-bench's two worst tasks are `real_or_fake_text` (32.2%) and `minute_mysteries_qa` (35.0%). The authors tie both to long inputs that must be read closely or reasoned over in several steps.
    - One BIG-bench item exceeded the context limit and was rejected. The limit is 32k tokens for the state plus the longest question.
    - The repo has no accuracy-by-length breakdown.
  - Multi-turn dialogue:
    - None of the 37 single-step datasets is built as a multi-turn chat classification task. ToxicChat is a single user prompt.
    - My inference, not stated in the repo: the LLM-AggreFact sources TofuEval-MeetB (meeting transcripts) and TofuEval-MediaS (interview transcripts) contain dialogue documents, and they score 0.827 and 0.747. HelpSteer2 prompts may include multi-turn context. I could not check this because Hugging Face is blocked.
    - The closest analogue is the sequential track, where the full episode history is in the state:
      - ALFWorld: 35.1% success, with 44.7% of steps repeating one of the previous two;
      - BabyAI-Text: 20.8% success, repeat rate 0.740;
      - action probabilities are overconfident (ALFWorld ECE 0.247), unlike single-step Choice.
    - Authors' conclusion: "Placing the history in the state is therefore not sufficient". They say tracking the episode is better left to the harness.
  - Cost and timing (author-measured, `jev-1.13.0`, client-side, from one machine with 32 concurrent connections): $0.042 per 1M input tokens. The average request was 630 input tokens and the mean latency was 0.36 s. A 28-Noul GoEmotions request used 765 tokens on average, against 559 for one Choice question.

- What I reproduced and how:
  - Reproduced from saved artifacts (the per-dataset `results/eval/*.json` committed in the repo):
    - Choice calibration summary: 22 Choice heads, median ECE 0.028, mean 0.061, 20 of 22 overconfident, Spearman(accuracy, ECE) = -0.83. This matches the paper.
    - Per-head binary metrics at 0.5:
      - prompt_injections: precision 1.0, recall 0.50, AUROC 0.982;
      - toxic_chat jailbreak: precision 0.582, recall 0.934;
      - agb_de: F1 0.204, AUROC 0.784.
    - The threshold table in `results/eval/thresholds.json` matches the paper's table.
    - These checks only confirm that the summary files and the paper agree. I could not rebuild them from raw responses. The Zenodo response databases (zenodo.org) and the Hugging Face datasets (huggingface.co) were both unreachable from the machine I worked on (HTTP 403), so `scripts/evaluate.py` and threshold re-tuning could not run.
  - Offline tests: `pytest` (excluding `tests/test_sequential.py`, which needs `rlcard`) gave 30 passed, 3 skipped, in a fresh virtualenv, with `typesafe-sdk==0.7.6`.
  - Reproduced with fresh model calls: 4 calls in total (one-off script, not kept).
    - `client.models.list()` lists only `jev-latest` (released 2026-10-22) and `jev-preview` (2026-10-14). Pinned `jev-1.13.0` is still served and echoed in responses.
    - The figure request, sent twice: Noul 0.57 both times. Score 2.33 then 2.28, with a level-3 probability of 0.43 then 0.40. The authors did not measure run-to-run variance, and this is a single pair of runs.
    - Same state, under wordings the repo uses for related tasks:
      - ToxicChat's toxic question: 0.24;
      - OpenAI-moderation "hate" with its definition: 0.58;
      - "harassment": 0.48.
    - Taken with the ToxiGen wording (0.57), the decision at 0.5 flips with the wording.
    - Confound: the ToxicChat wording names a `prompt` field that this state does not have. Treat this as one anecdote (n = 1), not a measurement.

- Limitation or open question:
  - One template per dataset means the benchmark cannot separate a model limit from a wording limit on single-step tasks. There is no paraphrase or broad-versus-narrow ablation outside FrozenLake and BabyAI.
  - Thresholds were tuned for only 4 datasets, on 1,000 dev examples each. They do not always transfer (Qwen jailbreak F1 fell from 0.743 to 0.726). Prompt injection, the clearest misplaced-threshold case, was not tuned.
  - There is no length-stratified analysis and no conversation-classification dataset. The only evidence on dialogue or history is indirect (AggreFact's TofuEval sources, the sequential track).
  - The MMLU calculation-heavy result (94.3% against 91.3% for other subjects) suggests possible training exposure. The authors treat results on long-established English benchmarks with caution.
  - Results are for `jev-1.13.0`. The model list now shows only `jev-latest` (2026-10-22), so a newer version exists.

- Source permalinks:
  - Question constructors (choice, noul, score) and letter keys: https://github.com/AppliedMachineLearning-Lab/jev-benchmarking/blob/b8e825b44fb8429842b589057258d9af3ab3213f/jev_benchmarking/tasks/base.py#L65-L86
  - ToxiGen adapter (traced example): https://github.com/AppliedMachineLearning-Lab/jev-benchmarking/blob/b8e825b44fb8429842b589057258d9af3ab3213f/jev_benchmarking/tasks/safety.py#L8-L34
  - ToxicChat and prompt-injection Nouls: https://github.com/AppliedMachineLearning-Lab/jev-benchmarking/blob/b8e825b44fb8429842b589057258d9af3ab3213f/jev_benchmarking/tasks/safety.py#L65-L91
  - UNFAIR-ToS narrow per-label Nouls with definitions: https://github.com/AppliedMachineLearning-Lab/jev-benchmarking/blob/b8e825b44fb8429842b589057258d9af3ab3213f/jev_benchmarking/tasks/safety.py#L110-L135
  - GoEmotions 28-Noul fan-out: https://github.com/AppliedMachineLearning-Lab/jev-benchmarking/blob/b8e825b44fb8429842b589057258d9af3ab3213f/jev_benchmarking/tasks/classification.py#L182-L204
  - CLINC150 explicit out-of-scope option: https://github.com/AppliedMachineLearning-Lab/jev-benchmarking/blob/b8e825b44fb8429842b589057258d9af3ab3213f/jev_benchmarking/tasks/classification.py#L92-L119
  - LLM-AggreFact grounding Noul with true/false criteria: https://github.com/AppliedMachineLearning-Lab/jev-benchmarking/blob/b8e825b44fb8429842b589057258d9af3ab3213f/jev_benchmarking/tasks/nli.py#L65-L94
  - SummEval and HelpSteer2 rubric Scores: https://github.com/AppliedMachineLearning-Lab/jev-benchmarking/blob/b8e825b44fb8429842b589057258d9af3ab3213f/jev_benchmarking/tasks/scoring.py#L50-L106
  - Runner (retries, permanent errors, spend cap, `system_one` call): https://github.com/AppliedMachineLearning-Lab/jev-benchmarking/blob/b8e825b44fb8429842b589057258d9af3ab3213f/jev_benchmarking/runner.py#L70-L187
  - Request-keyed cache: https://github.com/AppliedMachineLearning-Lab/jev-benchmarking/blob/b8e825b44fb8429842b589057258d9af3ab3213f/jev_benchmarking/cache.py#L34-L37
  - Evaluation (cache-only, bootstrap CI): https://github.com/AppliedMachineLearning-Lab/jev-benchmarking/blob/b8e825b44fb8429842b589057258d9af3ab3213f/jev_benchmarking/evaluate.py#L63-L102
  - Choice and binary metrics (ECE, selective accuracy, fixed 0.5): https://github.com/AppliedMachineLearning-Lab/jev-benchmarking/blob/b8e825b44fb8429842b589057258d9af3ab3213f/jev_benchmarking/metrics.py#L47-L94
  - Threshold grid search: https://github.com/AppliedMachineLearning-Lab/jev-benchmarking/blob/b8e825b44fb8429842b589057258d9af3ab3213f/jev_benchmarking/thresholds.py#L8-L31
  - Tune on dev, apply to eval: https://github.com/AppliedMachineLearning-Lab/jev-benchmarking/blob/b8e825b44fb8429842b589057258d9af3ab3213f/scripts/make_paper_assets.py#L84-L102
  - Saved thresholds and F1: https://github.com/AppliedMachineLearning-Lab/jev-benchmarking/blob/b8e825b44fb8429842b589057258d9af3ab3213f/results/eval/thresholds.json
  - Saved per-dataset summary: https://github.com/AppliedMachineLearning-Lab/jev-benchmarking/blob/b8e825b44fb8429842b589057258d9af3ab3213f/results/eval/summary.md
  - ALFWorld step request with full history in the state: https://github.com/AppliedMachineLearning-Lab/jev-benchmarking/blob/b8e825b44fb8429842b589057258d9af3ab3213f/jev_benchmarking/sequential/envs/alfworld.py#L113-L131
  - Paper, request construction and example request: https://github.com/AppliedMachineLearning-Lab/jev-benchmarking/blob/b8e825b44fb8429842b589057258d9af3ab3213f/paper/arxiv_v2/_main.tex#L182-L213
  - Paper, calibration and thresholds: https://github.com/AppliedMachineLearning-Lab/jev-benchmarking/blob/b8e825b44fb8429842b589057258d9af3ab3213f/paper/arxiv_v2/_main.tex#L298-L313
  - Paper, sequential discussion and limitations: https://github.com/AppliedMachineLearning-Lab/jev-benchmarking/blob/b8e825b44fb8429842b589057258d9af3ab3213f/paper/arxiv_v2/_main.tex#L469-L483
  - Paper, FrozenLake wording probe conclusions: https://github.com/AppliedMachineLearning-Lab/jev-benchmarking/blob/b8e825b44fb8429842b589057258d9af3ab3213f/paper/arxiv_v2/_main.tex#L580-L582

### Jev-like model training (`vinnylarouge/jevlike`)

- Repository and commit:
  - `vinnylarouge/jevlike` at `94f5fd1b0b11d52bbdfdf4e0ee6aa96b568f8452` ("Add shared Doom and chess training examples"). Shallow clone, one commit visible.
  - Entry points are the console scripts in `pyproject.toml`: `jevlike-data`, `jevlike-train`, `jevlike-eval`, `jevlike-predict`. The README quickstart is the release test (per `AGENTS.md`).
  - Game demos: `examples/doom/play.py` and `examples/chess/eval.py`, with three checkpoints committed.

- What the project demonstrates:
  - An independent, small PyTorch model with Jev's input/output shape: one context plus a variable list of N text options in, N probabilities summing to 1 out, in one forward pass.
  - It is not Jev and does not call Jev. The README says TypeSafe has not published Jev's design, and that the authors "did not show equal quality with Jev or reproduce TypeSafe's private training method".
  - The same option-attention head is reused as a game controller policy (7 Doom buttons, 5 chess keys) over image patches.
  - What it tells us about Jev: only that this I/O shape can be trained cheaply on labelled menus. It says nothing about Jev's architecture, training data, calibration or accuracy. My fresh Jev probes (below) show Jev behaves differently from this model on two simple cases.

- One decision traced end to end (text path, quickstart model I trained locally):
  - Input row (README example): context `"Choose the exact badge amber badger. Badge: amber badger."`; options `["azure crane", "amber badger", "gold heron"]`. No separate question field: the "question" is folded into the context text.
  - Tokenise (`ByteCollator`): context to UTF-8 bytes + 1, truncated to 192; each option to bytes, truncated to 32. `_tensor_batch` pads to the largest menu in the batch and builds `option_mask` so padded option slots are excluded.
  - Encode (`TinyScorer`): context = byte embedding + learned position embedding. Each option = mean of its byte embeddings (no position), so an option is a bag of bytes.
  - Score (`AttentionHead`): LayerNorm both sides. Each option's query attends over the context tokens (scaled dot product, masked). The option's logit is `query · attended_context / sqrt(rank)`. Padded options get logit `-inf`.
  - Each option is scored independently from the context. Options never see each other. They interact only through the final softmax over the menu.
  - Probabilities: `jevlike-predict` applies softmax and prints one probability per option. Result: amber badger 1.0, azure crane 1.0e-8, gold heron 5.0e-8.
  - Action: none. The text CLI only prints scores. There is no threshold, abstain option or "none of the above"; the menu always sums to 1.
  - In the games, the action is chosen by code: greedy `argmax` or `multinomial` sampling over the softmax (`play.py --greedy`, chess `eval.py --sample`).

- What the model decides:
  - A relative ranking over a menu the caller supplies, as a softmax distribution.
  - Nothing about whether any option is right. With a mismatched context it still puts all mass on one option (see probes).

- What the surrounding code handles:
  - Candidate generation: entirely the data. Synthetic menus are 2 to 8 random colour-animal pairs with the target inserted. Wikispeedia menus are the current article's outgoing links (up to 64, the clicked link included, shuffled).
  - Training objective: plain cross-entropy over the masked option logits, AdamW (lr 2e-3, wd 1e-4), grad-norm clip 1.0, 8 epochs. The checkpoint keeps the epoch with the lowest validation NLL. The test set is not touched in training.
  - Splits: synthetic uses disjoint seed ranges. Wikispeedia splits by a hash of the target article (10% test, 10% validation), so test targets are unseen.
  - Evaluation controls (`jevlike-eval`): top-1, top-3, 10-bin ECE, and a shuffled-context control that rolls contexts by one row within each batch, so each menu is paired with another row's context.
  - Not in the eval: a chance baseline (mean 1/N), per-menu-size breakdown, option-order or paraphrase tests, or any abstain/threshold analysis.
  - Two small eval issues I found in code:
    - ECE bins are `[lower, lower+0.1)`, so a confidence of exactly 1.0 falls in no bin. In my run, 91 of 400 test confidences were exactly 1.0 in float32 and were left out of ECE.
    - The shuffle control is a no-op for a batch of size 1 (`context.shape[0] > 1` guard).
  - Games: code owns the controller and its legality rules, the 40-key budget per chess turn (after which a random legal move is played and counted as a failure), greedy vs sampled selection, heuristic-expert and Stockfish labels, DAgger, reward shaping and PPO. An `audit.py` compares predictions on real, blank, averaged and shuffled-patch frames.
  - No retries, verification or LLM fallback exist in the text path.

- Reported result and how it was measured:
  - Author-reported (README "What to expect"): about 98% top-1 on synthetic menus. On target-disjoint Wikispeedia next-click, a frozen Qwen2.5-0.5B encoder plus scorer reached 26%, against about 8% for shuffled-context and random-encoder controls. A from-scratch model on 40,000 clicks reached 29%. "At eight options, one pass was about 100 times faster than a small decoder forced to write 400 tokens."
    - These are labelled "local experiments, not this quickstart run". No logs, result files or benchmark script for them are in the repo. I found no decoder timing code, so the 100x claim cannot be checked from the repo.
    - Wikispeedia sample size and per-N chance are not stated. Menus go up to 64 options, so chance is low but unreported.
  - Author-reported (chess README): chess-only checkpoint, 50 sampled games per opponent: random mover 4W/46D/0L; Stockfish level 0 0W/2D/48L; level 3 0W/0D/50L; 14 to 17% of turns hit the key budget; about 0.7 ms per key press on Apple MPS. The authors say it "learned the controller but not chess".
  - Author-reported (README demo): joint checkpoint averaged 0.60 kills and -97.50 reward over its ten recorded Doom episodes. The film windows were "selected for activity".
  - Reproduced from saved artifacts (checkpoint metadata, loaded with `weights_only=True`):
    - `deadly-dagger.pt` stores 100 episodes: mean 2.33 kills, mean raw reward 92.7, corridor armour reached 0/100. It stores `random_mean_kills` 0.4 as its baseline.
    - `chess-dagger1.pt` history: held-out next-key accuracy about 0.59 at step 6000, flat from step 500 (0.56).
    - `joint-imitation.pt` was trained for only 20 updates; its logged chess batch accuracy ends at 0.28. `AGENTS.md` itself says this short joint run "largely erased chess".

- What I reproduced and how:
  - Reproduced with fresh local training (CPU, torch 2.15.0 from PyPI, Python 3.13), in a fresh virtualenv:
    - `pytest -q`: 1 passed (tiny scorer loss drops and probabilities sum to 1).
    - Quickstart exactly as in README: 2,000 train / 400 validation / 400 test synthetic rows; training took 5.5 s wall time.
    - Test: top-1 0.9975, top-3 1.0, ECE 0.004 (with the 1.0-confidence gap above). Shuffled-context control: top-1 0.2275, top-3 0.6825, ECE 0.625.
    - I computed chance on the same test file: top-1 0.249, top-3 0.678. So the shuffled control here is about chance; it does not add much over a random baseline on this task.
    - The synthetic context literally contains the target string, so this is a string-matching task, not a judgment task.
  - Probes on my trained model (fresh local runs):
    - Word order: options `amber badger` vs `badger amber` tie at 0.50/0.50, because options are mean-pooled bytes.
    - Mismatched context (crimson-jaguar context, menu `coral ibis`/`coral heron`): 1.0 on coral ibis. Fully confident with no evidence.
  - Reproduced with fresh model calls to Jev (8 calls: 1 `models.list` plus 7 `system_one` with a `Choice` question, labels undescribed, repo inputs only). `typesafe-sdk` 0.7.6. Responses named `jev-1.14.0`; `jev-latest` lists release date 2026-10-22.
    - README example and 3 synthetic test rows: all correct, probability 1.0. 115 to 223 ms client wall time per call, including network. 302 to 330 input tokens reported.
    - Word order: Jev gave `amber badger` 1.0 and `badger amber` 0.0, unlike the jevlike tie.
    - Mismatched context: Jev gave 0.55/0.45 with `confidence` 0.1, where jevlike gave 1.0.
  - Not reproduced:
    - Wikispeedia results: need a SNAP download and, for the Qwen path, a Hugging Face model download and longer training. Not attempted under the brief's no-long-training rule.
    - Doom and chess play: need `vizdoom`, `python-chess` and Stockfish; not installed. Game smoke tests not run.
    - The 100x speed comparison: no code for it in the repo.

- Limitation or open question:
  - The only text benchmark that ships with code is a copy task. The broad-judgment case (long conversations, fuzzy labels) is exactly what is untested here.
  - Per-option independent scoring plus a forced softmax gives no way to say "none fit". The repo has no abstain or threshold logic, and on mismatched input it is overconfident.
  - Open question: would the Wikispeedia 26% vs 8% gap hold up against a chance baseline per menu size and against a simple title-similarity baseline? Neither is reported.

- Source permalinks:
  - README framing, not Jev: https://github.com/vinnylarouge/jevlike/blob/94f5fd1b0b11d52bbdfdf4e0ee6aa96b568f8452/README.md#L5-L5
  - README eval description and shuffled control: https://github.com/vinnylarouge/jevlike/blob/94f5fd1b0b11d52bbdfdf4e0ee6aa96b568f8452/README.md#L71-L71
  - README reported numbers and limitations: https://github.com/vinnylarouge/jevlike/blob/94f5fd1b0b11d52bbdfdf4e0ee6aa96b568f8452/README.md#L115-L128
  - Attention head (scoring, masking, shuffle control): https://github.com/vinnylarouge/jevlike/blob/94f5fd1b0b11d52bbdfdf4e0ee6aa96b568f8452/jevlike/model.py#L12-L43
  - Byte encoder and mean-pooled options: https://github.com/vinnylarouge/jevlike/blob/94f5fd1b0b11d52bbdfdf4e0ee6aa96b568f8452/jevlike/model.py#L46-L63
  - Frozen Hugging Face encoder path: https://github.com/vinnylarouge/jevlike/blob/94f5fd1b0b11d52bbdfdf4e0ee6aa96b568f8452/jevlike/model.py#L66-L94
  - Byte tokenising and variable-N padding/masks: https://github.com/vinnylarouge/jevlike/blob/94f5fd1b0b11d52bbdfdf4e0ee6aa96b568f8452/jevlike/data.py#L49-L107
  - Synthetic task generator: https://github.com/vinnylarouge/jevlike/blob/94f5fd1b0b11d52bbdfdf4e0ee6aa96b568f8452/jevlike/data.py#L114-L125
  - Wikispeedia menus and target-disjoint split: https://github.com/vinnylarouge/jevlike/blob/94f5fd1b0b11d52bbdfdf4e0ee6aa96b568f8452/jevlike/data.py#L175-L192
  - Training loop, cross-entropy, best-validation selection: https://github.com/vinnylarouge/jevlike/blob/94f5fd1b0b11d52bbdfdf4e0ee6aa96b568f8452/jevlike/train.py#L66-L91
  - Eval metrics and ECE bins: https://github.com/vinnylarouge/jevlike/blob/94f5fd1b0b11d52bbdfdf4e0ee6aa96b568f8452/jevlike/eval.py#L16-L48
  - Predict CLI softmax: https://github.com/vinnylarouge/jevlike/blob/94f5fd1b0b11d52bbdfdf4e0ee6aa96b568f8452/jevlike/predict.py#L25-L35
  - Visual scorer reusing the head: https://github.com/vinnylarouge/jevlike/blob/94f5fd1b0b11d52bbdfdf4e0ee6aa96b568f8452/jevlike/vision.py#L87-L127
  - Doom action selection (random, greedy, sampled): https://github.com/vinnylarouge/jevlike/blob/94f5fd1b0b11d52bbdfdf4e0ee6aa96b568f8452/examples/doom/play.py#L83-L88
  - Chess key-budget fallback to a random legal move: https://github.com/vinnylarouge/jevlike/blob/94f5fd1b0b11d52bbdfdf4e0ee6aa96b568f8452/examples/chess/eval.py#L106-L128
  - Chess reported results: https://github.com/vinnylarouge/jevlike/blob/94f5fd1b0b11d52bbdfdf4e0ee6aa96b568f8452/examples/chess/README.md#L64-L78
  - Authors' own caveats on the joint run and chess: https://github.com/vinnylarouge/jevlike/blob/94f5fd1b0b11d52bbdfdf4e0ee6aa96b568f8452/AGENTS.md#L45-L45 and https://github.com/vinnylarouge/jevlike/blob/94f5fd1b0b11d52bbdfdf4e0ee6aa96b568f8452/AGENTS.md#L64-L64

### Latency-focused demos: `jev-firehose` (`dabit3/jev-experiments`)

- Repository and commit:
  - `dabit3/jev-experiments` at `c469e5bfdc73eb3e1999bba2569e66b579a970fd` (shallow clone, 728 files).
  - A monorepo of about 20 latency demos "built by Devin". This note covers one demo, `jev-firehose/`.
  - Entry points: `npm run dev` (Vite UI plus Node proxy `jevProxy.mjs`), and the offline eval `eval.mjs`.
- What the project demonstrates:
  - jev-firehose: a simulated Twitch chat stream at about 300 msg/s. Every message gets one Jev request with six nouls and one choice. The browser stores the raw probabilities. Policy thresholds in code decide the mod queue, the streamer feed and the spoiler blur.
  - Why I picked it: it is the plainest "classify a short text" demo with a `TESTING.md` and a runnable eval. It is also the one Gloss can most easily compare with.
  - Other demos, one line each (from README headers only, not inspected):
    - agent-assist: support console; one Jev request per customer message gives intent, churn, frustration, flags and a confidence-gated macro. Closest to conversation classification, but it has no `TESTING.md`.
    - commit-sentry: pre-commit hook; Jev judges each staged hunk; it blocks or warns on leaked keys, DROP COLUMN and similar.
    - inbox-blitz ("Sift"): plain-English label descriptions judged against 500 emails; priority queue computed in code.
    - jev-ax-pilot: macOS agent; Jev picks actions over a flattened Accessibility tree.
    - jev-dispatch: 911-report triage with seven typed questions; code merges duplicates and dispatches units.
    - jev-instant-search: BM25 top-30 locally, then Jev re-ranks on each keystroke.
    - jev-launcher: macOS launcher; local search finds candidates and Jev judges intent (archived here).
    - jev-lint: editor that asks per-line semantic noul and choice questions to make squiggles.
    - jev-shell-guard: zsh hook; Jev rates each command before it runs (run, confirm or refuse).
    - jev-swarm: 32 arena agents, each with move, boost and target judgments every 400 ms.
    - jev-tower: air-traffic radar; code predicts conflicts, Jev picks one instruction, code validates it.
    - jev-voice-turn: on each partial transcript, asks turn_complete, intent and barge-in; it replies when a threshold is crossed. This is dialogue, but Swift/macOS only.
    - judge-sheets: spreadsheet where a typed column header fills the column with Jev predictions.
    - live-minutes ("Fern"): action items, decisions and risks extracted per meeting utterance.
    - log-sentinel: per-log-line actionable, severity and category, compared with regex rules.
    - modstream: hold-judge-release chat moderation with seven questions per message (close sibling of firehose).
    - nl-palette: command palette; Jev resolves 66 commands plus argument slots.
    - say: macOS voice companion (bring your own API keys).
    - send-guard: Slack-style composer; more than 10 judgments on each draft before sending.
    - turbo-rerank: one Jev request reranks 50 search candidates.
- One decision traced end to end:
  - Input state (README example, built by `buildState()`): `{stream:{streamer:"novakat", game:"Hollow Knight: Silksong", title, rules:"be respectful; no spoilers; no self-promotion, links or giveaways; no flooding"}, message:{user:"kaiog941", text:"skins gratis en valo-gratis[.]xyz codigo CHAT"}}`.
  - Typed questions (fixed for all messages, `src/jev.ts`):
    - six nouls with instructions and optional true/false criteria: `harassment`, `spam_or_scam`, `spoiler`, `question_for_streamer`, `needs_mod_attention` and `positive_hype`;
    - one choice, `language`, with 9 options.
  - Request: `POST https://api.typesafe.ai/v1/systemone` with `{state, model:"jev-latest", questions}`. One message per request; all seven questions go in one fan-out.
  - Returned (fresh call, 2026-11-27, `model: "jev-1.14.0"`):
    - nouls: harassment 0.02, spam_or_scam 0.98, spoiler 0.01, question 0.01, needs_mod_attention 0.99, hype 0.02;
    - language: choice `portuguese`, confidence 0.60, probabilities spanish 0.36 / portuguese 0.64. This is wrong: the text is Spanish.
    - 840 input tokens, 202 output tokens, 140 ms.
  - Resulting action (`src/policy.ts`):
    - `inModQueue`: 0.99 ≥ 0.60, so true. `modReason`: harassment < 0.5 and spam ≥ 0.5, so "scam". `isStreamerQuestion` is false. `isSpoiler` is false.
    - The card shows in the mod queue with a SPAM / SCAM badge. The human moderator then clicks Timeout, Delete or Ignore, which only logs to a local ticker.
- What the model decides:
  - Only the per-message probabilities for six narrow yes/no judgments and one language choice.
  - Each question is "one narrow judgment" with explicit criteria. One question, `needs_mod_attention`, is broader ("breaks `stream.rules`"). The stream rules are put in the state for it.
  - The model makes no routing, ranking or action decisions.
- What the surrounding code handles:
  - Candidate generation: none needed. The question set and the language option list are fixed constants. The messages come from a seeded generator (mulberry32) with hidden category labels.
  - Thresholds: all in `policy.ts`, adjustable with sliders:
    - mod queue: `needs_mod_attention ≥ 0.60 || harassment ≥ 0.50`;
    - streamer feed: `question ≥ 0.80 && harassment < 0.5 && spam < 0.5`;
    - spoiler blur: `spoiler ≥ 0.80`;
    - reason badge: a fixed priority order (harassment > scam ≥ 0.5 > spoiler ≥ 0.5 > review).
    - Probabilities are stored once, so moving a slider re-filters without new calls.
  - Verification: no model-side verification and no second pass. A human moderator acts on the cards. `parseJudgment()` clamps values to [0, 1]. A missing or malformed answer becomes 0, or "other" for language.
  - Retries: the Node proxy retries HTTP 429 and 529 up to 4 attempts. Backoff is exponential (150 ms × 2^n, capped at 1 s, plus jitter), and `retry-after` is honoured. Other errors are not retried.
  - Fallbacks: `heuristicJudgment()` is a regex lexicon. It is used when a request fails, when a queued message is older than 4 s, or when the backlog exceeds 3,000. Its cards are labelled HEURISTIC. Answers that arrive after a message was shed are counted as stale and dropped.
  - Execution:
    - `JudgePool` keeps up to 96 messages in flight over one WebSocket, one frame per message, so there is no head-of-line blocking.
    - The UI renders 10 snapshots a second.
    - Mod actions are only logged locally.
    - "Simulate slow LLM" adds 2 s of artificial delay. It is not a real LLM call.
- Reported result and how it was measured (all author-reported):
  - Live run against `jev-latest`, resolved as `jev-1.13.0`: seed 2024, headless Chromium, numbers read off the console.
  - At 300 msg/s with 96 in flight for 30 s: 8,934 messages judged, backlog 0, Jev p50 122 ms and p95 366 ms, 0.0 % fallback, 835 input tokens per message, $37.86 per hour at $0.042 per million input tokens.
  - At 400 msg/s the account's 429 rate limit becomes the cap: about 230 judged per second and 12.6 % heuristic fallback.
  - Mod-queue precision 1.00: the author hand-checked the first 50 cards (only 37 distinct texts). The reason badge was right on 49 of 50.
  - From `eval.mjs` on 400 seeded messages:
    - mod-queue recall 0.86 against the generator's template labels;
    - streamer-feed precision 1.00 and recall 0.80.
    - The README gives no mod-queue precision from this run, and no `eval-out.jsonl` is committed.
  - Baselines: the regex heuristic ("heuristic only" mode, described in words only), and the simulated 2 s delay. There was no real LLM classifier baseline and no real chat data.
- What I reproduced and how:
  - Offline: `npm ci && npm test` ran on Node 22.23.5, and 22 of 22 vitest tests passed. The tests use a fake transport and no network. (Reproduced from saved artifacts.)
  - Fresh model calls, 18 in total:
    - 17 messages hand-picked from the first 40 of seed 2024 to cover all categories, plus the README's Spanish scam example.
    - The run used the repo's own `buildState`, `questions`, `parseJudgment` and `policy` code, through a one-off script (not kept).
    - The API reported `model: "jev-1.14.0"`, not the README's 1.13.0. It gives no release date.
  - Fresh results (reproduced with fresh model calls, n=18, not random):
    - All 9 labelled bad messages went to the mod queue (spam, scam, selfpromo, spoiler, harassment). None of the 9 benign messages did.
    - The single real question ("what mouse do you use?", q=0.97) reached the streamer feed.
    - Both spoilers were blurred (0.93 and 0.96).
    - The regex heuristic on the same 18 messages missed the harassment message ("nobody watches this crap, get a job"). It also missed the question, because its score is 0.75 against the 0.80 bar, and both spoiler blurs, because its score is 0.7.
    - Language was correct on 17 of 18. The miss was Spanish read as Portuguese, at 0.60.
    - Latency p50 was 138 ms, with a maximum of 409 ms, measured client-side from a cloud machine, through an HTTPS proxy, with sequential calls.
    - Input was about 839 tokens per message. Output was about 200 tokens per message, not the "~20" the README states.
  - Not reproduced: throughput, rate-limit, cost and slow-LLM figures (they need a sustained high-rate run); the 400-message eval (over my call budget); the UI screenshots.
- Limitation or open question:
  - Ground truth is the generator's own template category, on a small finite corpus. Precision and recall on real, ambiguous chat are unknown.
  - Each message is judged alone, with no conversation history. So the demo does not test long-context judgment, which is where Gloss saw Jev fail.
  - `model: "jev-latest"` is an unpinned alias. The resolved version moved from 1.13.0 to 1.14.0 between the README run and mine.
  - The default thresholds were chosen by eye from one hand-checked sample. They are not calibrated on held-out data.
  - The choice `confidence` (0.60) does not equal the top option's probability (0.64). The README does not explain how the two relate.
- Source permalinks:
  - README summary: https://github.com/dabit3/jev-experiments/blob/c469e5bfdc73eb3e1999bba2569e66b579a970fd/jev-firehose/README.md#L3-L3
  - State, questions and policy (README): https://github.com/dabit3/jev-experiments/blob/c469e5bfdc73eb3e1999bba2569e66b579a970fd/jev-firehose/README.md#L50-L75
  - Keeping up, fallback and retries (README): https://github.com/dabit3/jev-experiments/blob/c469e5bfdc73eb3e1999bba2569e66b579a970fd/jev-firehose/README.md#L77-L82
  - Measured results: https://github.com/dabit3/jev-experiments/blob/c469e5bfdc73eb3e1999bba2569e66b579a970fd/jev-firehose/README.md#L84-L132
  - Offline eval instructions: https://github.com/dabit3/jev-experiments/blob/c469e5bfdc73eb3e1999bba2569e66b579a970fd/jev-firehose/TESTING.md#L61-L67
  - Questions: https://github.com/dabit3/jev-experiments/blob/c469e5bfdc73eb3e1999bba2569e66b579a970fd/jev-firehose/src/jev.ts#L9-L42
  - buildState: https://github.com/dabit3/jev-experiments/blob/c469e5bfdc73eb3e1999bba2569e66b579a970fd/jev-firehose/src/jev.ts#L60-L65
  - parseJudgment: https://github.com/dabit3/jev-experiments/blob/c469e5bfdc73eb3e1999bba2569e66b579a970fd/jev-firehose/src/jev.ts#L83-L105
  - Heuristic fallback: https://github.com/dabit3/jev-experiments/blob/c469e5bfdc73eb3e1999bba2569e66b579a970fd/jev-firehose/src/jev.ts#L107-L149
  - Policy thresholds: https://github.com/dabit3/jev-experiments/blob/c469e5bfdc73eb3e1999bba2569e66b579a970fd/jev-firehose/src/policy.ts#L13-L32
  - Stream context: https://github.com/dabit3/jev-experiments/blob/c469e5bfdc73eb3e1999bba2569e66b579a970fd/jev-firehose/src/generator.ts#L171-L176
  - Pool config, shedding and dispatch: https://github.com/dabit3/jev-experiments/blob/c469e5bfdc73eb3e1999bba2569e66b579a970fd/jev-firehose/src/pool.ts#L21-L26 and https://github.com/dabit3/jev-experiments/blob/c469e5bfdc73eb3e1999bba2569e66b579a970fd/jev-firehose/src/pool.ts#L112-L157
  - Proxy 429/529 retry: https://github.com/dabit3/jev-experiments/blob/c469e5bfdc73eb3e1999bba2569e66b579a970fd/jev-firehose/jevProxy.mjs#L57-L68
  - Proxy Jev call: https://github.com/dabit3/jev-experiments/blob/c469e5bfdc73eb3e1999bba2569e66b579a970fd/jev-firehose/jevProxy.mjs#L103-L106
  - Where the UI applies policy: https://github.com/dabit3/jev-experiments/blob/c469e5bfdc73eb3e1999bba2569e66b579a970fd/jev-firehose/src/App.tsx#L59-L60
  - Eval request and labels: https://github.com/dabit3/jev-experiments/blob/c469e5bfdc73eb3e1999bba2569e66b579a970fd/jev-firehose/eval.mjs#L30-L34 and https://github.com/dabit3/jev-experiments/blob/c469e5bfdc73eb3e1999bba2569e66b579a970fd/jev-firehose/eval.mjs#L61-L68

### Jev integration index (`ozers/jevsome-projects`)

- Repository and commit:
  - `ozers/jevsome-projects` at `bdf1f07ee98eff5cbaf89767c5533bfe978b5603`.
  - The data snapshot is `data/index.json`, generated 2026-11-26T14:03:55Z.
  - Entry point: `npm run refresh`, which runs `pipeline/run.mjs` (carry, discover, enrich, verify, classify, health, build). A GitHub Action runs it every day.
  - This is an index, not a program that uses Jev for its product. I checked five entries against their sources.

- What the project demonstrates:
  - A directory of repos that "provably call" Jev. Each listed entry links to one line of source.
  - The proof is regex rules over a downloaded file: an endpoint URL, an SDK import, a pinned `jev-latest` route or a declared dependency.
  - Counts in the snapshot: 2,811 entries, 434 "verified" on the README, 2,377 candidates.
  - The pipeline also has a Jev classification step. It categorises each repo. It is wired up but did not produce any of the published data (see below).

- One decision traced end to end:
  - Entry: `wechat-jev-assistant`, README line 397, section Applications. It is a WeChat conversation analyser, which makes it the closest match to Gloss.
  - Index proof: `src/wechat_jev/typesafe_client.py:15`, `API_URL = "https://api.typesafe.ai/v1/systemone"`. The rule is `api-call`, strength 3. I checked it at commit `b0559fa`, and it holds.
  - Input state, built in `ui.py` L437-L450: the OCR'd and redacted `messages` (up to about 12k chars, newest first), `participants` (at most 6), `participant_context` (the last 8 messages per person), `focus_message` (the latest message from the other side), `reply_evaluation` (my last reply plus up to 3 responses to it) and, optionally, `candidate_replies`. `anonymize_state` runs on the state before it is sent.
  - Typed questions: 12 fixed ones, sent in one call (`typesafe_client.py` L17-L141).
    - Choices: `situation` (7 options, one of which means "context insufficient"), `relationship_need` (7), `intent` (7, including "cannot judge") and `next_action` (6).
    - Nouls: `cares_test`, `concrete_reply_risk`, `needs_repair_first`, `conflict_emergency`, `deescalated`, `stop_explaining` and `literal_only`.
    - Score: `tension`, on 10 levels (0 to 9).
    - Dynamic questions (L202-L278): one `person_intent_i` choice per group member; `my_reply_relevance`, `my_reply_outcome` and `my_reply_effectiveness` when there is a reply to grade; and `best_candidate_reply`, a choice over 2 to 4 candidates.
  - Candidate options: the reply candidates come from a separate LLM (DeepSeek by default, `draft_client.py` L14-L15). Code appends a fixed "pause, do not reply" option. Jev only picks among them.
  - Model call: `TypeSafeClient.evaluate`, `typesafe_client.py` L325-L389. It sends POST `{state, model: "jev-latest", questions}` and runs in a subprocess (`evaluate_isolated`, `ui.py` L477-L480).
  - Returned values used: `choice` and `confidence` for choices, `noul` for nouls, and `score` plus `legend` for scores. `best_candidate_reply.probabilities` orders the candidates.
  - Resulting action: display only. If a choice's `confidence` is below 0.35 (`config.py` L24), the UI shows "cannot judge reliably" instead (`ui.py` L509-L517). The top candidate is shown first. The user can copy it to the clipboard and must send it by hand (`ui.py` L680-L690). Nothing is sent automatically.

- What the model decides:
  - In the index itself: nothing, as of this snapshot.
    - `classifiedBy` is `{rules: 5055}`. All 2,811 entries have `categoryBy` set to `rules` (2,783) or `human` (28), and `categoryConfidence` is null for all of them.
    - So the categories come from keyword regexes (`classify.mjs` `RULES`) and from `overrides.yaml`.
  - The wired path, used only when `TYPESAFE_API_KEY` is set: one call per repo with three questions.
    - `category`: a choice over 9 options. Each criterion is the section's "what" plus its "not" text.
    - `is_project`: a noul.
    - `substance`: a score from 0 to 2.
  - If that path ran, Jev would do two things:
    - Its `category` would decide the README section.
    - An `is_project` below 0.5 would drop the repo (`build.mjs` L79-L82).
    - `substance` is stored but never read.
  - Jev never decides whether a repo "calls Jev". Regex code decides that.

- What the surrounding code handles:
  - Candidate generation: GitHub repository search, a code search that the daily job turns off (`CODE_SEARCH: '0'`), npm, submissions, and archive scans of up to 300 repos a day.
  - Verification: the matching file is fetched, and the first strong line is picked with `LINE_RULES` (`verify.mjs` L17-L41) or a manifest parser (L56-L77). Docs, lockfiles and comments are capped at "claimed".
  - Thresholds and the bar: `tier()` requires all four of the following (`quality.mjs` L134-L141).
    - The repo was created after 2026-09-15, or is named after Jev.
    - The name, description or topics mention Jev.
    - It has a "strong" proof, which excludes mock, fixture and cassette paths and test paths.
    - It has at least 5 stars.
  - Disqualifiers: regexes for dotfiles, forks, docs repos, catalogues and reimplementations.
  - Overrides: `overrides.yaml` can `force` an entry in, which skips both the proof gate and the "is it a project" gate.
  - Retries: `jev.mjs` retries 429 and 529 responses with exponential backoff, up to 4 times. Any other error throws.
  - Fallback: any Jev error sends that repo back to the keyword rules (`classify.mjs` L128-L131). Results are cached by `pushedAt`.
  - Execution: the job writes the README and JSON, commits them and deploys a Cloudflare site.

- Reported result and how it was measured:
  - Author-reported: "434 verified projects · 2377 more in the JSON · 5,080 search hits examined". Also 1,718 hits with no Jev line found and 551 that had proof but were excluded.
  - The method is regex proof plus metadata gates. There is no human audit of a sample and no precision figure.
  - The README says (rule 5) that a proof line is "not a mock, a recorded cassette or a data file".

- What I reproduced and how:
  - Reproduced from saved artifacts (`data/index.json`, with Python over the committed file):
    - 434 verified rows, but only 419 unique repos. 15 renamed or transferred repos appear twice, for example `gudcks/jev-java` and `gudcks0305/jev-java`.
    - 27 verified proofs link to `blob/main`, not to a commit SHA.
    - 13 verified proofs are `.env.example` lines.
    - 19 proof URLs point at a different owner or repo than the entry's own URL.
    - No entry was classified by Jev.
  - Spot checks: I shallow-cloned each repo and read the proof line and the real call site.
    - `wechat-jev-assistant`: the proof holds, and the call is in the product path.
    - `jev-mail`: the proof holds, but `src/simulate.ts` is a live evaluation over synthetic fixtures (`examples/mock-emails.json`). The product call is in `src/gas/worker.ts:16`.
    - `jev-chat-jarvis-mac`: the proof is a config line in `.env.example:8`. Real Jev code exists in `src/judge_jev.py`, but it is optional. By default the project uses a local `decider-2b` clone (`src/judge.py` L594-L602). The integration is real, but the proof the index chose is weak.
    - `OpenDecision`: false positive. The proof "declares typesafe = [" is the name of an optional-extras group in `pyproject.toml`, not a dependency. The only use of the extra (`examples/m3_typesafe_sdk_demo.py`) points `TypeSafeClient` at `http://127.0.0.1:8000`, which is the project's own server. The project is an open "alternative for Jev". The index's reimplementation regex only matches "alternative **to**".
      - I ran the index's own `inspect()` and `disqualify()` locally. They reproduce both misses: the extras line becomes `dependency` with strength 3, and the description is not disqualified.
    - `system-one-adapter-python` (official): the proof is a VCR cassette (`tests/cassettes/...json:7`). `strongProof()` rejects it, which I checked locally. `overrides.yaml` (`force` and `tier: verified`) keeps it anyway, and that contradicts README rule 5.
      - The product replaces Jev with OpenAI, Anthropic or Gemini. The only Jev call is a live test that uses `model="speed_latest"`.
  - Reproduced with fresh model calls: 3 calls through the index's own `ask()` (`pipeline/lib/jev.mjs`), with `retries: 0`. The questions were identical to `classify.mjs`.
    - The state was built from each repo's `index.json` row. `readme_summary` was null because `data/repos.json` is not committed.
    - The API reported the model `jev-1.14.0`. It reported no release date.
    - Wall-clock latency was 126 to 187 ms per call, from a cloud machine through an HTTPS proxy. The first call used 1,098 input tokens and 119 output tokens.
    - The response shape matches what `classify.mjs` parses (`choice`, `confidence`, `noul`, `score`).
    - Results:
      | Repo | Jev `category` | `confidence` | `is_project` | Other probabilities |
      | --- | --- | --- | --- | --- |
      | `wechat-jev-assistant` | `app` | 0.68 | 0.68 | p(app) = 0.72 |
      | `OpenDecision` | `app` | 0.52 | 0.44 | none recorded |
      | `system-one-adapter-python` | `integration` | 0.48 | 0.59 | p = 0.54 against `sdk` 0.46 |
    - `OpenDecision`'s `is_project` of 0.44 is below the 0.5 gate in `build.mjs` L79. If the Jev path ran, it would reject this false positive.
    - For `system-one-adapter-python`, the human override pins `sdk`.
    - The `confidence` field is not the top probability (0.68 against 0.72, and 0.48 against 0.54). `classify.mjs` stores `confidence`.
    - An earlier attempt with Node `fetch` failed before reaching the API because of a local network setting, which I fixed. Those failed attempts are not counted.
  - Not run: the full pipeline. It needs a GitHub token and would rewrite the committed data.

- Limitation or open question:
  - "Verified" means that a regex matched one line. My sample was 5 entries. In it, 1 was a clear false positive (OpenDecision), 1 was kept against the stated rule by an override (the adapter), and 2 had weaker proof lines than the code they contain (jarvis-mac and jev-mail).
  - What is the precision of the 434? A labelled audit of a random sample would answer that.
  - The Jev classification path has never run in production, so its accuracy on this taxonomy is unmeasured. In my 3 calls it caught the false positive, but 3 calls are not an evaluation.

- Source permalinks:
  - Index rules, README: https://github.com/ozers/jevsome-projects/blob/bdf1f07ee98eff5cbaf89767c5533bfe978b5603/README.md#L11-L17
  - Entries checked: https://github.com/ozers/jevsome-projects/blob/bdf1f07ee98eff5cbaf89767c5533bfe978b5603/README.md#L44-L44 (adapter), https://github.com/ozers/jevsome-projects/blob/bdf1f07ee98eff5cbaf89767c5533bfe978b5603/README.md#L334-L334 (jarvis-mac), https://github.com/ozers/jevsome-projects/blob/bdf1f07ee98eff5cbaf89767c5533bfe978b5603/README.md#L356-L356 (OpenDecision), https://github.com/ozers/jevsome-projects/blob/bdf1f07ee98eff5cbaf89767c5533bfe978b5603/README.md#L397-L398 (wechat, jev-mail)
  - Jev client: https://github.com/ozers/jevsome-projects/blob/bdf1f07ee98eff5cbaf89767c5533bfe978b5603/pipeline/lib/jev.mjs#L9-L30
  - Classification questions: https://github.com/ozers/jevsome-projects/blob/bdf1f07ee98eff5cbaf89767c5533bfe978b5603/pipeline/classify.mjs#L70-L93
  - Classification call and fallback: https://github.com/ozers/jevsome-projects/blob/bdf1f07ee98eff5cbaf89767c5533bfe978b5603/pipeline/classify.mjs#L100-L131
  - Build gates and the `is_project` threshold: https://github.com/ozers/jevsome-projects/blob/bdf1f07ee98eff5cbaf89767c5533bfe978b5603/pipeline/build.mjs#L67-L82
  - Tier decision: https://github.com/ozers/jevsome-projects/blob/bdf1f07ee98eff5cbaf89767c5533bfe978b5603/pipeline/build.mjs#L111-L115
  - Line rules: https://github.com/ozers/jevsome-projects/blob/bdf1f07ee98eff5cbaf89767c5533bfe978b5603/pipeline/verify.mjs#L17-L41
  - Manifest parser (the OpenDecision miss): https://github.com/ozers/jevsome-projects/blob/bdf1f07ee98eff5cbaf89767c5533bfe978b5603/pipeline/verify.mjs#L49-L77
  - Reimplementation regex: https://github.com/ozers/jevsome-projects/blob/bdf1f07ee98eff5cbaf89767c5533bfe978b5603/pipeline/lib/quality.mjs#L19-L19
  - strongProof and tier: https://github.com/ozers/jevsome-projects/blob/bdf1f07ee98eff5cbaf89767c5533bfe978b5603/pipeline/lib/quality.mjs#L115-L141
  - Force override for the cassette: https://github.com/ozers/jevsome-projects/blob/bdf1f07ee98eff5cbaf89767c5533bfe978b5603/data/overrides.yaml#L8-L16
  - wechat questions: https://github.com/yushen100/wechat-jev-assistant/blob/b0559fa2bb3535201c65ff1fec64edfa66f7cc63/src/wechat_jev/typesafe_client.py#L17-L141
  - wechat dynamic questions and candidate choice: https://github.com/yushen100/wechat-jev-assistant/blob/b0559fa2bb3535201c65ff1fec64edfa66f7cc63/src/wechat_jev/typesafe_client.py#L202-L278
  - wechat call, retry and compaction: https://github.com/yushen100/wechat-jev-assistant/blob/b0559fa2bb3535201c65ff1fec64edfa66f7cc63/src/wechat_jev/typesafe_client.py#L325-L389
  - wechat state: https://github.com/yushen100/wechat-jev-assistant/blob/b0559fa2bb3535201c65ff1fec64edfa66f7cc63/src/wechat_jev/ui.py#L437-L480
  - wechat 0.35 abstain: https://github.com/yushen100/wechat-jev-assistant/blob/b0559fa2bb3535201c65ff1fec64edfa66f7cc63/src/wechat_jev/ui.py#L509-L517
  - wechat manual send: https://github.com/yushen100/wechat-jev-assistant/blob/b0559fa2bb3535201c65ff1fec64edfa66f7cc63/src/wechat_jev/ui.py#L680-L690
  - wechat threshold: https://github.com/yushen100/wechat-jev-assistant/blob/b0559fa2bb3535201c65ff1fec64edfa66f7cc63/src/wechat_jev/config.py#L24-L24
  - jev-mail eval script: https://github.com/vynnlee/jev-mail/blob/61e346f9034161e4cb7ddf04907326841e01300b/src/simulate.ts#L1-L37
  - jev-mail product call: https://github.com/vynnlee/jev-mail/blob/61e346f9034161e4cb7ddf04907326841e01300b/src/gas/worker.ts#L16-L16
  - jarvis-mac proof: https://github.com/jev-chat/jev-chat-jarvis-mac/blob/cbf6fe45aedbe78652c46fe87357ae4761dd9a79/.env.example#L5-L9
  - jarvis-mac real call: https://github.com/jev-chat/jev-chat-jarvis-mac/blob/cbf6fe45aedbe78652c46fe87357ae4761dd9a79/src/judge_jev.py#L60-L126
  - jarvis-mac default to local: https://github.com/jev-chat/jev-chat-jarvis-mac/blob/cbf6fe45aedbe78652c46fe87357ae4761dd9a79/src/judge.py#L594-L602
  - OpenDecision extras: https://github.com/deepanwadhwa/OpenDecision/blob/cbd0b50db42bba6975f342de1789fb3c8f2dc670/pyproject.toml#L29-L43
  - OpenDecision localhost: https://github.com/deepanwadhwa/OpenDecision/blob/cbd0b50db42bba6975f342de1789fb3c8f2dc670/examples/m3_typesafe_sdk_demo.py#L1-L8
  - Adapter README: https://github.com/typesafe-ai/system-one-adapter-python/blob/e1d4cc938204b22fc5a3c3aca7044072fe3f712d/README.md#L1-L7
  - Adapter cassette: https://github.com/typesafe-ai/system-one-adapter-python/blob/e1d4cc938204b22fc5a3c3aca7044072fe3f712d/tests/cassettes/test_client_with_live_apis/test_live_typesafe_response_matches_reference_shape.json#L5-L10
  - Adapter live test: https://github.com/typesafe-ai/system-one-adapter-python/blob/e1d4cc938204b22fc5a3c3aca7044072fe3f712d/tests/test_client_with_live_apis.py#L239-L246
  - The index pins the adapter cassette at the older commit `adffc2e`. I read it at HEAD `e1d4cc9`.

#### Follow-up projects closest to text classification or conversation analysis

Only `wechat-jev-assistant` and `jev-mail` were checked in source. For the rest, I only read the index line.

1. `jev-calibrate` (smkrv), README L525. It tunes Jev question criteria on labelled examples and confirms them on a held-out set, giving a verdict per question. This is the closest match to Gloss's held-out test.
2. `jev-phishing-bench` (anisselbd), README L541. Jev against Claude Haiku 4.5 on 2,000 phishing emails, measuring accuracy, calibration, latency and cost. It is a text classification benchmark with an LLM baseline.
3. `wechat-jev-assistant` (yushen100), README L397. Multi-question analysis of long chats, with per-speaker intent and abstention below 0.35. Traced above.
4. `jev-mail` (vynnlee), README L398. Email triage with a review label for abstention, a live evaluation over synthetic fixtures, and saved results in `docs/live-evaluation.json` (jev-latest, 2026-09-20).
5. `hush` (emreozyoruk), README L438. Issue triage with calibrated labels, spam and duplicate detection, and abstention.
- Alternates, from the index line only: `wechat-triage-hud` (L390), `Jev-Moderation-Bot` (L374), `toolgate` (L174, labelled on real sessions with a blind second labeler).

## Comparison

| Project | What Jev decides | What the code owns | Strongest evidence | One open question |
|---|---|---|---|---|
| Pokémon Red | One key among the legal options: battle move, route target, intent, menu item | RAM reading, options with precomputed facts, pruning, pathfinding, button presses, retries, loop rules | Author-reported full-game win; no logs published; code read only | How much of the win comes from the harness's facts and pruning? |
| Robot-arm control | An 8-way intent, then three axis signs and a gripper command | Features and booleans, step size, limits, IK, answer checks, success stop; no thresholds or fallback | Saved replay rerun exactly in MuJoCo; fresh calls matched the traced cycle | Would gating on Jev's probability cut errors and cycles? |
| Voice-controlled browser | Act, wait or ignore on each partial command (9–11 questions per call) | Candidates, ordered thresholds, silence timing, disambiguation, confirmation, memory | 45 offline tests pass; fresh calls matched 6 test cases | Were the thresholds ever calibrated? |
| Neo4j navigation | The next edge (a choice over up to 60) and "goal reached?" per hop | Candidate fetch and caps, top-k, beam ranking, goal threshold, id checks, depth and budget limits | Saved notebook outputs replayed through the repo's code with matching scores; fresh calls | Is the weak goal check the model, or the missing context? |
| Browser automation benchmark | The browser or desktop action (exact output not published) | Verification (not described), fallback to an LLM agent, staged hand-off on long tasks | Author-reported totals; the overall table recomputed from saved per-lane data | How many tasks fell back, and what decided "can't be verified"? |
| Evaluation across 37 datasets | Typed questions on public datasets, scored against gold labels | Templates, an out-of-scope option, thresholds tuned on dev, retries, caching, metrics | Summary figures match the committed result files; raw responses not rebuilt | How much of the weak results is question wording? |
| Jev-like model training | Ranking a menu the caller supplies (an independent model, not Jev) | Menu building, training, best-checkpoint pick, accuracy and calibration checks | Retrained locally: 99.75% top-1, but the shuffled control is at chance | Does Wikispeedia's 26% against 8% hold against a fair chance baseline? |
| Latency demos (`jev-firehose`) | Per-message scores on 6 narrow yes/no questions and a language choice | Thresholds and combining rules, retries, a regex fallback after 4 s or a backlog, a human action | 22 offline tests pass; 18 fresh calls: 9 of 9 bad messages flagged, 0 of 9 benign | Does accuracy hold on real chat, with conversation context? |
| Jev integration index | Nothing: every category comes from rules or hand overrides | Discovery, line proofs, gates, overrides, keyword fallback, retries | 5 entries read in source, 2 misses rerun with the index's code, 3 fresh calls | How precise is "verified"? Of 5 sampled, 1 was a false positive and 1 was kept by override. |
