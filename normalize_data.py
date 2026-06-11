#!/usr/bin/env python3
"""Normalize all raw World Cup 2026 odds data into a common schema."""

import csv, json, re, sys
from pathlib import Path
from datetime import datetime, timezone

RAW = Path("_data/raw")
NORM = Path("_data/norm")
NORM.mkdir(parents=True, exist_ok=True)
rows = []
stats = {}

FIELDS = [
    "source","match_id","home_team","away_team","group","date",
    "home_win_prob","draw_prob","away_win_prob",
    "home_win_odds","draw_odds","away_win_odds","extra",
]

ALIASES = {
    "czech republic":"Czech Republic","czechia":"Czech Republic",
    "south korea":"South Korea","korea republic":"South Korea",
    "bosnia-herzegovina":"Bosnia and Herzegovina",
    "bosnia herzegovina":"Bosnia and Herzegovina",
    "bosnia and herzegovina":"Bosnia and Herzegovina",
    "united states":"USA","usa":"USA",
    "turkiye":"Turkey","turkiye":"Turkey",
    "ivory coast":"Ivory Coast","cote d'ivoire":"Ivory Coast",
    "cape verde":"Cape Verde","cabo verde":"Cape Verde",
    "d-r congo":"DR Congo","dr congo":"DR Congo","d.r. congo":"DR Congo",
    "saudi arabia":"Saudi Arabia","new zealand":"New Zealand",
    "uzbekistan":"Uzbekistan","jordan":"Jordan","algeria":"Algeria",
    "senegal":"Senegal","norway":"Norway","iran":"Iran","haiti":"Haiti",
    "curacao":"Curaçao","curaçao":"Curaçao","tunisia":"Tunisia",
    "panama":"Panama","ghana":"Ghana","morocco":"Morocco","egypt":"Egypt",
    "ecuador":"Ecuador","paraguay":"Paraguay","uruguay":"Uruguay",
    "colombia":"Colombia","japan":"Japan","sweden":"Sweden",
    "netherlands":"Netherlands","germany":"Germany","belgium":"Belgium",
    "spain":"Spain","france":"France","england":"England",
    "portugal":"Portugal","argentina":"Argentina","brazil":"Brazil",
    "mexico":"Mexico","canada":"Canada","switzerland":"Switzerland",
    "austria":"Austria","croatia":"Croatia","scotland":"Scotland",
    "south africa":"South Africa","qatar":"Qatar","iraq":"Iraq",
}

def nteam(name):
    if not name: return name
    name = re.sub(r"[^\x00-\x7F]+", "", name).strip()
    name = re.sub(r"\s*\(.*?\)\s*$", "", name).strip()
    return ALIASES.get(name.lower(), name)

def mid(h, a):
    h2 = re.sub(r"[^\w]","_",nteam(h).lower())
    a2 = re.sub(r"[^\w]","_",nteam(a).lower())
    h2 = re.sub(r"_+","_",h2).strip("_")
    a2 = re.sub(r"_+","_",a2).strip("_")
    return f"{h2}_vs_{a2}"

def pfromo(h,d,a):
    try:
        hp,dp,ap = 1.0/float(h), 1.0/float(d), 1.0/float(a)
        o = hp+dp+ap
        return round(hp/o,6), round(dp/o,6), round(ap/o,6)
    except: return None,None,None

def add(**kw):
    r = {k: kw.get(k) for k in FIELDS}
    if r["extra"] and not isinstance(r["extra"], str):
        r["extra"] = json.dumps(r["extra"])
    rows.append(r)

def log(src, n):
    stats[src] = n
    print(f"  {src}: {n} rows")

def _load_json_arrays(obj):
    """Parse stringified JSON arrays in Polymarket data."""
    if isinstance(obj, str):
        try: return json.loads(obj)
        except: return obj
    return obj

def parse_betexplorer():
    print("\n--- BetExplorer ---")
    p = RAW/"betexplorer"/"world-cup-calendar.ics"
    if not p.exists(): print("  [SKIP]"); return
    content = re.sub(r"\r?\n ","",p.read_text())
    events = re.findall(r"BEGIN:VEVENT(.*?)END:VEVENT",content,re.DOTALL)
    c = 0
    for ev in events:
        dm = re.search(r"DESCRIPTION:(.*?)(?:\r?\n[A-Z-]+:|$)",ev,re.DOTALL)
        if not dm: continue
        t = dm.group(1)
        om = re.search(r"Average odds:\s*([\d.]+)/([\d.]+)/([\d.]+)",t)
        if not om: continue
        ho,do,ao = float(om.group(1)),float(om.group(2)),float(om.group(3))
        ht = at = None
        sm = re.search(r"SUMMARY:(.*?)(?:\r?\n|$)",ev)
        if sm:
            s = sm.group(1).strip()
            for sep in [" vs "," - "," v "]:
                if sep in s:
                    pts = s.split(sep,1)
                    if len(pts)==2: ht,at = pts[0].strip(),pts[1].strip(); break
        if not ht: continue
        ds = re.search(r"DTSTART[^:]*:(\d{8})",ev)
        dt = f"{ds.group(1)[:4]}-{ds.group(1)[4:6]}-{ds.group(1)[6:8]}" if ds else ""
        gm = re.search(r"Group ([A-L])",t)
        g = gm.group(1) if gm else ""
        hp,dp,ap = pfromo(ho,do,ao)
        ht,at = nteam(ht),nteam(at)
        add(source="betexplorer",match_id=mid(ht,at),home_team=ht,away_team=at,
            group=g,date=dt,home_win_prob=hp,draw_prob=dp,away_win_prob=ap,
            home_win_odds=ho,draw_odds=do,away_win_odds=ao)
        c += 1
    log("betexplorer",c)

def parse_uanalyse():
    print("\n--- uanalyse ---")
    p = RAW/"uanalyse"/"latest"/"match_predictions.csv"
    if not p.exists(): print("  [SKIP]"); return
    c = 0
    with open(p,newline="",encoding="utf-8") as f:
        for r in csv.DictReader(f):
            h,a = nteam(r.get("home_team","")),nteam(r.get("away_team",""))
            if not h or not a: continue
            st = r.get("stage",""); g = ""
            m2 = re.search(r"Group ([A-L])",st)
            if m2: g = m2.group(1)
            add(source="uanalyse",match_id=mid(h,a),home_team=h,away_team=a,
                group=g,date=r.get("kickoff_date",""),
                home_win_prob=round(float(r.get("prob_home_win",0) or 0),6),
                draw_prob=round(float(r.get("prob_draw",0) or 0),6),
                away_win_prob=round(float(r.get("prob_away_win",0) or 0),6),
                extra={"snapshot":r.get("snapshot_date",""),"stage":st,
                       "xhg":r.get("exp_home_goals"),"xag":r.get("exp_away_goals")})
            c += 1
    log("uanalyse",c)

def parse_wcpredictor():
    print("\n--- worldcup-predictor ---")
    p = RAW/"worldcup-predictor"/"wc2026_predictions.csv"
    if not p.exists(): print("  [SKIP]"); return
    c = 0
    with open(p,newline="",encoding="utf-8") as f:
        for r in csv.DictReader(f):
            h,a = nteam(r.get("home_team","")),nteam(r.get("away_team",""))
            if not h or not a: continue
            add(source="worldcup-predictor",match_id=mid(h,a),home_team=h,away_team=a,
                date=r.get("date",""),
                home_win_prob=round(float(r.get("p_home",0) or 0),6),
                draw_prob=round(float(r.get("p_draw",0) or 0),6),
                away_win_prob=round(float(r.get("p_away",0) or 0),6),
                extra={"elo_h":r.get("elo_home"),"elo_a":r.get("elo_away"),
                       "neutral":r.get("neutral"),"city":r.get("city",""),
                       "pick":r.get("pick","")})
            c += 1
    log("worldcup-predictor",c)

def parse_polymarket():
    print("\n--- Polymarket ---")
    p = RAW/"polymarket"/"fifa-wc-match-events-fixed.json"
    if not p.exists(): print("  [SKIP]"); return
    with open(p) as f: events = json.load(f)
    c = 0
    for ev in events:
        title = ev.get("title",""); et = title.lower()
        skip_keywords = ["exact score","more markets","spread","o/u","over/under",
                         "both teams","team to advance","knockout"]
        if any(x in et for x in skip_keywords): continue
        ht = at = None
        for sep in [" vs. "," vs "," - "," @ "]:
            if sep in title:
                pts = title.split(sep,1)
                if len(pts)==2: ht,at = pts[0].strip(),pts[1].strip(); break
        if not ht: continue
        # Normalize team names for comparison
        nht = nteam(ht).lower()
        nat = nteam(at).lower()
        hp = dp = ap = None
        for m in ev.get("markets",[]):
            q = m.get("question","").lower()
            outs = _load_json_arrays(m.get("outcomes",[]))
            prs = _load_json_arrays(m.get("outcomePrices",[]))
            if not isinstance(outs, list) or not isinstance(prs, list): continue
            if len(outs)!=2 or len(prs)!=2: continue
            try: yp = float(prs[0])
            except: continue
            if "end in a draw" in q:
                dp = yp
            elif "will" in q and "win" in q:
                tm = re.match(r"will (.+?) win on",q)
                if tm:
                    tn = tm.group(1).strip().lower()
                    ntn = nteam(tn).lower() if tn else tn
                    # Match against normalized team names
                    if ntn == nht or ntn in nht or nht in ntn:
                        hp = yp
                    elif ntn == nat or ntn in nat or nat in ntn:
                        ap = yp
        ht,at = nteam(ht),nteam(at)
        ds = ev.get("startDate","")[:10] if ev.get("startDate") else ""
        add(source="polymarket",match_id=mid(ht,at),home_team=ht,away_team=at,
            date=ds,
            home_win_prob=round(hp,6) if hp is not None else None,
            draw_prob=round(dp,6) if dp is not None else None,
            away_win_prob=round(ap,6) if ap is not None else None,
            extra={"slug":ev.get("slug",""),"n_markets":len(ev.get("markets",[]))})
        c += 1
    log("polymarket",c)

def parse_openfootball():
    print("\n--- openfootball ---")
    p = RAW/"openfootball"/"worldcup-2026.json"
    if not p.exists(): print("  [SKIP]"); return
    with open(p) as f: data = json.load(f)
    c = 0
    for m in data.get("matches",[]):
        h,a = nteam(m.get("team1","")),nteam(m.get("team2",""))
        if not h or not a: continue
        g = m.get("group","")
        if g.startswith("Group "): g = g.replace("Group ","")
        add(source="openfootball",match_id=mid(h,a),home_team=h,away_team=a,
            group=g,date=m.get("date",""),
            extra={"round":m.get("round",""),"time":m.get("time",""),
                   "ground":m.get("ground","")})
        c += 1
    log("openfootball",c)

def parse_fivethirtyeight():
    print("\n--- FiveThirtyEight ---")
    print("  [INFO] Tournament-level data only — skipping")
    log("fivethirtyeight-2014",0)

def parse_oddsharvester():
    print("\n--- OddsHarvester ---")
    cp = RAW/"oddsharvester"/"worldcup-2026-odds.csv"
    if not cp.exists(): print("  [SKIP]"); return
    c = 0
    with open(cp,newline="",encoding="utf-8") as f:
        for r in csv.DictReader(f):
            h,a = nteam(r.get("home_team","")),nteam(r.get("away_team",""))
            if not h or not a: continue
            ds = r.get("match_date","")[:10]
            ms = r.get("1x2_market","")
            bks = []
            try: bks = json.loads(ms.replace("'",'"'))
            except: pass
            h2,d2,a2 = [],[],[]
            for b in bks:
                try:
                    h2.append(float(b.get("1",0)))
                    d2.append(float(b.get("X",0)))
                    a2.append(float(b.get("2",0)))
                except: pass
            ah = round(sum(h2)/len(h2),2) if h2 else None
            ad = round(sum(d2)/len(d2),2) if d2 else None
            aa = round(sum(a2)/len(a2),2) if a2 else None
            hp,dp,ap = pfromo(ah,ad,aa) if (ah and ad and aa) else (None,None,None)
            add(source="oddsharvester",match_id=mid(h,a),home_team=h,away_team=a,
                date=ds,home_win_prob=hp,draw_prob=dp,away_win_prob=ap,
                home_win_odds=ah,draw_odds=ad,away_win_odds=aa,
                extra={"n_bookies":len(bks),
                       "bookmakers":[b.get("bookmaker_name","") for b in bks],
                       "url":r.get("match_link",""),"venue":r.get("venue","")})
            c += 1
    log("oddsharvester",c)

def write_output():
    print("\n--- Writing ---")
    op = NORM/"all_odds_normalized.csv"
    with open(op,"w",newline="",encoding="utf-8") as f:
        w = csv.DictWriter(f,fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    print(f"  {len(rows)} rows -> {op}")
    report = {"generated_at":datetime.now(timezone.utc).isoformat(),
              "total_rows":len(rows),"sources":stats,
              "unique_matches":len(set(r["match_id"] for r in rows))}
    (NORM/"normalization_report.json").write_text(json.dumps(report,indent=2))
    print(f"\n{'='*50}\nDone: {len(rows)} rows, {report['unique_matches']} unique matches")
    for s,n in stats.items(): print(f"  {s}: {n}")

def main():
    print("="*60); print("World Cup 2026 — Normalizer"); print("="*60)
    parse_betexplorer(); parse_uanalyse(); parse_wcpredictor()
    parse_polymarket(); parse_openfootball(); parse_fivethirtyeight()
    parse_oddsharvester(); write_output()

if __name__ == "__main__": main()
