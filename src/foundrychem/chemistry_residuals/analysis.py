from dataclasses import dataclass
from math import fsum,sqrt
from statistics import median
from .contracts import HeatHistory


@dataclass(frozen=True)
class ResidualEstimator:
    centers: tuple
    spreads: tuple
    coefficients: tuple
    offset: float
    examples: int


def features(reclaim,mass,temp):
    return (reclaim,mass,temp)


def eligible(archive, day, *, grade, element):
    indexed={}
    conflicting=set()
    for item in archive:
        if not (item.closed and item.heated<day and item.published<day and item.grade==grade and item.element==element):
            continue
        if item.archive in indexed and indexed[item.archive] != item:
            conflicting.add(item.archive)
        indexed[item.archive]=item
    return sorted((row for key,row in indexed.items() if key not in conflicting),key=lambda r:(r.heated,r.archive))


def robust_deviation(items):
    center=median(items)
    width=median(abs(item-center) for item in items)*1.4826
    return center,max(width,0.00001)


def calibrate(past, penalty=.15):
    if len(past)<7 or penalty<0:
        raise ValueError("HEAT_BASELINE_INSUFFICIENT")
    raw=[features(row.reclaim,row.mass,row.temp) for row in past]
    stats=[robust_deviation(col) for col in zip(*raw,strict=True)]
    data=[tuple(max(-8.0,min(8.0,(x-mu)/sigma)) for x,(mu,sigma) in zip(row,stats,strict=True)) for row in raw]
    residuals=[row.after-row.before for row in past]
    offset=median(residuals)
    weights=[0.0]*len(stats)
    for _ in range(90):
        gradients=[]
        for row, actual in zip(data,residuals,strict=True):
            signed=offset+fsum(a*b for a,b in zip(weights,row,strict=True))-actual
            gradients.append(max(-.06,min(.06,signed)))
        offset-=.06*fsum(gradients)/len(data)
        for i,weight in enumerate(weights):
            direction=fsum(error*row[i] for error,row in zip(gradients,data,strict=True))/len(data)
            weights[i]=weight-.06*(direction+penalty*weight)
    return ResidualEstimator(tuple(mu for mu,_ in stats),tuple(s for _,s in stats),tuple(weights),offset,len(past))


def residual(model, features):
    vector=tuple((x-mu)/sigma for x,mu,sigma in zip(features,model.centers,model.spreads,strict=True))
    estimate=model.offset+fsum(x*w for x,w in zip(vector,model.coefficients,strict=True))
    return estimate,sqrt(fsum(x*x for x in vector))
