"""按台位证据一致性给每炉裁定唯一的当班复验去向。

队列只以炉次为标识：迟到的旧修订、同台位的复测重试都不会新增记录；
证书状态优先于化验证据，撤销凭证不能靠补做化验恢复。
"""

from collections import defaultdict
from dataclasses import dataclass
from statistics import median

from ..ladle_assays.lab_controls import accepted_work

CERTIFICATE_HOLD = "凭证待查"
STOP_FURNACE = "停炉复检"
CHECK_STATION = "查台位"
CORRECTION_RECHECK = "按纠偏复验"
NORMAL_RELEASE = "正常放行"

DESTINATIONS = (CERTIFICATE_HOLD, STOP_FURNACE, CHECK_STATION, CORRECTION_RECHECK, NORMAL_RELEASE)
RANK = {name: index for index, name in enumerate(DESTINATIONS)}

OUT_OF_SUPPORT = ("历史工况外复验", "验证炉次不足")
CORRECTION_STATES = ("成分下界偏低", "已批准复验", "无需纠偏", "纠偏称量额度不足",
                     "最小称量超过安全余量", "未配置纠偏称", "重复纠偏申请")


@dataclass(frozen=True, slots=True)
class StationCenter:
    lab: str
    center: float


@dataclass(frozen=True, slots=True)
class ElementCase:
    heat: str
    element: str
    state: str = ""
    low: float | None = None
    high: float | None = None
    distance: float | None = None
    lab_state: str | None = None
    centers: tuple = ()
    revision: int = 0


@dataclass(frozen=True, slots=True)
class QueueEntry:
    heat: str
    destination: str
    basis: str
    elements: tuple = ()
    stations: tuple = ()
    distance: float | None = None

    @property
    def needs_review(self) -> bool:
        return self.destination != NORMAL_RELEASE

    def evidence(self) -> dict:
        return {
            "炉次": self.heat,
            "去向": self.destination,
            "依据": self.basis,
            "涉及元素": list(self.elements),
            "台位": list(self.stations),
            "置信距离": None if self.distance is None else round(self.distance, 3),
            "需复验": self.needs_review,
        }


def station_centers(slips, *, day):
    """按当前可见修订汇总每个台位的中位数，复测只并入同一台位而不新增台位。

    ``accepted_work`` 先按化验单号取最高修订；同一台位若有更高修订的补证，
    只保留该台位的最高修订，迟到的旧修订不会拉动中位数或另立记录。
    """
    admitted, _conflicts = accepted_work(slips, day)
    per_station = defaultdict(list)
    for slip in admitted:
        if slip.phase == "炉前":
            per_station[(slip.heat, slip.element, slip.lab)].append(slip)
    centers = defaultdict(list)
    for (heat, element, lab), versions in per_station.items():
        current = max(item.revision for item in versions)
        values = [item.result_pct for item in versions if item.revision == current]
        centers[(heat, element)].append(StationCenter(lab, median(values)))
    return {key: tuple(sorted(values, key=lambda item: item.lab)) for key, values in centers.items()}


def _station_fault(case):
    if case.lab_state == "复测台位不足":
        return f"{case.element} 复测台位不足，补第二台位后复核"
    if case.lab_state == "台内重复性不合格":
        return f"{case.element} 台内重复性不合格，先查该台位"
    if case.lab_state == "复测槽号冲突":
        return f"{case.element} 复测槽号冲突，先隔离冲突台位"
    if case.lab_state == "台间差异超限":
        return f"{case.element} 台间差异超限，先查台位"
    return None


def _position(center, low, high):
    if center < low:
        return "low"
    if center > high:
        return "high"
    return "in"


_POSITION_TEXT = {"low": "低于估算区间", "high": "高于估算区间", "in": "落在估算区间内"}


def _station_consistency(case, positions):
    inside = [item for item, pos in zip(case.centers, positions) if pos == "in"]
    outside = [item for item, pos in zip(case.centers, positions) if pos != "in"]
    if inside and outside:
        matched = "、".join(item.lab for item in inside)
        deviated = "、".join(item.lab for item in outside)
        return (False,
                f"{case.element} 单台偏离：{matched} 与终检估算相符，"
                f"{deviated} 偏离，查台位后继续生产")
    if len(set(positions)) > 1:
        detail = "、".join(f"{item.lab} {_POSITION_TEXT[pos]}"
                          for item, pos in zip(case.centers, positions))
        return False, f"{case.element} 两台方向相反：{detail}，先查台位"
    if positions[0] == "in":
        return True, f"{case.element} 两台一致，落在估算区间内"
    return True, f"{case.element} 两台一致，均{_POSITION_TEXT[positions[0]]}"


def decide_element(case, support_limit):
    """单个元素的证据裁决，返回 (去向, 依据)。

    先看台位证据本身是否可靠：台内重复性、复测槽号冲突、台位不足都会
    先判查台位，避免用不可靠读数去停炉。台位可靠后再看一致性：两台站位
    在估算区间两侧（单台偏离或方向相反）时查台位即可恢复生产；两台一致
    且置信距离明显越出历史支持时才停炉复检。
    """
    fault = _station_fault(case)
    if fault:
        return CHECK_STATION, fault
    if case.low is None or case.high is None:
        return CHECK_STATION, f"{case.element} 缺少可比对的台位证据，先查台位"
    if len(case.centers) < 2:
        return CHECK_STATION, f"{case.element} 仅有单台位，需补第二台位"
    positions = [_position(item.center, case.low, case.high) for item in case.centers]
    agree, detail = _station_consistency(case, positions)
    if not agree:
        return CHECK_STATION, detail
    if case.state in OUT_OF_SUPPORT or (case.distance is not None and case.distance > support_limit):
        if case.distance is None:
            return STOP_FURNACE, f"{case.element} 两台一致但缺少可用支持样本，停炉复检"
        return (STOP_FURNACE,
                f"{case.element} 两台一致，置信距离 {case.distance:.3f} 明显超出历史支持 {support_limit:g}，停炉复检")
    if case.state == "成分上界超差":
        return STOP_FURNACE, f"{detail}；成分上界超差，无法靠加料回调"
    if case.state in CORRECTION_STATES:
        return CORRECTION_RECHECK, f"{detail}；成分下界偏低，按纠偏复验后交割"
    return NORMAL_RELEASE, detail

def _certificate_basis(info):
    if isinstance(info, dict):
        state = info.get("状态") or "凭证未通过"
        code = info.get("证书")
    else:
        state = str(info)
        code = ""
    label = f"{state}（{code}）" if code else state
    return f"{label}；补做化验不能恢复，需补证核验"


def assemble(cases, *, certificates=None, support_limit=7.5, heats=None):
    """把元素证据折成每炉唯一去向；同一炉次只保留一条记录。"""
    certificates = certificates or {}
    retained = {}
    for case in cases:
        key = (case.heat, case.element)
        prior = retained.get(key)
        if prior is None or case.revision > prior.revision:
            retained[key] = case
    grouped = defaultdict(list)
    for case in retained.values():
        grouped[case.heat].append(case)
    if heats is None:
        heats = set(grouped) | set(certificates)
    entries = []
    for heat in sorted(heats):
        if heat in certificates:
            entries.append(QueueEntry(heat, CERTIFICATE_HOLD, _certificate_basis(certificates[heat])))
            continue
        decisions = [(decide_element(case, support_limit), case)
                     for case in sorted(grouped.get(heat, ()), key=lambda item: item.element)]
        if not decisions:
            entries.append(QueueEntry(heat, CHECK_STATION, "缺少可用化验台位，需补验台位"))
            continue
        destination = min(decisions, key=lambda pair: RANK[pair[0][0]])[0][0]
        chosen = [pair for pair in decisions if pair[0][0] == destination]
        elements = tuple(sorted({case.element for _, case in chosen}))
        basis = "；".join(dict.fromkeys(text for (_, text), _ in chosen))
        stations = tuple(sorted({center.lab for _, case in chosen for center in case.centers}))
        distances = [case.distance for _, case in chosen if case.distance is not None]
        entries.append(QueueEntry(heat, destination, basis, elements, stations,
                                  max(distances) if distances else None))
    return tuple(entries)
