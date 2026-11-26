from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from .contracts import ReleaseAssay, RecordError, Rejection
from .analysis import verify_release, proof_signature, check_heats


@dataclass(frozen=True, slots=True)
class Intake:
    records: tuple[ReleaseAssay, ...]
    rejected: tuple[Rejection, ...]
    read_count: int

    @property
    def accepted_count(self) -> int:
        return len(self.records)

    def rejection_counts(self) -> dict[str, int]:
        return dict(sorted(Counter(item.reason for item in self.rejected).items()))

    def evidence(self) -> dict:
        return {
            "read": self.read_count,
            "accepted": self.accepted_count,
            "excluded": len(self.rejected),
            "reason_counts": self.rejection_counts(),
            "rejected": [item.evidence() for item in self.rejected],
        }


def inspect(documents: Iterable[Mapping]) -> Intake:
    accepted: list[ReleaseAssay] = []
    refused: list[Rejection] = []
    read_count = 0
    for read_count, document in enumerate(documents, start=1):
        try:
            entry = ReleaseAssay.parse(document)
        except RecordError as exc:
            raw_key = document.get('release') if isinstance(document, Mapping) else None
            identifier = str(raw_key)[:140] if raw_key is not None else ""
            refused.append(Rejection(read_count, identifier, exc.field, exc.reason))
        else:
            accepted.append(entry)
    return Intake(tuple(accepted), tuple(refused), read_count)


from .shift_summary import status_by_element, handover_totals
