"""Moneyball 5.0: auditable, read-only R12 public-market bridge.

Reads CSVs or ZIPs; never asserts public prices, fixtures, or availability are verified.
No transfers, no optimizer execution. Python standard library only.
"""
import argparse
import csv
import io
import json
import math
import re
import unicodedata
import zipfile
from collections import defaultdict
from pathlib import Path

FIELDS = ['player','team','credit','position','turn','expected_fantasy_if_play',
          'upside_p90_approx','availability','verified_price','verified_matchup',
          'coach_expected_fantasy','source','match_status','opponent']


def read_table(path, filename=None):
    path = Path(path)
    if path.suffix.lower() == '.zip':
        if not filename:
            raise ValueError('ZIP input requires its --*-member CSV filename')
        with zipfile.ZipFile(path) as z:
            matches = [n for n in z.namelist() if n == filename or n.endswith('/'+filename)]
            if len(matches) != 1:
                raise ValueError(f'ZIP {path}: expected exactly one {filename}, got {matches}')
            data = z.read(matches[0]).decode('utf-8-sig')
    else:
        data = path.read_text(encoding='utf-8-sig')
    return list(csv.DictReader(io.StringIO(data)))


def key(s):
    s = unicodedata.normalize('NFKD', str(s or ''))
    return ''.join(c for c in s.casefold() if c.isalnum() and not unicodedata.combining(c))


def number(s):
    try:
        v = float(s)
        return v if math.isfinite(v) else None
    except (TypeError, ValueError):
        return None


def verified(v):
    return str(v).strip().lower() in ('true', 'yes', '1')


def write_csv(path, rows, fields):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore')
        w.writeheader()
        w.writerows(rows)


def build(players, coaches, projections, coach_projections, turns):
    market = players + coaches
    projection_index = defaultdict(list)
    for p in projections:
        projection_index[(key(p.get('player')), key(p.get('team')))].append(p)
    coach_index = defaultdict(list)
    for c in coach_projections:
        coach_index[key(c.get('team'))].append(c)
    turn_index = defaultdict(set)
    for t in turns:
        team = key(t.get('team'))
        turn = str(t.get('turn', '')).upper().strip()
        if team and turn in ('T1','T2','T3','T4'):
            turn_index[team].add(turn)

    out, issues, used = [], [], set()
    seen = set()
    for m in market:
        name, team = m.get('player','').strip(), m.get('team','').strip()
        pos = m.get('position','').strip().upper()
        identity = (key(name), key(team))
        if not all(identity) or identity in seen:
            issues.append({'player':name,'team':team,'issue':'missing_or_duplicate_market_identity'})
            continue
        seen.add(identity)
        if pos not in ('G','F','C','HC'):
            issues.append({'player':name,'team':team,'issue':'invalid_position'})
            continue
        options = coach_index[key(team)] if pos == 'HC' else projection_index[identity]
        status = 'matched' if len(options) == 1 else ('missing_projection' if not options else 'ambiguous_projection')
        projection = options[0] if len(options) == 1 else {}
        if pos != 'HC' and len(options) == 1:
            used.add(id(options[0]))
        turn_options = turn_index[key(team)]
        turn = next(iter(turn_options)) if len(turn_options) == 1 else ''
        if not turn:
            issues.append({'player':name,'team':team,'issue':'missing_or_ambiguous_turn'})
        if status != 'matched':
            issues.append({'player':name,'team':team,'issue':status})
        price = number(m.get('credit'))
        if price is None or price <= 0:
            issues.append({'player':name,'team':team,'issue':'invalid_price'})
        expected = number(projection.get('expected_coach_fantasy' if pos == 'HC' else 'expected_fantasy_if_play'))
        upside = expected if pos == 'HC' else number(projection.get('upside_p90_approx'))
        # External public snapshot flags are preserved, never upgraded by matching.
        price_ok = verified(m.get('verified_price'))
        matchup_ok = verified(m.get('verified_matchup')) and bool(turn)
        availability = m.get('availability','uncertain').strip().lower()
        if availability != 'confirmed':
            availability = 'uncertain'
        out.append({
            'player':name,'team':team,'credit':price if price is not None else '',
            'position':pos,'turn':turn,
            'expected_fantasy_if_play':expected if expected is not None else '',
            'upside_p90_approx':upside if upside is not None else '',
            'availability':availability,'verified_price':str(price_ok).lower(),
            'verified_matchup':str(matchup_ok).lower(),
            'coach_expected_fantasy':expected if pos == 'HC' and expected is not None else '',
            'source':m.get('source',''),'match_status':status,
            'opponent':projection.get('opponent',''),
        })
    for p in projections:
        if id(p) not in used:
            issues.append({'player':p.get('player',''),'team':p.get('team',''),
                           'issue':'projection_without_safe_market_match'})
    report = {
        'market_players':len(players),'market_coaches':len(coaches),
        'player_projections':len(projections),'coach_projections':len(coach_projections),
        'candidates':len(out),
        'matched_players':sum(x['match_status']=='matched' and x['position']!='HC' for x in out),
        'matched_coaches':sum(x['match_status']=='matched' and x['position']=='HC' for x in out),
        'candidates_with_verified_price':sum(x['verified_price']=='true' for x in out),
        'candidates_with_verified_matchup':sum(x['verified_matchup']=='true' for x in out),
        'ready_for_optimizer':False,
        'global_market_completeness':'NOT VERIFIED',
        'note':'Public data are unverified; turn requires independently supplied team-turn CSV. Missing projections stay blank, not zero. Coach upside is an expected-value placeholder, not a percentile.',
        'transfers_executed':False,
        'issues':issues,
    }
    return out, report


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('players','coaches','projections','coach-projections'):
        p.add_argument('--'+name, required=True)
        p.add_argument('--'+name+'-member', default={
            'players':'public_market_snapshot.csv',
            'coaches':'public_coaches_snapshot.csv',
            'projections':'conditional_projections.csv',
            'coach-projections':'coach_projections_r12.csv'}[name])
    p.add_argument('--turns',help='Optional verified CSV with columns team,turn; never inferred')
    p.add_argument('--output',default='results/market_candidates_v5.csv')
    p.add_argument('--report',default='results/market_bridge_v5_report.json')
    args=p.parse_args()
    data={name.replace('-','_'):read_table(getattr(args,name.replace('-','_')),
        getattr(args,name.replace('-','_')+'_member')) for name in ('players','coaches','projections','coach-projections')}
    turns=read_table(args.turns) if args.turns else []
    out,report=build(data['players'],data['coaches'],data['projections'],data['coach_projections'],turns)
    write_csv(args.output,out,FIELDS)
    path=Path(args.report);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k!='issues'},ensure_ascii=False,indent=2))

if __name__=='__main__':
    main()
