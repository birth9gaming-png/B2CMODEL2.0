"""Tests for the Vegas-anchored proven spots, the 'games like this' records and the play verdicts."""
import sys, unittest
from pathlib import Path
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parent))

import proven, situations


def row(home_spread, away_rank=None, home_rank=None, rival=False, neutral=False, **kw):
    r = dict(id='g', current_home=home_spread, neutral=neutral, kickoff=pd.Timestamp('2026-10-17T19:30Z'),
             rule_flags=dict(away_rank=away_rank, home_rank=home_rank, rival=rival, **kw), move_home=0.0)
    s = proven.anchor(pd.DataFrame([dict(r, stats_home=home_spread)]), {'g': r['rule_flags']}, 'CFB').iloc[0].to_dict()
    return s


class TestProven(unittest.TestCase):
    def test_star_is_home_only(self):
        home_fav = row(-6.5, away_rank=12, home_rank=5)           # ranked home favorite vs ranked team
        self.assertEqual(len(home_fav['proven']['home']), 1)
        self.assertAlmostEqual(home_fav['model_home'], -8.5)       # model moves 2 pts toward the home favorite
        road_fav = row(9.5, away_rank=8, home_rank=7)             # Notre Dame -9.5 at BYU
        self.assertEqual(road_fav['proven'], {'away': [], 'home': []})
        self.assertAlmostEqual(road_fav['model_home'], 9.5)        # sits on the Vegas line

    def test_rivalry_road_favorite(self):
        r = row(10.5, away_rank=4, home_rank=None, rival=True)    # ranked road favorite at unranked rival
        self.assertEqual([p['key'] for p in r['proven']['away']], ['rival_road_fav'])
        a = proven.assess('CFB', r, 'home')                         # the home dog side is a bad play
        self.assertEqual(a['verdict'], 'Bad play')

    def test_verdicts(self):
        nd = row(9.5, away_rank=8, home_rank=7)
        self.assertEqual(proven.assess('CFB', nd, 'away')['verdict'], 'Coin flip')
        self.assertEqual(proven.assess('CFB', row(-6.5, away_rank=12, home_rank=5), 'home')['verdict'], 'Good play')
        self.assertEqual(proven.assess('CFB', row(-6.5, away_rank=12, home_rank=5), 'away')['verdict'], 'Bad play')
        moved = dict(nd, move_home=-3.5)                            # market moved 3.5 away from the road favorite
        self.assertEqual(proven.assess('CFB', moved, 'away')['verdict'], 'Bad play')
        sharp = dict(nd, sharp_home=8.0)                            # sharp books only have ND -8
        a = proven.assess('CFB', sharp, 'away')
        self.assertEqual(a['verdict'], 'Bad play')
        self.assertTrue(any('sharp' in x for x in a['against']))

    def test_flags_need_both_halves(self):
        self.assertEqual(situations.verdict_of(40, 60, 40, 60), 'bad')
        self.assertIsNone(situations.verdict_of(40, 60, 60, 40))   # flipped between halves: not a flag
        self.assertIsNone(situations.verdict_of(10, 20, 10, 20))   # too few games
        self.assertEqual(situations.verdict_of(60, 40, 58, 42), 'good')
        recs = situations.lookup('CFB', dict(line=-9.5, home=0.0, road=1.0, own_rank=1.0, opp_rank=1.0))
        self.assertTrue(any(x['text'] == 'road favorites in a ranked-vs-ranked game' for x in recs))


if __name__ == '__main__':
    unittest.main()


class TestNFL(unittest.TestCase):
    def nfl_row(self, home_spread, aw=(3, 3), hw=(1, 3), neutral=False):
        fl = dict(away_wins=aw[0], away_games=aw[1], home_wins=hw[0], home_games=hw[1], rival=False)
        return dict(id='n', away='SF', home='ATL', current_home=home_spread, neutral=neutral, season=2026, week=7,
                    kickoff=pd.Timestamp('2026-10-25T17:00Z'), rule_flags=fl, proven={'away': [], 'home': []},
                    move_home=0.0, injuries={})

    def test_public_and_worse_record(self):
        r = dict(self.nfl_row(3.0, aw=(5, 5), hw=(3, 6)),          # KC 5-0 at SEA, SEA -3
                 splits={'away': {'bets': 78.0, 'handle': 70.0}, 'home': {'bets': 22.0, 'handle': 30.0}})
        r['away'], r['home'] = 'KC', 'SEA'
        rs = proven.angle_reasons('NFL', r, 'home')
        self.assertTrue(any('undefeated' in x for x in rs))
        self.assertTrue(any('public is all over KC (78%' in x for x in rs))
        self.assertEqual(proven.angle_count(rs), 2)
        self.assertFalse(any('public' in x for x in proven.angle_reasons('NFL', r, 'away')))
        home_fav_worse = self.nfl_row(-3.0, aw=(4, 6), hw=(2, 6))   # home favorite with the worse record
        self.assertTrue(any('favored with the worse record' in x for x in proven.angle_reasons('NFL', home_fav_worse, 'home')))

    def test_never_more_than_two_points(self):
        import style
        for lg in ('CFB', 'NFL'):
            for line in [x / 2 for x in range(-50, 51)]:
                leg = style.how_you_play(None, line, lg)
                if leg['kind'] == 'alt spread':
                    self.assertLessEqual(abs(leg['leg_line'] - line), 2.0)

    def test_app_bets_count_as_history(self):
        import mypicks
        p = [dict(logged_at='2026-10-25T15:00:00+00:00', league='NFL', season=2026, week=7, game_id='g', away='KC',
                  home='SEA', team='SEA', side='home', line=-2.5, leg_kind='alt spread', status='open', result=None),
             dict(logged_at='2026-10-25T15:00:00+00:00', league='NFL', season=2026, week=7, game_id='h', away='SF',
                  home='ATL', team='ATL', side='home', line=0.0, leg_kind='moneyline', status='graded', result='W')]
        h = mypicks.ledger_as_history(p)
        self.assertEqual(list(h.kind), ['alt spread', 'moneyline'])
        self.assertEqual(h.result.iloc[1], 'W')
        self.assertTrue(pd.isna(h.result.iloc[0]))

    def test_your_angles(self):
        r = self.nfl_row(2.5)                                       # SF undefeated 3-0, ATL home
        self.assertTrue(any('home team vs an undefeated opponent' in x for x in proven.angle_reasons('NFL', r, 'home')))
        rams = dict(self.nfl_row(3.5, aw=(2, 5), hw=(3, 5)))        # road favorite with the worse record
        self.assertTrue(any('road favorite with the worse record' in x for x in proven.angle_reasons('NFL', rams, 'away')))
        self.assertEqual(proven.angle_reasons('CFB', r, 'home'), [])


class TestTracker(unittest.TestCase):
    def test_record_and_grade(self):
        import shutil, tempfile, tracker
        from storage import Store
        tmp = tempfile.mkdtemp()
        try:
            st = Store({}, local_dir=tmp)
            ko = pd.Timestamp.now(tz='UTC') + pd.Timedelta(days=2)
            p = [dict(id='g1', season=2026, week=8, kickoff=ko, team='ATL', side='home', kind='teaser', leg_line=8.5, verdict='Coin flip'),
                 dict(id='g2', season=2026, week=8, kickoff=ko, team='SEA', side='home', kind='spread', leg_line=-3.0, verdict='Good play')]
            tracker.record(st, 'NFL', 'Teaser legs', p)
            tracker.record(st, 'NFL', 'Teaser legs', [dict(p[0], leg_line=7.5)])        # second sighting ignored
            games = pd.DataFrame([dict(id='g1', completed=True, away_score=27, home_score=20),
                                  dict(id='g2', completed=True, away_score=3, home_score=20)])
            d = tracker.graded(st, 'NFL', games)
            self.assertEqual(len(d), 2)
            self.assertEqual(d.set_index('id').loc['g1', 'result'], 'W')                 # lost by 7 with +8.5
            self.assertEqual(d.set_index('id').loc['g1', 'leg_line'], 8.5)
            self.assertEqual(d.set_index('id').loc['g2', 'result'], 'W')
            self.assertEqual(int(tracker.summary(d).W.sum()), 2)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
