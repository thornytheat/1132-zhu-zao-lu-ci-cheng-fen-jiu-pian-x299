from dataclasses import replace
from decimal import Decimal
from itertools import product

import pytest

from foundrychem.charge_correction.contracts import CorrectionBatch
from foundrychem.charge_correction.service import bench_units, correction_plan
from foundrychem.pipeline import run


def eligible(batch, *, material="Si", deficit=.04, space=.08, kg=540, grade="NG-A", urgency=.6):
    return CorrectionBatch.parse(dict(heat=batch,element=material,grade=grade,state="成分下界偏低",
                                       deficit=deficit,space=space,mass_kg=kg,priority=urgency))


def test_discrete_step_limits_match_an_exhaustive_reference_window():
    for deficit, avail, size, step in product((0,.012,.046,.091),(.02,.051,.098), (280,1100),(2,3,5)):
        order=eligible("BF-88",deficit=deficit,space=avail,kg=size)
        gain=Decimal("7.5")
        mass=Decimal(str(size))
        reference=[step*index for index in range(100)]
        target_mass=mass*Decimal(str(deficit))
        admissible_mass=mass*Decimal(str(avail))
        required=min(value for value in reference if value*gain>=target_mass)
        allowable=max(value for value in reference if value*gain<=admissible_mass)
        assert bench_units(order,gain,step)==(required,allowable)


def test_unadjustable_part_line_never_takes_team_budget():
    unsafe=eligible("F-1",deficit=.11,space=.05,urgency=.92)
    supported=eligible("F-2",deficit=.02,space=.1)
    absent=eligible("F-3",material="Mn",deficit=.01,space=.1)
    calibration={"Si":dict(gain=12,step=2,limit=6)}
    before,used=correction_plan([unsafe,supported,absent],calibration,10)
    assert used=={"Si":2}
    assert before[0]["reason"]=="最小称量超过安全余量"
    assert before[1]["reason"]=="已批准复验"
    assert before[2]["reason"]=="未配置纠偏称"
    assert before==correction_plan([absent,unsafe,supported],calibration,10)[0]


def test_shape_duplicate_does_not_reduce_usable_dose_for_other_elements():
    first=eligible("F-1",material="Si",space=.2)
    second=replace(first,deficit=.015,priority=.8)
    third=replace(first,element="Mn",space=.2)
    allowed={"Si":dict(gain=12,step=2,limit=10),"Mn":dict(gain=11,step=2,limit=10)}
    steps,used=correction_plan([first,second,third],allowed,10)
    assert used=={"Mn":2}
    assert all(row["approved_units"]==0 and row["reason"]=="重复纠偏申请" for row in steps if row["element"]=="Si")
    assert sum(row["approved_units"] for row in steps)==2


def test_one_residual_correction_never_claims_capacity_from_out_of_support_furnace():
    snapshot=run(100)
    decisions=snapshot["rows"]
    border=[row for row in decisions if row["reason"]=="历史工况外复验"]
    assert border
    assert all(row["approved_units"]==0 for row in border)
    assert {row["heat"] for row in border}=={"HJ-11"}
    judged=[row for row in decisions if row["reason"]=="已批准复验"]
    assert judged
    assert all(row["approved_units"]>0 for row in judged)
    by_element={key:sum(row["approved_units"] for row in judged if row["element"]==key) for key in ("Si","Mn")}
    assert by_element["Si"] <= 45
    assert by_element["Mn"] <= 36


@pytest.mark.parametrize("gain, step",[(0,1),(-.1,2),(5,-1)])
def test_unusable_bench_calibration_blocks_calculation(gain,step):
    order=eligible("F-284",deficit=.01,space=.1)
    with pytest.raises(ValueError,match="STEP_INVALID"):
        bench_units(order,gain,step)


def test_larger_budget_preserves_lab_residual_and_certificate_blocks():
    baseline=run(4)
    expanded=run(88)
    for index in range(4):
        assert baseline["stages"][index] == expanded["stages"][index]
    assert baseline["archive_replay"] == expanded["archive_replay"]
    invalid={"历史工况外复验","料批凭证待查","台内重复性不合格","复测台位不足"}
    assert [(line["heat"],line["element"],line["reason"]) for line in baseline["rows"] if line["reason"] in invalid] == [
        (line["heat"],line["element"],line["reason"]) for line in expanded["rows"] if line["reason"] in invalid
    ]
    assert baseline["readiness"]["台架预留"] < expanded["readiness"]["台架预留"]
    assert baseline["audit_id"] != expanded["audit_id"]
