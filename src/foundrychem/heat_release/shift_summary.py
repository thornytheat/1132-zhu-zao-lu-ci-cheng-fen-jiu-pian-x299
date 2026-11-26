from collections import Counter, defaultdict
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Handover:
    heat: str
    required: tuple
    passed: tuple
    unresolved: tuple
    reserved: int
    used: int
    reason: str

    def evidence(self):
        return {"炉次":self.heat,"应验项目":list(self.required),"通过项目":list(self.passed),"待验项目":list(self.unresolved),
                "批准台架单位":self.reserved,"已实用台架单位":self.used,"台架待释放":self.reserved-self.used,"交割结果":self.reason}


def status_by_element(limits, verdict, results):
    by_heat=defaultdict(list)
    outcomes=defaultdict(list)
    assigned=defaultdict(int)
    for decision in verdict:
        heat=decision["heat"]
        by_heat[heat].append(decision)
        assigned[heat]+=decision["approved_units"]
    for receipt in results:
        outcomes[receipt["heat"]].append(receipt)
    handovers=[]
    unknown=[]
    for heat, decisions in sorted(by_heat.items()):
        grades={row["grade"] for row in decisions}
        if len(grades)==1:
            grade=next(iter(grades))
            requirements=sorted(element for known,element in limits if grade==known)
        else:
            requirements=[]
        rows=outcomes.pop(heat,[])
        grouped=defaultdict(list)
        for row in rows:
            grouped[row["element"]].append(row)
        passed=[]
        for element in requirements:
            actual=grouped[element]
            if actual and all(line["state"]=="允许交割" for line in actual):
                passed.append(element)
        pending=tuple(element for element in requirements if element not in passed)
        legitimate=sum(row["actual_units"] for row in rows if row["state"]=="允许交割")
        if legitimate>assigned[heat]:
            raise ValueError("ACTUAL_EXCEEDS_BENCH_RESERVATION")
        if not requirements:
            state="待核产品牌号"
        elif not rows:
            state="待送终检"
        elif pending:
            state="交割挂起"
        else:
            state="可交割"
        handovers.append(Handover(heat,tuple(requirements),tuple(passed),pending,assigned[heat],legitimate,state))
    for heat, rows in sorted(outcomes.items()):
        for report in rows:
            unknown.append({"炉次":heat,"交割单":report["release"],"交割结果":"未能对应纠偏审理"})
    return handovers, unknown


def handover_totals(handover):
    status=Counter(row.reason for row in handover)
    reserved=sum(row.reserved for row in handover)
    consumed=sum(row.used for row in handover)
    if reserved<consumed:
        raise ValueError("SHIFT_BENCH_OVERCOMMIT")
    return {"总炉次":len(handover),"交割通过":status["可交割"],"待终检":status["待送终检"],
            "待查牌号":status["待核产品牌号"],"交割挂起":status["交割挂起"],"台架预留":reserved,
            "台架实用":consumed,"台架待释放":reserved-consumed}
