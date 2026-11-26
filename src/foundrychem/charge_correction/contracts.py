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
class CorrectionBatch:
    heat: str
    element: str
    grade: str
    state: str
    deficit: float
    space: float
    mass_kg: float
    priority: float

    @classmethod
    def parse(cls, document: Mapping) -> "CorrectionBatch":
        if not isinstance(document, Mapping):
            raise RecordError("document", "OBJECT_REQUIRED")
        heat = label(document, 'heat', max_chars=30)
        element = label(document, 'element', max_chars=18)
        grade = label(document, 'grade', max_chars=30)
        state = label(document, 'state', max_chars=34)
        deficit = magnitude(document, 'deficit', 0, 100, whole=False)
        space = magnitude(document, 'space', 0, 100, whole=False)
        mass_kg = magnitude(document, 'mass_kg', 1, 50000, whole=False)
        priority = magnitude(document, 'priority', 0, 1, whole=False)
        return cls(
            heat=heat,
            element=element,
            grade=grade,
            state=state,
            deficit=deficit,
            space=space,
            mass_kg=mass_kg,
            priority=priority,
        )

    def evidence(self) -> dict:
        return {
            'heat': self.heat,
            'element': self.element,
            'grade': self.grade,
            'state': self.state,
            'deficit': self.deficit,
            'space': self.space,
            'mass_kg': self.mass_kg,
            'priority': self.priority,
        }


@dataclass(frozen=True, slots=True)
class Rejection:
    row: int
    source: str
    field: str
    reason: str

    def evidence(self) -> dict:
        return {"row": self.row, "source": self.source, "field": self.field, "reason": self.reason}
