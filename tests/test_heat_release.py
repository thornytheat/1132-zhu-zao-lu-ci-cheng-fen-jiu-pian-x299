import pytest

from foundrychem.heat_release.service import inspect, verify_release, proof_signature, check_heats
from foundrychem.heat_release.contracts import ReleaseAssay, RecordError


@pytest.fixture
def document():
    return {'release': 'RELEASE', 'heat': 'HEAT', 'element': 'ELEMENT', 'result_pct': 0.0, 'minute': 0, 'observed_day': 1, 'actual_units': 0, 'signer': 'SIGNER'}


def test_contract_round_trip(document):
    entry = ReleaseAssay.parse(document)
    assert entry.evidence() == document
    assert ReleaseAssay.parse(entry.evidence()) == entry


def test_record_identity_normalizes_fullwidth(document):
    document['release'] = "　ＡＢＣ-１２　"
    entry = ReleaseAssay.parse(document)
    assert getattr(entry, 'release') == "ABC-12"


def test_missing_identity_isolated(document):
    missing = dict(document)
    del missing['release']
    intake = inspect([missing, document])
    assert intake.read_count == 2
    assert intake.accepted_count == 1
    assert intake.rejection_counts() == {"TEXT_REQUIRED": 1}
    assert intake.rejected[0].row == 1
    assert intake.rejected[0].field == 'release'


def test_boolean_is_not_magnitude(document):
    document['result_pct'] = True
    with pytest.raises(RecordError, match="NUMBER_REQUIRED"):
        ReleaseAssay.parse(document)


def test_nonfinite_measure_isolated(document):
    corrupted = {**document, 'result_pct': "nan"}
    batch = inspect([document, corrupted, document])
    assert [item.evidence() for item in batch.records] == [document, document]
    assert batch.rejected[0].row == 2
    assert batch.evidence()["reason_counts"]["NUMBER_NONFINITE"] == 1


def test_invalid_range_reserves_no_entry(document):
    document['result_pct'] = 0 - 1
    intake = inspect([document])
    assert intake.accepted_count == 0
    assert intake.rejected[0].field == 'result_pct'
    assert intake.rejected[0].reason == "NUMBER_RANGE"


from dataclasses import replace


def test_finishing_control_changes_fingerprint():
    # TRAP-54
    key=proof_signature(dict(gain=.5),["s1","l1"],[])
    assert key!=proof_signature(dict(gain=.6),["s1","l1"],[])
    assert key!=proof_signature(dict(gain=.5),["s1","l2"],[])


def test_ship_requires_complete_element_coverage():
    vals=[dict(heat="HA",element="Cu",state="允许交割"),dict(heat="HB",element="Si",state="允许交割")]
    assert check_heats(vals,["Cu","Si"])=={"HA":False,"HB":False}
    vals.append(dict(heat="HA",element="Si",state="允许交割"))
    assert check_heats(vals,["Cu","Si"])=={"HA":True,"HB":False}


def test_final_pct_controls_release_even_after_authorization(document):
    reading=ReleaseAssay.parse({**document,"result_pct":1.65,"actual_units":2})
    authorization=[dict(heat=reading.heat,element=reading.element,grade="P2",approved_units=10,reason="已批准复验")]
    result=verify_release([reading],authorization,{("P2",reading.element):(1.75,2.00)},2)
    assert result[0]["state"]=="终检仍超差"
    allowed=verify_release([replace(reading,result_pct=1.75)],authorization,{("P2",reading.element):(1.75,2.00)},2)
    assert allowed[0]["state"]=="允许交割"
