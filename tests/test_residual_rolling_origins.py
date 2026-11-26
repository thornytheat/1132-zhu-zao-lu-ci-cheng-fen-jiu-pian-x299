from dataclasses import replace
from statistics import mean

import pytest

from foundrychem.chemistry_residuals.contracts import HeatHistory
from foundrychem.chemistry_residuals.replay import BlindReading, control_variance, held_heat_paths
from foundrychem.pipeline import run


def archive(n):
    records=[]
    for day in range(1,n+1):
        before=2.03+(day%4)*.001
        reclaim=.09+day/100
        grade="墙体-SV"
        after=before+.2*reclaim+(day%7)*.0003
        records.append(HeatHistory.parse(dict(archive=f"ARCH-{day:02}",grade=grade,element="S",
                      heated=day,published=day,closed=1,reclaim=reclaim,mass=108,temp=1245,
                      before=before,after=after)))
    return records


def test_walk_forward_reference_improves_when_reclaimed_fraction_shift_is_predictable():
    records=archive(28)
    tested,omitted=held_heat_paths(records,first_day=17,final_day=27,allowance=.15)
    assert not omitted
    assert [line.week for line in tested]==list(range(17,27))
    assert [line.support for line in tested]==list(range(16,26))
    details,=control_variance(tested)
    assert details["模型胜出炉次"]==10
    assert details["残差平均绝对值"] < details["基线平均绝对值"]
    assert details["误差改善比例"]>.5
    assert all(abs(row.truth-row.estimated)<abs(row.truth-row.naive) for row in tested)


def test_late_conflicting_version_cannot_affect_earlier_training_prefix():
    observed=archive(21)
    changed=replace(observed[2],published=19,after=4.0)
    old,_=held_heat_paths(observed,first_day=15,final_day=22,allowance=.15)
    current,_=held_heat_paths(observed+[changed],first_day=15,final_day=22,allowance=.15)
    by_day={row.week:row for row in current}
    for line in old:
        if line.week<=19:
            assert line==by_day[line.week]
        else:
            assert line.support==by_day[line.week].support+1
            assert line.estimated!=by_day[line.week].estimated


def test_baseline_zero_error_keeps_relative_improvement_undefined():
    points=[BlindReading("迭代A","C","G-101",12,1,.9,1,10),BlindReading("迭代A","C","G-102",13,2.1,2.2,2.1,11)]
    result,=control_variance(points)
    assert result["误差改善比例"] is None
    assert result["基线平均绝对值"]==0
    assert result["平均偏差"]==0
    assert result["残差平均绝对值"]==.1
    assert result["最大误差"]==.1
    assert result["模型胜出炉次"]==0
    assert points[1].evidence()["前缀样本"]==11


def test_underpowered_ledger_emits_each_unavailable_trial_date():
    selected,rejected=held_heat_paths(archive(5),first_day=3,final_day=6,allowance=.4)
    assert not selected
    assert [line["回放日"] for line in rejected]==[3,4,5]
    assert {line["状态"] for line in rejected}=={"训练期炉次过少"}


def test_case_results_match_calendar_and_control_variance_summary():
    result=run(53)
    evidence=result["archive_replay"]
    assert all(59<=line["回放日"]<=62 for line in evidence)
    detail=[row for row in result["stages"][2]["records"] if "误差改善比例" in row]
    assert len(detail)==4
    assert sum(row["回放炉次"] for row in detail)==len(evidence)
    for row in detail:
        rows=[point for point in evidence if (point["牌号"],point["元素"])==(row["牌号"],row["元素"])]
        true=mean(abs(point["终检"]-point["估计终检"]) for point in rows)
        assert row["残差平均绝对值"]==pytest.approx(true,abs=.00001)
