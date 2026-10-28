"""What has actually beaten the closing line, measured on 2016-2025 games (Oct 16 2026).

The Vegas-anchored model starts at the market line and only moves off it for these spots.
Every reason shown in the app carries its real record from the same test, so you can see which
of your spots are proven and which are just context.

How it was measured: every game side in power-conference games (college) / every game (NFL),
graded against the CLOSING spread, using our own definitions of each spot (rules.py).
"""
from __future__ import annotations
import numpy as np
import pandas as pd

# points the anchored model moves toward the side (about half the side's average cover margin - shrunk)
PROVEN = {
    # Oct 20 2026: split by venue - the edge is all HOME favorites (road ones went 61-65, 48.4%)
    'CFB': {'rvr_fav': dict(pts=2.0, rate=0.623, record='134-81', label='HOME favorite in a ranked-vs-ranked game'),
            # held in both halves: 2016-20 62-36 (63%), 2021-25 63-43 (59%)
            'rival_road_fav': dict(pts=1.5, rate=0.613, record='125-79',
                                   label='ROAD favorite in a rivalry game vs an unranked team')},
    # home dogs 156-126 (55.3%); road dogs only 211-189 (52.8%), so road dogs no longer count
    'NFL': {'dog_vs_look': dict(pts=1.0, rate=0.553, record='156-126',
                                label='HOME underdog vs a favorite looking ahead (borderline)')},
}
# your other spots, same test (context - not proven on their own)
RECORDS = {
    'CFB': {'lookahead': ('50.1%', '841-837'), 'letdown': ('48.8%', '250-262'), 'trap': ('51.5%', '53-50'),
            'move': ('50.8%', '1335-1295'), 'rival_fav': ('52.8%', '314-281')},
    'NFL': {'lookahead': ('51.1%', '582-557'), 'letdown': ('49.8%', '211-213'), 'trap': ('47.0%', '55-62'),
            'move': (None, None), 'rival_fav': ('48.4%', '455-486')},
}
# the stats model's gap with the market barely comes true (slope 0.03-0.06 in college, none in the NFL)
STATS_WEIGHT = {'CFB': 0.05, 'NFL': 0.0}


def record_text(league: str, key: str) -> str:
    rate, rec = RECORDS.get(league, {}).get(key, (None, None))
    return f' ({rate} since 2016)' if rate else ''


def proven_for_side(league: str, side: str, fl: dict, line_side: float, neutral: bool = False) -> list[dict]:
    """Proven spots backing `side` (fl = rules.flag_games row as a dict)."""
    other = 'home' if side == 'away' else 'away'
    out = []
    if line_side is None or pd.isna(line_side):
        return out
    at_home = side == 'home' and not neutral
    if league == 'CFB':
        if fl.get(f'{side}_rank') is not None and pd.notna(fl.get(f'{side}_rank')) and \
                fl.get(f'{other}_rank') is not None and pd.notna(fl.get(f'{other}_rank')) and line_side < 0 and at_home:
            out.append(dict(key='rvr_fav', **PROVEN['CFB']['rvr_fav']))
        opp_ranked = fl.get(f'{other}_rank') is not None and pd.notna(fl.get(f'{other}_rank'))
        if fl.get('rival') and side == 'away' and not neutral and line_side < 0 and not opp_ranked:
            out.append(dict(key='rival_road_fav', **PROVEN['CFB']['rival_road_fav']))
    else:
        if line_side > 0 and fl.get(f'{other}_lookahead') and at_home:
            out.append(dict(key='dog_vs_look', **PROVEN['NFL']['dog_vs_look']))
    return out


def anchor(slate: pd.DataFrame, flags: dict, league: str) -> pd.DataFrame:
    """Vegas-anchored model line for every game.

    model_home = market home spread
                 - points for proven spots backing home  + points for proven spots backing away
                 + a small slice of the stats model's disagreement (STATS_WEIGHT)
    Most games land exactly on the market; the few that don't are the bets."""
    s = slate.copy()
    adj, notes = [], []
    for r in s.to_dict('records'):
        cur = r.get('current_home')
        fl = flags.get(r['id'], {})
        a, n = 0.0, {'away': [], 'home': []}
        if cur is not None and pd.notna(cur):
            for side in ('away', 'home'):
                line_side = -cur if side == 'away' else cur
                for p in proven_for_side(league, side, fl, line_side, bool(r.get('neutral'))):
                    a += p['pts'] if side == 'away' else -p['pts']     # +: model likes away more than market
                    n[side].append(p)
        adj.append(a); notes.append(n)
    s['proven_adjust'] = adj
    s['proven'] = notes
    w = STATS_WEIGHT.get(league, 0.0)
    stats_gap = (s['stats_home'] - s['current_home']).fillna(0.0)
    s['model_home'] = s['current_home'] + s['proven_adjust'] + w * stats_gap
    return s


def side_prob(league: str, row: dict, side: str) -> float:
    """Cover chance for `side`: the proven spot's record, else a coin flip."""
    ps = (row.get('proven') or {}).get(side) or []
    if ps:
        return float(np.mean([p['rate'] for p in ps])) - 0.01        # small shrink toward 50%
    return 0.5


# ---------------------------------------------------------------- is this a bad play?
def side_situation(league: str, row: dict, side: str) -> dict:
    """The side described the way situations.py needs it, from a board row (with rule_flags)."""
    other = 'home' if side == 'away' else 'away'
    fl = row.get('rule_flags') or {}
    cur = row.get('current_home')
    line = (-cur if side == 'away' else cur) if cur is not None and pd.notna(cur) else None
    neutral = bool(row.get('neutral'))
    ko = pd.Timestamp(row['kickoff']).tz_convert('America/New_York') if row.get('kickoff') is not None else None
    return dict(line=line, home=float(side == 'home' and not neutral), road=float(side == 'away' and not neutral),
                own_rank=float(pd.notna(fl.get(f'{side}_rank')) if fl.get(f'{side}_rank') is not None else 0),
                opp_rank=float(pd.notna(fl.get(f'{other}_rank')) if fl.get(f'{other}_rank') is not None else 0),
                rival=float(bool(fl.get('rival'))), opp_look=float(bool(fl.get(f'{other}_lookahead'))),
                opp_letdown=float(bool(fl.get(f'{other}_letdown'))),
                primetime=float(ko is not None and (ko.hour >= 19 or ko.dayofweek in (0, 3))))


def assess(league: str, row: dict, side: str) -> dict:
    """Verdict for betting `side`: Good play / Coin flip / Bad play, with the case for and against.

    Bad play  : sides like this have lost since 2016 (48.5% or worse over 80+ games), a proven spot backs the
                other team, a key player is out, the line moved 3+ points against you, or the sharpest books
                price your side a point+ cheaper than the market you'd bet into.
    Good play : a proven spot (⭐) or a winning situation (56%+) and nothing against.
    Coin flip : everything else - most games, because the Vegas line is usually right."""
    import situations
    other = 'home' if side == 'away' else 'away'
    sit = situations.lookup(league, side_situation(league, row, side))
    against, support = [], []
    star_mine = bool((row.get('proven') or {}).get(side))
    star_theirs = bool((row.get('proven') or {}).get(other))
    for x in sit:
        txt = f"{x['text']}: {x['w']}-{x['l']} ({100 * x['rate']:.1f}%) since 2016, losing in both halves" \
            if x['verdict'] == 'bad' else f"{x['text']}: {x['w']}-{x['l']} ({100 * x['rate']:.1f}%) since 2016, winning in both halves"
        if x['verdict'] == 'bad' and not star_theirs:          # (the ⭐ line below already says it)
            against.append(txt)
        elif x['verdict'] == 'good' and not star_mine:
            support.append(txt)
    for p in (row.get('proven') or {}).get(other) or []:
        against.append(f"⭐ proven spot on the other side — {p['label']}: {100 * p['rate']:.1f}% ({p['record']})")
    for p in (row.get('proven') or {}).get(side) or []:
        support.append(f"⭐ {p['label']}: {100 * p['rate']:.1f}% ({p['record']}) since 2016")
    inj = (row.get('injuries') or {}).get(side) or {}
    if inj.get('missing') or inj.get('qb_questionable'):
        against.append('key player out or QB questionable')
    mv = row.get('move_home')
    if mv is not None and pd.notna(mv):
        moved = float(mv) if side == 'home' else -float(mv)          # + = moved against this side
        if moved >= 3:
            against.append(f'line moved {moved:.1f} pts against them since the open (usually news)')
    cur, sharp = row.get('current_home'), row.get('sharp_home')
    if cur is not None and sharp is not None and pd.notna(cur) and pd.notna(sharp):
        mine, sh = (-cur, -sharp) if side == 'away' else (cur, sharp)
        if sh - mine >= 1.0:
            against.append(f'sharp books (Pinnacle etc.) have them {sh:+g} vs {mine:+g} where you would bet — '
                           f'you are paying {sh - mine:.1f} pts more than the sharpest price')
        elif mine - sh >= 1.0:
            support.append(f'sharp books have them {sh:+g} — you are getting {mine - sh:.1f} pts better than the sharpest price')
    verdict = 'Bad play' if against else 'Good play' if support else 'Coin flip'
    note = {'Good play': 'An edge that has held up since 2016 — still loses 4 in 10.',
            'Coin flip': 'No edge either way: the Vegas line is usually right here. Coin flips at -110 lose ~4.5% over time, '
                         'and more inside parlays.',
            'Bad play': 'The data is against this side — skip it or flip it.'}[verdict]
    return dict(verdict=verdict, against=against, support=support, situations=sit, note=note,
                icon=VERDICT_ICON[verdict])


VERDICT_ICON = {'Good play': '🟢', 'Coin flip': '🟡', 'Bad play': '🔴'}


# ---------------------------------------------------------------- your NFL angles (tested Oct 27 2026)
# Records vs the closing spread, 2016-2025 regular seasons (nflverse).  Small samples: shown as reasons
# with their records, they do NOT make a pick a 🟢 good play on their own.
NFL_ANGLES = {
    'vs_undefeated_home': dict(rate=0.627, record='32-19', label='home team vs an undefeated opponent'),
    'vs_undefeated': dict(rate=0.579, record='62-45', label='betting against an undefeated team'),
    'road_fav_worse': dict(rate=0.538, record='57-49', label='road favorite with the worse record'),
    'fav_worse': dict(rate=0.494, record='193-198', label='favored with the worse record'),
}
PUBLIC_PCT = 65          # % of DraftKings bets on one side = "the public is all over them"


def angle_count(reasons: list[str]) -> int:
    return sum(x.startswith('🏈') for x in reasons)


def _rec(fl, side):
    g, w = fl.get(f'{side}_games') or 0, fl.get(f'{side}_wins') or 0
    return w, g


def angle_reasons(league: str, row: dict, side: str) -> list[str]:
    """Your NFL angles that back `side`, each with its record."""
    if league != 'NFL':
        return []
    fl = row.get('rule_flags') or {}
    other = 'home' if side == 'away' else 'away'
    cur = row.get('current_home')
    if cur is None or pd.isna(cur):
        return []
    line = -cur if side == 'away' else cur
    (w, g), (ow, og) = _rec(fl, side), _rec(fl, other)
    out = []
    home = side == 'home' and not bool(row.get('neutral'))
    if og >= 3 and ow == og:
        a = NFL_ANGLES['vs_undefeated_home' if home else 'vs_undefeated']
        out.append(f"🏈 your angle — {a['label']}: {100 * a['rate']:.1f}% ({a['record']}) since 2016, small sample")
    if g >= 3 and og >= 3 and line < 0 and side == 'away' and w / g < ow / og:
        a = NFL_ANGLES['road_fav_worse']
        out.append(f"🏈 your angle — {a['label']}: {100 * a['rate']:.1f}% ({a['record']}) since 2016")
    elif g >= 3 and og >= 3 and line < 0 and w / g < ow / og:
        out.append(f"🏈 your angle — favored with the worse record ({w}-{g - w} vs {ow}-{og - ow}): "
                   f"{100 * NFL_ANGLES['fav_worse']['rate']:.1f}% ({NFL_ANGLES['fav_worse']['record']}) since 2016")
    # the public all over the other team (DraftKings bets %) - live only, no history to test yet
    spl = row.get('splits') or {}
    try:
        pct = float(spl[other]['bets'])
    except (KeyError, TypeError, ValueError):
        pct = None
    if pct is not None and pct >= PUBLIC_PCT:
        out.append(f"🏈 your angle — the public is all over {row.get(other, other)} ({pct:.0f}% of DraftKings bets); "
                   f"no splits history to test yet")
    return out
