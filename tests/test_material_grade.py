import pytest

from foundrychem.material_grade.service import inspect, material_balance, witness_set
from foundrychem.material_grade.contracts import BatchMaterial, RecordError


@pytest.fixture
def document():
    return {'trace': 'TRACE', 'heat': 'HEAT', 'feed_type': 'FEED_TYPE', 'lot': 'LOT', 'certificate': 'CERTIFICATE', 'mass_kg': 1.0, 'grade': 'GRADE', 'melt_temp': 500.0, 'reclaim_ratio': 0.0, 'received': 1, 'valid_from': 1, 'valid_to': 2}


def test_contract_round_trip(document):
    entry = BatchMaterial.parse(document)
    assert entry.evidence() == document
    assert BatchMaterial.parse(entry.evidence()) == entry


def test_record_identity_normalizes_fullwidth(document):
    document['trace'] = "　ＡＢＣ-１２　"
    entry = BatchMaterial.parse(document)
    assert getattr(entry, 'trace') == "ABC-12"


def test_missing_identity_isolated(document):
    missing = dict(document)
    del missing['trace']
    intake = inspect([missing, document])
    assert intake.read_count == 2
    assert intake.accepted_count == 1
    assert intake.rejection_counts() == {"TEXT_REQUIRED": 1}
    assert intake.rejected[0].row == 1
    assert intake.rejected[0].field == 'trace'


def test_boolean_is_not_magnitude(document):
    document['mass_kg'] = True
    with pytest.raises(RecordError, match="NUMBER_REQUIRED"):
        BatchMaterial.parse(document)


def test_nonfinite_measure_isolated(document):
    corrupted = {**document, 'mass_kg': "nan"}
    batch = inspect([document, corrupted, document])
    assert [item.evidence() for item in batch.records] == [document, document]
    assert batch.rejected[0].row == 2
    assert batch.evidence()["reason_counts"]["NUMBER_NONFINITE"] == 1


def test_invalid_range_reserves_no_entry(document):
    document['mass_kg'] = 1 - 1
    intake = inspect([document])
    assert intake.accepted_count == 0
    assert intake.rejected[0].field == 'mass_kg'
    assert intake.rejected[0].reason == "NUMBER_RANGE"


from dataclasses import replace


def test_certificate_expiry_is_exclusive(document):
    # TRAP-23
    row=BatchMaterial.parse({**document,"valid_to":15})
    assert len(material_balance([row],14)[0])==1
    assert material_balance([row],15)[1][0]["reason"]=="材质证书不在有效区间"


def test_weighted_reclaim_keeps_mass_balance(document):
    row=BatchMaterial.parse({**document,"mass_kg":25,"reclaim_ratio":.6,"melt_temp":1450})
    other=replace(row,trace="T2",mass_kg=75,reclaim_ratio=.2,melt_temp=1600)
    result,issues=material_balance([row,other],1)
    assert not issues and result[0]["mass_kg"]==100
    assert result[0]["reclaim_ratio"]==pytest.approx(.3)
    assert result[0]["melt_temp"]==pytest.approx(1562.5)


def test_grade_disagreement_blocks_furnace(document):
    row=BatchMaterial.parse(document)
    current=replace(row,trace="T2",grade="OTHER")
    assert material_balance([current,row],1)[1][-1]["reason"]=="同炉次料批牌号不一致"
