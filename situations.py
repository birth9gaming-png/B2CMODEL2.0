"""'Games like this since 2016': the record of every kind of side against the closing line.

Each side you look at is described a few ways (favorite/underdog, home/road/neutral, who is ranked,
line size, rivalry, the opponent's lookahead/letdown spot, primetime).  situations.json holds the
2016-2025 record for each description (college: games with a power-conference team).

A description only counts as a red flag when sides like it lost in BOTH halves of the decade
(48% or worse in 2016-2020 AND in 2021-2025, 40+ games each), and as a green flag when they won 55%+ in
both.  Tested Oct 20 2026: one-off losing records (flagged from all ten years at once) did not hold up on
later seasons (50.5%), so they are shown as records only.  52.4% is what -110 bets need to break even.
"""
from __future__ import annotations
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
MIN_HALF = 40
BAD, GOOD = 0.48, 0.55
_TABLES = None


def _bucket(league: str, absl: float) -> str:
    if league == 'CFB':
        return '0-3.5' if absl <= 3.5 else '4-7' if absl <= 7 else '7.5-14' if absl <= 14 else '14.5+'
    return '0-3' if absl <= 3 else '3.5-7' if absl <= 7 else '7.5+'


def keys_for(league: str, r: dict) -> list[tuple[str, str]]:
    """(dimension, key) pairs describing one side.  r: side features (style.side_features columns)."""
    line = r.get('line')
    if line is None or line != line or line == 0:
        return []
    role = 'fav' if line < 0 else 'dog'
    venue = 'home' if r.get('home') else 'road' if r.get('road') else 'neutral'
    out = [('line', f'{role}|{venue}|{_bucket(league, abs(line))}')]
    if league == 'CFB':
        me, opp = bool(r.get('own_rank')), bool(r.get('opp_rank'))
        ranks = 'both' if me and opp else 'me' if me else 'opp' if opp else 'none'
        out.append(('matchup', f'{role}|{venue}|{ranks}'))
        if r.get('rival'):
            out.append(('rivalry', f"{role}|{venue}|{'ranked' if opp else 'unranked'}"))
    else:
        if r.get('rival'):
            out.append(('division', f'{role}|{venue}'))
        if r.get('primetime', r.get('night')):
            out.append(('primetime', f'{role}|{venue}'))
    if r.get('opp_look'):
        out.append(('spot', f'{role}|{venue}|opp_lookahead'))
    if r.get('opp_letdown'):
        out.append(('spot', f'{role}|{venue}|opp_letdown'))
    return out


def describe(league: str, dim: str, key: str) -> str:
    parts = key.split('|')
    role = {'fav': 'favorites', 'dog': 'underdogs'}[parts[0]]
    venue = {'home': 'home', 'road': 'road', 'neutral': 'neutral-site'}[parts[1]]
    who = f'{venue} {role}'
    if dim == 'line':
        return f"{who} of {parts[2]} pts"
    if dim == 'matchup':
        return {'both': f'{who} in a ranked-vs-ranked game', 'me': f'ranked {who} vs an unranked team',
                'opp': f'unranked {who} vs a ranked team', 'none': f'{who}, neither team ranked'}[parts[2]]
    if dim == 'rivalry':
        return f"{who} in a rivalry game vs a{' ranked' if parts[2] == 'ranked' else 'n unranked'} team"
    if dim == 'division':
        return f'{who} in a division game'
    if dim == 'primetime':
        return f'{who} in primetime'
    if dim == 'spot':
        return f"{who} vs an opponent in a {'lookahead' if parts[2] == 'opp_lookahead' else 'letdown'} spot"
    return key


def verdict_of(*rec) -> str | None:
    """rec = (w_2016_20, l_2016_20, w_2021_25, l_2021_25)."""
    if len(rec) != 4:
        return None
    wa, la, wb, lb = rec
    if wa + la < MIN_HALF or wb + lb < MIN_HALF:
        return None
    ra, rb = wa / (wa + la), wb / (wb + lb)
    if ra <= BAD and rb <= BAD:
        return 'bad'
    if ra >= GOOD and rb >= GOOD:
        return 'good'
    return None


def tables() -> dict:
    global _TABLES
    if _TABLES is None:
        p = HERE / 'situations.json'
        _TABLES = json.loads(p.read_text())['tables'] if p.exists() else {}
    return _TABLES


def lookup(league: str, r: dict) -> list[dict]:
    """Every description of this side with its record since 2016, worst first."""
    t = tables().get(league, {})
    out = []
    for dim, key in keys_for(league, r):
        rec = t.get(dim, {}).get(key, [0, 0, 0, 0])
        w, l = rec[0] + rec[2], rec[1] + rec[3]
        if w + l == 0:
            continue
        out.append(dict(dim=dim, key=key, text=describe(league, dim, key), w=w, l=l, rate=w / (w + l),
                        verdict=verdict_of(*rec)))
    return sorted(out, key=lambda x: x['rate'])
