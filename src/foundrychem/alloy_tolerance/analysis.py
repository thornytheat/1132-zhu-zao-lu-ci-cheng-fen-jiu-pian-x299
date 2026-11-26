from dataclasses import dataclass
from math import ceil,isfinite,fsum,exp
from .contracts import ElementLimit


@dataclass(frozen=True)
class ForecastError:
    radius: float
    support: int
    exceedance: float | None


def empirical_errors(pairs, coverage=.9):
    if not 0<coverage<1:
        raise ValueError("INVALID_CONFIDENCE")
    errors=sorted(abs(actual-predicted) for actual,predicted in pairs if isfinite(actual) and isfinite(predicted))
    if not errors:
        return ForecastError(0,0,None)
    threshold=errors[min(len(errors),ceil((len(errors)+1)*coverage))-1]
    return ForecastError(threshold,len(errors),sum(x>threshold for x in errors)/len(errors))


def stable_risk(z):
    value=exp(-abs(z))
    return 1/(1+value) if z>=0 else value/(1+value)


def check_band(record, evidence, *, support_distance=7.5):
    if record.low>=record.high:
        raise ValueError("INVALID_GRADE_LIMITS")
    low=max(0,record.predicted-evidence.radius-record.shift)
    high=min(100,record.predicted+evidence.radius+record.shift)
    if evidence.support<record.minimum_validation:
        state="验证炉次不足"
    elif record.distance>support_distance:
        state="历史工况外复验"
    elif high>record.high:
        state="成分上界超差"
    elif low<record.low:
        state="成分下界偏低"
    else:
        state="合格区间"
    return dict(element=record.element,low=round(low,5),high=round(high,5),lower_limit=record.low,
                upper_limit=record.high,risk=stable_risk((record.low-low)/max(evidence.radius,.002)),state=state,
                deficit=max(0,record.low-low),space=max(0,record.high-high))
