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
class ElementLimit:
    element: str
    grade: str
    low: float
    high: float
    predicted: float
    shift: float
    distance: float
    minimum_validation: int

    @classmethod
    def parse(cls, document: Mapping) -> "ElementLimit":
        if not isinstance(document, Mapping):
            raise RecordError("document", "OBJECT_REQUIRED")
        element = label(document, 'element', max_chars=20)
        grade = label(document, 'grade', max_chars=32)
        low = magnitude(document, 'low', 0, 100, whole=False)
        high = magnitude(document, 'high', 0, 100, whole=False)
        predicted = magnitude(document, 'predicted', 0, 100, whole=False)
        shift = magnitude(document, 'shift', 0, 100, whole=False)
        distance = magnitude(document, 'distance', 0, 30000000, whole=False)
        minimum_validation = magnitude(document, 'minimum_validation', 1, 60, whole=True)
        return cls(
            element=element,
            grade=grade,
            low=low,
            high=high,
            predicted=predicted,
            shift=shift,
            distance=distance,
            minimum_validation=minimum_validation,
        )

    def evidence(self) -> dict:
        return {
            'element': self.element,
            'grade': self.grade,
            'low': self.low,
            'high': self.high,
            'predicted': self.predicted,
            'shift': self.shift,
            'distance': self.distance,
            'minimum_validation': self.minimum_validation,
        }


@dataclass(frozen=True, slots=True)
class Rejection:
    row: int
    source: str
    field: str
    reason: str

    def evidence(self) -> dict:
        return {"row": self.row, "source": self.source, "field": self.field, "reason": self.reason}
