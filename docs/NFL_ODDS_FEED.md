# NFL line feed

Pulls spreads, totals and moneylines for every upcoming NFL game from
[The Odds API](https://the-odds-api.com/) on a schedule, saves each pull, and
builds line movement tables. Runs in GitHub Actions on the free plan.

## Files

```
nfl_odds/                         the package
.github/workflows/nfl_odds_feed.yml
requirements-odds.txt
```

## Setup

1. Get a free key at the-odds-api.com (Starter plan, 500 credits a month).
2. Repo **Settings → Secrets and variables → Actions → New repository secret**,
   name `ODDS_API_KEY`, value = the key.
3. Repo **Settings → Actions → General → Workflow permissions → Read and write**.
4. **Actions → NFL line feed → Run workflow** once to test.

## Schedule and credits

Every 6 hours plus extra pulls before the Sunday afternoon, Sunday night,
Monday night and Thursday night games (times are in the workflow file).
Each pull is 3 markets x 1 bookmaker group = 3 credits, so about 415 credits
a month. Games that have kicked off are excluded from every pull, so the last
saved pull before kickoff is the closing line. Before each pull the script
checks the balance (free call) and skips if fewer than 6 credits are left.

Bookmakers (up to 10 bill as one region): Pinnacle as the sharp reference,
plus DraftKings, FanDuel, BetMGM, BetRivers, theScore/ESPN Bet, BetOnline,
LowVig and Bovada. Change them in `nfl_odds/config.py`. bet365 is not
available for the NFL on The Odds API.

## Outputs (data/nfl/odds/)

| File | What it is |
|---|---|
| snapshots/<season>/<time>.csv.gz | Every price from every book in that pull |
| latest/summary.md | Readable board: flags, open vs now, Pinnacle, best prices |
| latest/line_movement.csv | Upcoming games: open / previous / current consensus spread, total and no-vig ML, moves, key numbers crossed, best price per side |
| latest/closing_lines.csv | Every game that has kicked off: opening and closing consensus, for CLV |
| latest/run_info.json | Time of the last pull, credits left, settings |

Spreads in the CSVs use the sportsbook convention: `home_spread` negative =
home team favoured. Consensus = median across books. No-vig probabilities
remove the juice from each book's two-way price, then take the median.

Flags: spread move of 1+ point, crossing 3, 7 or 10, total move of 1.5+,
no-vig ML move of 3+ points, Pinnacle 1+ point off the market, or a big move
since the previous pull.

## Commands

```bash
pip install -r requirements-odds.txt
ODDS_API_KEY=... python -m nfl_odds.run       # one live pull
python -m nfl_odds.run --rebuild              # rebuild tables from saved pulls, no API call
python -m nfl_odds.clv my_bets.csv            # grade a bet log against closing lines
```

The bet log format is documented at the top of `nfl_odds/clv.py`. Keep it out
of this repo if the repo is public.
