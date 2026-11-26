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
class HeatHistory:
    archive: str
    grade: str
    element: str
    heated: int
    published: int
    closed: int
    reclaim: float
    mass: float
    temp: float
    before: float
    after: float

    @classmethod
    def parse(cls, document: Mapping) -> "HeatHistory":
        if not isinstance(document, Mapping):
            raise RecordError("document", "OBJECT_REQUIRED")
        archive = label(document, 'archive', max_chars=40)
        grade = label(document, 'grade', max_chars=30)
        element = label(document, 'element', max_chars=18)
        heated = magnitude(document, 'heated', 1, 366, whole=True)
        published = magnitude(document, 'published', 1, 366, whole=True)
        closed = magnitude(document, 'closed', 0, 1, whole=True)
        reclaim = magnitude(document, 'reclaim', 0, 1, whole=False)
        mass = magnitude(document, 'mass', 1, 50000, whole=False)
        temp = magnitude(document, 'temp', 500, 2000, whole=False)
        before = magnitude(document, 'before', 0, 100, whole=False)
        after = magnitude(document, 'after', 0, 100, whole=False)
        return cls(
            archive=archive,
            grade=grade,
            element=element,
            heated=heated,
            published=published,
            closed=closed,
            reclaim=reclaim,
            mass=mass,
            temp=temp,
            before=before,
            after=after,
        )

    def evidence(self) -> dict:
        return {
            'archive': self.archive,
            'grade': self.grade,
            'element': self.element,
            'heated': self.heated,
            'published': self.published,
            'closed': self.closed,
            'reclaim': self.reclaim,
            'mass': self.mass,
            'temp': self.temp,
            'before': self.before,
            'after': self.after,
        }


@dataclass(frozen=True, slots=True)
class Rejection:
    row: int
    source: str
    field: str
    reason: str

    def evidence(self) -> dict:
        return {"row": self.row, "source": self.source, "field": self.field, "reason": self.reason}
