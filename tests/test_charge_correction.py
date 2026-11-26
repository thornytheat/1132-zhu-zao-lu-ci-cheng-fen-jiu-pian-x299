import pytest

from foundrychem.charge_correction.service import inspect, bench_units, correction_plan
from foundrychem.charge_correction.contracts import CorrectionBatch, RecordError


@pytest.fixture
def document():
    return {'heat': 'HEAT', 'element': 'ELEMENT', 'grade': 'GRADE', 'state': 'STATE', 'deficit': 0.0, 'space': 0.0, 'mass_kg': 1.0, 'priority': 0.0}


def test_contract_round_trip(document):
    entry = CorrectionBatch.parse(document)
    assert entry.evidence() == document
    assert CorrectionBatch.parse(entry.evidence()) == entry


def test_record_identity_normalizes_fullwidth(document):
    document['heat'] = "　ＡＢＣ-１２　"
    entry = CorrectionBatch.parse(document)
    assert getattr(entry, 'heat') == "ABC-12"


def test_missing_identity_isolated(document):
    missing = dict(document)
    del missing['heat']
    intake = inspect([missing, document])
    assert intake.read_count == 2
    assert intake.accepted_count == 1
    assert intake.rejection_counts() == {"TEXT_REQUIRED": 1}
    assert intake.rejected[0].row == 1
    assert intake.rejected[0].field == 'heat'


def test_boolean_is_not_magnitude(document):
    document['deficit'] = True
    with pytest.raises(RecordError, match="NUMBER_REQUIRED"):
        CorrectionBatch.parse(document)


def test_nonfinite_measure_isolated(document):
    corrupted = {**document, 'deficit': "nan"}
    batch = inspect([document, corrupted, document])
    assert [item.evidence() for item in batch.records] == [document, document]
    assert batch.rejected[0].row == 2
    assert batch.evidence()["reason_counts"]["NUMBER_NONFINITE"] == 1


def test_invalid_range_reserves_no_entry(document):
    document['deficit'] = 0 - 1
    intake = inspect([document])
    assert intake.accepted_count == 0
    assert intake.rejected[0].field == 'deficit'
    assert intake.rejected[0].reason == "NUMBER_RANGE"


from dataclasses import replace


def test_scale_increment_rounds_up_target_and_down_ceiling(document):
    order=CorrectionBatch.parse({**document,"deficit":.11,"space":.31,"mass_kg":100})
    assert bench_units(order,1,5)==(15,30)


def test_remaining_budget_cannot_split_required_correction(document):
    order=CorrectionBatch.parse({**document,"deficit":.11,"space":.31,"mass_kg":100,"state":"成分下界偏低"})
    controls={order.element:dict(gain=1,step=5,limit=30)}
    plan, used=correction_plan([order],controls,12)
    assert not used and plan[0]["reason"]=="纠偏称量额度不足"


def test_two_furnaces_spend_only_whole_increment(document):
    row=CorrectionBatch.parse({**document,"deficit":.11,"space":.31,"mass_kg":100,"state":"成分下界偏低","priority":.8})
    controls={row.element:dict(gain=1,step=5,limit=25)}
    plan, used=correction_plan([replace(row,heat="ZZ",priority=.7),row],controls,50)
    assert used=={row.element:15}
    assert [x["approved_units"] for x in plan]==[15,0]
