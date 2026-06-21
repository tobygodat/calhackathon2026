# Synthetic intake test set

20 synthetic gut-microbiome papers written against the seeded lab profile (`baskr/data/profile_seed.json`) to exercise and demo data ingestion + the classification scanner.

Each record has the normal paper fields plus ground truth:

- `expected_label` — the system Label the scanner *should* emit
- `expected_category` — the human flag wording for the demo
- `expected_match` — the profile item id it is built to hit

## Label distribution

- `ANSWERS`: 5
- `CONTRADICTS`: 5
- `EXTENDS`: 6
- `NOT_RELEVANT`: 4

## How to use

- **Plain ingestion demo:** drag any of the `paper_*.json` files (or all of them) onto the dev-UI Intake tester — they flow through the real stream + consumer.
- **Scored accuracy test:** upload `testset.json` via *Run labeled test* in the dev UI. The backend runs each paper through the real scanner and reports how many it classified correctly on the dashboard scorecard.

Regenerate with `python baskr/scripts/gen_synthetic_intake.py`.
