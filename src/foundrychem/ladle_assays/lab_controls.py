from collections import defaultdict
from dataclasses import dataclass
from math import fsum, sqrt
from statistics import median


@dataclass(frozen=True, slots=True)
class Register:
    heat: str
    element: str
    effective_labs: int
    shots: int
    laboratory_span: float | None
    repeat_error: float | None
    discarded_shots: int
    state: str

    def evidence(self):
        return {
            "炉次":self.heat,"元素":self.element,"有效台位":self.effective_labs,"有效复测":self.shots,
            "跨台极差":round(self.laboratory_span,5) if self.laboratory_span is not None else None,
            "台内合成偏差":round(self.repeat_error,5) if self.repeat_error is not None else None,
            "丢弃复测":self.discarded_shots,"量具状态":self.state,
        }


def accepted_work(readings, due):
    seen=defaultdict(set)
    for entry in readings:
        if entry.phase=="炉前" and entry.day<=due and entry.arrived<=due:
            seen[entry.assay].add(entry)
    accepted=[]
    known=defaultdict(int)
    for versions in seen.values():
        active=max(line.revision for line in versions)
        current=[line for line in versions if line.revision==active]
        if len(current)==1:
            accepted.append(current[0])
        else:
            for key in {(row.heat,row.element) for row in current}:
                known[key]+=len(current)
    return accepted,known


def pooled_repeatability(samples):
    deviations=[]
    degrees=0
    for group in samples:
        count=len(group)
        if count<2:
            continue
        mean=fsum(group)/count
        error=fsum((m-mean)**2 for m in group)
        deviations.append(error)
        degrees+=count-1
    return sqrt(fsum(deviations)/degrees) if degrees else None


def examine_lab_groups(readings, *, day, repeat_limit, interlab_limit):
    if min(repeat_limit,interlab_limit)<0:
        raise ValueError("LAB_LIMIT_NEGATIVE")
    admitted, known_errors=accepted_work(readings,day)
    slots=defaultdict(set)
    for item in admitted:
        slots[item.heat,item.element,item.lab,item.replicate].add(item.result_pct)
    observed=defaultdict(lambda:defaultdict(list))
    for (heat, element, lab, replicate),same_sample in sorted(slots.items()):
        if len(same_sample)>1:
            known_errors[heat,element]+=len(same_sample)
            continue
        observed[heat,element][lab].append(same_sample.pop())
    diagnoses=[]
    for heat,element in sorted(observed.keys() | known_errors.keys()):
        laboratory=observed[heat, element]
        repetitions=list(laboratory.values())
        centers=[median(run) for run in repetitions]
        spread=max(centers)-min(centers) if len(centers)>=2 else None
        pooled=pooled_repeatability(repetitions)
        disagreements=known_errors[heat,element]
        if disagreements:
            status="复测槽号冲突"
        elif spread is None:
            status="复测台位不足"
        elif spread>interlab_limit:
            status="台间差异超限"
        elif pooled is not None and pooled>repeat_limit:
            status="台内重复性不合格"
        elif pooled is None:
            status="仅有跨台对照"
        else:
            status="量具复验通过"
        diagnoses.append(Register(heat,element,len(centers),sum(map(len,repetitions)),spread,pooled,disagreements,status))
    return diagnoses


def risky_pairs(diagnoses):
    blocking={"复测槽号冲突","复测台位不足","台间差异超限","台内重复性不合格"}
    return {(line.heat,line.element):line.state for line in diagnoses if line.state in blocking}
