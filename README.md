# portfolio

A plain-language view of a personal, rules-based ETF portfolio: what it holds
today, how it is split, and the simulated record.

**Live: [phuazz.github.io/portfolio](https://phuazz.github.io/portfolio/)**

Every performance figure on the page is simulated from historical prices. There
is no live track record. It is not investment advice.

## This repo publishes; it does not build

`index.html` is **generated — do not edit it here.** It is built in
[phuazz/breadth-thrust-etf](https://github.com/phuazz/breadth-thrust-etf) by
`scripts/build_simple_page.py` from `simple_template.html`, and this repo pulls
the result. An edit made here is silently overwritten by the next sync.

To change the page, change the template in that repo.

## How the sync works

`.github/workflows/sync.yml` runs daily at 23:00 UTC and on manual dispatch. It
fetches `build/portfolio.html` from the source repo's `main`, validates it, and
commits it as `index.html` only if it both passes and differs.

It pulls rather than being pushed to, so no cross-repo deploy key or token
exists anywhere. The trade is up to a day of lag; use **Actions → Sync portfolio
page → Run workflow** when that is not good enough.

## Why the page is re-validated here

The source repo builds under its own guards, but nothing there knows what this
repo has already published. `scripts/validate.py` refuses to publish a page
that is truncated, has lost its disclosures, carries no holdings, has weights
that do not sum to NAV, or whose curve disagrees with its own as-of date.

The check worth naming: **the as-of date may not move backwards.** A page that
is well-formed but older than the one already up — an upstream rollback, a
stale cache, a refresh that republished old state — passes every structural
test and would quietly walk the page back in time.

Rejection is not a failure to retry blindly. It leaves the previous page up,
which is the safe outcome: a day-old holdings table is a far smaller problem
than a wrong one.
