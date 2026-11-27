"""E7h's margin rule: decide() must give E7's own table, and the band sends a
decision to the LLM only when a checked score is near its threshold."""
from app.pipeline import jev_ground as jg
from eval import e7_hybrid as hy
from eval import g43_eval as ge

QUESTIONS = ("investigation", "conflicts_constraint", "problem_described", "achieves_goal", "facts_against_cause",
             "plan_ruled_out", "evidence_for_cause", "link_stated", "plan_reversible", "plan_large")


def answers(**scores):
    base = {"investigation": 0.0, "conflicts_constraint": 0.0, "problem_described": 1.0, "achieves_goal": 1.0,
            "facts_against_cause": 0.0, "plan_ruled_out": 0.0, "evidence_for_cause": 0.0, "link_stated": 0.0,
            "plan_reversible": 1.0, "plan_large": 0.0}
    base.update(scores)
    return {q: {"type": "noul", "noul": v} for q, v in base.items()}


def test_decide_matches_the_e7_table_on_a_grid():
    import itertools
    for vals in itertools.product((0.0, 0.29, 0.31, 0.49, 0.51, 0.69, 0.71, 1.0), repeat=3):
        for qs in (("investigation", "conflicts_constraint", "problem_described"),
                   ("facts_against_cause", "plan_ruled_out", "evidence_for_cause"),
                   ("evidence_for_cause", "achieves_goal", "link_stated"),
                   ("link_stated", "plan_reversible", "plan_large")):
            a = answers(**dict(zip(qs, vals)))
            for conv in (False, True):
                row, act, _ = hy.decide(a, ge.E7_CONFIG, conv)
                assert (row, act) == jg.e7_row(a, ge.E7_CONFIG, conv)


def test_margin_is_the_closest_checked_score():
    # row 7: every row's first score was checked; link_stated 0.45 is 0.05 under t_link
    _, act, m = hy.decide(answers(link_stated=0.45), ge.E7_CONFIG, False)
    assert act == "asked" and abs(m - 0.05) < 1e-9
    # row 1 checks only investigation
    _, act, m = hy.decide(answers(investigation=0.9, link_stated=0.5), ge.E7_CONFIG, False)
    assert act == "none" and abs(m - 0.4) < 1e-9


def test_the_band_hands_only_near_threshold_decisions_to_the_llm():
    cases = [{"id": "near", "shape": "single"}, {"id": "far", "shape": "single"}]
    jev = {"near": [answers(link_stated=0.45)], "far": [answers(link_stated=0.0, problem_described=1.0,
                                                                 evidence_for_cause=0.0)]}
    llm = {"near": {0: "objected"}, "far": {0: "objected"}}
    preds, rate = hy.hybrid(jev, llm, cases, 0.1)
    assert preds["near"] == ["objected"]
    assert preds["far"] == ["asked"]          # every checked score is at least 0.5 from its threshold
    assert rate == 0.5


def test_a_failed_llm_call_counts_as_none():
    cases = [{"id": "near", "shape": "single"}]
    preds, _ = hy.hybrid({"near": [answers(link_stated=0.45)]}, {"near": {0: None}}, cases, 0.1)
    assert preds["near"] == ["none"]
