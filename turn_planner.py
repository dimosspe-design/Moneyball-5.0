"""Between-turn decision aid. Not a substitute for live legal lineup validation.
Scores for finished players are observed FPT, not PIR. For each proposed
bench-to-field swap, gain = (unplayed conditional projection - finished FPT)/2.
Does not assume an unplayed player's availability is certain.
"""
import argparse,json,pandas as pd

def suggest(df):
    need=['player','turn','slot','observed_fpt','expected_fantasy_if_play','availability']
    if any(c not in df for c in need):raise ValueError('Required columns: '+', '.join(need))
    done=df[(df.turn=='T1') & df.observed_fpt.notna() & df.slot.isin(['starter','captain','sixth'])]
    future=df[(df.turn!='T1') & df.observed_fpt.isna() & (df.slot=='bench')]
    swaps=[]
    for _,a in done.iterrows():
        for _,b in future.iterrows():
            gain=(float(b.expected_fantasy_if_play)-float(a.observed_fpt))/2
            if gain>0:swaps.append({'bench_out':a.player,'field_in':b.player,'estimated_conditional_gain':round(gain,2),'availability':b.availability,'requires_formation_check':True})
    return sorted(swaps,key=lambda z:z['estimated_conditional_gain'],reverse=True)

def main():
    p=argparse.ArgumentParser();p.add_argument('--turn-state',required=True);p.add_argument('--out',required=True);a=p.parse_args()
    data=pd.read_csv(a.turn_state);result={'candidate_swaps':suggest(data),'caveat':'Alternatives overlap; do not apply all simultaneously. Check legal formation, captain and live scores before acting. No transfer executed.'}
    with open(a.out,'w') as f:json.dump(result,f,indent=2)
if __name__=='__main__':main()
