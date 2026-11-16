"""Fail-closed readiness audit for weekly Moneyball research; no trades or credentials."""
import argparse, json, pathlib, zipfile, csv, datetime

def check(data,market=None,roster=None):
    out={'checked_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'data_zip':str(data),'checks':{},'blockers':[]}
    required={'games-2026.csv.gz','player_box-2026.csv.gz','team_games-2026.csv.gz'}
    try:
        with zipfile.ZipFile(data) as z:
            names=set(z.namelist());out['checks']['required_statistical_files']=required<=names
            if not required<=names:out['blockers'].append('Missing required game/player/team CSV files')
            bad=z.testzip();out['checks']['zip_integrity']=bad is None
            if bad:out['blockers'].append('Corrupt ZIP entry: '+bad)
    except (OSError,zipfile.BadZipFile) as e:
        out['checks']['zip_integrity']=False;out['blockers'].append('Cannot read statistical ZIP: '+str(e))
    out['checks']['verified_full_market']=False
    if not market:
        out['blockers'].append('No complete, verified current Fantasy market supplied')
    else:
        try:
            with open(market,newline='',encoding='utf-8') as f:rows=list(csv.DictReader(f))
            keys={'player','team','credit','position','turn','expected_fantasy_if_play','upside_p90_approx','availability','verified_price','verified_matchup'}
            good=bool(rows) and all(keys<=set(row) and row.get('verified_price','').lower() in ('true','yes','1') and row.get('verified_matchup','').lower() in ('true','yes','1') for row in rows)
            out['checks']['verified_market_rows']=len(rows)
            if not good:out['blockers'].append('Market missing verified fields/rows')
            else:out['checks']['verified_full_market']='rows validated, coverage not attested'
        except (OSError,UnicodeError) as e:out['blockers'].append('Cannot read market CSV: '+str(e))
    if not roster:out['blockers'].append('No 11-entry current roster including verified coach')
    else:
        try:
            with open(roster,newline='',encoding='utf-8') as f:rows=list(csv.DictReader(f))
            out['checks']['roster_11_with_coach']=len(rows)==11 and any(r.get('position')=='HC' for r in rows)
            if not out['checks']['roster_11_with_coach']:out['blockers'].append('Roster must have 10 players and 1 coach')
        except (OSError,UnicodeError) as e:out['blockers'].append('Cannot read roster CSV: '+str(e))
    out['checks']['live_market_connector']=False
    out['checks']['unattended_retraining']=False
    out['checks']['calibrated_team_upside']=False
    out['checks']['availability_probabilities']=False
    out['ready_for_baseline_retraining']=out['checks'].get('required_statistical_files',False) and out['checks'].get('zip_integrity',False)
    out['ready_for_certified_full_optimization']=False
    return out
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--data',required=True);p.add_argument('--market');p.add_argument('--roster');p.add_argument('--out');a=p.parse_args()
    result=check(a.data,a.market,a.roster)
    s=json.dumps(result,indent=2,ensure_ascii=False)
    if a.out:pathlib.Path(a.out).write_text(s,encoding='utf-8')
    print(s)
