from collections import defaultdict
from dataclasses import dataclass
from math import fsum

from .contracts import RecordError, label, magnitude


@dataclass(frozen=True, slots=True)
class Certificate:
    code: str
    lot: str
    grade: str
    firm: str
    begin: int
    until: int
    publication: int
    revision: int
    revoked: int

    @classmethod
    def parse(cls, record):
        if not isinstance(record,dict):
            raise RecordError("document","DOCUMENT_REQUIRED")
        return cls(
            label(record,"certificate",max_chars=48), label(record,"lot",max_chars=36),
            label(record,"grade",max_chars=40), label(record,"firm",max_chars=24),
            magnitude(record,"begin",1,366,whole=True),magnitude(record,"until",2,367,whole=True),
            magnitude(record,"publication",1,366,whole=True),magnitude(record,"revision",1,20,whole=True),
            magnitude(record,"revoked",0,1,whole=True),
        )


def certificate_book(entries, *, asof):
    revisions=defaultdict(set)
    dropped=[]
    for order, item in enumerate(entries,start=1):
        try:
            row=Certificate.parse(item)
        except RecordError as error:
            dropped.append({"异常凭证行":order,"字段":error.field,"原因":error.reason})
            continue
        if row.publication<=asof:
            revisions[row.code].add(row)
    available={}
    withheld={}
    for reference, versions in sorted(revisions.items()):
        newest=max(item.revision for item in versions)
        candidates=[row for row in versions if row.revision==newest]
        if len(candidates)>1:
            withheld[reference]="证书修订冲突"
            continue
        leaf=candidates[0]
        if leaf.revoked:
            withheld[reference]="状态已撤销"
        elif not leaf.begin<=asof<leaf.until:
            withheld[reference]="签发生效时间不符"
        else:
            available[reference]=leaf
    return available,withheld,dropped


def verify_materials(records, documents, *, day):
    available,blocked,dropped=certificate_book(documents,asof=day)
    signed=[]
    unverified=[]
    for row in sorted(records,key=lambda row:(row.heat,row.trace)):
        if row.received > day:
            continue
        certificate=available.get(row.certificate)
        if certificate is None or certificate.lot!=row.lot or certificate.grade!=row.grade:
            state=blocked.get(row.certificate,"无有效签发凭证" if certificate is None else "证书批号或牌号不符")
            unverified.append({"炉次":row.heat,"料批":row.lot,"证书":row.certificate,"状态":state,"质量公斤":row.mass_kg,"称重追踪":row.trace})
        else:
            signed.append({"炉次":row.heat,"料批":row.lot,"证书":row.certificate,"供应方":certificate.firm,
                           "证书版":certificate.revision,"质量公斤":row.mass_kg,"状态":"凭证核验通过","称重追踪":row.trace})
    return signed, unverified, dropped


def mass_by_certificate(verified, blocked):
    by_heat=defaultdict(lambda: {"通过":[],"挂起":[]})
    for rows,field in ((verified,"通过"),(blocked,"挂起")):
        for item in rows:
            by_heat[item["炉次"]][field].append(item["质量公斤"])
    report=[]
    for heat,staged in sorted(by_heat.items()):
        received=fsum((*staged["通过"],*staged["挂起"]))
        verified_mass=fsum(staged["通过"])
        report.append({"炉次":heat,"已收料公斤":round(received,3),"过证公斤":round(verified_mass,3),
                       "挂起公斤":round(fsum(staged["挂起"]),3),"已过证比例":round(verified_mass/received,4) if received else None})
    return report
