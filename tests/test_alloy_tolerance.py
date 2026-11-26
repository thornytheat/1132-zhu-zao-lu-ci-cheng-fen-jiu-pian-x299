import pytest

from foundrychem.alloy_tolerance.service import inspect, ForecastError, empirical_errors, stable_risk, check_band
from foundrychem.alloy_tolerance.contracts import ElementLimit, RecordError


@pytest.fixture
def document():
    return {'element': 'ELEMENT', 'grade': 'GRADE', 'low': 0.0, 'high': 0.0, 'predicted': 0.0, 'shift': 0.0, 'distance': 0.0, 'minimum_validation': 1}


def test_contract_round_trip(document):
    entry = ElementLimit.parse(document)
    assert entry.evidence() == document
    assert ElementLimit.parse(entry.evidence()) == entry


def test_record_identity_normalizes_fullwidth(document):
    document['element'] = "　ＡＢＣ-１２　"
    entry = ElementLimit.parse(document)
    assert getattr(entry, 'element') == "ABC-12"


def test_missing_identity_isolated(document):
    missing = dict(document)
    del missing['element']
    intake = inspect([missing, document])
    assert intake.read_count == 2
    assert intake.accepted_count == 1
    assert intake.rejection_counts() == {"TEXT_REQUIRED": 1}
    assert intake.rejected[0].row == 1
    assert intake.rejected[0].field == 'element'


def test_boolean_is_not_magnitude(document):
    document['low'] = True
    with pytest.raises(RecordError, match="NUMBER_REQUIRED"):
        ElementLimit.parse(document)


def test_nonfinite_measure_isolated(document):
    corrupted = {**document, 'low': "nan"}
    batch = inspect([document, corrupted, document])
    assert [item.evidence() for item in batch.records] == [document, document]
    assert batch.rejected[0].row == 2
    assert batch.evidence()["reason_counts"]["NUMBER_NONFINITE"] == 1


def test_invalid_range_reserves_no_entry(document):
    document['low'] = 0 - 1
    intake = inspect([document])
    assert intake.accepted_count == 0
    assert intake.rejected[0].field == 'low'
    assert intake.rejected[0].reason == "NUMBER_RANGE"


def test_empty_holdout_yields_undefined_exceedance(document):
    # TRAP-43
    band=empirical_errors([])
    line=ElementLimit.parse({**document,"high":1.0})
    assert band.exceedance is None
    assert check_band(line,band)["state"]=="验证炉次不足"


def test_nominal_estimate_does_not_release_out_of_support_heat(document):
    # TRAP-44
    line=ElementLimit.parse({**document,"distance":10,"predicted":1.1,"low":.9,"high":1.3})
    assert check_band(line,empirical_errors([(1,1.01)]*15))["state"]=="历史工况外复验"


def test_dispersion_can_change_nominal_pass_into_inspection(document):
    line=ElementLimit.parse({**document,"predicted":1.04,"low":1.0,"high":1.2,"shift":.025})
    result=check_band(line,empirical_errors([(1,1.02)]*15))
    assert result["state"]=="成分下界偏低"
    assert result["deficit"]==pytest.approx(.005)


def test_very_large_margin_has_finite_risk():
    # TRAP-31
    assert stable_risk(-1000)==0 and stable_risk(1000)==1
