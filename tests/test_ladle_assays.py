import pytest

from foundrychem.ladle_assays.service import inspect, review_assays, coverage
from foundrychem.ladle_assays.contracts import AssaySlip, RecordError


@pytest.fixture
def document():
    return {'assay': 'ASSAY', 'heat': 'HEAT', 'element': 'ELEMENT', 'lab': 'LAB', 'phase': 'PHASE', 'replicate': 1, 'result_pct': 0.0, 'day': 1, 'arrived': 1, 'revision': 1}


def test_contract_round_trip(document):
    entry = AssaySlip.parse(document)
    assert entry.evidence() == document
    assert AssaySlip.parse(entry.evidence()) == entry


def test_record_identity_normalizes_fullwidth(document):
    document['assay'] = "　ＡＢＣ-１２　"
    entry = AssaySlip.parse(document)
    assert getattr(entry, 'assay') == "ABC-12"


def test_missing_identity_isolated(document):
    missing = dict(document)
    del missing['assay']
    intake = inspect([missing, document])
    assert intake.read_count == 2
    assert intake.accepted_count == 1
    assert intake.rejection_counts() == {"TEXT_REQUIRED": 1}
    assert intake.rejected[0].row == 1
    assert intake.rejected[0].field == 'assay'


def test_boolean_is_not_magnitude(document):
    document['replicate'] = True
    with pytest.raises(RecordError, match="NUMBER_REQUIRED"):
        AssaySlip.parse(document)


def test_nonfinite_measure_isolated(document):
    corrupted = {**document, 'replicate': "nan"}
    batch = inspect([document, corrupted, document])
    assert [item.evidence() for item in batch.records] == [document, document]
    assert batch.rejected[0].row == 2
    assert batch.evidence()["reason_counts"]["NUMBER_NONFINITE"] == 1


def test_invalid_range_reserves_no_entry(document):
    document['replicate'] = 1 - 1
    intake = inspect([document])
    assert intake.accepted_count == 0
    assert intake.rejected[0].field == 'replicate'
    assert intake.rejected[0].reason == "NUMBER_RANGE"


from dataclasses import replace


def test_old_revision_cannot_override_current_assay(document):
    # TRAP-26
    control=AssaySlip.parse({**document,"phase":"炉前","result_pct":.5})
    latest=replace(control,revision=3,result_pct=.8)
    cross=replace(control,lab="L-B",assay="B",result_pct=.9)
    supported,unknown=review_assays([latest,cross,control],1,.21)
    assert not unknown and supported[0]["pre_pct"]==pytest.approx(.85)


def test_missing_second_lab_keeps_material_on_hold(document):
    single=AssaySlip.parse({**document,"phase":"炉前","result_pct":.8})
    rows,issues=review_assays([single,single],1,.1)
    assert not rows and issues[0]["reason"]=="化验复测差异"


def test_coverage_requires_every_declared_element():
    assert coverage([dict(heat="H1",element="Cu"),dict(heat="H1",element="Mg")],["Cu","Mg","Si"])=={"H1":["Si"]}
