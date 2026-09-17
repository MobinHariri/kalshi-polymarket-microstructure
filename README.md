# Cross-Venue Microstructure of Binary Event Contracts

**Do price differences between Kalshi and Polymarket survive fees and order-book depth?**

A measurement study. Two prediction-market venues list contracts on the same real-world events —
the same Fed decision, the same Bitcoin threshold, the same football match. Their prices differ.
This project records those differences at a 20-second cadence and asks whether any of them are
actually tradeable once you pay to cross the spread.

## Scope

**Public, read-only market data only. No trading, no order placement, no positions, no account
funding.** Both venues publish unauthenticated market-data endpoints; this project reads them and
nothing else.

The study measures the *size* and *persistence* of divergence. It does not claim risk-free profit,
and at a 20-second polling cadence it cannot and does not measure latency or which venue leads the
other.

## Why this is not just "find the arbitrage"

Two prices differing is not an opportunity. Three things stand between a quoted gap and a trade:

1. **Mid prices are not tradeable.** The gap that matters is between what you can *sell* at on one
   venue and *buy* at on the other — `max(bid_a − ask_b, bid_b − ask_a, 0)`, not `mid_a − mid_b`.
2. **Fees.** Both venues charge takers a fee proportional to `P × (1 − P)` — the Bernoulli variance
   — so the cost of crossing peaks at 50¢ and vanishes at the extremes.
3. **Depth.** Top-of-book size is often trivial. The gap has to survive walking the book for real
   notional.

And underneath all of it: **the two contracts may not be the same claim.** Different resolution
sources, different cutoff times, different definitions of the triggering event. Gebele & Matthes
(arXiv 2601.01706) call this *semantic non-fungibility*, and it is the main reason cross-venue
divergence persists. Classifying each market pair as equivalent, subset, superset or ambiguous —
by reading both venues' published resolution rules — is the analytical core of this project, not a
preliminary.

## Early findings

Two worked examples from live data, both at the top of book with real size behind them.

**La Liga, Elche v Real Madrid, 15 Sept 2026.** Kalshi bid 0.82 / Polymarket ask 0.81 — a 1¢
executable crossing with ~119,000 contracts available, about $97k of notional.

```
Gross edge, per 100 contracts                             $1.00
Kalshi taker fee    0.07 × 100 × 0.82 × 0.18  = $1.0332 → $1.04
Polymarket fee      0.05 × 100 × 0.81 × 0.19  =           $0.77
                                                        ───────
Net                                                      −$0.81
```

At full available size the trade loses ~$957. The loss is proportional; no size makes it work.

**Bitcoin to $100k by 31 Dec 2026, 16 Sept 2026.** Mid gap 3¢ (Kalshi 16.5%, Polymarket 19.5%).
Executable gap after using real bids and asks: **2¢** — a third of the apparent divergence was
spread and tick-size artifact. Fees at that price level, with Polymarket's crypto rate of θ = 0.07:
0.99¢ + 1.08¢ = **2.07¢**. Net **−0.07¢ per contract**, on a bid holding 171 contracts.

The gap is priced to within a rounding error of the cost of taking it.

**The structural point.** Breakeven gap by price level:

| Price | Kalshi fee | Polymarket fee | Gap needed to break even |
|------:|-----------:|---------------:|-------------------------:|
| 0.82  | 1.03¢      | 0.74¢          | **1.77¢** |
| 0.70  | 1.47¢      | 1.05¢          | **2.52¢** |
| 0.50  | 1.75¢      | 1.25¢          | **3.00¢** |

Kalshi's tick size is 1¢, so divergence can only appear in whole-cent steps on that side. A 1¢ gap
is structurally unprofitable and a 2¢ gap nets a fraction of a cent before slippage. And because
both fee schedules peak at 50¢, the cost of crossing is *highest* exactly where two venues with
different trader populations are most likely to disagree. That is a limits-to-arbitrage mechanism,
and it is why divergence persists rather than being competed away.

## Method

**Collection.** `collector.py` polls both venues every 20 seconds and writes to SQLite.

Kalshi's `/markets` response carries top-of-book directly (`yes_bid_dollars`, `yes_ask_dollars`,
and sizes), so one request covers every pair and all quotes share a single timestamp. Polymarket
has no batch book endpoint, so its quotes are fetched per token and are smeared a few seconds
within each cycle — a known limitation, recorded here rather than hidden.

Kalshi's order book returns **bids only on both the YES and NO sides**, because a NO bid at price
*p* is a YES ask at *1 − p*. Best YES ask is therefore `1 − (best NO bid)`. Prices are fixed-point
strings and are stored as text, never floats.

**Reliability.** Every venue call and every cycle is wrapped in error handling; a failed request is
logged and the loop continues. Over an unattended overnight run of ~1,570 cycles: Polymarket
captured essentially every cycle, Kalshi missed ~18 (**~99% capture**), with no crash and no manual
intervention.

**Planned analysis.** As-of join with a 30-second staleness tolerance and no interpolation;
fee-adjusted and depth-walked executable gaps at $100 / $500 / $1,000 notional; gap-episode
duration distributions; all confidence intervals by **block bootstrap**, because 20-second
observations are heavily autocorrelated and iid standard errors would overstate significance.

## Current status

- Collector live since 15 Sept 2026, running unattended
- Config-driven pairs (`pairs.json`) — markets can be added without touching code
- Fee model for both venues implemented and validated against two live examples
- ~48,000 quote rows as of 17 Sept

**Next:** expand from 2 matched pairs to 15–20; pull resolution rules from both APIs
(`rules_primary` on Kalshi, `description` on Polymarket) and classify each pair; build the
as-of join, depth-walking and persistence analysis; block-bootstrap intervals; figures.

## Running it

```bash
conda create -n crossvenue python=3.12 requests pandas matplotlib jupyterlab -y
conda activate crossvenue
python collector.py
```

No API keys. Both venues' market-data endpoints are public. `pairs.json` defines what is
collected; `crossvenue.db` is created on first run and is not committed.

## References

1. Gebele & Matthes, *Semantic Non-Fungibility and Violations of the Law of One Price in Prediction
   Markets*, arXiv 2601.01706 — cross-venue divergence as structural rather than transient
2. Ng, Peng, Tao & Zhou, *Price Discovery and Trading in Prediction Markets*, SSRN 5331995 —
   cross-venue price discovery; Polymarket leads Kalshi
3. Saguillo, Ghafouri, Kiffer & Suarez-Tangil, *Unravelling the Probabilistic Forest*, AFT 2025 /
   arXiv 2508.03474 — intra-venue arbitrage at scale on Polymarket
4. Gebele, Mutzel & Matthes, *Executable Arbitrage and Market Efficiency*, arXiv 2608.00666 —
   payoff-space vs protocol-executable no-arbitrage
5. Bürgi et al., *The Economics of the Kalshi Prediction Market*, UCD WP2025/19 — calibration and
   favourite–longshot bias

---

Mobin Hariri — MEng Mechanical Engineering, University of Warwick
