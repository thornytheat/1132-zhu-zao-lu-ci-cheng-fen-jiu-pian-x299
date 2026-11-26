from collections import defaultdict
from hashlib import sha256
from json import dumps
from .contracts import ReleaseAssay


def verify_release(readings, authorizations, limits, visible_day):
    planned={(row["heat"],row["element"]):row for row in authorizations}
    repeats=defaultdict(set)
    for row in readings:
        if row.observed_day<=visible_day:
            repeats[row.release].add(row)
    records=[]
    claimed=defaultdict(int)
    for key, variants in sorted(repeats.items()):
        if len(variants)>1:
            records.append(dict(release=key,heat="—",element="—",state="交割记录冲突"))
            continue
        row=variants.pop()
        match=(row.heat,row.element)
        item=planned.get(match)
        band=limits.get((item["grade"],row.element)) if item else None
        if not item or not band:
            state="未找到质控授权"
        elif not band[0] <= row.result_pct <= band[1]:
            state="终检仍超差"
        elif row.actual_units+claimed[match] > item["approved_units"]:
            state="称重超出授权"
        elif item["reason"] not in ("已批准复验","合格区间"):
            state="需质检员解除挂起"
        else:
            state="允许交割"
            claimed[match]+=row.actual_units
        records.append(dict(release=row.release,heat=row.heat,element=row.element,state=state,
                            result_pct=row.result_pct,operator=row.signer,actual_units=row.actual_units))
    return records


def proof_signature(config,sources,decisions):
    stamp={"edition":"heat-release-v1","control":config,"documents":sources,"resolution":decisions}
    return sha256(dumps(stamp,ensure_ascii=False,sort_keys=True,separators=(",",":"),allow_nan=False).encode()).hexdigest()


def check_heats(rows,required):
    grouped=defaultdict(dict)
    for row in rows:
        heat=row["heat"]
        element=row["element"]
        existing=grouped[heat].get(element,True)
        grouped[heat][element]=existing and row["state"]=="允许交割"
    return {heat:all(states.get(e,False) for e in required) for heat,states in sorted(grouped.items()) if heat!="—"}
