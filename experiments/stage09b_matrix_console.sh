#!/usr/bin/env bash
# Jalankan sekali di konsol teks Debian setelah controller siap.
set -euo pipefail
umask 077
root=${1:?direktori batch}
[[ $# = 1 && $root = /* && -z ${SSH_CONNECTION:-} && -t 0 ]]
console_tty=$(tty)
[[ $console_tty =~ ^/dev/tty[0-9]+$ ]]
[[ $(hostname -s) = debian-pqc && $(id -un) = research ]]
cd "$HOME/hpqc_demo"
exec 9>private-data/stage09b/matrix-console.lock
flock -n 9
sudo -v
mkdir "$root/console-started"
py=.venv/bin/python

run_profile() {
    local run=$1 output=$1/console client observer apply_rc=0 rollback_rc=1 client_rc=0
    mkdir "$output"
    # Pewaris FD 9 menjaga lock konsol selama proses profil masih hidup.
    sudo -n -v
    (cd "$run"; sha256sum -c pilot.sha256)
    [[ $(stat -c %a "$run/resilience.psk") = 600 && $(wc -c < "$run/resilience.psk") = 32 ]]
    bash "$run/pilot-reviewed.sh" before "$output/pilot"
    grep -q '4 packets transmitted, 4 received, 0% packet loss' "$output/pilot/ping-before"
    local args=(--host 10.10.30.10 --port 5061 --suite ml-kem-768 --timeout 3
        --psk-file "$run/resilience.psk" --text HPQC-09B --retries 8 --backoff 0.2 --backoff-cap 2)
    timeout 100 "$py" -Bu -m protocol.resilience_cli client "${args[@]}" \
        --count 45 --interval 1 --heartbeat 0.3 > "$output/client.jsonl" 2> "$output/client.stderr" &
    client=$!
    # Observer mencatat akhir qdisc meskipun client selesai lebih awal.
    (
        while [[ ! -f $output/stop-observer ]]; do
            "$py" -B -c 'import time; print(time.perf_counter_ns())'
            /usr/sbin/tc -s qdisc show dev enp0s8
            ss -nti dst 10.10.30.10:5061
            sleep 0.5
        done
    ) > "$output/samples.txt" 2> "$output/samples.stderr" &
    observer=$!
    trap 'touch "$output/stop-observer"; kill "$client" 2>/dev/null || true; wait "$client" "$observer" 2>/dev/null || true' EXIT
    for ((i=0; i<80; i++)); do
        if grep -q '"event": "delivered"' "$output/client.jsonl"; then break; fi
        kill -0 "$client"
        sleep 0.25
    done
    grep -q '"event": "delivered"' "$output/client.jsonl"
    kill -0 "$client"
    [[ ! -e $root/abort && -f $run/ready ]]
    (( $(date +%s) < $(cat "$run/ready") ))
    kill -0 "$observer"
    bash "$run/pilot-reviewed.sh" apply "$output/pilot" > "$output/unit.txt" 2>&1 || apply_rc=$?
    if [[ -f $output/pilot/armed-at ]]; then
        rollback_rc=0
        bash "$run/pilot-reviewed.sh" after "$output/pilot" > "$output/rollback.txt" 2>&1 || rollback_rc=$?
    fi
    printf 'apply_exit=%s\nafter_exit=%s\n' "$apply_rc" "$rollback_rc" > "$output/network-status.txt"
    ((apply_rc == 0 && rollback_rc == 0))
    grep -q '4 packets transmitted, 4 received, 0% packet loss' "$output/pilot/ping-after"
    wait "$client" || client_rc=$?
    printf '%s\n' "$client_rc" > "$output/client-exit.txt"
    touch "$output/stop-observer"
    wait "$observer"
    trap - EXIT
    # Receipt probe merupakan bagian dari verifikasi keamanan operasional.
    timeout 20 "$py" -Bu -m protocol.resilience_cli client "${args[@]}" --count 1 \
        > "$output/post-client.jsonl" 2> "$output/post-client.stderr"
    grep -q '"event": "delivered"' "$output/post-client.jsonl"
    touch "$output/complete"
}

while IFS= read -r profile; do
    [[ $profile =~ ^[a-z0-9-]+$ ]]
    run=$root/$profile
    for ((i=0; i<600; i++)); do
        [[ ! -e $root/abort ]] || exit 1
        [[ ! -e $run/ready ]] || break
        sleep 1
    done
    test -f "$run/ready"
    echo "Profil $profile dimulai."
    # Bash baru mempertahankan errexit di dalam run_profile.
    export -f run_profile
    export root py
    set +e
    bash -euo pipefail -c 'run_profile "$1"' runner "$run" < "$console_tty" > "$run/runner.txt" 2>&1
    rc=$?
    set -e
    printf '%s\n' "$rc" > "$run/console-exit"
    if ((rc != 0)); then
        echo "Profil $profile berhenti. Periksa $run/runner.txt."
        exit "$rc"
    fi
done < "$root/profiles.txt"
