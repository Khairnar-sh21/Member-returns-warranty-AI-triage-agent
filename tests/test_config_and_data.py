from datetime import date

import pytest
import yaml

from triage.config import RULES_PATH, RulesConfigError, load_rules


def test_rules_yaml_loads_with_expected_thresholds(rules):
    assert rules.return_remorse.window_days == 30
    assert rules.warranty_months_for("US") == 12
    assert rules.warranty_months_for("EU") == 24
    assert rules.warranty_months_for("UK") == 24
    assert rules.escalation.min_confidence == 0.70
    assert rules.today() == date(2026, 11, 5)


@pytest.mark.parametrize(
    "path, bad_value, expected_message",
    [
        (("escalation", "min_confidence"), 7, "escalation.min_confidence"),
        (("return_remorse", "window_days"), -5, "return_remorse.window_days"),
        (("routing", "region_to_warehouse", "AU"), "MARS", "routing.region_to_warehouse.AU"),
    ],
)
def test_invalid_rules_fail_with_readable_message(tmp_path, path, bad_value, expected_message):
    raw = yaml.safe_load(RULES_PATH.read_text())
    node = raw
    for key in path[:-1]:
        node = node[key]
    node[path[-1]] = bad_value
    bad_file = tmp_path / "rules.yaml"
    bad_file.write_text(yaml.safe_dump(raw))

    with pytest.raises(RulesConfigError, match=expected_message):
        load_rules(bad_file)


def test_misspelled_key_is_rejected(tmp_path):
    raw = yaml.safe_load(RULES_PATH.read_text())
    raw["return_remorse"]["window_dayz"] = raw["return_remorse"].pop("window_days")
    bad_file = tmp_path / "rules.yaml"
    bad_file.write_text(yaml.safe_dump(raw))

    with pytest.raises(RulesConfigError, match="window_dayz"):
        load_rules(bad_file)


def test_data_loads(store):
    assert len(store.members) == 60
    lost = store.get_context("M0009")
    assert lost.latest_order().delivered_date is None
    assert store.get_context("NOPE") is None
