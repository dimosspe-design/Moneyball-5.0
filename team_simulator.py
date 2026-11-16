"""Empirical-residual Monte Carlo for conditional team score scenarios.
Research diagnostic only: no participation or cross-player correlation model.
"""
import argparse,json
import numpy as np,pandas as pd
WEIGHTS={'captain':2,'starter2':1,'starter3':1,'starter4':1,'starter5':1,'sixth':1,'bench1':.5,'bench2':.5,'bench3':.5,'bench4':.5,'coach':1}

def simulate(lineup,backtest,draws=20000,seed=42):
    bt=pd.read_csv(backtest); required={'actual','pred'}
    if not required.issubset(bt):raise ValueError('Backtest missing actual/pred')
    resid=(bt.actual-bt.pred).replace([np.inf,-np.inf],np.nan).dropna().to_numpy()
    if len(resid)<100:raise ValueError('Insufficient empirical backtest residuals')
    if isinstance(lineup,dict):lineup=lineup['lineup']
    rng=np.random.default_rng(seed); total=np.zeros(draws)
    for p in lineup:
        slot=p['slot'];mean=float(p['conditional_projection']);w=WEIGHTS[slot]
        if slot=='coach':
            # No verified coach residual distribution; deterministic conditional estimate.
            total+=w*mean
        else:
            total+=w*np.maximum(-5,mean+rng.choice(resid,size=draws,replace=True))
    return {'mean':round(float(total.mean()),2),'p10':round(float(np.quantile(total,.1)),2),'p50':round(float(np.median(total)),2),'p90':round(float(np.quantile(total,.9)),2),'n_simulations':draws,'n_backtest_residuals':len(resid),'assumptions':['All selected players participate','Residuals sampled independently across players','Coach score held deterministic: no validated coach residuals','Backtest target reconstructed Fantasy points; not audited against official Fantasy scores','No T1/T2 adaptive substitution or captain policy included','Not calibrated team-level upside']}

def main():
    p=argparse.ArgumentParser();p.add_argument('--lineups',required=True);p.add_argument('--backtest',required=True);p.add_argument('--out',required=True);a=p.parse_args()
    with open(a.lineups) as f:lines=json.load(f)
    result={key:simulate(value,a.backtest) for key,value in lines.items() if isinstance(value,dict) and 'lineup' in value}
    with open(a.out,'w') as f:json.dump(result,f,indent=2)
if __name__=='__main__':main()
