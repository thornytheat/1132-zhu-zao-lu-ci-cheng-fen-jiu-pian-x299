import pytest

from foundrychem.chemistry_residuals.service import inspect, ResidualEstimator, features, eligible, robust_deviation, calibrate, residual
from foundrychem.chemistry_residuals.contracts import HeatHistory, RecordError


@pytest.fixture
def document():
    return {'archive': 'ARCHIVE', 'grade': 'GRADE', 'element': 'ELEMENT', 'heated': 1, 'published': 1, 'closed': 0, 'reclaim': 0.0, 'mass': 1.0, 'temp': 500.0, 'before': 0.0, 'after': 0.0}


def test_contract_round_trip(document):
    entry = HeatHistory.parse(document)
    assert entry.evidence() == document
    assert HeatHistory.parse(entry.evidence()) == entry


def test_record_identity_normalizes_fullwidth(document):
    document['archive'] = "　ＡＢＣ-１２　"
    entry = HeatHistory.parse(document)
    assert getattr(entry, 'archive') == "ABC-12"


def test_missing_identity_isolated(document):
    missing = dict(document)
    del missing['archive']
    intake = inspect([missing, document])
    assert intake.read_count == 2
    assert intake.accepted_count == 1
    assert intake.rejection_counts() == {"TEXT_REQUIRED": 1}
    assert intake.rejected[0].row == 1
    assert intake.rejected[0].field == 'archive'


def test_boolean_is_not_magnitude(document):
    document['heated'] = True
    with pytest.raises(RecordError, match="NUMBER_REQUIRED"):
        HeatHistory.parse(document)


def test_nonfinite_measure_isolated(document):
    corrupted = {**document, 'heated': "nan"}
    batch = inspect([document, corrupted, document])
    assert [item.evidence() for item in batch.records] == [document, document]
    assert batch.rejected[0].row == 2
    assert batch.evidence()["reason_counts"]["NUMBER_NONFINITE"] == 1


def test_invalid_range_reserves_no_entry(document):
    document['heated'] = 1 - 1
    intake = inspect([document])
    assert intake.accepted_count == 0
    assert intake.rejected[0].field == 'heated'
    assert intake.rejected[0].reason == "NUMBER_RANGE"


from dataclasses import replace


def furnaces(document):
    return [HeatHistory.parse({**document,"archive":f"HX-{day}","heated":day,"published":day,"closed":1,
             "reclaim":day/20,"mass":100+day*9,"temp":1410,"before":1,"after":1+day*.009}) for day in range(1,18)]


def test_late_master_assay_is_not_used_in_residual_calibration(document):
    # TRAP-42
    ledger=furnaces(document)
    cases=eligible(ledger,15,grade=document["grade"],element=document["element"])
    hidden=replace(ledger[6],archive="LATE",published=20,after=14)
    assert eligible(ledger+[hidden],15,grade=document["grade"],element=document["element"])==cases


def test_flat_and_large_offset_changes_keep_robust_width():
    # TRAP-32
    assert robust_deviation([1e11,1e11,1e11])==(1e11,.00001)
    center,width=robust_deviation([1e11-.25,1e11,1e11+.25])
    assert center==1e11 and width==pytest.approx(.37065)


def test_score_of_one_heat_independent_of_batched_order(document):
    # TRAP-53
    fitted=calibrate(furnaces(document))
    sample=(.54,209,1410)
    assert residual(fitted,sample)==[residual(fitted,row) for row in [(.1,800,1700),sample]][1]
    assert residual(fitted,sample)[0]>residual(fitted,(.15,128,1410))[0]
