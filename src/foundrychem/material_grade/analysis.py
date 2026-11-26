from collections import defaultdict
from math import fsum
from .contracts import BatchMaterial


def material_balance(tickets, at_day):
    by_heat=defaultdict(list)
    ignored=[]
    tickets_by_trace=defaultdict(set)
    for item in tickets:
        if item.received <= at_day:
            tickets_by_trace[item.trace].add(item)
    for trace, copies in sorted(tickets_by_trace.items()):
        if len(copies) != 1:
            affected=sorted({copy.heat for copy in copies})
            ignored.extend(dict(trace=trace,heat=heat,reason="料批追踪冲突") for heat in affected)
            continue
        item=copies.pop()
        if not item.valid_from<=at_day<item.valid_to:
            ignored.append(dict(trace=trace,heat=item.heat,reason="材质证书不在有效区间"))
            continue
        by_heat[item.heat].append(item)
    totals=[]
    blocking={row["heat"] for row in ignored}
    for heat, rows in sorted(by_heat.items()):
        grades={row.grade for row in rows}
        if len(grades)>1:
            ignored.append(dict(heat=heat,reason="同炉次料批牌号不一致"))
            continue
        mass=fsum(row.mass_kg for row in rows)
        totals.append(dict(heat=heat,grade=grades.pop(),mass_kg=mass,parts=len(rows),
                           reclaim_ratio=fsum(row.mass_kg*row.reclaim_ratio for row in rows)/mass,
                           melt_temp=fsum(row.mass_kg*row.melt_temp for row in rows)/mass,blocked=heat in blocking))
    return totals,ignored


def witness_set(tickets,heat):
    return sorted({(r.certificate,r.lot,r.feed_type) for r in tickets if r.heat==heat})
