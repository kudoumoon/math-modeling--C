from copy import deepcopy
from types import SimpleNamespace
import numpy as np
import pandas as pd
import pytest
import q3_api as q3


@pytest.fixture(scope='module')
def real():
    return q3.load_inputs(),q3.load_upstream()


def toy(days=3):
    dates=pd.date_range('2025-01-01',periods=days)
    x=q3.Inputs(dates,np.full((days,144),600.),np.zeros((days,144)),np.ones(144),np.zeros((days,4,24)))
    u=SimpleNamespace(q0=np.full((days,144),100.),load_forecast_kw=x.load_kw.copy(),
        pv_forecast_kw=x.pv_kw.copy(),soc=np.full((days,145),6000.),
        daily=pd.DataFrame({'planned_initial_energy_kwh':np.full(days,6000.)}))
    return x,u


def assert_physics(f):
    np.testing.assert_allclose(f.qfinal_kwh+f.emergency_kwh+f.pv_actual_kwh+f.discharge_kwh,
                               f.load_actual_kwh+f.charge_kwh+f.unused_supply_kwh,atol=1e-6,rtol=0)
    np.testing.assert_allclose(f.soc_after_kwh,f.soc_before_kwh+.9*f.charge_kwh-f.discharge_kwh/.9,atol=1e-6,rtol=0)
    np.testing.assert_allclose(f.soc_after_kwh.to_numpy()[:-1],f.soc_before_kwh.to_numpy()[1:],atol=1e-6,rtol=0)
    assert f[['soc_before_kwh','soc_after_kwh']].min().min()>=1200-1e-6
    assert f[['soc_before_kwh','soc_after_kwh']].max().max()<=10800+1e-6
    assert f[['charge_kwh','discharge_kwh']].max().max()<=5000/6+1e-6
    assert not ((f.charge_kwh>1e-6)&(f.discharge_kwh>1e-6)).any()
    assert not ((f.charge_kwh>1e-6)&(f.emergency_kwh>1e-6)).any()


def test_no_emergency_charging_counterexample():
    result=q3.solve_adjustment(np.array([0.]),np.array([0.]),np.array([.01]),1200.,np.array([False]))
    np.testing.assert_allclose(result['charge'],0,atol=1e-7)
    np.testing.assert_allclose(result['emergency'],0,atol=1e-7)
    np.testing.assert_allclose(result['soc'],[1200,1200],atol=1e-7)


@pytest.mark.parametrize('settlement',['A','B'])
def test_planner_exclusivity_low_and_zero_prices(settlement):
    q=np.array([0.,1000.,0.,0.])
    net=np.array([100.,-200.,1000.,0.])
    result=q3.solve_adjustment(q,net,np.array([.01,0.,1.,.01]),1200.,np.array([False,True,True,False]),settlement)
    c,d,h=result['charge'],result['discharge'],result['emergency']
    assert not ((c>1e-6)&(d>1e-6)).any()
    assert not ((c>1e-6)&(h>1e-6)).any()
    np.testing.assert_allclose(result['q'][[0,3]],q[[0,3]],atol=1e-7)
    assert (result['r']<=q+1e-7).all()


def test_settlement_hand_calculation():
    # q0 is paid once, excess at 1.5p, decrease at +/-0.5p; emergency at 5p.
    for rule,want in [('A',np.array([22.,15.])),('B',np.array([22.,11.]))]:
        got=q3.settle(np.array([10.,10.]),np.array([14.,6.]),np.ones(2),np.array([1.2,.6]),rule)
        np.testing.assert_allclose(got['total_cost_yuan'],want)


def test_release_future_perturbation_and_anchors(real):
    x,u=real
    for hour,slot in [(6,34),(12,70),(18,106)]:
        before=q3.build_release_forecast(x,u,78,hour)
        dirty=deepcopy(x)
        dirty.load_kw[78,slot+1:]+=1e6
        dirty.pv_kw[78,slot+1:]+=1e6
        dirty.load_kw[79:]+=1e6
        dirty.pv_kw[79:]+=1e6
        dirty.releases_kw[78,hour//6+1:]+=1e6
        after=q3.build_release_forecast(dirty,u,78,hour)
        assert before.anchor_slot==slot and before.cutoff==before.issue_time
        np.testing.assert_array_equal(before.net_kwh,after.net_kwh)
    f=q3.build_release_forecast(x,u,78,0)
    dirty=deepcopy(x)
    dirty.pv_kw[77,143]+=1e6
    np.testing.assert_array_equal(f.pv_kwh,q3.build_release_forecast(dirty,u,78,0).pv_kwh)
    assert f.anchor_slot==142 and f.anchor_day==77


def test_callback_after_bridge_once_and_before_next_completion():
    x,u=toy()
    x.load_kw[0,143]=1200.
    events=[]
    def midnight(day,soc):
        events.append(('plan',day,soc))
        return u.q0[day]
    def complete(day,initial):
        events.append(('complete',day,initial))
    log,_,plans=q3.simulate(x,u,end_day=2,release_hours=(),q0_override=midnight,on_day_complete=complete)
    assert [(a,b) for a,b,_ in events]==[('plan',0),('plan',1),('complete',0),('plan',2),('complete',1),('complete',2)]
    for _,day,initial in [e for e in events if e[0]=='complete']:
        assert initial==pytest.approx(plans.iloc[day].executed_initial_energy_kwh)
    assert_physics(log)


def test_pending_bridge_truth_cannot_change_midnight_contract():
    x,u=toy()
    def replay(inputs):
        observed=[]
        def callback(day,soc):
            observed.append(soc)
            return np.full(144,100.+soc/1e4)
        log,_,plans=q3.simulate(inputs,u,end_day=1,release_hours=(),q0_override=callback)
        return observed,log,plans
    before,_,_=replay(x)
    dirty=deepcopy(x)
    dirty.load_kw[0,143]+=6000
    after,log,plans=replay(dirty)
    assert before==after
    assert plans.iloc[1].executed_initial_energy_kwh!=pytest.approx(plans.iloc[1].planned_initial_energy_kwh)
    assert_physics(log)


def test_real_baseline_matches_upstream_and_natural_bridge(real):
    x,u=real
    f,_,_=q3.simulate(x,u,start_day=31,end_day=32,release_hours=())
    assert len(f)==289
    assert f.iloc[0].day_index==30 and f.iloc[0].time_index==143
    assert_physics(f)
    for day in [31,32]:
        part=f[f.day_index==day]
        np.testing.assert_array_equal(part.q0_kwh,u.q0[day])
        np.testing.assert_allclose(part.soc_after_kwh,u.soc[day,1:],rtol=0,atol=1e-6)


def test_mature_gate_accepts_and_rejects(real):
    x,u=real
    risk,gate,rids,gids=q3.residual_pools(x,u,78,6)
    assert len(gate)>=7 and not set(rids)&set(gids)
    assert max(rids)<78 and max(gids)<78
    f=q3.build_release_forecast(x,u,78,6)
    # Real release and held-out histories, deliberately empty q0 causes deficits.
    q0=np.zeros(len(f.steps)); p=x.price[f.steps]
    candidate=q3.solve_adjustment(q0,f.net_kwh,p,1200.,np.ones(len(q0),bool))
    keep=q3.gate_score(q0,q0,f.net_kwh,p,1200.,gate)
    new=q3.gate_score(q0,candidate['q'],f.net_kwh,p,1200.,gate)
    assert new<keep-1e-6
    excessive=candidate['q']+1e5
    assert q3.gate_score(q0,excessive,f.net_kwh,p,1200.,gate)>keep


def test_verified_upstream_is_provisional(real):
    _,u=real
    assert not u.provenance['formal_use']
    assert u.provenance['source_commit']==q3.SOURCE_COMMIT
    assert u.provenance['manifest_sha256']==q3.MANIFEST_HASH
    assert not u.q0.flags.writeable
