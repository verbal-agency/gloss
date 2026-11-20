"""G43 exploration: the user-only state, the graded cause question, the relabels. No network."""
from app.pipeline import jev_ground as jg
from eval import g43_explore as x


def test_user_only_view_drops_every_assistant_turn():
    msgs = [{"role": "user", "content": "u1"}, {"role": "assistant", "content": "SECRET"},
            {"role": "user", "content": "u2"}]
    view = jg.user_turns_view(msgs)
    assert "SECRET" not in view and "u1" in view and view.endswith("u2")
    assert jg.user_turns_view([{"role": "user", "content": "only"}]) is None


def test_user_only_battery_swaps_the_note_and_nothing_else():
    full, user = jg.g43_battery(True, False), jg.g43_battery(True, True)
    assert set(full) == set(user)
    for k in full:
        assert full[k]["instructions"].replace(jg._CONVERSATION_NOTE, jg._USER_ONLY_NOTE) == user[k]["instructions"]
        assert full[k]["criteria"] == user[k]["criteria"]
    assert jg.g43_battery(False, True) == jg.g42_battery(False, False)


def test_cause_level_is_accepted_by_the_sdk_and_ordered():
    from typesafe_sdk import Choice
    for conv in (False, True):
        for user_only in (False, True):
            Choice(**jg.cause_level_question(conv, user_only)["cause_level"])
    assert jg.CAUSE_LEVELS == ("none", "implied", "asserted", "observed")
    a = {"cause_level": {"probabilities": {"none": 0.1, "implied": 0.2, "asserted": 0.3, "observed": 0.4}}}
    assert abs(jg.stated_probability(a) - 0.7) < 1e-9


def test_relabels_follow_ruling_one():
    by_id = {c["id"]: c for c in x.pool()}
    assert all(by_id[i]["expected"] == "none" for i in x.RELABELLED)
    assert by_id["g42/single/absent/french-tickets-fits"]["expected"] == "asked"
    assert by_id["g42/single/absent/mail-connections-misses"]["expected"] == "asked"


def test_objection_needs_evidence_in_r1_and_l1():
    a = {"contradicted": {"noul": 0.9}, "problem_described": {"noul": 0.9},
         "mechanism_stated": {"noul": 0.1},
         "link": {"probabilities": {"contradicted": 0.9, "absent": 0.0, "stated": 0.1}},
         "cause_level": {"probabilities": {"none": 0.9, "implied": 0.1, "asserted": 0.0, "observed": 0.0}}}
    assert x.r0(a) == "objected" and x.r1(a) == "asked" and x.l1(a) == "asked"


def _risk(mech=0.9, contra=0.1, pcon=0.0, misses=0.1, breaks=0.1, wasted=0.1, problem=0.9):
    return {"mechanism_stated": {"noul": mech}, "contradicted": {"noul": contra},
            "problem_described": {"noul": problem},
            "link": {"probabilities": {"contradicted": pcon, "absent": 0.0, "stated": 1 - pcon}},
            "plan_misses_cause": {"noul": misses}, "plan_breaks_requirement": {"noul": breaks},
            "wasted_effort": {"noul": wasted}}


def test_split_contradiction_rules():
    from eval import g43_explore2 as y
    assert y.s1(_risk(misses=0.8)) == "objected"
    assert y.s1(_risk(mech=0.2, misses=0.8)) == "asked"        # no stated cause: nothing to miss
    assert y.s1(_risk(mech=0.2, breaks=0.8)) == "objected"     # a requirement needs no cause
    assert y.k1(_risk(mech=0.2, wasted=0.2)) == "none" and y.k1(_risk(wasted=0.8)) == "asked"


def test_cascade_band_defers_only_near_thresholds():
    from eval import g43_explore2 as y
    assert y.uncertain(_risk(mech=0.7), "R1")
    assert not y.uncertain(_risk(mech=0.95), "R1") and not y.uncertain(_risk(mech=0.1), "R1")
    assert y.uncertain(_risk(mech=0.95, contra=0.3), "R1")
    assert y.uncertain(_risk(mech=0.1, breaks=0.5), "S1")


def _tree(problem=0.9, inv=0.1, mech=0.9, miss=0.1, breaks=0.1, scope="small"):
    probs = {k: (1.0 if k == scope else 0.0) for k in ("small", "component", "system", "organisation")}
    return {"problem_described": {"noul": problem}, "plan_is_investigation": {"noul": inv},
            "mechanism_stated": {"noul": mech}, "misses_stated_cause": {"noul": miss},
            "breaks_stated_requirement": {"noul": breaks}, "plan_scope": {"probabilities": probs}}


def test_tree_steps_in_order():
    from eval import g43_explore3 as z
    assert z.t1(_tree(problem=0.1, mech=0.1)) == "none"          # step 1: no problem
    assert z.t1(_tree(inv=0.9, mech=0.1)) == "none"              # step 2: an investigation
    assert z.t1(_tree(mech=0.1, miss=0.9)) == "asked"            # step 3 comes before step 4
    assert z.t1(_tree(miss=0.9)) == "objected" and z.t1(_tree()) == "none"


def test_value_of_information_asks_only_when_it_pays():
    from eval import g43_explore3 as z
    unsupported = _tree(mech=0.0, scope="system")                # P(wrong)=0.5, L=10
    assert z.v1(unsupported, c=0.5) == "asked"                   # 0.5*0.8*10 = 4 > 0.5
    assert z.v1(_tree(mech=0.0, scope="small"), c=0.5) == "none"    # 0.5*0.8*1 = 0.4 < 0.5
    assert z.v1(_tree(inv=0.9, mech=0.0, scope="system"), c=0.05) == "none"


def test_utility_table():
    from eval import g43_explore3 as z
    wrong = {"id": "g42/single/absent/x-misses", "scenario": "absent"}
    right = {"id": "g42/single/sound/x", "scenario": "sound"}
    answered = {"id": "g42/late_answered/x", "scenario": "late_answered"}
    assert z.utility("none", wrong, 3, 0.1) == -3 and z.utility("none", right, 3, 0.1) == 0
    assert abs(z.utility("asked", wrong, 3, 0.1) - (-0.1 - 0.6)) < 1e-9
    assert z.utility("objected", right, 3, 0.1) == -0.1 - 0.2
    assert z.utility("asked", answered, 3, 0.1) == -0.2


def test_route_type_sends_only_checkable_requests_on():
    from eval import g43_explore3 as z
    assert z.route_type(_tree(problem=0.1)) == "task"
    assert z.route_type(_tree(inv=0.9)) == "investigation"
    assert z.route_type(_tree(mech=0.2)) == "unsupported fix"
    assert z.route_type(_tree()) == "supported fix"
    llm = {"a": ["objected"]}
    preds, share = z.routed({"a": [_tree()]}, llm, [{"id": "a"}], ("supported fix",))
    assert preds == {"a": ["objected"]} and share == 1.0
    preds, _ = z.routed({"a": [_tree(mech=0.2)]}, llm, [{"id": "a"}], ("supported fix",))
    assert preds == {"a": ["asked"]}


def test_redesigned_split_objects_on_a_checkable_task():
    from eval import g43_explore4 as w
    a = {**_tree(problem=0.18, mech=0.66), "goal_stated": {"noul": 0.95}, "contradicted": {"noul": 0.59},
         "link": {"probabilities": {"contradicted": 0.38, "absent": 0.14, "stated": 0.48}},
         "plan_misses_cause": {"noul": 0.26}, "plan_breaks_requirement": {"noul": 0.34},
         "plan_correct": {"noul": 0.23}, "user_assuming": {"noul": 0.88}}
    assert w.d(a) == "objected"                         # the full/mis-02 pattern
    a_task = {**a, "contradicted": {"noul": 0.1}, "plan_correct": {"noul": 0.9}}
    assert w.d(a_task) == "none"                        # a task with nothing wrong stays quiet
    no_goal = {**a_task, "goal_stated": {"noul": 0.1}, "problem_described": {"noul": 0.9},
               "mechanism_stated": {"noul": 0.1}}
    assert w.d(no_goal) == "asked"


def _e5(goal="both", link=0.9, achieves=0.9, conflicts=0.1, inv=0.1):
    probs = {k: (1.0 if k == goal else 0.0) for k in ("problem", "requirement", "both", "neither")}
    return {"goal_type": {"probabilities": probs}, "link_stated": {"noul": link},
            "achieves_goal": {"noul": achieves}, "conflicts_constraint": {"noul": conflicts},
            "investigation": {"noul": inv}}


def test_e5_decision_table_rows_in_order():
    from app.pipeline import jev_ground as jg
    assert jg.e5_action(_e5(inv=0.9, conflicts=0.9)) == "none"           # row 1
    assert jg.e5_action(_e5(goal="neither", achieves=0.1)) == "none"    # row 2
    assert jg.e5_action(_e5(link=0.1, conflicts=0.9)) == "objected"     # row 3 before row 4
    assert jg.e5_action(_e5(link=0.1, achieves=0.1)) == "asked"         # row 4: ruling 2
    assert jg.e5_action(_e5(goal="requirement", link=0.1, achieves=0.1)) == "objected"  # row 5
    assert jg.e5_action(_e5()) == "none"


def test_e5b_drops_the_goal_row_and_words_conversations():
    from app.pipeline import jev_ground as jg
    conv, single = jg.e5b_battery(True), jg.e5b_battery(False)
    assert "goal_type" not in conv and "problem_described" in conv
    assert jg._E5B_OVERALL in conv["achieves_goal"]["instructions"]
    assert jg._E5B_OVERALL not in single["achieves_goal"]["instructions"]
    a = {**_e5(), "problem_described": {"noul": 0.1}}
    assert jg.e5b_action({**a, "link_stated": {"noul": 0.1}}) == "none"       # a task is not asked
    assert jg.e5b_action({**a, "achieves_goal": {"noul": 0.2}}) == "objected"  # but it can be objected to
