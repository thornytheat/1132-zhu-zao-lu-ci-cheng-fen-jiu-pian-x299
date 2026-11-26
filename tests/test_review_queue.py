from statistics import median

import pytest

from foundrychem.ladle_assays.contracts import AssaySlip
from foundrychem.pipeline import run
from foundrychem.review_queue.analysis import (
    CHECK_STATION,
    CORRECTION_RECHECK,
    NORMAL_RELEASE,
    STOP_FURNACE,
    ElementCase,
    StationCenter,
    assemble,
    decide_element,
)
from foundrychem.review_queue.service import (
    build_cases,
    certificate_holds,
    queue_totals,
    queue_evidence,
    shift_queue,
    visible_revisions,
)

INTERVAL = (0.90, 0.95)


def case(heat="HJ-00", *, element="Mn", state="合格区间", low=INTERVAL[0], high=INTERVAL[1],
         distance=1.0, lab_state="量具复验通过", centers=None, revision=1):
    if centers is None:
        centers = (StationCenter("甲", 0.91), StationCenter("乙", 0.93))
    return ElementCase(heat=heat, element=element, state=state, low=low, high=high,
                       distance=distance, lab_state=lab_state, centers=centers, revision=revision)


def slip(key, value, *, heat="HJ-00", element="Mn", lab="甲", replicate=1, revision=1, day=10, arrived=10):
    return AssaySlip.parse(dict(assay=key, heat=heat, element=element, lab=lab, phase="炉前",
                                replicate=replicate, result_pct=value, day=day, arrived=arrived,
                                revision=revision))


# --- 证据一致性裁决 ---------------------------------------------------------


def test_single_station_deviation_reopens_release_instead_of_stopping():
    line = case(centers=(StationCenter("甲", 0.92), StationCenter("乙", 1.30)))
    destination, basis = decide_element(line, 7.5)
    assert destination == CHECK_STATION
    assert "单台偏离" in basis and "甲" in basis and "乙" in basis
    assert "继续生产" in basis


@pytest.mark.parametrize("distance", [7.6, 9.2, 30.0])
def test_two_agreeing_stations_beyond_historical_support_stop_the_furnace(distance):
    line = case(distance=distance, centers=(StationCenter("甲", 0.91), StationCenter("乙", 0.92)))
    destination, basis = decide_element(line, 7.5)
    assert destination == STOP_FURNACE
    assert "两台一致" in basis and "历史支持" in basis


def test_agreeing_stations_inside_support_never_stop_for_distance():
    line = case(distance=7.5, state="合格区间")
    assert decide_element(line, 7.5)[0] == NORMAL_RELEASE


def test_state_out_of_support_stops_even_when_distance_is_unavailable():
    line = case(state="历史工况外复验", distance=None)
    assert decide_element(line, 7.5)[0] == STOP_FURNACE


def test_single_station_deviation_wins_over_far_distance():
    # 一台吻合、一台明显偏离时先查台位，即便整炉距离也偏大。
    line = case(distance=12.0, centers=(StationCenter("甲", 0.92), StationCenter("乙", 1.40)))
    assert decide_element(line, 7.5)[0] == CHECK_STATION


def test_opposite_direction_stations_are_checked_as_station_disagreement():
    line = case(centers=(StationCenter("甲", 0.80), StationCenter("乙", 1.10)))
    destination, basis = decide_element(line, 7.5)
    assert destination == CHECK_STATION
    assert "方向相反" in basis


def test_same_side_outside_stations_agree_and_stop_when_out_of_support():
    line = case(state="成分上界超差", distance=1.0,
                centers=(StationCenter("甲", 0.97), StationCenter("乙", 0.99)))
    destination, basis = decide_element(line, 7.5)
    assert destination == STOP_FURNACE
    assert "两台一致" in basis and "高于估算区间" in basis


def test_unreliable_station_is_investigated_before_stopping():
    for lab_state, needle in (("台内重复性不合格", "台内重复性"), ("复测槽号冲突", "槽号冲突"),
                              ("复测台位不足", "台位不足"), ("台间差异超限", "台间差异")):
        line = case(lab_state=lab_state, distance=20.0)
        destination, basis = decide_element(line, 7.5)
        assert destination == CHECK_STATION
        assert needle in basis


def test_upper_bound_failure_with_agreeing_stations_stops_furnace():
    line = case(state="成分上界超差")
    assert decide_element(line, 7.5)[0] == STOP_FURNACE


def test_lower_bound_deficit_routes_to_correction_recheck():
    line = case(state="成分下界偏低")
    assert decide_element(line, 7.5)[0] == CORRECTION_RECHECK


def test_single_station_without_interval_evidence_is_checked_not_stopped():
    line = case(low=None, high=None)
    assert decide_element(line, 7.5)[0] == CHECK_STATION
    single = case(centers=(StationCenter("甲", 0.92),))
    assert decide_element(single, 7.5)[0] == CHECK_STATION


# --- 每炉唯一去向 -----------------------------------------------------------


def test_each_heat_has_exactly_one_destination():
    cases = [case("HJ-1", element="Mn", state="成分下界偏低"),
             case("HJ-1", element="Si", state="成分上界超差"),
             case("HJ-2", element="Mn")]
    entries = assemble(cases)
    assert [entry.heat for entry in entries] == ["HJ-1", "HJ-2"]
    assert len(entries) == 2 and len({entry.heat for entry in entries}) == len(entries)
    # 停炉优先于纠偏，同炉只留最保守的一条去向。
    assert entries[0].destination == STOP_FURNACE
    assert entries[0].elements == ("Si",)
    assert entries[1].destination == NORMAL_RELEASE


def test_certificate_hold_cannot_be_cleared_by_fresh_assays():
    entries = assemble([case("HJ-7")],
                       certificates={"HJ-7": {"状态": "状态已撤销", "证书": "CE-7"}})
    assert len(entries) == 1
    assert entries[0].destination == "凭证待查"
    assert "CE-7" in entries[0].basis and "补做化验不能恢复" in entries[0].basis
    assert entries[0].elements == ()


# --- 旧修订与重试不新增记录 -------------------------------------------------


def test_late_old_revision_cannot_add_or_move_a_queue_record():
    current = case("HJ-3", revision=3, state="成分上界超差")
    stale = case("HJ-3", revision=1, state="合格区间")
    baseline = assemble([current])
    with_stale = assemble([current, stale])
    assert with_stale == baseline
    assert [entry.destination for entry in with_stale] == [STOP_FURNACE]


def test_station_centers_ignore_stale_revision_and_fold_retries():
    heat = "HJ-41"
    trusted = [slip("A", 0.92, heat=heat, revision=2), slip("B", 0.914, heat=heat, lab="乙", revision=2)]
    stale = slip("A", 4.0, heat=heat, revision=1)
    retry = [slip("A-复测", 0.921, heat=heat, replicate=2, revision=2),
             slip("B-复测", 0.915, heat=heat, lab="乙", replicate=2, revision=2)]
    revisions = visible_revisions([*trusted, *retry, stale], day=10)
    assert revisions[heat, "Mn"] == 2

    cases = build_cases(measurements=[dict(heat=heat, element="Mn")],
                        tolerance={(heat, "Mn"): dict(state="合格区间", low=INTERVAL[0], high=INTERVAL[1], distance=1.0)},
                        lab_reviews=[], slips=[*trusted, *retry, stale], day=10)
    line, = cases
    assert {item.lab for item in line.centers} == {"甲", "乙"}
    values = {item.lab: item.center for item in line.centers}
    assert values["甲"] == pytest.approx(median([0.92, 0.921]))
    assert values["乙"] == pytest.approx(median([0.914, 0.915]))


def test_supplementary_current_revision_only_changes_that_heat():
    untouched = case("HJ-8", element="Mn", state="合格区间", revision=1)
    before = {entry.heat: entry.destination for entry in assemble([untouched, case("HJ-9", state="成分上界超差")])}
    supplemented = case("HJ-9", element="Mn", state="合格区间", revision=2,
                        centers=(StationCenter("甲", 0.92), StationCenter("乙", 0.925)))
    after = {entry.heat: entry.destination for entry in assemble([untouched, supplemented])}
    assert before["HJ-8"] == after["HJ-8"] == NORMAL_RELEASE
    assert before["HJ-9"] == STOP_FURNACE and after["HJ-9"] == NORMAL_RELEASE


def test_duplicate_same_revision_cases_collapse_to_one_entry():
    first = case("HJ-12", element="Mn", revision=2, distance=9.0)
    retry = case("HJ-12", element="Mn", revision=2, distance=9.0)
    entries = assemble([first, retry])
    assert len(entries) == 1 and entries[0].destination == STOP_FURNACE
    assert entries[0].distance == 9.0


# --- 管道接入 ---------------------------------------------------------------


def test_live_snapshot_exposes_one_queue_row_per_heat():
    report = run(40)
    queue = report["review_queue"]
    records = queue["records"]
    heats = [row["炉次"] for row in records]
    assert heats == sorted(set(heats))
    assert len(records) == len(set(heats))
    assert len(records) == report["metrics"]["复验队列炉次"]
    assert queue["totals"]["需复验炉次"] == sum(report["review_queue"]["totals"][k] for k in
                                                ("查台位炉次", "停炉复检炉次", "凭证待查炉次", "按纠偏复验炉次"))
    assert all(row["去向"] for row in records)
    assert set(queue["columns"]).issuperset({"炉次", "去向", "依据"})


def test_live_queue_sets_expected_destinations_for_seed_cases():
    report = run(40)
    destinations = {row["炉次"]: row["去向"] for row in report["review_queue"]["records"]}
    assert destinations["HJ-05"] == CHECK_STATION      # 单台偏离、另一台吻合
    assert destinations["HJ-11"] == STOP_FURNACE       # 两台一致且越出历史支持
    assert destinations["HJ-06"] == "凭证待查"          # 撤销凭证
    assert destinations["HJ-13"] == CHECK_STATION      # 台内重复性不合格
    assert destinations["HJ-01"] == NORMAL_RELEASE


def test_queue_destinations_do_not_depend_on_bench_budget():
    small = run(1)["review_queue"]
    large = run(90)["review_queue"]
    assert small == large


def test_queue_evidence_and_totals_reconcile():
    report = run(40)
    tolerance = {(row["炉次"], row["element"]): row
                 for row in report["stages"][3]["records"] if "炉次" in row}
    entries = shift_queue(
        measurements=[dict(row) for row in report["stages"][0]["records"] if "pre_pct" in row],
        tolerance=tolerance,
        lab_reviews=[],
        slips=[],
        day=63,
        heats={row["heat"] for row in report["rows"]},
        certificates={},
    )
    assert queue_totals(entries)["复验炉次"] == len(entries)
    assert len(queue_evidence(entries)) == len(entries)


def test_missing_assay_coverage_is_queued_for_check_not_silently_released():
    cases = build_cases(measurements=[dict(heat="HJ-50", element="Mn")],
                        tolerance={(("HJ-50"), "Mn"): dict(state="合格区间", low=INTERVAL[0], high=INTERVAL[1], distance=0.5),
                                   ("HJ-50", "Si"): dict(state="合格区间", low=INTERVAL[0], high=INTERVAL[1], distance=0.5)},
                        lab_reviews=[],
                        slips=[slip("A", 0.92, heat="HJ-50"), slip("B", 0.914, heat="HJ-50", lab="乙")],
                        day=10,
                        missing={"HJ-50": ["Si"]})
    entries = assemble(cases)
    assert len(entries) == 1
    assert entries[0].destination == CHECK_STATION
    assert "Si" in entries[0].elements
    assert "台位" in entries[0].basis

    holds = certificate_holds(
        [{"炉次": "HJ-1", "状态": "状态已撤销", "证书": "CE-1"}],
        [{"heat": "HJ-2", "reason": "材质证书不在有效区间"}],
    )
    assert holds["HJ-1"]["状态"] == "状态已撤销"
    assert holds["HJ-2"]["状态"] == "材质证书不在有效区间"
