# 04 — Registry Pull Stress Test

Stress-tests the [Nest registry](https://nest.nydus.ag/) by pulling two eggs
(`admin/openclaw:0.0.1` and `admin/zeroclaw:0.0.1`) repeatedly with
configurable concurrency. Reports summary statistics: total wall-clock time,
per-pull avg/min/max/median, success/failure count, and SHA-256 verification
pass rate.

## Prerequisites

- pynydus installed: `uv pip install -e .` from repo root
- A Nest registry account (register at https://nest.nydus.ag/ or via
  `nydus register`)

## Usage

### Cross-platform (Windows, macOS, Linux)

From the repo root:

```
uv run python examples/04-pull-registry-stress/run.py --output-dir ./stress-eggs
```

Or from this directory:

```
uv run python run.py --output-dir ./stress-eggs
```

### Unix only

```
cd examples/04-pull-registry-stress
./run.sh --output-dir ./stress-eggs
```

### Options

| Flag | Default | Description |
|------|---------|-------------|
| `--output-dir` | *(required)* | Directory to save downloaded eggs into |
| `--concurrency` | `4` | Max parallel pull threads |
| `--repeats` | `30` | Number of times to pull each egg |

### Example invocation

```
uv run python run.py --output-dir ./stress-eggs --concurrency 8 --repeats 10
```

The script will prompt for your Nest registry email and password. Authentication
is handled automatically — the script queries the registry's `/health` endpoint
to discover whether it uses Supabase or custom auth, then authenticates
accordingly.

## Output structure

```
stress-eggs/
  admin_openclaw_0.0.1/
    pull_001.egg
    pull_002.egg
    ...
    pull_030.egg
  admin_zeroclaw_0.0.1/
    pull_001.egg
    ...
    pull_030.egg
```

Total disk usage: ~1 MB (60 copies of ~16 KB eggs at default settings).

## Sample output

```
Registry : https://nest.nydus.ag
Eggs     : admin/openclaw:0.0.1, admin/zeroclaw:0.0.1
Repeats  : 30 per egg (60 total)
Workers  : 4
Output   : C:\Users\you\stress-eggs

Log in to Nest registry:
  Email: alice@example.com
  Password:
  Logged in successfully.

  [  1/ 60] admin_openclaw_0.0.1/pull_003.egg  0.412s  OK
  [  2/ 60] admin_zeroclaw_0.0.1/pull_001.egg  0.438s  OK
  ...

============================================================
STRESS TEST SUMMARY
============================================================
  Total pulls attempted : 60
  Successes             : 60
  Failures              : 0
  Success rate          : 100.0%
  Avg pull time         : 0.425s
  Min pull time         : 0.312s
  Max pull time         : 0.891s
  Std dev               : 0.087s
  Median                : 0.410s
  Wall-clock time       : 7.234s
============================================================
```

## Known limitations

- **JWT expiry**: Supabase JWTs typically expire after 1 hour. The script does
  not refresh tokens. For very large runs (high `--repeats` with low
  `--concurrency`), the token may expire mid-run and later pulls will fail
  with auth errors.
- **No retry logic**: Failed pulls (rate-limiting, transient network errors)
  are recorded as failures rather than retried. Increase `--concurrency`
  cautiously — the default of 4 is conservative.
- **No connection pooling**: Each pull opens a new TCP connection via httpx.
  At high concurrency this may exhaust local connections or trigger
  server-side rate limiting.
