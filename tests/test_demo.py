"""Demo mode must always work on the public link: every sample has a cached AI result."""

from triage.demo import cached_classification, load_cache, load_scenarios, message_key
from triage.pipeline import triage_with_classification


def test_there_are_ten_sample_scenarios_with_real_members(store):
    scenarios = load_scenarios()
    assert len(scenarios) == 10
    assert len({s.id for s in scenarios}) == 10
    assert all(s.member_id in store.members for s in scenarios)


def test_every_scenario_has_a_successful_cached_classification():
    cache = load_cache()
    assert cache is not None, "Run scripts/build_demo_cache.py"
    for s in load_scenarios():
        cached = cached_classification(s.message)
        assert cached is not None, f"{s.id} missing from cache; rebuild it"
        assert cached.status != "fallback"


def test_cache_lookup_ignores_spacing_and_case():
    s = load_scenarios()[0]
    assert message_key(s.message) == message_key("  " + s.message.upper().replace(" ", "   "))


def test_cached_classification_works_for_any_member(store, rules):
    """The AI never saw account data, so a cached reading applies to every member."""
    s = load_scenarios()[1]  # return request
    clf = cached_classification(s.message)
    in_window = triage_with_classification(s.message, "M0002", clf, mode="demo",
                                           store=store, rules=rules)
    out_of_window = triage_with_classification(s.message, "M0004", clf, mode="demo",
                                               store=store, rules=rules)
    assert in_window.decision.decision == "approve_return"
    assert out_of_window.decision.decision == "deny_return_window_closed"


def test_samples_cover_all_three_outcome_tiers(store, rules):
    tiers = set()
    for s in load_scenarios():
        r = triage_with_classification(s.message, s.member_id, cached_classification(s.message),
                                       mode="demo", store=store, rules=rules)
        tiers.add(r.case.outcome)
    assert tiers == {"automated", "needs_review", "escalated"}
