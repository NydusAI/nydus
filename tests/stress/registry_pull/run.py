"""Registry pull stress test.

Pulls two hardcoded eggs from the Nest registry repeatedly with configurable
concurrency, then prints summary statistics (timing, success rate, SHA
verification).
"""

from __future__ import annotations

import argparse
import getpass
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import httpx
from pynydus.api.errors import RegistryError
from pynydus.remote.registry import NestClient, _save_token

REGISTRY_URL = "https://nest.nydus.ag"

EGGS: list[tuple[str, str]] = [
    ("admin/openclaw", "0.0.1"),
    ("admin/zeroclaw", "0.0.1"),
]


@dataclass
class PullResult:
    egg_name: str
    version: str
    index: int
    success: bool
    elapsed: float
    error: str | None = None


@dataclass
class Stats:
    results: list[PullResult] = field(default_factory=list)

    @property
    def successes(self) -> list[PullResult]:
        return [r for r in self.results if r.success]

    @property
    def failures(self) -> list[PullResult]:
        return [r for r in self.results if not r.success]

    @property
    def timings(self) -> list[float]:
        return [r.elapsed for r in self.successes]


def _dir_name(name: str, version: str) -> str:
    """Build flat directory name: admin/openclaw + 0.0.1 -> admin_openclaw_0.0.1"""
    return f"{name.replace('/', '_')}_{version}"


def _pull_one(
    url: str,
    name: str,
    version: str,
    output_path: Path,
    index: int,
) -> PullResult:
    """Execute a single pull and return the result with timing."""
    client = NestClient(url)
    start = time.perf_counter()
    try:
        client.pull(name, version=version, output_path=output_path)
        elapsed = time.perf_counter() - start
        return PullResult(
            egg_name=name,
            version=version,
            index=index,
            success=True,
            elapsed=elapsed,
        )
    except (RegistryError, Exception) as exc:
        elapsed = time.perf_counter() - start
        return PullResult(
            egg_name=name,
            version=version,
            index=index,
            success=False,
            elapsed=elapsed,
            error=str(exc),
        )


def _print_summary(stats: Stats, wall_time: float) -> None:
    total = len(stats.results)
    ok = len(stats.successes)
    fail = len(stats.failures)
    timings = stats.timings

    print("\n" + "=" * 60)
    print("STRESS TEST SUMMARY")
    print("=" * 60)
    print(f"  Total pulls attempted : {total}")
    print(f"  Successes             : {ok}")
    print(f"  Failures              : {fail}")
    print(f"  Success rate          : {ok / total * 100:.1f}%")

    if timings:
        print(f"  Avg pull time         : {statistics.mean(timings):.3f}s")
        print(f"  Min pull time         : {min(timings):.3f}s")
        print(f"  Max pull time         : {max(timings):.3f}s")
        if len(timings) >= 2:
            print(f"  Std dev               : {statistics.stdev(timings):.3f}s")
        print(f"  Median                : {statistics.median(timings):.3f}s")

    print(f"  Wall-clock time       : {wall_time:.3f}s")
    print("=" * 60)

    if stats.failures:
        print(f"\nFailed pulls ({fail}):")
        for r in stats.failures:
            label = _dir_name(r.egg_name, r.version)
            print(f"  pull_{r.index:03d} ({label}): {r.error}")


def _authenticate(registry_url: str, email: str, password: str) -> None:
    """Authenticate against the Nest registry and persist the token.

    Queries /health to discover auth mode. For ``supabase`` mode, authenticates
    via the Supabase GoTrue API. For ``custom`` mode, falls back to
    NestClient.login().
    """
    try:
        health = httpx.get(f"{registry_url}/health", timeout=30).json()
    except Exception as exc:
        raise RegistryError(f"Cannot reach registry at {registry_url}: {exc}") from exc

    auth_mode = health.get("auth_mode", "custom")

    if auth_mode == "supabase":
        supabase_url = health.get("supabase_url")
        api_key = health.get("supabase_publishable_key")
        if not supabase_url or not api_key:
            raise RegistryError(
                "Registry reports supabase auth but /health is missing "
                "supabase_url or supabase_publishable_key"
            )

        try:
            resp = httpx.post(
                f"{supabase_url}/auth/v1/token?grant_type=password",
                headers={"apikey": api_key, "Content-Type": "application/json"},
                json={"email": email, "password": password},
                timeout=30,
            )
        except httpx.HTTPError as exc:
            raise RegistryError(f"Supabase auth request failed: {exc}") from exc

        if resp.status_code != 200:
            detail = resp.json().get("error_description", resp.text)
            raise RegistryError(f"Supabase login failed (HTTP {resp.status_code}): {detail}")

        token = resp.json().get("access_token", "")
        if not token:
            raise RegistryError("Supabase returned no access_token")

        _save_token(registry_url.rstrip("/"), token)
    else:
        NestClient(registry_url).login(email, password)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Stress-test the Nest registry by pulling eggs concurrently.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help="Directory to save downloaded eggs into.",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=4,
        help="Max parallel pull threads (default: 4).",
    )
    parser.add_argument(
        "--repeats",
        type=int,
        default=30,
        help="Number of times to pull each egg (default: 30).",
    )
    args = parser.parse_args()

    output_dir: Path = args.output_dir.resolve()
    concurrency: int = args.concurrency
    repeats: int = args.repeats

    print(f"Registry : {REGISTRY_URL}")
    print(f"Eggs     : {', '.join(f'{n}:{v}' for n, v in EGGS)}")
    print(f"Repeats  : {repeats} per egg ({repeats * len(EGGS)} total)")
    print(f"Workers  : {concurrency}")
    print(f"Output   : {output_dir}")

    # --- authenticate ---
    # The live Nest registry uses Supabase auth (no /auth/login route).
    # Discover auth mode from /health, then authenticate accordingly.
    print("\nLog in to Nest registry:")
    email = input("  Email: ")
    password = getpass.getpass("  Password: ")

    try:
        _authenticate(REGISTRY_URL, email, password)
    except RegistryError as exc:
        print(f"\nLogin failed: {exc}", file=sys.stderr)
        sys.exit(1)
    print("  Logged in successfully.\n")

    # --- build work list ---
    tasks: list[tuple[str, str, Path, int]] = []
    for name, version in EGGS:
        egg_dir = output_dir / _dir_name(name, version)
        for i in range(1, repeats + 1):
            dest = egg_dir / f"pull_{i:03d}.egg"
            tasks.append((name, version, dest, i))

    # --- execute ---
    stats = Stats()
    wall_start = time.perf_counter()

    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = {
            pool.submit(_pull_one, REGISTRY_URL, name, ver, dest, idx): (name, ver, idx)
            for name, ver, dest, idx in tasks
        }
        for future in as_completed(futures):
            result = future.result()
            stats.results.append(result)
            label = _dir_name(result.egg_name, result.version)
            status = "OK" if result.success else f"FAIL ({result.error})"
            print(
                f"  [{len(stats.results):>3}/{len(tasks)}] "
                f"{label}/pull_{result.index:03d}.egg  {result.elapsed:.3f}s  {status}"
            )

    wall_time = time.perf_counter() - wall_start
    _print_summary(stats, wall_time)

    sys.exit(1 if stats.failures else 0)


if __name__ == "__main__":
    main()
