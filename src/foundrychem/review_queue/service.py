"""由管道证据构建当班复验队列。

只读输入：当前可见的炉前化验、量具复核、风险分级区间和料批凭证状态。
输出以炉次为唯一键，迟到的旧修订和同台位重试都在进入队列前折叠。
"""

from collections import defaultdict

from .analysis import (
    CHECK_STATION,
    CORRECTION_RECHECK,
    CERTIFICATE_HOLD,
    NORMAL_RELEASE,
    STOP_FURNACE,
    ElementCase,
    assemble,
    station_centers,
)


def visible_revisions(slips, *, day, phase="炉前"):
    """每个炉次元素当前可见的最高修订，旧修订不会另立队列记录。"""
    latest = defaultdict(int)
    for slip in slips:
        if slip.phase == phase and slip.day <= day and slip.arrived <= day:
            key = (slip.heat, slip.element)
            latest[key] = max(latest[key], slip.revision)
    return latest


def certificate_holds(alerts, blocked):
    """汇总凭证层面的挂起，返回 {炉次: {状态, 证书}}。

    撤销与生效区间不符都进入此表；同一炉次只保留一条，补证后的当前修订
    若已恢复可见，则不再出现在这里。
    """
    holds = {}
    for row in alerts:
        heat = row.get("炉次")
        if heat:
            holds.setdefault(heat, {"状态": row.get("状态") or "凭证未通过", "证书": row.get("证书") or ""})
    for row in blocked:
        heat = row.get("heat")
        if heat:
            holds.setdefault(heat, {"状态": row.get("reason") or "凭证待查", "证书": ""})
    return holds


def build_cases(*, measurements, tolerance, lab_reviews, slips, day, missing=None):
    """合并化验、量具和风险分级证据，返回逐炉次元素的裁决输入。

    ``missing`` 给出该炉次缺少可用化验的元素，这些元素没有台位证据，
    会作为「缺少可比对台位」的查台位条目进入队列，而不是无声放行。
    """
    revisions = visible_revisions(slips, day=day)
    centers = station_centers(slips, day=day)
    lab_state = {(row.heat, row.element): row.state for row in lab_reviews}
    keys = {(row["heat"], row["element"]) for row in measurements} | set(lab_state)
    for heat, elements in (missing or {}).items():
        keys |= {(heat, element) for element in elements}
    cases = []
    for heat, element in sorted(keys):
        decision = tolerance.get((heat, element), {})
        cases.append(ElementCase(
            heat=heat,
            element=element,
            state=decision.get("state", ""),
            low=decision.get("low"),
            high=decision.get("high"),
            distance=decision.get("distance"),
            lab_state=lab_state.get((heat, element)),
            centers=centers.get((heat, element), ()),
            revision=revisions.get((heat, element), 0),
        ))
    return cases


def shift_queue(*, measurements, tolerance, lab_reviews, slips, day, heats, certificates=None,
                support_limit=7.5, missing=None):
    """生成当班复验队列：每炉恰好一条去向。"""
    cases = build_cases(measurements=measurements, tolerance=tolerance, lab_reviews=lab_reviews,
                        slips=slips, day=day, missing=missing)
    return assemble(cases, certificates=certificates, support_limit=support_limit, heats=heats)


def queue_evidence(entries):
    return [entry.evidence() for entry in entries]


def queue_totals(entries):
    counts = defaultdict(int)
    for entry in entries:
        counts[entry.destination] += 1
    return {
        "复验炉次": len(entries),
        "需复验炉次": sum(entry.needs_review for entry in entries),
        "查台位炉次": counts.get(CHECK_STATION, 0),
        "停炉复检炉次": counts.get(STOP_FURNACE, 0),
        "凭证待查炉次": counts.get(CERTIFICATE_HOLD, 0),
        "按纠偏复验炉次": counts.get(CORRECTION_RECHECK, 0),
        "正常放行炉次": counts.get(NORMAL_RELEASE, 0),
    }
