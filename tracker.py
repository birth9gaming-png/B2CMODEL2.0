"""Every pick the app SHOWS you, saved the first time it appears and graded when the game ends.

So we can see, week by week, whether 🟢 picks beat 🟡 ones, whether your-style picks win, whether
teaser legs hit - without you logging anything.  Saved to storage at shown/{league}/{season}_{week}.json.
"""
from __future__ import annotations
import numpy as np
import pandas as pd


def _key(league, season, week):
    return f'shown/{league}/{int(season)}_{int(week):02d}.json'


def record(store, league: str, section: str, picks: list[dict]):
    """picks: dicts with id, season, week, kickoff, team, side, kind (spread/alt spread/moneyline/teaser),
    leg_line (the number shown; None for moneyline), verdict.  Only the first sighting of a pick is kept,
    and only before kickoff."""
    now = pd.Timestamp.now(tz='UTC')
    by_week = {}
    for p in picks:
        if p.get('season') is None or p.get('week') is None or pd.isna(p.get('season')) or pd.isna(p.get('week')):
            continue
        ko = pd.Timestamp(p['kickoff']) if p.get('kickoff') is not None else None
        if ko is not None and ko <= now:
            continue
        by_week.setdefault((int(p['season']), int(p['week'])), []).append(p)
    for (s, w), ps in by_week.items():
        k = _key(league, s, w)
        cur = store.get_json(k) or {'picks': []}
        seen = {(x['section'], str(x['id']), x['side']) for x in cur['picks']}
        changed = False
        for p in ps:
            sig = (section, str(p['id']), p['side'])
            if sig in seen:
                continue
            leg = p.get('leg_line')
            cur['picks'].append(dict(section=section, id=str(p['id']), side=p['side'], team=p['team'],
                                     kind=p.get('kind', 'spread'), leg_line=None if leg is None or pd.isna(leg) else float(leg),
                                     verdict=p.get('verdict'), shown_at=now.isoformat(), kickoff=str(p.get('kickoff'))))
            seen.add(sig); changed = True
        if changed:
            store.put_json(k, cur)


def graded(store, league: str, games: pd.DataFrame) -> pd.DataFrame:
    """Every shown pick with its result (W/L/P) once the game is final."""
    keys = store.list(f'shown/{league}/')
    rows = []
    for k in keys:
        for p in (store.get_json(k) or {}).get('picks', []):
            rows.append(p)
    if not rows:
        return pd.DataFrame()
    d = pd.DataFrame(rows)
    g = games.copy(); g['id'] = g['id'].astype(str)
    g = g.set_index('id')
    res = []
    for p in d.itertuples():
        if p.id not in g.index:
            res.append(None); continue
        x = g.loc[p.id]
        if not bool(x['completed']) or pd.isna(x['away_score']) or pd.isna(x['home_score']):
            res.append(None); continue
        margin = (x['away_score'] - x['home_score']) * (1 if p.side == 'away' else -1)
        v = margin if p.kind == 'moneyline' else margin + (p.leg_line or 0.0)
        res.append('W' if v > 0 else 'L' if v < 0 else 'P')
    d['result'] = res
    return d


def summary(d: pd.DataFrame) -> pd.DataFrame:
    """Record by section and verdict."""
    if d.empty or 'result' not in d:
        return pd.DataFrame()
    x = d[d['result'].isin(['W', 'L'])]
    if x.empty:
        return pd.DataFrame()
    t = x.groupby(['section', 'verdict'], dropna=False)['result'].agg(
        W=lambda s: int((s == 'W').sum()), L=lambda s: int((s == 'L').sum())).reset_index()
    t['Win %'] = (100 * t.W / (t.W + t.L)).round(1)
    t['verdict'] = t['verdict'].fillna('—')
    return t
