#!/usr/bin/env bash
# Pilot tunggal Debian. Jalankan dari SSH manajemen atau konsol lokal berizin.
set -euo pipefail
export LC_ALL=C
mode=${1:?before, apply, atau after}
dir=${2:?direktori bukti absolut baru untuk pilot}
[[ $dir = /* && $# = 2 ]]
unit=hpqc-stage09b-matrix.service
tc=/usr/sbin/tc
expected='qdisc fq_codel 0: root refcnt 2 limit 10240p flows 1024 quantum 1514 target 5ms interval 100ms memory_limit 32Mb ecn drop_batch 64'
[[ $(hostname -s) = debian-pqc ]]
if [[ -n ${SSH_CONNECTION:-} ]]; then
    read -r manager _ local_ip _ <<< "$SSH_CONNECTION"
    [[ $manager = 10.10.20.1 && $local_ip = 10.10.20.4 ]]
else
    # Alamat sumber SSH ini diverifikasi pada sesi BatchMode dari Windows.
    [[ -t 0 && $(tty) =~ ^/dev/tty[0-9]+$ ]] || {
        echo 'Gunakan SSH manajemen atau konsol VirtualBox Debian.' >&2
        exit 1
    }
    manager=10.10.20.1
fi
[[ $(cat /sys/class/net/enp0s8/address) = 08:00:27:4f:1a:51 ]]
umask 077

snapshot() {
    local dest=$1
    mkdir -- "$dest"
    ip -br -4 addr show > "$dest/addresses"
    ip -4 route show table all > "$dest/routes"
    ip -4 route get 10.10.30.10 > "$dest/data-route"
    ip -4 route get 10.10.20.1 > "$dest/gateway-route"
    ip -4 route get "$manager" > "$dest/ssh-route"
    "$tc" qdisc show dev enp0s8 > "$dest/qdisc"
    "$tc" class show dev enp0s8 > "$dest/classes"
    "$tc" filter show dev enp0s8 root > "$dest/filters"
    "$tc" qdisc show dev enp0s3 > "$dest/management-qdisc"
    cat /proc/sys/net/core/default_qdisc > "$dest/default"
    grep -Eq '^enp0s8 +UP +.*10\.10\.30\.20/24( |$)' "$dest/addresses"
    grep -Eq '^enp0s3 +UP +.*10\.10\.20\.4/24( |$)' "$dest/addresses"
    grep -Eq ' dev enp0s8 .*src 10\.10\.30\.20( |$)' "$dest/data-route"
    for route in gateway-route ssh-route; do
        grep -Eq ' dev enp0s3 .*src 10\.10\.20\.4( |$)' "$dest/$route"
    done
    # tc pada Debian dapat menambahkan spasi di akhir baris. Simpan output mentah untuk diff.
    [[ $(cat "$dest/default") = fq_codel && $(sed 's/[[:blank:]]*$//' "$dest/qdisc") = "$expected" ]]
    [[ ! -s $dest/classes && ! -s $dest/filters ]]
}

case $mode in
before)
    mkdir -- "$dir"
    snapshot "$dir/before"
    ping -I enp0s8 -c 4 -W 2 10.10.30.10 > "$dir/ping-before"
    touch "$dir/baseline-ok"
    ;;
apply)
    [[ -f $dir/baseline-ok && ! -e $dir/armed-at && ! -e $dir/after ]]
    snapshot "$dir/recheck"
    diff -ru "$dir/before" "$dir/recheck"
    ping -I enp0s8 -c 4 -W 2 10.10.30.10 > "$dir/ping-recheck"
    # PID 1 menerima batas durasi dan perintah pemulihan sebelum memulai tc.
    cleanup="ExecStopPost=/bin/sh -ec 'if /usr/sbin/tc qdisc show dev enp0s8 | /usr/bin/grep -q \"^qdisc netem 709: root \"; then exec /usr/sbin/tc qdisc del dev enp0s8 root handle 709:; else /usr/sbin/tc qdisc show dev enp0s8 | /usr/bin/grep -q \"^qdisc fq_codel 0: root \"; fi'"
    [[ ! -e $root/abort && -f ${dir%/console/pilot}/ready ]]
    (( $(date +%s) < $(cat "${dir%/console/pilot}/ready") ))
    date --iso-8601=seconds > "$dir/armed-at"
    sudo -n systemd-run --unit="$unit" --wait --service-type=exec \
        --property=RuntimeMaxSec=16s --property=TimeoutStopSec=3s \
        --property="$cleanup" /bin/sh -ec \
        '/usr/sbin/tc qdisc add dev enp0s8 root handle 709: netem delay 50ms 10ms
         /usr/sbin/tc -s qdisc show dev enp0s8
         /bin/sleep 12
         /usr/sbin/tc -s qdisc show dev enp0s8'
    ;;
after)
    [[ -f $dir/armed-at ]]
    snapshot "$dir/after"
    diff -ru "$dir/before" "$dir/after"
    ping -I enp0s8 -c 4 -W 2 10.10.30.10 > "$dir/ping-after"
    ;;
*) exit 2 ;;
esac
