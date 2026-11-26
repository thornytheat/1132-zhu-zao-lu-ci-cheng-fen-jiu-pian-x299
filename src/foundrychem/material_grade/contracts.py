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
class BatchMaterial:
    trace: str
    heat: str
    feed_type: str
    lot: str
    certificate: str
    mass_kg: float
    grade: str
    melt_temp: float
    reclaim_ratio: float
    received: int
    valid_from: int
    valid_to: int

    @classmethod
    def parse(cls, document: Mapping) -> "BatchMaterial":
        if not isinstance(document, Mapping):
            raise RecordError("document", "OBJECT_REQUIRED")
        trace = label(document, 'trace', max_chars=40)
        heat = label(document, 'heat', max_chars=28)
        feed_type = label(document, 'feed_type', max_chars=28)
        lot = label(document, 'lot', max_chars=32)
        certificate = label(document, 'certificate', max_chars=33)
        mass_kg = magnitude(document, 'mass_kg', 1, 50000, whole=False)
        grade = label(document, 'grade', max_chars=20)
        melt_temp = magnitude(document, 'melt_temp', 500, 2000, whole=False)
        reclaim_ratio = magnitude(document, 'reclaim_ratio', 0, 1, whole=False)
        received = magnitude(document, 'received', 1, 366, whole=True)
        valid_from = magnitude(document, 'valid_from', 1, 366, whole=True)
        valid_to = magnitude(document, 'valid_to', 2, 367, whole=True)
        return cls(
            trace=trace,
            heat=heat,
            feed_type=feed_type,
            lot=lot,
            certificate=certificate,
            mass_kg=mass_kg,
            grade=grade,
            melt_temp=melt_temp,
            reclaim_ratio=reclaim_ratio,
            received=received,
            valid_from=valid_from,
            valid_to=valid_to,
        )

    def evidence(self) -> dict:
        return {
            'trace': self.trace,
            'heat': self.heat,
            'feed_type': self.feed_type,
            'lot': self.lot,
            'certificate': self.certificate,
            'mass_kg': self.mass_kg,
            'grade': self.grade,
            'melt_temp': self.melt_temp,
            'reclaim_ratio': self.reclaim_ratio,
            'received': self.received,
            'valid_from': self.valid_from,
            'valid_to': self.valid_to,
        }


@dataclass(frozen=True, slots=True)
class Rejection:
    row: int
    source: str
    field: str
    reason: str

    def evidence(self) -> dict:
        return {"row": self.row, "source": self.source, "field": self.field, "reason": self.reason}
