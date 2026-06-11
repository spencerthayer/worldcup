#!/usr/bin/env python3
import argparse, csv, json, math, random, re, sys
from collections import defaultdict
from datetime import datetime, timezone
from itertools import permutations
from pathlib import Path

DATA = Path("_data"); RAW = DATA / "raw"; NORM = DATA / "norm"

ALIASES = {"czech republic":"Czech Republic","czechia":"Czech Republic","czech":"Czech Republic","south korea":"South Korea","korea republic":"South Korea","bosnia-herzegovina":"Bosnia and Herzegovina","bosnia herzegovina":"Bosnia and Herzegovina","bosnia & herzegovina":"Bosnia and Herzegovina","bosnia-and-herzegovina":"Bosnia and Herzegovina","united states":"USA","usa":"USA","turkiye":"Turkey","türkiye":"Turkey","trkiye":"Turkey","ivory coast":"Ivory Coast","cote d'ivoire":"Ivory Coast","côte d'ivoire":"Ivory Coast","ivory-coast":"Ivory Coast","cape verde":"Cape Verde","cabo verde":"Cape Verde","cape-verde":"Cape Verde","d-r congo":"DR Congo","dr congo":"DR Congo","d.r. congo":"DR Congo","congo dr":"DR Congo","democratic republic of the congo":"DR Congo","saudi arabia":"Saudi Arabia","saudi-arabia":"Saudi Arabia","new zealand":"New Zealand","new-zealand":"New Zealand","uzbekistan":"Uzbekistan","jordan":"Jordan","algeria":"Algeria","senegal":"Senegal","norway":"Norway","iran":"Iran","haiti":"Haiti","curacao":"Curaçao","curaçao":"Curaçao","curaao":"Curaçao","tunisia":"Tunisia","panama":"Panama","ghana":"Ghana","morocco":"Morocco","egypt":"Egypt","ecuador":"Ecuador","paraguay":"Paraguay","uruguay":"Uruguay","colombia":"Colombia","japan":"Japan","sweden":"Sweden","netherlands":"Netherlands","germany":"Germany","belgium":"Belgium","spain":"Spain","france":"France","england":"England","portugal":"Portugal","argentina":"Argentina","brazil":"Brazil","mexico":"Mexico","canada":"Canada","switzerland":"Switzerland","austria":"Austria","croatia":"Croatia","scotland":"Scotland","south africa":"South Africa","south-africa":"South Africa","qatar":"Qatar","iraq":"Iraq","korea republic":"South Korea","czech-republic":"Czech Republic"}

def nteam(name):
    if not name: return name
    name = re.sub(r"[^\x00-\x7F]+","",name).strip()
    name = re.sub(r"\s*\(.*?\)\s*$","",name).strip()
    return ALIASES.get(name.lower(), name)

def match_key(a, b):
    a, b = nteam(a), nteam(b)
    return tuple(sorted([a, b]))

def load_odds():
    p = NORM/"all_odds_normalized.csv"
    if not p.exists(): sys.exit(f"ERROR: {p} not found.")
    with open(p,newline="",encoding="utf-8") as f: return list(csv.DictReader(f))

def load_fixtures():
    p = RAW/"openfootball"/"worldcup-2026.json"
    if not p.exists(): sys.exit(f"ERROR: {p} not found.")
    with open(p) as f: return json.load(f)

def load_elo():
    fp = RAW/"hicruben"/"elo-calibrated.json"
    if not fp.exists(): return {}
    with open(fp) as fh: data = json.load(fh)
    result = {}
    for slug, rating in data.get("ratings",{}).items():
        name = ALIASES.get(slug, slug.replace("-"," ").title())
        result[nteam(name)] = rating
    return result

def load_xg():
    p = RAW/"uanalyse"/"latest"/"match_predictions.csv"
    if not p.exists(): return {}
    xg = {}
    with open(p,newline="",encoding="utf-8") as f:
        for r in csv.DictReader(f):
            h,a = nteam(r.get("home_team","")),nteam(r.get("away_team",""))
            if not h or not a: continue
            key = match_key(h,a)
            try: xg[key] = {"home":float(r.get("exp_home_goals",0) or 0),"away":float(r.get("exp_away_goals",0) or 0)}
            except: pass
    return xg

def load_priors():
    p = RAW/"uanalyse"/"latest"/"tournament_probabilities.csv"
    if not p.exists(): return {}
    priors = {}
    with open(p,newline="",encoding="utf-8") as f:
        for r in csv.DictReader(f):
            t = nteam(r.get("team",""))
            if not t: continue
            priors[t] = {k:float(r.get(k,0) or 0) for k in ["prob_reach_round_of_32","prob_reach_quarterfinals","prob_reach_semifinals","prob_reach_final","prob_champion"]}
    return priors

def parse_bracket(matches):
    groups = defaultdict(list); group_fixtures = defaultdict(list); knockout = []
    for m in matches:
        if m.get("group"):
            g = m["group"]
            if g.startswith("Group "): g = g[len("Group "):]
            t1,t2 = nteam(m["team1"]),nteam(m["team2"])
            group_fixtures[g].append((t1,t2))
            for t in [t1,t2]:
                if t not in groups[g]: groups[g].append(t)
        else:
            knockout.append({"num":m.get("num"),"team1":m["team1"],"team2":m["team2"],"round":m.get("round",""),"date":m.get("date","")})
    return dict(groups), dict(group_fixtures), knockout

SOURCE_WEIGHTS = {"betexplorer":0.30,"oddsharvester":0.25,"polymarket":0.20,"uanalyse":0.15,"worldcup-predictor":0.10}
ELO_DEFAULT = 1650

def build_consensus(odds):
    sp = defaultdict(dict)
    for row in odds:
        s = row.get("source","")
        if s not in SOURCE_WEIGHTS: continue
        h,a = nteam(row.get("home_team","")),nteam(row.get("away_team",""))
        if not h or not a: continue
        try:
            hw = float(row["home_win_prob"]) if row.get("home_win_prob") else None
            dw = float(row["draw_prob"]) if row.get("draw_prob") else None
            aw = float(row["away_win_prob"]) if row.get("away_win_prob") else None
        except: continue
        if any(v is None or not math.isfinite(v) for v in [hw,dw,aw]): continue
        key = match_key(h,a)
        st = sorted(key)
        sp[key][s] = (hw,dw,aw) if h==st[0] else (aw,dw,hw)
    consensus = {}
    for key,srcs in sp.items():
        tw=0; phw,pd,paw=0,0,0
        for s,w in SOURCE_WEIGHTS.items():
            if s in srcs:
                hw,d,aw = srcs[s]; phw+=w*hw; pd+=d*w; paw+=w*aw; tw+=w
        if tw>0:
            phw/=tw; pd/=tw; paw/=tw
            ss=phw+pd+paw
            if ss>0: consensus[key]=(phw/ss,pd/ss,paw/ss)
    return consensus

def elo_probs(a,b,elo):
    ra=elo.get(nteam(a),ELO_DEFAULT); rb=elo.get(nteam(b),ELO_DEFAULT)
    qa=1.0/(1.0+10**(-(ra-rb)/400)); qb=1.0-qa
    draw=max(0.18,min(0.30,0.26-0.04*abs(ra-rb)/400))
    return ((1-draw)*qa,draw,(1-draw)*qb)

def match_probs(a,b,consensus,elo):
    key=match_key(a,b)
    if key in consensus:
        hw,d,aw=consensus[key]; st=sorted(key)
        return (hw,d,aw) if nteam(a)==st[0] else (aw,d,hw)
    return elo_probs(a,b,elo)

def advance_prob(a,b,consensus,elo):
    hw,d,aw=match_probs(a,b,consensus,elo)
    ra=elo.get(nteam(a),ELO_DEFAULT); rb=elo.get(nteam(b),ELO_DEFAULT)
    qa=1.0/(1.0+10**(-(ra-rb)/400))
    sa=0.5+0.20*(qa-0.5)
    return hw+d*sa

DRAW_SCORES=[(0,0),(1,1),(1,1),(2,2)]
LOSER_GOALS=[0,1,1,2]

def synth_score(hw,aw,rng):
    if not hw and not aw: return rng.choice(DRAW_SCORES)
    if hw:
        m=1+(1 if rng.random()<0.28 else 0)+(1 if rng.random()<0.10 else 0)
        lg=rng.choice(LOSER_GOALS); return (lg+m,lg)
    else:
        m=1+(1 if rng.random()<0.28 else 0)+(1 if rng.random()<0.10 else 0)
        lg=rng.choice(LOSER_GOALS); return (lg,lg+m)

def rank_group(teams,results,elo,rng):
    tbl={t:{"pts":0,"gf":0,"ga":0} for t in teams}
    for (t1,t2),(p1,p2,gf1,ga1,gf2,ga2) in results.items():
        tbl[t1]["pts"]+=p1; tbl[t2]["pts"]+=p2; tbl[t1]["gf"]+=gf1; tbl[t1]["ga"]+=ga1; tbl[t2]["gf"]+=gf2; tbl[t2]["ga"]+=ga2
    for t in tbl: tbl[t]["gd"]=tbl[t]["gf"]-tbl[t]["ga"]
    return sorted(teams,key=lambda t:(-tbl[t]["pts"],-tbl[t]["gd"],-tbl[t]["gf"],-elo.get(t,ELO_DEFAULT),rng.random()))

def assign_thirds(qualified,third_groups,knockout,rng):
    tp_slots = []
    for km in knockout:
        for sk in [km["team1"],km["team2"]]:
            if sk.startswith("3") and len(sk)>1:
                allowed=set(sk[1:].replace("/",""))
                tp_slots.append((sk, allowed))
    def n_eligible(allowed):
        return sum(1 for t in qualified if third_groups.get(t,"") in allowed)
    tp_slots.sort(key=lambda x: n_eligible(x[1]))
    def backtrack(idx, used, assignment):
        if idx==len(tp_slots): return assignment.copy()
        sname, allowed = tp_slots[idx]
        for t in qualified:
            if t in used: continue
            g = third_groups.get(t,"")
            if g in allowed:
                assignment[sname]=t; used.add(t)
                r = backtrack(idx+1, used, assignment)
                if r is not None: return r
                used.remove(t); del assignment[sname]
        return None
    r = backtrack(0, set(), {})
    return r if r else {}

def _process_knockout(knockout, seeds, consensus, elo, rng):
    winners={}; losers={}
    r32=set(); r16=set(); qf=set(); sf=set(); fins=set(); champ=None
    def resolve(slot):
        if slot in seeds: return seeds[slot]
        if slot.startswith("W"): return winners.get(int(slot[1:]))
        if slot.startswith("L"): return losers.get(int(slot[1:]))
        return None
    for km in knockout:
        num=km["num"]
        t1=resolve(km["team1"]); t2=resolve(km["team2"])
        if not t1 or not t2: continue
        p=advance_prob(t1,t2,consensus,elo)
        if rng.random()<p: w,l=t1,t2
        else: w,l=t2,t1
        if num is not None:
            winners[num]=w; losers[num]=l
            if 73<=num<=88: r32.add(t1); r32.add(t2)
            elif 89<=num<=96: r16.add(t1); r16.add(t2)
            elif 97<=num<=100: qf.add(t1); qf.add(t2)
            elif 101<=num<=102: sf.add(t1); sf.add(t2)
        elif km["round"]=="Final":
            fins.add(t1); fins.add(t2)
            champ=t1 if rng.random()<p else t2
    return winners, losers, r32, r16, qf, sf, fins, champ

def simulate(groups,gfix,knockout,consensus,elo,xg,n_sims,seed,model="consensus"):
    rng=random.Random(seed)
    pcnt=defaultdict(lambda:defaultdict(int))
    scnt={s:defaultdict(int) for s in ["r32","r16","qf","sf","final","champion"]}
    for _ in range(n_sims):
        grank={}; all_thirds=[]
        for gl in sorted(groups.keys()):
            teams=groups[gl]; fixtures=gfix[gl]; results={}
            for (t1,t2) in fixtures:
                pw,pd,pl=match_probs(t1,t2,consensus,elo)
                u=rng.random()
                if u<pw: p1,p2,hw2,aw2=3,0,True,False
                elif u<pw+pd: p1,p2,hw2,aw2=1,1,False,False
                else: p1,p2,hw2,aw2=0,3,False,True
                s1,s2=synth_score(hw2,aw2,rng)
                results[(t1,t2)]=(p1,p2,s1,s2,s2,s1)
            ranking=rank_group(teams,results,elo,rng)
            grank[gl]=ranking
            for pos,team in enumerate(ranking): pcnt[team][pos+1]+=1
            if len(ranking)>=3:
                t3=ranking[2]
                tbl={t:{"pts":0,"gf":0,"ga":0} for t in teams}
                for (t1,t2),(p1,p2,gf1,ga1,gf2,ga2) in results.items():
                    if t1 in tbl: tbl[t1]["pts"]+=p1; tbl[t1]["gf"]+=gf1; tbl[t1]["ga"]+=ga1
                    if t2 in tbl: tbl[t2]["pts"]+=p2; tbl[t2]["gf"]+=gf2; tbl[t2]["ga"]+=ga2
                all_thirds.append((t3,gl,tbl.get(t3,{"pts":0,"gf":0,"ga":0})))
        all_thirds.sort(key=lambda x:(-x[2]["pts"],-(x[2]["gf"]-x[2]["ga"]),-x[2]["gf"],-elo.get(x[0],ELO_DEFAULT),rng.random()))
        qt=[t[0] for t in all_thirds[:8]]
        tg={t[0]:t[1] for t in all_thirds[:8]}
        seeds={}
        for gl,ranking in grank.items():
            seeds[f"1{gl}"]=ranking[0]; seeds[f"2{gl}"]=ranking[1]
        ts=assign_thirds(qt,tg,knockout,rng)
        for sk,team in ts.items(): seeds[sk]=team
        _, _, r32, r16, qf, sf, fins, champ = _process_knockout(knockout, seeds, consensus, elo, rng)
        for t in r32: scnt["r32"][t]+=1
        for t in r16: scnt["r16"][t]+=1
        for t in qf: scnt["qf"][t]+=1
        for t in sf: scnt["sf"][t]+=1
        for t in fins: scnt["final"][t]+=1
        if champ: scnt["champion"][champ]+=1
    n=n_sims
    return {"placement":{t:{p:c/n for p,c in pos.items()} for t,pos in pcnt.items()},**{s:{t:c/n for t,c in cnt.items()} for s,cnt in scnt.items()}}

def optimize_groups(groups,sim):
    placements={}
    pp = sim.get("placement",{})
    for gl,teams in groups.items():
        best=None; best_score=-1
        for perm in permutations(teams):
            score=sum(pp.get(t,{}).get(pos+1,0) for pos,t in enumerate(perm))
            if score>best_score: best_score=score; best=perm
        placements[gl]=list(best)
    return placements

def fill_knockout_bracket(gplacements,sim,consensus,elo,groups,gfix,knockout,rng):
    seeds={}
    for gl,ordering in gplacements.items():
        seeds[f'1{gl}']=ordering[0]; seeds[f'2{gl}']=ordering[1]
    r32p=sim.get("r32",{})
    tp={}
    for gl,ordering in gplacements.items():
        if len(ordering)>=3: tp[ordering[2]]=r32p.get(ordering[2],0)
    qt=sorted(tp,key=lambda t:-tp[t])[:8]
    tg={}
    for gl,ordering in gplacements.items():
        if len(ordering)>=3: tg[ordering[2]]=gl
    ts=assign_thirds(qt,tg,knockout,rng)
    for sk,team in ts.items(): seeds[sk]=team
    _, _, r32, r16, qf, sf, fins, champ = _process_knockout(knockout, seeds, consensus, elo, rng)
    return {"r32":r32,"r16":r16,"qf":qf,"sf":sf,"final":fins,"champion":champ}

def compute_score(bracket,sim):
    score=0.0
    for gl,ordering in bracket["group_placements"].items():
        for pos,t in enumerate(ordering):
            score+=sim.get("placement",{}).get(t,{}).get(pos+1,0)*1
    sp={"round_of_32":1,"round_of_16":2,"quarter_finals":4,"semi_finals":6,"finalists":10}
    pk={"round_of_32":"r32","round_of_16":"r16","quarter_finals":"qf","semi_finals":"sf","finalists":"final"}
    for stage,pts in sp.items():
        for t in bracket.get(stage,[]):
            score+=sim.get(pk[stage],{}).get(t,0)*pts
    w=bracket.get("winner","")
    if w: score+=sim.get("champion",{}).get(w,0)*15
    return score

def validate(bracket,groups,sim):
    errs=[]
    for gl,ordering in bracket["group_placements"].items():
        if set(ordering)!=set(groups[gl]): errs.append(f"Group {gl} not a permutation")
        if len(ordering)!=4: errs.append(f"Group {gl}: {len(ordering)} teams")
    if len(bracket.get("round_of_32",[]))!=32: errs.append(f"R32: {len(bracket.get('round_of_32',[]))}")
    if len(bracket.get("round_of_16",[]))!=16: errs.append(f"R16: {len(bracket.get('round_of_16',[]))}")
    if len(bracket.get("quarter_finals",[]))!=8: errs.append(f"QF: {len(bracket.get('quarter_finals',[]))}")
    if len(bracket.get("semi_finals",[]))!=4: errs.append(f"SF: {len(bracket.get('semi_finals',[]))}")
    if len(bracket.get("finalists",[]))!=2: errs.append(f"Final: {len(bracket.get('finalists',[]))}")
    if not bracket.get("winner"): errs.append("No winner")
    r32=set(bracket.get("round_of_32",[])); r16=set(bracket.get("round_of_16",[]))
    qf=set(bracket.get("quarter_finals",[])); sf=set(bracket.get("semi_finals",[]))
    fin=set(bracket.get("finalists",[])); w=bracket.get("winner")
    if not r16.issubset(r32): errs.append("R16 not subset R32")
    if not qf.issubset(r16): errs.append("QF not subset R16")
    if not sf.issubset(qf): errs.append("SF not subset QF")
    if not fin.issubset(sf): errs.append("Final not subset SF")
    if w and w not in fin: errs.append("Winner not in finalists")
    return errs

def compute_mad(sim,priors):
    mad={}
    sm={"r32":"prob_reach_round_of_32","qf":"prob_reach_quarterfinals","sf":"prob_reach_semifinals","final":"prob_reach_final","champion":"prob_champion"}
    for ss,pk in sm.items():
        total=0; count=0
        for t,pp in priors.items():
            total+=abs(sim.get(ss,{}).get(t,0)-pp.get(pk,0)); count+=1
        if count>0: mad[ss]=round(total/count,6)
    return mad

def render_json(result,path):
    with open(path,"w",encoding="utf-8") as f: json.dump(result,f,indent=2,ensure_ascii=False)

def render_csv(bracket,sim,path):
    rows=[]
    pts_map={"group_placement":1,"round_of_32":1,"round_of_16":2,"quarter_finals":4,"semi_finals":6,"finalists":10,"winner":15}
    pr_map={"group_placement":"placement","round_of_32":"r32","round_of_16":"r16","quarter_finals":"qf","semi_finals":"sf","finalists":"final","winner":"champion"}
    for gl in sorted(bracket["group_placements"].keys()):
        for slot,t in enumerate(bracket["group_placements"][gl]):
            p=sim.get("placement",{}).get(t,{}).get(slot+1,0); pt=pts_map["group_placement"]
            rows.append({"stage":"group_placement","group":gl,"slot":str(slot+1),"team":t,"reach_prob":round(p,6),"points_if_correct":pt,"expected_points":round(p*pt,6)})
    for stage in ["round_of_32","round_of_16","quarter_finals","semi_finals","finalists"]:
        for t in sorted(bracket.get(stage,[])):
            p=sim.get(pr_map[stage],{}).get(t,0); pt=pts_map[stage]
            rows.append({"stage":stage,"group":"","slot":"","team":t,"reach_prob":round(p,6),"points_if_correct":pt,"expected_points":round(p*pt,6)})
    w=bracket.get("winner","")
    if w:
        p=sim.get("champion",{}).get(w,0); pt=pts_map["winner"]
        rows.append({"stage":"winner","group":"","slot":"","team":w,"reach_prob":round(p,6),"points_if_correct":pt,"expected_points":round(p*pt,6)})
    with open(path,"w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=["stage","group","slot","team","reach_prob","points_if_correct","expected_points"])
        w.writeheader(); w.writerows(rows)

def render_md(bracket,sim,config,mad,path):
    L=[]
    L.append("# 2026 World Cup Bracket Analysis\n")
    L.append(f"**Generated:** {datetime.now(timezone.utc).isoformat()}\n")
    L.append(f"**Model:** {config['model']} | **Sims:** {config['sims']:,} | **Seed:** {config['seed']}\n")
    score=compute_score(bracket,sim)
    L.append(f"**Expected Score:** {score:.2f} / 203\n")
    L.append("## Source Weights\n"); L.append("| Source | Weight |"); L.append("|---|---|")
    for s,w in SOURCE_WEIGHTS.items(): L.append(f"| {s} | {w:.2f} |")
    L.append("")
    L.append("## Group Placements\n")
    L.append("| Group | 1st | 2nd | 3rd | 4th |")
    L.append("|---|---|---|---|---|")
    for g in sorted(bracket["group_placements"].keys()):
        teams=bracket["group_placements"][g]; probs=[]
        for i,t in enumerate(teams):
            p=sim.get("placement",{}).get(t,{}).get(i+1,0)
            probs.append(f"{t} ({p*100:.1f}%)")
        L.append(f"| {g} | {' | '.join(probs)} |")
    L.append("")
    for stage,label in [("round_of_32","Round of 32"),("round_of_16","Round of 16"),("quarter_finals","Quarter-Finals"),("semi_finals","Semi-Finals"),("finalists","Finalists")]:
        teams=sorted(bracket.get(stage,[]))
        if teams:
            L.append(f"## {label} ({len(teams)} teams)\n")
            pk={"round_of_32":"r32","round_of_16":"r16","quarter_finals":"qf","semi_finals":"sf","finalists":"final"}[stage]
            for t in teams:
                p=sim.get(pk,{}).get(t,0)
                L.append(f"- {t} ({p*100:.1f}%)")
            L.append("")
    w=bracket.get("winner","")
    if w:
        p=sim.get("champion",{}).get(w,0)
        L.append(f"## Champion: {w} ({p*100:.1f}%)\n")
    L.append("## Top Champion Probabilities\n")
    L.append("| Team | Probability |"); L.append("|---|---|")
    for t,p in sorted(sim.get("champion",{}).items(),key=lambda x:-x[1])[:10]:
        L.append(f"| {t} | {p*100:.1f}% |")
    L.append("")
    if mad:
        L.append("## Validation vs UAnalyse Priors (MAD)\n")
        L.append("| Stage | MAD |"); L.append("|---|---|")
        for s,v in mad.items(): L.append(f"| {s} | {v:.4f} |")
        L.append("")
    L.append("## Known Data Issues\n")
    L.append("- Bosnia & Herzegovina canonicalized to Bosnia and Herzegovina")
    L.append("- Curaçao / Curacao canonicalized to Curaçao")
    L.append("- Polymarket coverage limited (6 matches with 3-outcome markets)")
    L.append("- FIFA 2026 third-place allocation table not available; using greedy fallback")
    with open(path,"w",encoding="utf-8") as f: f.write("\n".join(L))

def main():
    parser=argparse.ArgumentParser(description="World Cup 2026 Bracket Generator")
    parser.add_argument("--sims",type=int,default=50000)
    parser.add_argument("--seed",type=int,default=42)
    parser.add_argument("--model",choices=["consensus","elo","poisson"],default="consensus")
    parser.add_argument("--strategy",choices=["ev-bracket","greedy"],default="ev-bracket")
    parser.add_argument("--probabilities",choices=["sim","blend"],default="sim")
    parser.add_argument("--out",default="_data/bracket")
    parser.add_argument("--formats",default="csv,json,md")
    parser.add_argument("--dry-run",action="store_true")
    args=parser.parse_args()
    out_stem=args.out
    for ext in [".json",".csv",".md"]:
        if out_stem.endswith(ext): out_stem=out_stem[:-len(ext)]
    formats=[f.strip() for f in args.formats.split(",")]
    print("="*60); print("World Cup 2026 Bracket Generator"); print("="*60)
    print("\nLoading data...")
    odds=load_odds(); fixtures=load_fixtures(); elo=load_elo(); xg=load_xg(); priors=load_priors()
    print(f"  Odds: {len(odds)}, Elo: {len(elo)}, xG: {len(xg)}, Priors: {len(priors)}")
    groups,gfix,knockout=parse_bracket(fixtures["matches"])
    print(f"  Groups: {len(groups)}, Knockout: {len(knockout)}")
    consensus=build_consensus(odds)
    print(f"  Consensus: {len(consensus)} matches")
    if args.dry_run:
        print("\n*** DRY RUN ***"); return
    print(f"\nSimulating {args.sims:,} iterations...")
    sim=simulate(groups,gfix,knockout,consensus,elo,xg,args.sims,args.seed,args.model)
    print("  Done.")
    print("\nOptimizing...")
    gplacements=optimize_groups(groups,sim)
    rng=random.Random(args.seed)
    ko=fill_knockout_bracket(gplacements,sim,consensus,elo,groups,gfix,knockout,rng)
    bracket={"group_placements":gplacements,"round_of_32":sorted(ko["r32"]),"round_of_16":sorted(ko["r16"]),"quarter_finals":sorted(ko["qf"]),"semi_finals":sorted(ko["sf"]),"finalists":sorted(ko["final"]),"winner":ko["champion"]}
    score=compute_score(bracket,sim)
    bracket["expected_score"]=score
    print("\nValidating...")
    errs=validate(bracket,groups,sim)
    for e in errs: print(f"  ERROR: {e}")
    if not errs: print("  All invariants passed.")
    mad=compute_mad(sim,priors)
    result={"generated_at":datetime.now(timezone.utc).isoformat(),"config":{"sims":args.sims,"seed":args.seed,"model":args.model,"strategy":args.strategy,"probabilities":args.probabilities},"expected_score":score,"group_placements":bracket["group_placements"],"round_of_32":bracket["round_of_32"],"round_of_16":bracket["round_of_16"],"quarter_finals":bracket["quarter_finals"],"semi_finals":bracket["semi_finals"],"finalists":bracket["finalists"],"winner":bracket["winner"],"validation":{"errors":errs,"mad_vs_uanalyse":mad}}
    print(f"\nWriting outputs...")
    if "json" in formats: render_json(result,f"{out_stem}.json"); print(f"  {out_stem}.json")
    if "csv" in formats: render_csv(bracket,sim,f"{out_stem}.csv"); print(f"  {out_stem}.csv")
    if "md" in formats: render_md(bracket,sim,result["config"],mad,f"{out_stem}.md"); print(f"  {out_stem}.md")
    print(f"\n{'='*60}\nExpected Score: {score:.2f} / 203\nWinner: {bracket['winner']}")
    if mad: print(f"MAD: {', '.join(f'{s}={v:.4f}' for s,v in mad.items())}")
    print("="*60)

if __name__=="__main__": main()
