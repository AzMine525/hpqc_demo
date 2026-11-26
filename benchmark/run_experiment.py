"""Run the Stage 08 benchmark and export raw trials, summaries and provenance."""

import argparse
from collections import defaultdict
from dataclasses import asdict
from datetime import datetime, timezone
from hashlib import sha256
from importlib.metadata import version
import csv
import json
import math
from pathlib import Path
import platform
import statistics
import subprocess
import sys
from typing import Iterable

from cryptography.exceptions import InvalidTag
import psutil

from benchmark.workloads import BenchmarkError, LOOPBACK, SIZES, crypto_trial, network_trial
from crypto_engine.v2.suites import SUITES
from protocol.handshake_v2 import DEFAULT_TIMEOUT, HandshakeError

ROOT = Path(__file__).resolve().parents[1]
GROUP = ("workload", "suite", "payload_bytes", "direction", "metric", "unit")
RAW_FIELDS = GROUP + ("phase", "trial", "status", "value", "error")
SUMMARY_FIELDS = GROUP + ("n", "unavailable", "mean", "median", "sd_sample", "p95")
TRIAL_ERRORS = (OSError, EOFError, ValueError, RuntimeError, HandshakeError,
                InvalidTag, BenchmarkError, psutil.Error)


def summary(rows: Iterable[dict]) -> Iterable[dict]:
    """Aggregate measured samples only. p95 uses nearest rank and SD uses n-1."""
    groups = defaultdict(list)
    for row in rows:
        if row["metric"] == "trial" or row["phase"] != "measured":
            continue
        if row["status"] in ("ok", "unavailable"):
            groups[tuple(row[field] for field in GROUP)].append(row["value"])
    for key, observed in sorted(groups.items()):
        values = sorted(value for value in observed if value is not None)
        n = len(values)
        yield dict(
            zip(GROUP, key), n=n, unavailable=len(observed) - n,
            mean=statistics.mean(values) if n else None,
            median=statistics.median(values) if n else None,
            sd_sample=statistics.stdev(values) if n > 1 else None,
            p95=values[math.ceil(0.95 * n) - 1] if n else None,
        )


def collect(suites: list[str], modes: tuple[str, ...], warmup: int, trials: int,
            timeout: float, process: psutil.Process) -> list[dict]:
    """Interleave suites within each trial index and retain every attempted trial."""
    rows = []
    for phase, count in (("warmup", warmup), ("measured", trials)):
        for index in range(1, count + 1):
            for suite in suites:
                for workload in modes:
                    for size in (SIZES if workload == "network" else (0,)):
                        samples = []
                        status = "ok"
                        error = ""
                        try:
                            if workload == "crypto":
                                crypto_trial(samples, process, suite)
                            else:
                                network_trial(samples, process, suite, size, timeout)
                        except TRIAL_ERRORS as exc:
                            status = "failed"
                            error = type(exc).__name__
                        labels = dict(workload=workload, suite=suite, phase=phase, trial=index)
                        rows.extend(dict(**labels, **asdict(sample)) for sample in samples)
                        rows.append(dict(**labels, payload_bytes=size, direction="", metric="trial",
                                         unit="", value=None, status=status, error=error))
    return rows


def write_csv(path: Path, fields: tuple[str, ...], rows: Iterable[dict]) -> None:
    """Write portable CSV into a new file without overwriting prior results."""
    with path.open("x", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def source_info() -> dict:
    """Identify the HEAD and the actual Python source bytes used by the runner."""
    try:
        commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT,
                                         text=True, stderr=subprocess.DEVNULL).strip()
    except (OSError, subprocess.CalledProcessError):
        commit = None
    files = sorted(path for directory in ("benchmark", "crypto_engine", "protocol")
                   for path in (ROOT / directory).rglob("*.py"))
    return dict(commit=commit, sha256={
        path.relative_to(ROOT).as_posix(): sha256(path.read_bytes()).hexdigest() for path in files
    })


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path, help="New results directory")
    parser.add_argument("--suite", action="append", choices=tuple(SUITES), help="Repeat to select suites")
    parser.add_argument("--mode", choices=("both", "crypto", "network"), default="both")
    parser.add_argument("--warmup", type=int, default=3)
    parser.add_argument("--trials", type=int, default=20)
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)
    args = parser.parse_args()
    if args.warmup < 0 or args.trials < 1:
        parser.error("--warmup must be nonnegative and --trials must be positive")
    if not math.isfinite(args.timeout) or args.timeout <= 0:
        parser.error("--timeout must be finite and positive")
    try:
        args.output.mkdir(parents=True, exist_ok=False)
    except OSError as exc:
        parser.error(f"Cannot create output directory ({type(exc).__name__})")
    suites = list(dict.fromkeys(args.suite or SUITES))
    modes = ("crypto", "network") if args.mode == "both" else (args.mode,)
    manifest = dict(
        schema_version=1, started_utc=datetime.now(timezone.utc).isoformat(),
        host=platform.node(), platform=platform.platform(), python=platform.python_version(),
        dependencies={name: version(name) for name in ("pqcrypto", "cryptography", "psutil")},
        source=source_info(),
        command=getattr(sys, "orig_argv", [sys.executable, "-m", "benchmark.run_experiment", *sys.argv[1:]]),
        suites={name: SUITES[name].wire_id for name in suites}, modes=modes, loopback=LOOPBACK,
        payload_bytes=SIZES, warmup=args.warmup, trials=args.trials, timeout_s=args.timeout,
    )
    rows = collect(suites, modes, args.warmup, args.trials, args.timeout, psutil.Process())
    for mode in modes:
        write_csv(args.output / f"{mode}_raw.csv", RAW_FIELDS,
                  (row for row in rows if row["workload"] == mode))
    write_csv(args.output / "summary.csv", SUMMARY_FIELDS, summary(rows))
    attempts = [row for row in rows if row["metric"] == "trial"]
    failures = sum(row["status"] == "failed" for row in attempts)
    manifest.update(attempts=len(attempts), failures=failures,
                    finished_utc=datetime.now(timezone.utc).isoformat())
    with (args.output / "manifest.json").open("x", encoding="utf-8", newline="\n") as file:
        json.dump(manifest, file, ensure_ascii=False, indent=2)
        file.write("\n")
    print(f"{len(attempts)} attempts, {failures} failed. Evidence: {args.output}")
    return int(failures > 0)


if __name__ == "__main__":
    raise SystemExit(main())
