from collections import defaultdict
from dataclasses import dataclass
from math import fsum
from statistics import median

from .analysis import calibrate, eligible, features, residual


@dataclass(frozen=True, slots=True)
class BlindReading:
    grade: str
    element: str
    case: str
    week: int
    truth: float
    estimated: float
    naive: float
    support: int

    def evidence(self):
        return {"牌号":self.grade,"元素":self.element,"归档炉次":self.case,"回放日":self.week,
                "终检":self.truth,"估计终检":round(self.estimated,5),"基线终检":round(self.naive,5),"前缀样本":self.support}


def held_heat_paths(archive, *, first_day, final_day, allowance):
    sequence=defaultdict(list)
    by_identifier=defaultdict(set)
    for sample in archive:
        if sample.closed and sample.heated < final_day and sample.published < final_day:
            by_identifier[sample.archive].add(sample)
    for rows in by_identifier.values():
        if len(rows)==1:
            selected=rows.pop()
            sequence[selected.grade,selected.element].append(selected)
    evidence=[]
    omitted=[]
    for (grade,element), rows in sorted(sequence.items()):
        by_heat=defaultdict(list)
        for r in rows:
            by_heat[r.heated].append(r)
        for day, held in sorted(by_heat.items()):
            if day<first_day:
                continue
            history=eligible(archive,day,grade=grade,element=element)
            if len(history)<7:
                omitted.append({"牌号":grade,"元素":element,"回放日":day,"状态":"训练期炉次过少"})
                continue
            estimator=calibrate(history,penalty=allowance)
            simple=median(row.after-row.before for row in history)
            for row in sorted(held,key=lambda record:record.archive):
                drift,_=residual(estimator,features(row.reclaim,row.mass,row.temp))
                evidence.append(BlindReading(grade,element,row.archive,day,row.after,row.before+drift,row.before+simple,len(history)))
    return evidence,omitted


def control_variance(samples):
    choices=defaultdict(list)
    for run in samples:
        choices[run.grade,run.element].append(run)
    measures=[]
    for (grade,element),rows in sorted(choices.items()):
        errors=[line.truth-line.estimated for line in rows]
        naive=[abs(line.truth-line.naive) for line in rows]
        signed=fsum(errors)/len(rows)
        mae=fsum(abs(x) for x in errors)/len(rows)
        base=fsum(naive)/len(rows)
        absolute=sorted(abs(x) for x in errors)
        detail={"牌号":grade,"元素":element,"回放炉次":len(rows),"平均偏差":round(signed,6),
                "残差平均绝对值":round(mae,6),"基线平均绝对值":round(base,6),"最大误差":round(absolute[-1],6),
                "中位绝对误差":round(median(absolute),6),"模型胜出炉次":sum(abs(x)<y for x,y in zip(errors,naive,strict=True))}
        detail["误差改善比例"]=round((base-mae)/base,4) if base else None
        measures.append(detail)
    return measures
