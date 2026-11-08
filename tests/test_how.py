from ui.how_tab import WHY, warranty_period_label, _policy_rows


def test_warranty_period_groups_eu_and_uk():
    label = warranty_period_label()
    assert "24 months (EU and UK)" in label
    assert "24 months (EU)," not in label
    assert "24 months (EU), 24 months (UK)" not in label


def test_policy_table_uses_grouped_warranty():
    row = next(r for r in _policy_rows() if r[0] == "Warranty period")
    assert row[1] == warranty_period_label()


def test_why_it_matters_covers_cost_experience_and_data():
    titles = [t for t, _, _ in WHY]
    assert titles == ["Lower handling cost", "Better member experience", "Clean data"]
