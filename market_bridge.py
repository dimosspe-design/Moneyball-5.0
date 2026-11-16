"""Validate Fantasy market CSV and emit v3 optimizer-ready CSV; no web login or transfers."""
import argparse, csv, json
from pathlib import Path
REQUIRED={'player','credit','position','turn','expected_fantasy_if_play','upside_p90_approx','availability','verified_price','verified_matchup'}
def main():
 p=argparse.ArgumentParser();p.add_argument('--input',required=True);p.add_argument('--output',required=True);p.add_argument('--report',required=True);a=p.parse_args()
 with open(a.input,encoding='utf-8-sig',newline='') as f:
  reader=csv.DictReader(f);headers=set(reader.fieldnames or []);missing=REQUIRED-headers
  if missing:raise SystemExit('Missing columns: '+', '.join(sorted(missing)))
  rows=list(reader)
 problems=[];seen=set()
 for i,r in enumerate(rows,2):
  name=r['player'].strip()
  if not name or name in seen:problems.append(f'row {i}: missing/duplicate player')
  seen.add(name)
  if r['position'] not in {'C','F','G'}:problems.append(f'row {i}: invalid position')
  if r['turn'] not in {'T1','T2','T3'}:problems.append(f'row {i}: invalid turn')
  if r['availability'] not in {'confirmed','uncertain'}:problems.append(f'row {i}: availability not verified')
  if r['verified_price'].lower()!='true' or r['verified_matchup'].lower()!='true':problems.append(f'row {i}: price/matchup unverified')
  for col in ('credit','expected_fantasy_if_play','upside_p90_approx'):
   try:
    v=float(r[col]);assert v==v
    if col=='credit' and v<=0:raise ValueError()
   except (ValueError,AssertionError):problems.append(f'row {i}: invalid {col}')
 report={'rows':len(rows),'status':'validated_rows_only' if not problems else 'blocked','issues':problems,'global_market_completeness':'NOT VERIFIED','coach_optimization':'NOT IMPLEMENTED','t1_t2_option_value':'NOT IMPLEMENTED','source_authentication':'MANUAL VERIFIED INPUT REQUIRED'}
 Path(a.report).write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')
 if problems:raise SystemExit(f'Validation failed: {len(problems)} issues. See {a.report}')
 with open(a.output,'w',newline='',encoding='utf-8') as f:
  w=csv.DictWriter(f,fieldnames=list(reader.fieldnames));w.writeheader();w.writerows(rows)
 print('Validated input, but market completeness still needs independent confirmation.')
if __name__=='__main__':main()
