from collections import defaultdict
from statistics import median
from .contracts import AssaySlip


def review_assays(slips, decision_day, max_lab_difference):
    by_id=defaultdict(set)
    for slip in slips:
        if slip.day <= decision_day and slip.arrived <= decision_day and slip.phase == "炉前":
            by_id[slip.assay].add(slip)
    measurements=defaultdict(lambda:defaultdict(list))
    failures=[]
    for assay, readings in sorted(by_id.items()):
        revision=max(row.revision for row in readings)
        current=[row for row in readings if row.revision==revision]
        if len(current)>1:
            failures.append(dict(assay=assay,reason="同修订存在冲突"))
            continue
        row=current[0]
        measurements[(row.heat,row.element)][row.lab].append(row.result_pct)
    selected=[]
    for (heat,element), labs in sorted(measurements.items()):
        values=[median(points) for points in labs.values()]
        spread=max(values)-min(values)
        if len(values)<2 or spread>max_lab_difference:
            failures.append(dict(heat=heat,element=element,reason="化验复测差异",lab_count=len(values),spread=round(spread,5)))
            continue
        selected.append(dict(heat=heat,element=element,pre_pct=median(values),lab_count=len(values),spread=round(spread,5)))
    return selected, failures


def coverage(confirmed, elements):
    present=defaultdict(set)
    for row in confirmed:
        present[row["heat"]].add(row["element"])
    return {heat:sorted(set(elements)-seen) for heat,seen in sorted(present.items())}
