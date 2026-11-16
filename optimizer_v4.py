"""Guarded complete-roster MILP: coach, legal formation, captain, team cap.
Does NOT fetch private Fantasy prices or execute transfers.
Expected and upside_proxy are CONDITIONAL player values; coach projection is separate.
"""
import argparse,json
import numpy as np,pandas as pd
from scipy.optimize import milp,Bounds,LinearConstraint
FORMATIONS=[(2,2,1),(1,2,2),(2,1,2),(1,3,1),(3,1,1)]
SLOTS=['captain','starter2','starter3','starter4','starter5','sixth','bench1','bench2','bench3','bench4','coach']
WEIGHTS=np.array([2,1,1,1,1,1,.5,.5,.5,.5,1.])

def optimize(market,roster,budget=103.7,max_trades=4,metric='expected_fantasy_if_play'):
    m=market.reset_index(drop=True).copy();n=len(m);k=len(SLOTS);N=n*k
    orig=set(roster.player.astype(str)); rows=[];low=[];high=[]
    def add(terms,lo,hi):
        row=np.zeros(N)
        for i,j,v in terms:row[i*k+j]+=v
        rows.append(row);low.append(lo);high.append(hi)
    for j in range(k):add([(i,j,1) for i in range(n)],1,1)
    for i in range(n):add([(i,j,1) for j in range(k)],0,1)
    for i in range(n):
        pos=m.loc[i,'position']
        for j in range(k):
            if (j==10)!=(pos=='HC'):add([(i,j,1)],0,0)
    for pos,num in [('G',4),('F',4),('C',2),('HC',1)]:
        add([(i,j,1) for i in range(n) if m.loc[i,'position']==pos for j in range(k)],num,num)
    add([(i,j,float(m.loc[i,'credit'])) for i in range(n) for j in range(k)],0,budget)
    add([(i,j,int(m.loc[i,'player'] not in orig)) for i in range(n) for j in range(k)],0,max_trades)
    for team in m.team.dropna().unique():
        add([(i,j,1) for i in range(n) if m.loc[i,'team']==team and j<10],0,6)
    # legal starting-five formation. Solve once per formation, require captain in the five.
    solutions=[]
    for g,f,c in FORMATIONS:
        rr=list(rows);ll=list(low);hh=list(high)
        for pos,num in [('G',g),('F',f),('C',c)]:
            a=np.zeros(N)
            for i in range(n):
                if m.loc[i,'position']==pos:
                    for j in range(5):a[i*k+j]=1
            rr.append(a);ll.append(num);hh.append(num)
        objective=np.zeros(N)
        for i in range(n):
            for j in range(k):objective[i*k+j]=-float(m.loc[i,metric])*WEIGHTS[j]
        res=milp(objective,integrality=np.ones(N),bounds=Bounds(np.zeros(N),np.ones(N)),constraints=LinearConstraint(np.array(rr),ll,hh),options={'time_limit':25,'mip_rel_gap':0.005})
        if res.x is not None and res.success:
            x=res.x.reshape(n,k);chosen=[]
            for j,slot in enumerate(SLOTS):
                i=int(np.argmax(x[:,j]));chosen.append({'slot':slot,'player':str(m.loc[i,'player']),'position':str(m.loc[i,'position']),'team':str(m.loc[i,'team']),'turn':str(m.loc[i,'turn']),'credit':float(m.loc[i,'credit']),'conditional_projection':float(m.loc[i,metric])})
            solutions.append({'formation':f'{g}-{f}-{c}','conditional_weighted_score':round(-float(res.fun),2),'credits':round(sum(z['credit'] for z in chosen),2),'trades':sum(z['player'] not in orig for z in chosen),'lineup':chosen})
    if not solutions:raise RuntimeError('No feasible legal lineup (or solver did not converge)')
    return max(solutions,key=lambda z:z['conditional_weighted_score'])

def validate(m,r):
    req=['player','team','credit','position','turn','expected_fantasy_if_play','upside_p90_approx','availability','verified_price','verified_matchup']
    missing=set(req)-set(m)
    if missing:raise ValueError(f'Missing market columns: {sorted(missing)}')
    if len(m)<11 or m.player.isna().any() or m.player.duplicated().any():raise ValueError('Invalid market player identities')
    if len(r)!=11 or r.player.duplicated().any() or not set(r.player).issubset(set(m.player)):raise ValueError('Roster must contain 11 distinct market entries, including coach')
    if m.position.isin(['G','F','C','HC']).all() is False:raise ValueError('Invalid position')
    if (m.position=='HC').sum()<1:raise ValueError('Missing coach market')
    if m[['credit','expected_fantasy_if_play','upside_p90_approx']].isna().any().any() or (m.credit<=0).any():raise ValueError('Missing numeric inputs')
    for field in ['verified_price','verified_matchup']:
        if not m[field].astype(str).str.lower().isin(['true','1','yes']).all():raise ValueError('Unverified '+field)
    if not m.availability.isin(['confirmed','uncertain']).all():raise ValueError('Invalid availability status')
    if not m.turn.isin(['T1','T2','T3','T4']).all():raise ValueError('Unknown turn')
    if not m.team.astype(str).str.len().gt(0).all():raise ValueError('Missing team')

def main():
    p=argparse.ArgumentParser();p.add_argument('--market',required=True);p.add_argument('--roster',required=True);p.add_argument('--out',required=True);p.add_argument('--budget',type=float,default=103.7);p.add_argument('--trades',type=int,default=4);p.add_argument('--complete-market-confirmed',action='store_true');a=p.parse_args()
    m=pd.read_csv(a.market);r=pd.read_csv(a.roster);validate(m,r)
    results={metric:optimize(m,r,a.budget,a.trades,metric) for metric in ['expected_fantasy_if_play','upside_p90_approx']}
    results['market_complete_verified_by_user']=bool(a.complete_market_confirmed)
    results['caveats']=['Not a calibrated team upside percentile','Projections conditional on participation; availability uncertain is not a probability','T1/T2 substitutions require live round scores and separate decisions','Only global market optimal if full current eligible market is independently verified','No trades executed']
    with open(a.out,'w') as f:json.dump(results,f,indent=2,ensure_ascii=False)
    print(json.dumps({'status':'ok','output':a.out,'market_complete':a.complete_market_confirmed}))
if __name__=='__main__':main()
