from dataclasses import replace
from statistics import variance

import pytest

from foundrychem.ladle_assays.contracts import AssaySlip
from foundrychem.ladle_assays.lab_controls import accepted_work, examine_lab_groups, pooled_repeatability, risky_pairs
from foundrychem.pipeline import run


def reading(key, value, *, heat="HM-16", element="Cu", lab="中间验台", replicate=1, revision=1, arrived=2):
    return AssaySlip.parse(dict(assay=key,heat=heat,element=element,lab=lab,phase="炉前",replicate=replicate,
                               result_pct=value, day=2, arrived=arrived, revision=revision))


def test_reproducibility_and_repeatability_are_independent():
    records=[reading("A-0",1.0),reading("A-1",1.01,replicate=2),
             reading("B-0",1.24,lab="右位"),reading("B-1",1.25,lab="右位",replicate=2)]
    line,=examine_lab_groups(records,day=2,repeat_limit=.02,interlab_limit=.1)
    assert line.state=="台间差异超限"
    assert line.laboratory_span==pytest.approx(.24)
    assert line.repeat_error==pytest.approx((.0001/2)**.5)
    assert line.evidence()["有效台位"]==2
    assert line.evidence()["有效复测"]==4
    assert risky_pairs([line])=={("HM-16","Cu"):"台间差异超限"}


def test_same_lab_replicate_slot_cannot_count_twice():
    trusted=reading("A-0",1.0)
    independent=reading("B-0",1.01,lab="右位")
    collision=reading("A-2",1.8)
    line,=examine_lab_groups([trusted,independent,collision],day=2,repeat_limit=.02,interlab_limit=.05)
    assert line.state=="复测槽号冲突"
    assert line.shots==1
    assert line.discarded_shots==2
    assert line.laboratory_span is None
    assert line.evidence()["台内合成偏差"] is None


def test_visible_revisions_rank_after_time_cutoff_and_phase():
    early=reading("E-01",1.15)
    planned=replace(early,result_pct=4.3,revision=3,arrived=7)
    after_cast=replace(early,result_pct=8.0,phase="终检",revision=2)
    admitted, conflicts=accepted_work([planned,early,after_cast],3)
    assert admitted==[early] and not conflicts
    assert accepted_work([planned,early,after_cast],8)[0]==[planned]
    second=replace(early,result_pct=1.21)
    safe, doubt=accepted_work([early,second,planned,early],3)
    assert not safe and doubt=={("HM-16","Cu"):2}


def test_grouped_repeatability_matches_degrees_of_freedom_reference():
    labs=[[1.11,1.12,1.16],[2.12,2.21],[1.00,1.01,1.05,1.03],[0.3]]
    active=[values for values in labs if len(values)>1]
    per_lab=[(variance(values),len(values)-1) for values in active]
    expected=(sum(v*dof for v,dof in per_lab)/sum(dof for _,dof in per_lab))**.5
    assert pooled_repeatability(labs)==pytest.approx(expected)
    assert pooled_repeatability([[125],[51]]) is None


def test_seed_assay_reports_one_clear_repeatability_hold():
    result=run(28)
    readings=[row for row in result["stages"][0]["records"] if "量具状态" in row]
    states={item["炉次"]+"/"+item["元素"]:item["量具状态"] for item in readings}
    assert states["HJ-13/Mn"]=="台内重复性不合格"
    assert states["HJ-01/Mn"]=="量具复验通过"
    assert states["HJ-09/Mn"]=="复测台位不足"
    adjudicated={(row["heat"],row["element"]):row for row in result["rows"]}
    assert adjudicated["HJ-13","Mn"]["reason"]=="台内重复性不合格"
    assert adjudicated["HJ-13","Mn"]["approved_units"]==0
