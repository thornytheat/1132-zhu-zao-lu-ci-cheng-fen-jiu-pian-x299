from collections.abc import Mapping
from dataclasses import dataclass
from math import isfinite
from unicodedata import normalize


class RecordError(ValueError):
    def __init__(self, field: str, reason: str):
        super().__init__(f"{field}:{reason}")
        self.field = field
        self.reason = reason


def label(document: Mapping, key: str, *, max_chars: int) -> str:
    raw = document.get(key)
    if not isinstance(raw, str):
        raise RecordError(key, "TEXT_REQUIRED")
    value = normalize("NFKC", raw).strip()
    if not value or len(value) > max_chars:
        raise RecordError(key, "TEXT_LENGTH")
    if not all(ch.isprintable() for ch in value):
        raise RecordError(key, "TEXT_CONTROL")
    return value


def magnitude(document: Mapping, key: str, lower: float, upper: float, *, whole: bool) -> int | float:
    raw = document.get(key)
    if isinstance(raw, bool) or raw is None:
        raise RecordError(key, "NUMBER_REQUIRED")
    try:
        number = float(raw)
    except (ValueError, TypeError, OverflowError) as error:
        raise RecordError(key, "NUMBER_INVALID") from error
    if not isfinite(number):
        raise RecordError(key, "NUMBER_NONFINITE")
    if number < lower or number > upper:
        raise RecordError(key, "NUMBER_RANGE")
    if whole:
        if not number.is_integer():
            raise RecordError(key, "INTEGER_REQUIRED")
        return int(number)
    return number


@dataclass(frozen=True, slots=True)
class ReleaseAssay:
    release: str
    heat: str
    element: str
    result_pct: float
    minute: int
    observed_day: int
    actual_units: int
    signer: str

    @classmethod
    def parse(cls, document: Mapping) -> "ReleaseAssay":
        if not isinstance(document, Mapping):
            raise RecordError("document", "OBJECT_REQUIRED")
        release = label(document, 'release', max_chars=40)
        heat = label(document, 'heat', max_chars=34)
        element = label(document, 'element', max_chars=18)
        result_pct = magnitude(document, 'result_pct', 0, 100, whole=False)
        minute = magnitude(document, 'minute', 0, 1440, whole=True)
        observed_day = magnitude(document, 'observed_day', 1, 366, whole=True)
        actual_units = magnitude(document, 'actual_units', 0, 10000, whole=True)
        signer = label(document, 'signer', max_chars=32)
        return cls(
            release=release,
            heat=heat,
            element=element,
            result_pct=result_pct,
            minute=minute,
            observed_day=observed_day,
            actual_units=actual_units,
            signer=signer,
        )

    def evidence(self) -> dict:
        return {
            'release': self.release,
            'heat': self.heat,
            'element': self.element,
            'result_pct': self.result_pct,
            'minute': self.minute,
            'observed_day': self.observed_day,
            'actual_units': self.actual_units,
            'signer': self.signer,
        }


@dataclass(frozen=True, slots=True)
class Rejection:
    row: int
    source: str
    field: str
    reason: str

    def evidence(self) -> dict:
        return {"row": self.row, "source": self.source, "field": self.field, "reason": self.reason}
