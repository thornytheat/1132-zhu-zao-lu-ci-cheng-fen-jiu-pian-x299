from hashlib import sha256
from pathlib import Path
from json import loads

from .ladle_assays import service as assays
from .material_grade import service as materials
from .chemistry_residuals import service as prediction
from .alloy_tolerance import service as limits
from .charge_correction import service as dosing
from .heat_release import service as finishing

ROOT=Path(__file__).resolve().parents[2]


def read_assay_file(stem):
    data=(ROOT/"sample_data"/stem).read_bytes()
    rows=[]
    for entry in data.splitlines():
        try:
            rows.append(loads(entry))
        except ValueError:
            rows.append(None)
    return rows,sha256(data).hexdigest()


def workstep(title,summary,records):
    return {"title":title,"summary":summary,"records":records}


def calibrations(archive, settings):
    estimates={}
    for grade, elements in settings["grade_bounds"].items():
        for element in elements:
            archive_rows=prediction.eligible(archive,settings["day"],grade=grade,element=element)
            retained=prediction.eligible(archive,settings["holdout_mark"],grade=grade,element=element)
            validated=[row for row in archive_rows if row.published >= settings["holdout_mark"]]
            baselines=prediction.calibrate(retained,penalty=settings["ridge"])
            replay=[]
            for entry in validated:
                expected,_=prediction.residual(baselines,prediction.features(entry.reclaim,entry.mass,entry.temp))
                replay.append((entry.after,entry.before+expected))
            estimates[(grade,element)]=(baselines,limits.empirical_errors(replay))
    return estimates


def run(capacity: int | None = None) -> dict:
    config=loads((ROOT/"configs"/"release_shift.json").read_text(encoding="utf-8"))
    total_allowance=config["capacity"] if capacity is None else capacity
    if not 1<=total_allowance<=100:
        raise ValueError("CORRECTION_LIMIT_RANGE")
    batches=[read_assay_file(name) for name in ("front_laboratory.ndjson","charge_material_trace.ndjson","archived_final_assays.ndjson","release_tickets.ndjson","independent_certificates.ndjson")]
    input_assays, input_material, archive, input_release=[service.inspect(data[0]) for service,data in zip((assays,materials,prediction,finishing),batches[:4],strict=True)]
    measurements,bad_lab=assays.review_assays(input_assays.records,config["day"],config["assay_spread"])
    lab_reviews=assays.examine_lab_groups(input_assays.records,day=config["day"],
                                          repeat_limit=config["repeat_limit"],interlab_limit=config["assay_spread"])
    lab_stops=assays.risky_pairs(lab_reviews)
    material_index,bad_material=materials.material_balance(input_material.records,config["day"])
    unique_tickets={record.trace:record for record in input_material.records}
    approved_certificates,certificate_alerts,certificate_errors=materials.verify_materials(unique_tickets.values(),batches[4][0],day=config["day"])
    cert_totals=materials.mass_by_certificate(approved_certificates,certificate_alerts)
    missing_certificates={record["炉次"] for record in certificate_alerts}
    by_heat={row["heat"]:dict(row,blocked=row["blocked"] or row["heat"] in missing_certificates) for row in material_index}
    estimates=calibrations(archive.records,config)
    expected={key:tuple(bounds) for grade, elements in config["grade_bounds"].items() for element,bounds in elements.items() for key in [(grade,element)]}
    work=[]
    lookup={}
    saved_trials, skipped_trials=prediction.held_heat_paths(archive.records,first_day=config["day"]-config["replay_days"],
                                                           final_day=config["day"],allowance=config["ridge"])
    prior_check=prediction.control_variance(saved_trials)
    fit_records=[]
    tolerance_records=[]
    requirements=next(iter(config["grade_bounds"].values())).keys()
    missing=assays.coverage(measurements,requirements)
    for sample in measurements:
        heat, element=sample["heat"],sample["element"]
        material=by_heat.get(heat)
        if material is None or material["blocked"]:
            continue
        grade=material["grade"]
        fit, errors=estimates[grade,element]
        drift,distance=prediction.residual(fit,prediction.features(material["reclaim_ratio"],material["mass_kg"],material["melt_temp"]))
        value=max(0.0,sample["pre_pct"]+drift)
        lower,upper=expected[grade,element]
        element_spec=limits.ElementLimit.parse(dict(element=element,grade=grade,low=lower,high=upper,predicted=value,
                                 shift=sample["spread"]/2,distance=distance,minimum_validation=config["required_support"]))
        decision=limits.check_band(element_spec,errors,support_distance=config["distance_limit"])
        state=lab_stops.get((heat,element)) or ("关联成分化验不完整" if missing.get(heat) else decision["state"])
        lookup[heat,element]=dict(pre_pct=round(sample["pre_pct"],5), predicted=round(value,5), low=decision["low"],high=decision["high"])
        work.append(dict(heat=heat,element=element,grade=grade,state=state,deficit=decision["deficit"],space=decision["space"],
                         mass_kg=material["mass_kg"],priority=decision["risk"]))
        fit_records.append(dict(炉次=heat,元素=element,模型样本=fit.examples,终检估算=round(value,4),置信距离=round(distance,3),历史偏移=round(drift,4)))
        tolerance_records.append(dict(炉次=heat,支持样本=errors.support,**decision))
    formal=dosing.inspect(work)
    verdict, used=dosing.correction_plan(formal.records,config["scale"],total_allowance)
    planned={(row["heat"],row["element"]) for row in verdict}
    for sample in sorted({(line.heat,line.element) for line in input_assays.records if line.day <= config["day"] and line.arrived <= config["day"]} - planned):
        heat,element=sample
        material=by_heat.get(heat)
        reason="料批凭证待查" if material is None or material["blocked"] else lab_stops.get(sample,"化验复测不一致")
        verdict.append(dict(heat=heat,element=element,grade="—" if material is None else material["grade"],approved_units=0,reason=reason))
    final=finishing.verify_release(input_release.records,verdict,expected,config["day"])
    handover, unlinked=finishing.status_by_element(expected,verdict,final)
    readiness=finishing.handover_totals(handover)
    rows=[dict(line,**lookup.get((line["heat"],line["element"]),{})) for line in sorted(verdict,key=lambda row:(row["heat"],row["element"]))]
    return {"metrics":{"可交割炉次":readiness["交割通过"],"复验预留单位":sum(used.values()),"待交割炉次":readiness["总炉次"]-readiness["交割通过"],"有效化验组":len(measurements)},
            "columns":{"heat":"炉次","grade":"牌号","element":"合金元素","pre_pct":"炉前测值（%）","predicted":"估计终检（%）","low":"区间下界","high":"区间上界","approved_units":"预留台架单位","reason":"处置"},
            "rows":rows,"series":[dict(label=line["heat"]+"/"+line["element"],value=line["predicted"]) for line in rows if "predicted" in line][:16],
            "stages":[workstep("化验记录",f"{len(measurements)} 组双化验可用，排除 {len(bad_lab)+len(input_assays.rejected)} 条",measurements+bad_lab+[record.evidence() for record in lab_reviews]),
                      workstep("料批追踪",f"确认 {len(material_index)} 炉称重单",list(by_heat.values())+bad_material+approved_certificates+certificate_alerts+certificate_errors+cert_totals),
                      workstep("残差识别",f"独立拟合 {len(estimates)} 个牌号元素组合",fit_records+prior_check+skipped_trials),
                      workstep("风险分级",f"复核 {len(tolerance_records)} 条置信范围",tolerance_records),
                      workstep("称料纠偏",f"台架预留 {sum(used.values())}，当班额度 {total_allowance}",rows),
                      workstep("炉前交割",f"全部成分通过 {readiness['交割通过']} 炉",final+[item.evidence() for item in handover]+unlinked)],
            "readiness":readiness,"archive_replay":[item.evidence() for item in saved_trials],
            "audit_id":finishing.proof_signature({**config,"selected_cap":total_allowance},[part[1] for part in batches],final)}
