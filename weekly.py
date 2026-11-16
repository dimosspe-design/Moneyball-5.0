"""Safe weekly research runner. Never silently claims full-market optimization."""
import argparse, pathlib, subprocess, sys, json
from readiness import check
p=argparse.ArgumentParser();p.add_argument('--data',required=True);p.add_argument('--out',required=True);p.add_argument('--market');p.add_argument('--roster');p.add_argument('--budget',type=float,default=103.7);p.add_argument('--trades',type=int,default=4);a=p.parse_args()
out=pathlib.Path(a.out);out.mkdir(parents=True,exist_ok=True)
status=check(a.data,a.market,a.roster)
if not status['ready_for_baseline_retraining']:
    (out/'status.json').write_text(json.dumps(status,indent=2));raise SystemExit('Invalid statistical input')
subprocess.run([sys.executable,str(pathlib.Path(__file__).with_name('model.py')),'--data',a.data,'--out',str(out)],check=True)
status['baseline_retrained']=True
status['full_market_optimizer_run']=False
if a.market and a.roster:
    # Runs only on validated market rows; market completeness is NOT asserted.
    subprocess.run([sys.executable,str(pathlib.Path(__file__).with_name('optimizer_v4.py')),'--market',a.market,'--roster',a.roster,'--budget',str(a.budget),'--trades',str(a.trades),'--out',str(out/'candidate_lineups.json')],check=True)
    status['full_market_optimizer_run']=True
    status['blockers'].append('Candidate lineups are not globally certified without verified full market coverage and coach projection')
(out/'status.json').write_text(json.dumps(status,indent=2,ensure_ascii=False),encoding='utf-8')
print(json.dumps({'baseline_retrained':True,'optimization_run':status['full_market_optimizer_run'],'status_file':str(out/'status.json')}))
