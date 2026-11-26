import pytest

from foundrychem.heat_release.shift_summary import handover_totals, status_by_element
from foundrychem.pipeline import run


def decision(heat, element, reserved=0,grade="NG-1"):
    return dict(heat=heat,element=element,grade=grade,approved_units=reserved)


def final(key, heat, element, status="允许交割", spent=0):
    return dict(release=key,heat=heat,element=element,state=status,actual_units=spent)


def test_last_station_account_reconciles_pending_and_released_doses():
    plan=[decision("炉-A","Cu",12),decision("炉-A","Si"),decision("炉-B","Cu",18),decision("炉-B","Si"),
          decision("炉-C","Cu"),decision("炉-D","Cu",grade="—")]
    assays=[final("101","炉-A","Cu",spent=6),final("102","炉-A","Si"),final("103","炉-B","Si"),
            final("104","炉-B","Cu","终检仍超差",spent=8),final("105","边缘炉","Cu","未找到质控授权")]
    closing, isolated=status_by_element({("NG-1","Cu"):(.2,.3),("NG-1","Si"):(.5,.6)},plan,assays)
    assert [row.reason for row in closing]==["可交割","交割挂起","待送终检","待核产品牌号"]
    assert closing[1].unresolved==("Cu",)
    assert closing[0].used==6
    assert closing[0].evidence()["台架待释放"]==6
    assert isolated==[{"炉次":"边缘炉","交割单":"105","交割结果":"未能对应纠偏审理"}]
    profile=handover_totals(closing)
    assert profile["台架预留"]==30
    assert profile["台架实用"]==6
    assert profile["台架待释放"]==24
    assert profile["交割通过"]==1
    assert profile["待终检"]==1
    assert profile["待查牌号"]==1
    assert profile["交割挂起"]==1


def test_newly_signed_terminal_test_does_not_erase_failure_within_same_heat():
    plan=[decision("炉-E","Si",8)]
    readbacks=[final("X","炉-E","Si","终检仍超差"),final("Y","炉-E","Si",spent=3)]
    pending,_=status_by_element({("NG-1","Si"):(.1,.4)},plan,readbacks)
    assert pending[0].reason=="交割挂起"
    assert pending[0].passed==()
    assert pending[0].unresolved==("Si",)
    assert pending[0].used==3


def test_handover_does_not_accept_error_hidden_by_other_elements():
    lines=[decision("炉-D","Si",5),decision("炉-D","Mn",2)]
    limits={ ("NG-1","Si"):(1,1.2),("NG-1","Mn"):(.5,.7)}
    signed=[final("U","炉-D","Si",spent=8),final("V","炉-D","Mn")]
    with pytest.raises(ValueError,match="ACTUAL_EXCEEDS_BENCH_RESERVATION"):
        status_by_element(limits,lines,signed)


@pytest.mark.parametrize("quota",[1,29,89])
def test_live_shift_table_matches_heat_summary(quota):
    summary=run(quota)
    amounts=summary["readiness"]
    assert amounts["台架预留"] == sum(row["approved_units"] for row in summary["rows"])
    assert amounts["台架实用"]+amounts["台架待释放"]==amounts["台架预留"]<=quota
    outcomes=[row for row in summary["stages"][-1]["records"] if "应验项目" in row]
    assert len(outcomes)==amounts["总炉次"]
    assert summary["metrics"]["可交割炉次"]==sum(row["交割结果"]=="可交割" for row in outcomes)
    assert all(set(row["通过项目"]).isdisjoint(row["待验项目"]) for row in outcomes)
