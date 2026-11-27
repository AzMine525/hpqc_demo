#!/usr/bin/env bash
# Operator menjalankan ini sekali dari konsol Debian setelah listener siap.
set -euo pipefail
umask 077
run=${1:?direktori absolut run pilot}
[[ $run = /* && $# = 1 && -z ${SSH_CONNECTION:-} && -t 0 && $(tty) =~ ^/dev/tty[0-9]+$ ]]
cd "$HOME/hpqc_demo"
py=.venv/bin/python
test -f "$run/ready"
test "$(stat -c %a "$run/resilience.psk")" = 600
test "$(wc -c < "$run/resilience.psk")" -eq 32
(cd "$run" && sha256sum -c pilot.sha256)
sudo -v
# mkdir mengunci satu percobaan operator dan mempertahankan bukti percobaan itu.
mkdir "$run/console"
out=$run/console
exec > >(tee "$out/console.txt") 2>&1
bash "$run/pilot-reviewed.sh" before "$out/pilot"
args=(--host 10.10.30.10 --port 5061 --suite ml-kem-768 --timeout 3
      --psk-file "$run/resilience.psk" --text HPQC-09B --retries 8
      --backoff 0.2 --backoff-cap 2)

timeout 100 "$py" -Bu -m protocol.resilience_cli client "${args[@]}" \
    --count 45 --interval 1 --heartbeat 0.3 > "$out/client.jsonl" 2> "$out/client.stderr" &
client=$!
for ((i=0; i<80; i++)); do
    if grep -q '"event": "delivered"' "$out/client.jsonl"; then break; fi
    kill -0 "$client"
    sleep 0.25
done
grep -qm1 '"event": "delivered"' "$out/client.jsonl"
kill -0 "$client"

(
    while kill -0 "$client" 2>/dev/null; do
        "$py" -B -c 'import time; print(time.perf_counter_ns())'
        /usr/sbin/tc -s qdisc show dev enp0s8
        systemctl show hpqc-stage09b-delay50.service -p ActiveState -p RuntimeMaxUSec -p ExecStopPost
        ss -ti dst 10.10.30.10
        sleep 0.5
    done
) > "$out/samples.txt" 2> "$out/samples.stderr" &
observer=$!

apply_rc=0
bash "$run/pilot-reviewed.sh" apply "$out/pilot" 2>&1 | tee "$out/unit.txt" || apply_rc=$?
echo "apply_exit=$apply_rc"
after_rc=1
if test -f "$out/pilot/armed-at"; then
    after_rc=0
    bash "$run/pilot-reviewed.sh" after "$out/pilot" 2>&1 | tee "$out/rollback.txt" || after_rc=$?
    journalctl -b -u hpqc-stage09b-delay50.service --since "$(cat "$out/pilot/armed-at")" \
        -o short-monotonic > "$out/journal.txt" 2> "$out/journal.stderr" || true
fi
echo "after_exit=$after_rc"
if ((apply_rc != 0 || after_rc != 0)); then
    kill "$client" 2>/dev/null || true
    wait "$client" "$observer" || true
    exit 1
fi
wait "$client"
wait "$observer"
"$py" -Bu -m protocol.resilience_cli client "${args[@]}" --count 1 \
    > "$out/post-client.jsonl" 2> "$out/post-client.stderr"
grep -q '"event": "delivered"' "$out/post-client.jsonl"
touch "$out/complete"
