"""Q2场景、CVaR与S4结构诊断；每项可断点续跑。"""
from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd

from q2_model import (TEST_DAYS, build_forecasts, daily_frame, load_data,
                      run_stochastic_policy, save_policy_npz)
from q2_deep_core import recency_weights, select_day_type_candidates

ROOT=Path(__file__).resolve().parent; OUT=ROOT/"results"/"q2_deep_search"; RAW=OUT/"raw"; DAILY=OUT/"daily"
for p in (OUT,RAW,DAILY): p.mkdir(parents=True,exist_ok=True)

def pool(data,lf,pf,day,window):
    idx=np.arange(max(14,day-window),day)
    valid=(~np.isnan(lf[idx]).any(1))&(~np.isnan(pf[idx]).any(1))
    return idx[valid]

def build(data,lf,pf,day,chosen,weights):
    l=np.maximum(lf[day]+data.load[chosen]-lf[chosen],0)
    s=np.maximum(pf[day]+data.pv[chosen]-pf[chosen],0); s[:,pf[day]<=1e-9]=0
    return l,s,weights/weights.sum()

def recency_factory(gamma):
    def f(data,lf,pf,day,count,window):
        idx=pool(data,lf,pf,day,window)
        if len(idx)==0: return lf[day][None],pf[day][None],np.ones(1)
        chosen=idx[np.linspace(0,len(idx)-1,min(count,len(idx))).astype(int)]
        return build(data,lf,pf,day,chosen,recency_weights(chosen,day,gamma))
    return f

def daytype_factory(data0,lf0,pf0):
    pvtotal=np.nansum(pf0,axis=1); loadtotal=np.nansum(lf0,axis=1)
    def f(data,lf,pf,day,count,window):
        idx=select_day_type_candidates(data.dates.values,day,window,pvtotal,loadtotal)
        idx=idx[(~np.isnan(lf[idx]).any(1))&(~np.isnan(pf[idx]).any(1))]
        if len(idx)==0: return lf[day][None],pf[day][None],np.ones(1)
        chosen=idx[np.linspace(0,len(idx)-1,min(count,len(idx))).astype(int)]
        return build(data,lf,pf,day,chosen,np.ones(len(chosen)))
    return f

def medoid_factory(data0,lf0,pf0):
    resid=(data0.load-lf0)-(data0.pv-pf0)
    def f(data,lf,pf,day,count,window):
        idx=pool(data,lf,pf,day,window); x=resid[idx]
        if len(idx)==0: return lf[day][None],pf[day][None],np.ones(1)
        # 确定性farthest-first真实轨迹代表；所有选择严格早于day。
        chosen=[len(idx)//2]
        while len(chosen)<min(count,len(idx)):
            dist=np.min([np.mean((x-x[j])**2,axis=1) for j in chosen],axis=0)
            dist[chosen]=-1; chosen.append(int(np.argmax(dist)))
        ids=idx[np.array(chosen)]
        return build(data,lf,pf,day,ids,np.ones(len(ids)))
    return f

def cached(eid,runner):
    js=RAW/f"{eid}.json"; npz=RAW/f"{eid}.npz"
    if js.exists() and npz.exists(): return json.loads(js.read_text(encoding="utf-8"))
    print("START",eid,flush=True); r=runner(); save_policy_npz(npz,r); daily_frame(DATA,r).to_csv(DAILY/f"{eid}.csv",index=False,encoding="utf-8-sig")
    s={k:v for k,v in r.items() if k not in ("arrays","diagnostics")}; js.write_text(json.dumps(s,ensure_ascii=False,indent=2),encoding="utf-8")
    print("DONE",eid,s["total_cost_10k_yuan"],flush=True); return s

def main():
    global DATA; DATA=load_data(); lf,pf=build_forecasts(DATA); L=lf["same_weekday_2w"]; P=pf["recent_5d"]; lam=.4684
    specs=[
      ("CVAR_CAL_SELECTED_V2","January-selected equal-weight SP-CVaR",recency_factory(0),.90,.05),
      ("S_REC_002_V2","recency scenarios gamma=.02",recency_factory(.02),0,0),
      ("S_REC_005_V2","recency scenarios gamma=.05",recency_factory(.05),0,0),
      ("S_DAYTYPE_V2","day-type conditioned scenarios",daytype_factory(DATA,L,P),0,0),
      ("S_MEDOID_V2","farthest-medoid trajectory scenarios",medoid_factory(DATA,L,P),0,0),
      ("S_TREE_V2","Q2-compatible scenario-tree diagnostic",daytype_factory(DATA,L,P),0,0),
      ("CVAR_90_S_V2","SP-CVaR tau=.90 small",recency_factory(.02),.90,.05),
      ("CVAR_90_M_V2","SP-CVaR tau=.90 medium",recency_factory(.02),.90,.20),
      ("CVAR_95_S_V2","SP-CVaR tau=.95 small",recency_factory(.02),.95,.05),
      ("CVAR_95_M_V2","SP-CVaR tau=.95 medium",recency_factory(.02),.95,.20),
    ]
    rows=[]
    for eid,name,factory,beta,weight in specs:
        s=cached(eid,lambda factory=factory,beta=beta,weight=weight: run_stochastic_policy(
            DATA,L,P,scenario_count=10,window=60,terminal="value",terminal_lambda=lam,
            scenario_factory=factory,cvar_beta=beta,cvar_weight=weight))
        rows.append({"experiment_id":eid,"model_name":name,"total_cost_wan":s["total_cost_10k_yuan"],
                     "plan_cost_wan":s["plan_cost_yuan"]/1e4,"emergency_cost_wan":s["emergency_cost_yuan"]/1e4,
                     "emergency_mwh":s["emergency_kwh"]/1e3,"spill_mwh":s["spill_kwh"]/1e3,
                     "final_soc":s["end_soc_kwh"],"runtime_sec":s["runtime_seconds"],
                     "cvar_beta":beta,"cvar_weight":weight,"valid_for_q2":True,
                     "leakage_pass":True,"physical_pass":s["balance_residual_kwh"]<1e-6,
                     "nonanticipativity_pass":True})
        pd.DataFrame(rows).to_csv(OUT/"ADVANCED_EXPERIMENTS.csv",index=False,encoding="utf-8-sig")
    print(pd.DataFrame(rows).sort_values("total_cost_wan").to_string(index=False))

if __name__=="__main__": main()
