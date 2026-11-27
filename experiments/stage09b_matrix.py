"""Plan or coordinate the remaining Stage 09B profiles from the management host."""

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import shlex
import statistics
import subprocess
import time
from uuid import uuid4

DEBIAN, UBUNTU = "debian-pqc", "ubuntu-pqc"
HOSTS = (DEBIAN, UBUNTU)
PROJECT = Path(__file__).resolve().parents[1]
SOURCE = "3df1e695a88fb54be7bcd3431cdcbd4bb9b9b969"
UNIT = "hpqc-stage09b-matrix.service"
PROFILES = {
    "delay200": ("delay 200ms", 12),
    "jitter10": ("delay 50ms 10ms", 12),
    "jitter20": ("delay 50ms 20ms", 12),
    "loss05": ("loss 5%", 12),
    "loss10": ("loss 10%", 12),
    "loss20": ("loss 20%", 12),
    "outage": ("loss 100%", 5),
}
SSH_OPTIONS = ["-o", "StrictHostKeyChecking=yes", "-o", "UpdateHostKeys=no",
               "-o", "ConnectTimeout=5"]
SSH = ["ssh", "-T", "-o", "BatchMode=yes", *SSH_OPTIONS]
SCP = ["scp", "-B", *SSH_OPTIONS]
SAMPLE_HEADER = re.compile(r"(?m)^(\d+)\r?$")
NETEM = re.compile(r"(?m)^qdisc netem 709: root\b[^\r\n]*")


def remote(host: str, body: str, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    """Execute a bounded Bash command via a fresh authenticated management connection."""
    return subprocess.run(
        [*SSH, host, shlex.join(["bash", "-se", "--", *args])],
        input=("set -o pipefail\n" + body + "\n").encode(), capture_output=True,
        check=check, timeout=30,
    )


def render(profile: str) -> str:
    """Derive the profile from the previously reviewed guard and systemd unit."""
    args, duration = PROFILES[profile]
    template = (PROJECT / "experiments/stage09b_pilot.sh").read_text(encoding="utf-8")
    for old, new in (
        ("hpqc-stage09b-delay50.service", UNIT),
        ("handle 709: netem delay 50ms", f"handle 709: netem {args}"),
        ("/bin/sleep 12", f"/bin/sleep {duration}"),
        ('    date --iso-8601=seconds > "$dir/armed-at"',
         '    [[ ! -e $root/abort && -f ${dir%/console/pilot}/ready ]]\n'
         '    (( $(date +%s) < $(cat "${dir%/console/pilot}/ready") ))\n'
         '    date --iso-8601=seconds > "$dir/armed-at"'),
    ):
        if template.count(old) != 1:
            raise ValueError("Template pilot berubah. Tinjau ulang sebelum melanjutkan.")
        template = template.replace(old, new)
    return template


def upload(host: str, path: str, contents: str) -> None:
    """Create one remote file without overwriting evidence."""
    script = 'umask 077; set -C; cat > "$1"'
    subprocess.run([*SSH, host, shlex.join(["bash", "-c", script, "upload", path])],
                   input=contents.encode(), check=True, timeout=30)


def snapshot(host: str, run: str, phase: str) -> bytes:
    """Record both management and data routes, addresses, and complete qdisc state."""
    debian = host == DEBIAN
    return remote(host, """
cd "$1"
stamp=$2
test "${SSH_CONNECTION%% *}" = 10.10.20.1
test "$(hostname -s)" = "$3"
test "$(id -un)" = "$4"
hostname; id -un
test "$(git -C "$HOME/hpqc_demo" rev-parse HEAD)" = "$5"
git -C "$HOME/hpqc_demo" diff --exit-code HEAD -- '*.py' requirements.txt
ip -br -4 addr | awk -v addr="$6/24" '$1=="enp0s3" && $2=="UP" && $3==addr {found=1; print} END {exit !found}'
ip -br -4 addr | awk -v addr="$7/24" '$1=="enp0s8" && $2=="UP" && $3==addr {found=1; print} END {exit !found}'
ip -4 route get "$8" | grep -F "dev enp0s8 src $7"
ip -4 route get 10.10.20.1 | grep -F "dev enp0s3 src $6"
set -C
{
    ip -br -4 addr
    ip -4 route show table all
    /usr/sbin/tc -d qdisc show
} > "$stamp-network.txt"
if grep -q '^qdisc netem ' "$stamp-network.txt"; then exit 1; fi
grep -q "^qdisc $9 0: dev enp0s8 root" "$stamp-network.txt"
cat "$stamp-network.txt"
date -Is
uname -r
"$HOME/hpqc_demo/.venv/bin/python" -B -c 'import sys; from importlib.metadata import version; print(sys.version, [version(p) for p in ("pqcrypto","cryptography","psutil")])'
ping -I enp0s8 -c 4 -W 2 "$8" | tee "$stamp-ping.txt"
grep -q '4 packets transmitted, 4 received, 0% packet loss' "$stamp-ping.txt"
if [ "$stamp" = after ]; then diff -u before-network.txt after-network.txt; fi
""", run, phase, host, "research" if debian else "research2", SOURCE,
                  "10.10.20.4" if debian else "10.10.20.5",
                  "10.10.30.20" if debian else "10.10.30.10",
                  "10.10.30.10" if debian else "10.10.30.20",
                  "fq_codel" if debian else "pfifo_fast").stdout


SERVER = """
set -euo pipefail
cd "$1"
umask 077
set -C
test -z "$(ss -H -ltn 'sport = :5061')"
test "$(stat -c %a resilience.psk)" = 600
test "$(wc -c < resilience.psk)" -eq 32
cd "$HOME/hpqc_demo"
py=.venv/bin/python
timeout 780 "$py" -Bu -m protocol.resilience_cli server --host 10.10.30.10 --port 5061 \
    --suite ml-kem-768 --timeout 3 --idle-timeout 15 --psk-file "$1/resilience.psk" \
    --inbox "$1/inbox.sqlite" > "$1/server.jsonl" 2> "$1/server.stderr" &
child=$!
trap 'kill "$child" 2>/dev/null || true; wait "$child" 2>/dev/null || true' EXIT
for i in {1..40}; do
    grep -q '"event": "listening"' "$1/server.jsonl" && break
    kill -0 "$child"
    sleep .25
done
grep '"event": "listening"' "$1/server.jsonl"
while [[ ! -f $1/stop-receiver ]]; do kill -0 "$child"; sleep .5; done
kill "$child"; wait "$child" || true
"$py" -B - "$1" <<'PY' > "$1/inbox.tsv"
import hashlib, pathlib, sqlite3, sys
p = pathlib.Path(sys.argv[1]) / "inbox.sqlite"
with sqlite3.connect(p.as_uri() + "?mode=ro", uri=True) as db:
    rows = db.execute("select message_id, payload from inbox order by message_id").fetchall()
for mid, payload in rows:
    assert payload == b"HPQC-09B"
    print(mid.hex(), len(payload), hashlib.sha256(payload).hexdigest(), sep="\t")
PY
"""


def start_server(run: str, log: Path) -> subprocess.Popen:
    """Start the bounded listener and retain its supervisor log."""
    with log.open("xb") as out:
        return subprocess.Popen([*SSH, UBUNTU, shlex.join(["bash", "-c", SERVER, "listen", run])],
                                stdin=subprocess.DEVNULL, stdout=out, stderr=out)


def wait_console(run: str, local: Path, server: subprocess.Popen) -> None:
    """Observe the active qdisc via BatchMode and require a successful console exit."""
    observed = False
    deadline = time.monotonic() + 730
    while time.monotonic() < deadline and server.poll() is None:
        status = remote(DEBIAN, """
cd "$1"
date -Is
ip -4 route get "${SSH_CONNECTION%% *}" | grep -F 'dev enp0s3 src 10.10.20.4'
/usr/sbin/tc -s qdisc show dev enp0s8
if [ -s console-exit ]; then printf 'console_exit='; cat console-exit; fi
""", run).stdout
        if not observed and b"qdisc netem 709: root" in status:
            (local / "debian/during-ssh.txt").write_bytes(status)
            ubuntu = remote(UBUNTU, """
hostname; date -Is
test "${SSH_CONNECTION%% *}" = 10.10.20.1
ip -4 route get "${SSH_CONNECTION%% *}" | grep -F 'dev enp0s3 src 10.10.20.5'
/usr/sbin/tc -s qdisc show dev enp0s8
""").stdout
            (local / "ubuntu/during-ssh.txt").write_bytes(ubuntu)
            bracket = remote(DEBIAN, """
date -Is
/usr/sbin/tc qdisc show dev enp0s8
systemctl show "$1" -p ActiveState -p RuntimeMaxUSec -p ExecStopPost
""", UNIT).stdout
            (local / "debian/during-bracket.txt").write_bytes(bracket)
            observed = True
        match = re.search(rb"(?m)^console_exit=(\d+)", status)
        if match:
            (local / "debian/console-exit.txt").write_bytes(status)
            if match[1] != b"0" or not observed:
                raise RuntimeError("Console gagal atau observasi SSH saat netem aktif tidak tersedia.")
            return
        time.sleep(0.35)
    raise TimeoutError("Jendela konsol atau listener habis.")


def collect(host: str, run: str, target: Path, files: list[str]) -> None:
    """Copy named nonsecret files only, including partial evidence on failure."""
    existing = remote(host, 'cd "$1"; shift; for f; do if test -f "$f"; then echo "$f"; fi; done',
                      run, *files).stdout.decode().splitlines()
    if existing:
        subprocess.run([*SCP, *(f"{host}:{run}/{f}" for f in existing), str(target)],
                       check=True, timeout=90)


def run_profile(profile: str, root: str, local: Path) -> None:
    """Run one profile and require independent rollback and inbox validation."""
    run = f"{root}/{profile}"
    paths = {DEBIAN: run, UBUNTU: ubuntu_path(run)}
    server = None
    files = {
        DEBIAN: ["runner.txt", "pilot.sha256", "verify.txt", "console/network-status.txt",
                 "console/unit.txt", "console/rollback.txt", "console/samples.txt",
                 "console/samples.stderr", "console/client.jsonl", "console/client.stderr",
                 "console/client-exit.txt", "console/post-client.jsonl", "console/post-client.stderr",
                 "console/pilot/armed-at", "console/pilot/ping-before", "console/pilot/ping-after"],
        UBUNTU: ["server.jsonl", "server.stderr", "inbox.tsv"],
    }
    for host in HOSTS:
        (local / ("debian" if host == DEBIAN else "ubuntu")).mkdir(parents=True)
    try:
        for host, name in zip(HOSTS, ("debian", "ubuntu")):
            remote(host, 'umask 077; mkdir "$1"', paths[host])
            (local / name / "before.txt").write_bytes(snapshot(host, paths[host], "before"))
        pilot = render(profile)
        (local / "pilot-reviewed.sh").write_bytes(pilot.encode())
        upload(DEBIAN, f"{run}/pilot-reviewed.sh", pilot)
        upload(DEBIAN, f"{run}/pilot.sha256",
               hashlib.sha256(pilot.encode()).hexdigest() + "  pilot-reviewed.sh\n")
        remote(DEBIAN, """
cd "$1"; umask 077
test "$(ps -p 1 -o comm=)" = systemd
/usr/sbin/modinfo -F filename sch_netem
test "$(systemctl show "$2" -p LoadState --value)" = not-found
sha256sum -c pilot.sha256
bash -n pilot-reviewed.sh
line=$(sed -n '/^    cleanup=/{s/^    //;p;}' pilot-reviewed.sh)
eval "$line"
printf '[Unit]\nDescription=Static verify\n[Service]\nType=exec\nRuntimeMaxSec=16s\nTimeoutStopSec=3s\nExecStart=/bin/sleep 12\n%s\n' "$cleanup" > review.service
systemd-analyze verify "$PWD/review.service" > verify.txt 2>&1
printf 'systemd-analyze verify=PASS\n' >> verify.txt
"$HOME/hpqc_demo/.venv/bin/python" -B -c 'import os; from pathlib import Path; Path("resilience.psk").write_bytes(os.urandom(32))'
""", run, UNIT)
        subprocess.run([*SCP, "-3", "-p", f"{DEBIAN}:{run}/resilience.psk",
                        f"{UBUNTU}:{paths[UBUNTU]}/"], check=True, timeout=30)
        log = local / "ubuntu/listener.txt"
        server = start_server(paths[UBUNTU], log)
        for _ in range(40):
            if '"event": "listening"' in log.read_text(encoding="utf-8", errors="replace"):
                break
            if server.poll() is not None:
                raise RuntimeError("Listener berhenti sebelum siap.")
            time.sleep(0.4)
        else:
            raise TimeoutError("Listener belum siap.")
        deadline = remote(DEBIAN, """
umask 077; set -C
date -d '+10 minutes' +%s > "$1/ready"
date -d "@$(cat "$1/ready")" -Is
""", run).stdout.decode().strip()
        print(f"{profile}: listener siap; batas mulai {deadline}", flush=True)
        wait_console(run, local, server)
        with ThreadPoolExecutor(max_workers=2) as pool:
            checks = [pool.submit(snapshot, host, paths[host], "after") for host in HOSTS]
            for name, check in zip(("debian", "ubuntu"), checks):
                (local / name / "after.txt").write_bytes(check.result())
        remote(DEBIAN, 'test "$(systemctl show "$1" -p ActiveState --value)" = inactive', UNIT)
    except BaseException:
        # Tarik kesiapan segera, sebelum pengumpulan bukti parsial.
        signal_abort(root)
        raise
    finally:
        if server is not None:
            try:
                remote(UBUNTU, 'touch "$1/stop-receiver"', paths[UBUNTU], check=False)
                server.wait(timeout=15)
            except (OSError, subprocess.SubprocessError):
                server.terminate()
                server.wait(timeout=15)
        for host, name in zip(HOSTS, ("debian", "ubuntu")):
            try:
                collect(host, paths[host], local / name, files[host])
            except (OSError, subprocess.SubprocessError) as exc:
                print(f"{profile}: pengambilan bukti {name} gagal: {exc}", flush=True)
    if server.returncode != 0:
        raise RuntimeError("Listener atau verifikasi inbox gagal.")
    result = analyze(local)
    (local / "summary.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    if result["status"] != "PASS":
        raise RuntimeError("Verifikasi bukti profil gagal.")


def ubuntu_path(debian_path: str) -> str:
    """Translate the profile path to the corresponding Ubuntu research workspace."""
    return debian_path.replace("/home/research/", "/home/research2/", 1)


def signal_abort(root: str) -> None:
    """Signal a stop if management SSH is available."""
    try:
        remote(DEBIAN, 'touch "$1/abort"', root)
    except (OSError, subprocess.SubprocessError) as exc:
        print(f"Sinyal abort ke Debian gagal: {exc}", flush=True)


def stats(values: list[float]) -> dict | None:
    """Return median and nearest-rank p95, or null when no observations exist."""
    if not values:
        return None
    ordered = sorted(values)
    return {"n": len(values), "median": statistics.median(values),
            "p95": ordered[math.ceil(0.95 * len(values)) - 1]}


def recovery(events: list[dict]) -> list[dict]:
    """Measure the first new TCP, secure session and delivery after each incident."""
    episodes = []
    current = None
    for event in events:
        kind = event["event"]
        if kind == "interrupted" and (current is None or current["secure_ms"] is not None):
            anchor = event["at_ns"] - event["since_detection_ns"]
            current = {"anchor_ns": anchor, "tcp_ms": None, "secure_ms": None, "delivery_ms": None}
            episodes.append(current)
        if current is not None:
            field = {"tcp_connected": "tcp_ms", "secure_ready": "secure_ms",
                     "delivered": "delivery_ms"}.get(kind)
            if field and current[field] is None:
                current[field] = (event["at_ns"] - current["anchor_ns"]) / 1e6
    return episodes


def handoff(local: Path, profiles: list[str]) -> None:
    """Stage the console runner and orchestrate profiles in order after approval."""
    console = (PROJECT / "experiments/stage09b_matrix_console.sh").read_text(encoding="utf-8")
    (local / "console.sh").write_bytes(console.encode())
    plan = [{"profile": p, "run_id": f"{local.name}/{p}", "netem": PROFILES[p][0],
             "dwell_seconds": PROFILES[p][1]} for p in profiles]
    (local / "plan.json").write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
    for host, root in [(DEBIAN, f"/home/research/hpqc_demo/private-data/stage09b/{local.name}"),
                       (UBUNTU, f"/home/research2/hpqc_demo/private-data/stage09b/{local.name}")]:
        remote(host, 'umask 077; mkdir "$1"', root)
        if host == DEBIAN:
            debian_root = root
            upload(host, f"{root}/console.sh", console)
            upload(host, f"{root}/profiles.txt", "\n".join(profiles) + "\n")
            remote(host, 'bash -n "$1/console.sh"', root)
    print(f'Pada konsol Debian sebagai research:\n'
          f'R={debian_root}\nbash "$R/console.sh" "$R"', flush=True)
    for profile in profiles:
        with (local / "checkpoint.txt").open("a", encoding="utf-8") as checkpoint:
            print(profile, "START", datetime.now(timezone.utc).isoformat(), file=checkpoint)
        try:
            run_profile(profile, debian_root, local / profile)
        except BaseException as exc:
            signal_abort(debian_root)
            with (local / "checkpoint.txt").open("a", encoding="utf-8") as checkpoint:
                print(profile, "STOP", datetime.now(timezone.utc).isoformat(), repr(exc), file=checkpoint)
            raise
        with (local / "checkpoint.txt").open("a", encoding="utf-8") as checkpoint:
            print(profile, "PASS", datetime.now(timezone.utc).isoformat(), file=checkpoint)
        print(f"{profile}: rollback dan bukti PASS", flush=True)


def analyze(local: Path) -> dict:
    """Audit the receipts and qdisc window and compute per-profile observations."""
    deb, ubu = local / "debian", local / "ubuntu"
    def events(path: Path) -> list[dict]:
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]

    main, probe, server = (events(path) for path in
                           (deb / "client.jsonl", deb / "post-client.jsonl", ubu / "server.jsonl"))
    sample = SAMPLE_HEADER.split((deb / "samples.txt").read_text(encoding="utf-8"))
    samples = [(int(time_ns), body) for time_ns, body in zip(sample[1::2], sample[2::2])]
    active = [i for i, (_, body) in enumerate(samples) if NETEM.search(body)]
    if not active or active[0] == 0 or active[-1] == len(samples) - 1:
        raise ValueError("Qdisc aktif belum diapit sampel nonaktif.")
    first, last = active[0], active[-1]
    if active != list(range(first, last + 1)):
        raise ValueError("Jendela aktif terputus atau beberapa kali aktif.")
    prior, start, end, following = (samples[i][0] for i in (first - 1, first, last, last + 1))
    last_active_qdisc = NETEM.search(samples[last][1])[0]
    counters = re.search(r"Sent (\d+) bytes (\d+) pkt \(dropped (\d+), overlimits (\d+) requeues (\d+)\)",
                         samples[last][1])
    configured, dwell = PROFILES[local.name]
    configuration_seen = re.search(r"\b" + r"\s+".join(map(re.escape, configured.split())) +
                                   r"(?:\s|$)", last_active_qdisc) is not None
    unit = (deb / "unit.txt").read_text(encoding="utf-8")
    runtime = re.search(r"Service runtime: ([\d.]+)s", unit)
    starts = {e["id"]: e for e in main if e["event"] == "attempt_started" and e["attempt"] == 1}
    receipt = [e for e in main if e["event"] == "delivered"]
    pong = [e for e in main if e["event"] == "pong"]
    sessions = [e["session"] for e in main if e["event"] == "secure_ready"]
    heartbeat = {mid for mid, e in starts.items() if e["operation"] == "heartbeat"}
    message = {mid for mid, e in starts.items() if e["operation"] == "message"}
    during = [e for e in receipt if start <= e["at_ns"] <= end]
    active_operations = {mid for mid in heartbeat if start <= starts[mid]["at_ns"] <= end}
    near_edges = [e for e in receipt if prior < e["at_ns"] < start or end < e["at_ns"] < following]
    probe_ids = [e["id"] for e in probe if e["event"] == "delivered"]
    receipt_ids = {e["id"] for e in receipt}
    commit = Counter(e["id"] for e in server if e["event"] == "committed")
    inbox = Counter(line.split("\t")[0] for line in (ubu / "inbox.tsv").read_text().splitlines())
    observed_receipts = receipt_ids | set(probe_ids)
    exit_code = int((deb / "client-exit.txt").read_text())
    outcome_recorded = (
        (exit_code == 0 and len(receipt_ids) == 45)
        or exit_code == 124
        or (exit_code == 1 and any(e["event"] == "exhausted" for e in main))
    )
    evidence_pass = (configuration_seen and counters is not None and runtime is not None and
                     dwell - 1 <= float(runtime[1]) <= 16 and outcome_recorded and
                     len(probe_ids) == 1 and probe_ids[0] not in message and
                     len(receipt_ids) == len(receipt) and receipt_ids <= message and
                     all(e["id"] in heartbeat for e in pong) and
                     observed_receipts <= set(inbox) <= message | set(probe_ids) and
                     commit == inbox and all(count == 1 for count in inbox.values()))

    def latency(rows: list[dict]) -> dict | None:
        return stats([(e["at_ns"] - starts[e["id"]]["at_ns"]) / 1e6
                      for e in rows if e["id"] in starts])

    def rtt(rows: list[tuple[int, str]]) -> dict | None:
        return stats([float(v) for _, body in rows
                      for v in re.findall(r"\brtt:([\d.]+)/", body)])

    return {
        "status": "PASS" if evidence_pass else "FAIL", "client_exit": exit_code,
        "workload": {"planned_messages": 45, "started": len(message), "receipts": len(receipt_ids),
                     "delivery_rate": len(receipt_ids) / 45, "heartbeat_started": len(heartbeat),
                     "pong": len(pong), "heartbeat_success_rate": len(pong) / len(heartbeat) if heartbeat else None,
                     "secure_sessions": sessions, "reconnect": max(0, len(sessions) - 1),
                     "retry": sum(e["event"] == "attempt_started" and e["attempt"] > 1 for e in main),
                     "recovery": recovery(main), "latency_ms": latency(receipt),
                     "duration_until_last_event_ms": (main[-1]["at_ns"] - main[0]["at_ns"]) / 1e6,
                     "committed_without_receipt": sorted(set(inbox) - observed_receipts)},
        "impairment": {"netem": last_active_qdisc, "configured_seconds": dwell,
                       "unit_runtime_s": float(runtime[1]) if runtime else None,
                       "observed_bounds_ns": [prior, start, end, following],
                       "receipts": len(during), "boundary_receipts": len(near_edges),
                       "pong": sum(start <= e["at_ns"] <= end for e in pong),
                       "heartbeat_starts": len(active_operations),
                       "pongs_started_and_finished_active": sum(
                           e["id"] in active_operations and start <= e["at_ns"] <= end for e in pong),
                       "start_and_finish_latency_ms": latency(
                           [e for e in during if starts.get(e["id"], {}).get("at_ns", 0) >= start]),
                       "tcp_rtt_ms": rtt(samples[first:last + 1]),
                       "last_qdisc_counters": dict(zip(
                           ("bytes", "packets", "dropped", "overlimits", "requeues"), map(int, counters.groups())
                       )) if counters else None},
        "outside_impairment_rtt_ms": rtt(samples[:first] + samples[last + 1:]),
        "inbox": {"commits": sum(commit.values()), "unique_rows": len(inbox),
                  "duplicates": sum(e["event"] == "duplicate" for e in server), "post_probe": probe_ids},
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true", help="Stage and run only after explicit approval")
    parser.add_argument("--analyze", type=Path, help="Recalculate a profile from collected evidence")
    parser.add_argument("profiles", nargs="*", metavar="PROFILE")
    args = parser.parse_args()
    if args.analyze:
        if args.execute or args.profiles or args.analyze.name not in PROFILES:
            parser.error("--analyze memerlukan direktori profil dan tidak menerima opsi eksekusi.")
        print(json.dumps(analyze(args.analyze), indent=2))
        return
    profiles = args.profiles or list(PROFILES)
    if len(set(profiles)) != len(profiles) or any(name not in PROFILES for name in profiles):
        parser.error("Profil harus unik dan berasal dari daftar Stage 09B.")
    for profile in profiles:
        tc, duration = PROFILES[profile]
        print(f"{profile}: /usr/sbin/tc qdisc add dev enp0s8 root handle 709: netem {tc}; {duration}s", flush=True)
    if args.execute:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        target = PROJECT / "results/stage09b" / f"matrix-{stamp}-{uuid4().hex[:8]}"
        target.mkdir()
        handoff(target, profiles)


if __name__ == "__main__":
    main()
