raise ValueError(f"fixtures.csv must contain {sorted(required)}")
        rows = list(reader)
    selected = [r for r in rows if str(r["round"]).strip().lstrip("Rr").strip() == str(target_round)]
    if not selected:
        raise ValueError(f"No fixtures for round {target_round} in {path}")
    matchups = {}
    for row in selected:
        home_name, away_name = row["home_team"].strip(), row["away_team"].strip()
        if home_name not in TEAM_CODES or away_name not in TEAM_CODES:
            raise ValueError(f"Unknown fixture team: {home_name} / {away_name}")
        home, away = TEAM_CODES[home_name], TEAM_CODES[away_name]
        if home == away or home in matchups or away in matchups:
            raise ValueError(f"Duplicate or invalid fixture: {home_name} / {away_name}")
        matchups[home] = (away, 1)
        matchups[away] = (home, 0)
    if set(matchups) != set(TEAM_CODES.values()):
        raise ValueError(f"Round {target_round}: expected all 20 teams; found {len(matchups)}")
    missing = set(matchups) - set(valid_codes)
    if missing:
        raise ValueError(f"Fixture codes absent from historical dataset: {sorted(missing)}")
    return matchups

def fantasy(pir,won):
    # Bonus on absolute PIR in wins; ambiguous negative-PIR handling should be verified in-app
    return pir+0.1*np.abs(pir)*won

def load(z,name):return pd.read_csv(z.open(name+'-2026.csv.gz'),compression='gzip')

def make_features(p,g,t):
    p=p.merge(g[['game_id','round']],on='game_id',validate='many_to_one')
    p['fantasy']=fantasy(p.pir,p.won)
    t=t.copy();t['allowed_pir']=t.apply(lambda x:t[(t.game_id==x.game_id)&(t.team==x.opponent)].pir.iloc[0],axis=1)
    # all pre-game features from strictly prior rounds, no leakage
    feats=[]
    for r in sorted(p['round'].unique()):
        old=p[p['round']<r];oldteam=t[t['round']<r]
        now=p[p['round']==r]
        league_f=old.fantasy.mean() if len(old) else 10
        league_min=old.sec.mean()/60 if len(old) else 18
        for a in now.itertuples():
            h=old[old.player_id==a.player_id].sort_values(['round','date']);last=h.tail(5)
            ot=oldteam[oldteam.team==a.opponent].tail(5)
            own=oldteam[oldteam.team==a.team].tail(5)
            def avg(df,col,default):return float(df[col].mean()) if len(df) else default
            feats.append(dict(round=r,player_id=a.player_id,player=a.player,team=a.team,opponent=a.opponent,venue=a.venue,actual=float(a.fantasy),actual_pir=float(a.pir),minutes=float(a.sec/60),
                n=len(h),recent_n=len(last),mean5=avg(last,'fantasy',league_f),mean3=avg(last.tail(3),'fantasy',league_f),mean_all=avg(h,'fantasy',league_f),
                sd5=float(last.fantasy.std()) if len(last)>1 else 8.,minutes5=avg(last,'sec',league_min*60)/60,minutes3=avg(last.tail(3),'sec',league_min*60)/60,
                opponent_allowed_pir=avg(ot,'allowed_pir',90),opp_pace=avg(ot,'poss',78),team_pace=avg(own,'poss',78),team_win5=avg(own,'won',0.5),
                home=int(a.venue=='home'),played=int(a.sec>0)))
    return pd.DataFrame(feats)

cols=['n','mean5','mean3','mean_all','sd5','minutes5','minutes3','opponent_allowed_pir','opp_pace','team_pace','team_win5','home']

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--data',required=True);ap.add_argument('--out',required=True);ap.add_argument('--fixtures',default='fixtures.csv');args=ap.parse_args();os.makedirs(args.out,exist_ok=True)
 z=zipfile.ZipFile(args.data);p=load(z,'player_box');g=load(z,'games');t=load(z,'team_games')
 target_round=int(g['round'].max())+1
 matches=fixture_matchups(args.fixtures,target_round,set(t['team'].dropna().unique()))
 print(f'Using validated fixtures for round {target_round}: {len(matches)} teams')
 # detect missing / duplicated data
 assert not p.duplicated(['game_id','player_id']).any()
 assert len(g)==len(g.game_id.unique())
 df=make_features(p,g,t);df=df[df.n>=2].copy()
 def model():return make_pipeline(SimpleImputer(strategy='median'),StandardScaler(),Ridge(alpha=150))
 oof=[]
 for r in sorted(df['round'].unique()):
  if r<5:continue
  tr=df[df['round']<r];te=df[df['round']==r]
  if len(tr)<50:continue
  m=model();m.fit(tr[cols],tr.actual)
  tmp=te[['round','player_id','player','team','opponent','actual','actual_pir']].copy();tmp['pred']=m.predict(te[cols]);oof.append(tmp)
 bt=pd.concat(oof,ignore_index=True)
 # calibrate probabilities on rounds 5-8 only; assess on rounds 9-11 (chronologically later)
 fit=bt[bt['round']<=8];valid=bt[bt['round']>=9]
 calibrators={};metrics={'projection_round':target_round,'fixtures_source':str(args.fixtures),'fixture_teams_mapped':len(matches),'dataset_games':len(g),'dataset_player_games':len(p),'oof_n':len(bt),'oof_mae':float(mean_absolute_error(bt.actual,bt.pred)),'oof_rmse':float(np.sqrt(mean_squared_error(bt.actual,bt.pred))),'holdout_rounds':'9-11','holdout_n':len(valid),'holdout_mae':float(mean_absolute_error(valid.actual,valid.pred)),'scoring':'PIR + 0.10*abs(PIR) if win; verify negative-PIR bonus with app','conditional':'Only actual box-score participants, no probability of availability'}
 for threshold in (15,20,25):
  y=(fit.actual>=threshold).astype(int);logit=LogisticRegression(C=1.,max_iter=1000)
  logit.fit(fit[['pred']],y);calibrators[threshold]=logit
  prob=logit.predict_proba(valid[['pred']])[:,1];truth=(valid.actual>=threshold).astype(int)
  metrics[f'fantasy_ge_{threshold}']={'holdout_actual_rate':float(truth.mean()),'holdout_predicted_rate':float(prob.mean()),'holdout_brier':float(brier_score_loss(truth,prob)),'calibration_train_n':len(fit)}
  bt[f'p_fantasy_ge_{threshold}_if_play']=logit.predict_proba(bt[['pred']])[:,1]
 bt.to_csv(args.out+'/chronological_backtest.csv',index=False)
 # next round features derived strictly from R11 histories and matchup team stats
 latest=df.sort_values('round').groupby('player_id').tail(1).copy()
 # update historical statistics to include R11 (features at R11 excluded that match)
 history=p.merge(g[['game_id','round']],on='game_id')
 team_hist=t.copy()
 team_hist['allowed_pir']=team_hist.apply(lambda x:team_hist[(team_hist.game_id==x.game_id)&(team_hist.team==x.opponent)].pir.iloc[0],axis=1)
 rows=[]
 for pid,h in history.groupby('player_id'):
  h=h.sort_values(['round','date']);recent=h.tail(5);last=h.iloc[-1]
  if len(h)<2:continue
  hf=fantasy(h.pir,h.won);rf=fantasy(recent.pir,recent.won)
  opponent=None;home=None
  if last.team in matches:opponent,home=matches[last.team]
  opp=team_hist[team_hist.team==opponent].tail(5) if opponent else pd.DataFrame()
  own=team_hist[team_hist.team==last.team].tail(5)
  def avg(d,c,default):return float(d[c].mean()) if len(d) else default
  row=dict(player_id=pid,player=last.player,team=last.team,opponent=opponent or '',venue='home' if home==1 else 'away' if home==0 else 'unknown',games=len(h),last_round=int(last['round']),
  n=len(h),mean5=float(rf.mean()),mean3=float(rf.tail(3).mean()),mean_all=float(hf.mean()),sd5=float(rf.std()) if len(rf)>1 else 8.,minutes5=float(recent.sec.mean()/60),minutes3=float(recent.tail(3).sec.mean()/60),
  opponent_allowed_pir=avg(opp,'allowed_pir',90),opp_pace=avg(opp,'poss',78),team_pace=avg(own,'poss',78),team_win5=avg(own,'won',.5),home=home if home is not None else 0)
  rows.append(row)
 nextdf=pd.DataFrame(rows)
 m=model();m.fit(df[cols],df.actual)
 nextdf['expected_fantasy_if_play']=m.predict(nextdf[cols]);nextdf['value_target_1p1cr']='unavailable: no verified full-market prices'
 for th in (15,20,25):nextdf[f'p_fantasy_ge_{th}_if_play']=calibrators[th].predict_proba(nextdf[['expected_fantasy_if_play']].rename(columns={'expected_fantasy_if_play':'pred'}))[:,1]
 # Empirical residual quantiles from holdout, not individual predictive intervals
 residual=valid.actual-valid.pred
 nextdf['floor_p10_approx']=nextdf.expected_fantasy_if_play+residual.quantile(.1)
 nextdf['upside_p90_approx']=nextdf.expected_fantasy_if_play+residual.quantile(.9)
 nextdf['availability']='NOT VALIDATED — conditional on playing'
 nextdf['projection_round']=target_round
 nextdf.sort_values('expected_fantasy_if_play',ascending=False).to_csv(args.out+'/conditional_projections.csv',index=False)
 with open(args.out+'/metrics.json','w') as f:json.dump(metrics,f,indent=2)
 print(json.dumps(metrics,indent=2));print(nextdf[nextdf.player.str.contains('Valanciunas|Diarra|Feliz|Mantzoukas|Malcolm|Payne|Brooks|Ward|Abalde|Herrera',case=False,regex=True)][['player','team','expected_fantasy_if_play','p_fantasy_ge_20_if_play']].to_string(index=False))
if __name__=='__main__':main()
  
