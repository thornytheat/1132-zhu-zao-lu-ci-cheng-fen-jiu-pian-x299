from foundrychem.pipeline import run


def test_shift_replays_lab_coverage_and_release_actions():
    report=run(35)
    assert len(report["rows"]) >= 24
    states={row["reason"] for row in report["rows"]}
    assert {"料批凭证待查","关联成分化验不完整","历史工况外复验","成分上界超差"} <= states
    assert 0 < report["metrics"]["复验预留单位"] <= 35
    assert len(report["stages"])==6


def test_allowance_materially_changes_reservations_without_changing_evidence():
    small,large=run(1),run(60)
    assert small["stages"][3]==large["stages"][3]
    assert small["metrics"]["复验预留单位"] < large["metrics"]["复验预留单位"]
    assert small["audit_id"]!=large["audit_id"]
