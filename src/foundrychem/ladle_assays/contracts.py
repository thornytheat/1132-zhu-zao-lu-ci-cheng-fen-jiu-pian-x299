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
class AssaySlip:
    assay: str
    heat: str
    element: str
    lab: str
    phase: str
    replicate: int
    result_pct: float
    day: int
    arrived: int
    revision: int

    @classmethod
    def parse(cls, document: Mapping) -> "AssaySlip":
        if not isinstance(document, Mapping):
            raise RecordError("document", "OBJECT_REQUIRED")
        assay = label(document, 'assay', max_chars=38)
        heat = label(document, 'heat', max_chars=36)
        element = label(document, 'element', max_chars=18)
        lab = label(document, 'lab', max_chars=22)
        phase = label(document, 'phase', max_chars=22)
        replicate = magnitude(document, 'replicate', 1, 10, whole=True)
        result_pct = magnitude(document, 'result_pct', 0, 100, whole=False)
        day = magnitude(document, 'day', 1, 366, whole=True)
        arrived = magnitude(document, 'arrived', 1, 366, whole=True)
        revision = magnitude(document, 'revision', 1, 100, whole=True)
        return cls(
            assay=assay,
            heat=heat,
            element=element,
            lab=lab,
            phase=phase,
            replicate=replicate,
            result_pct=result_pct,
            day=day,
            arrived=arrived,
            revision=revision,
        )

    def evidence(self) -> dict:
        return {
            'assay': self.assay,
            'heat': self.heat,
            'element': self.element,
            'lab': self.lab,
            'phase': self.phase,
            'replicate': self.replicate,
            'result_pct': self.result_pct,
            'day': self.day,
            'arrived': self.arrived,
            'revision': self.revision,
        }


@dataclass(frozen=True, slots=True)
class Rejection:
    row: int
    source: str
    field: str
    reason: str

    def evidence(self) -> dict:
        return {"row": self.row, "source": self.source, "field": self.field, "reason": self.reason}
