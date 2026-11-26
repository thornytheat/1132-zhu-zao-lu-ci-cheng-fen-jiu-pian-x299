from dataclasses import replace

from foundrychem.material_grade.certificates import certificate_book, mass_by_certificate, verify_materials
from foundrychem.material_grade.contracts import BatchMaterial
from foundrychem.pipeline import run


def certificate(code="BZ-03", *, lot="BM-45", grade="HX-1", begin=2, until=20, recorded=3, revision=1, revoked=0):
    return dict(certificate=code,lot=lot,grade=grade,begin=begin,until=until,publication=recorded,
                firm="供应商甲",revision=revision,revoked=revoked)


def material(code="BZ-03", *, lot="BM-45", grade="HX-1", seen=2, mass=15, trace="F-91"):
    return BatchMaterial.parse(dict(trace=trace,heat="熔炉A",feed_type="成分合规来料",lot=lot,certificate=code,mass_kg=mass,
                   grade=grade,melt_temp=1110,reclaim_ratio=.15,received=seen,valid_from=1,valid_to=30))


def test_future_revocation_does_not_change_prior_certificate_snapshot():
    first=certificate()
    withdrawn=certificate(recorded=11,revision=2,revoked=1)
    results,blocked,rejected=certificate_book([withdrawn,first],asof=10)
    assert not rejected and not blocked
    assert results["BZ-03"].revision==1
    next_day, blocked,_=certificate_book([withdrawn,first],asof=11)
    assert not next_day and blocked=={"BZ-03":"状态已撤销"}
    reversed_input=certificate_book([first,withdrawn],asof=11)
    assert reversed_input[1]==blocked


def test_expiry_and_conflicting_certificate_published_versions_stop_use():
    normal=certificate(until=6)
    duplicate=certificate(lot="22",until=6)
    rets,blocked,rejected=certificate_book([normal,duplicate],asof=4)
    assert not rets and not rejected
    assert blocked=={"BZ-03":"证书修订冲突"}
    assert certificate_book([normal],asof=5)[0]
    assert not certificate_book([normal],asof=6)[0]
    assert certificate_book([normal],asof=6)[1]["BZ-03"]=="签发生效时间不符"


def test_material_grades_and_lots_match_signed_trace_and_preserve_mass():
    receipts=[material(mass=16,trace="F-1"),material(lot="缺批次",mass=1.01,trace="F-2"),
              material(grade="伪牌号",mass=24.3,trace="F-3"),material(seen=21,mass=189,trace="F-4")]
    valid,held,rejected=verify_materials(receipts,[certificate(),None],day=10)
    assert [row["称重追踪"] for row in valid]==["F-1"]
    assert [row["称重追踪"] for row in held]==["F-2","F-3"]
    assert all(row["状态"]=="证书批号或牌号不符" for row in held)
    assert rejected==[{"异常凭证行":2,"字段":"document","原因":"DOCUMENT_REQUIRED"}]
    row,=mass_by_certificate(valid,held)
    assert row["已收料公斤"]==41.31
    assert row["过证公斤"]==16
    assert row["挂起公斤"]==25.31
    assert row["已过证比例"]==round(16/41.31,4)


def test_missing_certificate_neither_creates_grade_nor_bypasses_date_interlock():
    line=material(code="无凭证", seen=8, mass=57)
    future=replace(line,trace="队列晚录",received=10)
    first, second, errors=verify_materials([line,future],[],day=9)
    assert not first and not errors
    blocked,=second
    assert blocked["状态"]=="无有效签发凭证"
    assert blocked["质量公斤"]==57
    assert blocked["称重追踪"]=="F-91"


def test_revoked_certificate_holds_entire_heat_and_keeps_evidence():
    report=run(36)
    balance=[row for row in report["stages"][1]["records"] if row.get("炉次")=="HJ-06"]
    assert any(row.get("状态")=="状态已撤销" for row in balance)
    reports=[row for row in balance if "已过证比例" in row]
    assert reports[0]["已过证比例"]==.5
    disposition=[row for row in report["rows"] if row["heat"]=="HJ-06"]
    assert all(row["reason"]=="料批凭证待查" and row["approved_units"]==0 for row in disposition)
