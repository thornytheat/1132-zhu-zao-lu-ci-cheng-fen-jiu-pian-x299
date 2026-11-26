from collections import Counter
from decimal import Decimal, ROUND_CEILING, ROUND_DOWN
from .contracts import CorrectionBatch


def bench_units(row, increments_per_kg, step):
    if increments_per_kg<=0 or step<1:
        raise ValueError("SCALE_STEP_INVALID")
    increment=Decimal(str(increments_per_kg))*Decimal(step)
    goal=Decimal(str(row.deficit))*Decimal(str(row.mass_kg))
    allowed=Decimal(str(row.space))*Decimal(str(row.mass_kg))
    needed=int((goal/increment).to_integral_value(rounding=ROUND_CEILING))*step
    maximum=int((allowed/increment).to_integral_value(rounding=ROUND_DOWN))*step
    return needed, maximum


def correction_plan(records, config, total_allowance):
    if total_allowance<0:
        raise ValueError("NEGATIVE_BATCH_ALLOWANCE")
    used=Counter()
    key_counts=Counter((row.heat,row.element) for row in records)
    spent=0
    ledger=[]
    for row in sorted(records,key=lambda x:(-x.priority,x.heat,x.element)):
        approved=0
        if key_counts[(row.heat,row.element)]>1:
            state="重复纠偏申请"
        elif row.state!="成分下界偏低":
            state=row.state
        elif row.element not in config:
            state="未配置纠偏称"
        else:
            rules=config[row.element]
            required, safe=bench_units(row,rules["gain"],rules["step"])
            if required>safe:
                state="最小称量超过安全余量"
            elif required+spent>total_allowance or required+used[row.element]>rules["limit"]:
                state="纠偏称量额度不足"
            else:
                approved=required
                spent+=approved
                used[row.element]+=approved
                state="已批准复验" if approved else "无需纠偏"
        ledger.append(dict(heat=row.heat,element=row.element,grade=row.grade,approved_units=approved,reason=state))
    return ledger, dict(used)
