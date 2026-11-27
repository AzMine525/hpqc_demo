# Stage 09B — validasi dua VM dan pilot Debian

## A. Tujuan dan status pada 27 November 2026

SSH BatchMode, smoke, 80/80 regresi per VM, DATA/ACK dua arah, receipt setelah commit, deduplikasi dan reconnect antar-VM terverifikasi. **Stage 09 PASS berdasarkan audit ROADMAP.md di akhir dokumen.** Seluruh kondisi matriks Linux memiliki bukti dan rollback setiap run impairment lulus. Tabel B dan C merekam konfigurasi awal dan pemeriksaan awal.

## B. Topologi dan asal bukti

| Pemeriksaan | Debian, client | Ubuntu, server |
|---|---|---|
| XML aktif pada disk host Windows, slot 0 / slot 1 | NATNetwork PQC-LAB / InternalNetwork PQC-EXPERIMENT | NATNetwork PQC-LAB / InternalNetwork PQC-EXPERIMENT |
| MAC slot eksperimen, cocok dengan catatan operator | 08:00:27:4f:1a:51 | 08:00:27:a3:fb:1a |
| Tuple forward TCP di VirtualBox.xml | 127.0.0.1:2222 → 10.10.20.4:22 | 127.0.0.1:2223 → 10.10.20.5:22 |
| Host, akun dan direktori menurut operator | debian-pqc, research, ~/hpqc_demo | ubuntu-pqc, research2, ~/hpqc_demo |
| Jalur manajemen menurut operator | enp0s3, 10.10.20.4/24, gateway 10.10.20.1 | enp0s3, 10.10.20.5/24, gateway 10.10.20.1 |
| Jalur data menuju peer menurut operator | enp0s8 UP, sumber 10.10.30.20/24 | enp0s8 UP, sumber 10.10.30.10/24 |
| iproute2 dan tc menurut operator | 6.15.0-1, tc 6.15.0 di /usr/sbin/tc | 6.19.0-1ubuntu1.1, tc 6.19.0 di /usr/sbin/tc |
| Root qdisc enp0s8 menurut operator | fq_codel handle 0:, parameter lengkap dalam skrip pilot | pfifo_fast 0: root refcnt 2 bands 3 priomap 1 2 2 2 1 2 0 0 1 1 1 1 1 1 1 1 |
| Ping enp0s8 menuju peer menurut operator | 4/4, loss 0%, min/avg/max/mdev 1,588/3,330/6,951/2,126 ms | 4/4, loss 0%, min/avg/max/mdev 1,944/2,578/3,699/0,667 ms |

Alamat eksperimen disetel manual dan dapat hilang setelah reboot. Pemeriksaan XML menunjukkan konfigurasi tersimpan. Rute balik ke sumber SSH aktual memerlukan pemeriksaan dalam sesi terautentikasi, termasuk bila VirtualBox menerjemahkan alamat pengelola.

## C. Pemeriksaan aktual dan bukti sebelumnya

Host LAPTOP-MNMLL0ST, OpenSSH_for_Windows_9.5p2. Working tree awal bersih pada branch step10, HEAD `f9578d3cedfa5104caf9f6123d36700b7c3e2b4c`. Pemeriksaan host meliputi `git status --short --branch`, `git diff --stat`, `git rev-parse HEAD`, pembacaan XML kedua mesin dan aturan PortForwarding4, serta `Get-FileHash results/stage09/*`.

```powershell
ssh -G debian-pqc
ssh -G ubuntu-pqc
ssh-add -l
ssh -T -o BatchMode=yes -o StrictHostKeyChecking=yes -o ConnectTimeout=5 -o UpdateHostKeys=no -o ClearAllForwardings=yes -p 2222 research@127.0.0.1 hostname
ssh -T -o BatchMode=yes -o StrictHostKeyChecking=yes -o ConnectTimeout=5 -o UpdateHostKeys=no -o ClearAllForwardings=yes -p 2223 research2@127.0.0.1 hostname
```

| Pemeriksaan | Status | Bukti |
|---|---|---|
| Dua NIC dan forward tersimpan | PASS | Slot serta MAC di bagian B. |
| SSH manajemen | PASS | Pada 26 November kedua percobaan awal berakhir `Permission denied (publickey,password)`. Pada 27 November alias dan agent pengguna Windows memberi exit 0 untuk `hostname; whoami` di kedua VM. Debian melaporkan research, Ubuntu research2. |
| Jalur balik SSH dan gateway | PASS | Sumber SSH yang terlihat di kedua guest adalah 10.10.20.1. Rute melalui enp0s3 dengan IP lokal masing-masing sesuai tabel B. |
| Jalur eksperimen | PASS pada 06.21 WIB | Sesudah operator memulihkan 10.10.30.10/24 di Ubuntu, kedua IP eksperimen UP dan rute data langsung menggunakan enp0s8. Ping terikat enp0s8 4/4 pada kedua arah. Pada 06.07 WIB alamat Ubuntu sempat hilang dan ping gagal 0/4. |
| Kernel dan qdisc | PASS untuk inspeksi | Kedua kernel melaporkan CONFIG_NET_SCH_NETEM=m dan modinfo menemukan modul untuk kernel aktif. Default sysctl keduanya fq_codel. Root aktual Debian fq_codel dan Ubuntu pfifo_fast dengan opsi pada tabel B. Filter/class yang diperiksa kosong. |
| Revisi dan dependency | PASS untuk source pengujian | HEAD kedua guest 3df1e695a88fb54be7bcd3431cdcbd4bb9b9b969. Empat puluh entri Git file Python dan requirements identik dengan indeks host, diff guest terhadap HEAD kosong pada file itu. Pada venv, pqcrypto 1.0.0, cryptography 49.0.0, psutil 7.2.2. Python sistem di keduanya tidak memiliki metadata pqcrypto. |
| Debian GNU/Linux 13, kernel 6.12.118+deb13-amd64, venv Python 3.13.5 | PASS | Smoke exit 0, agreement dan dekripsi True. Regresi 80/80, 10,624 detik, tanpa skip. |
| Ubuntu 26.04.1 LTS, kernel 7.0.0-44-generic, venv Python 3.14.4 | PASS | Smoke exit 0, agreement dan dekripsi True. Regresi 80/80, 7,326 detik, tanpa skip. |
| Stage 05 DATA/ACK antar-VM | PASS | 1.048.576 byte per arah, ACK mencocokkan ID DATA, SHA-256 kirim dan terima cocok silang. |
| Stage 09 normal dan deduplikasi antar-VM | PASS | Tiga pesan memperoleh tiga receipt dan empat PONG. Dua kiriman tambahan dengan satu ID memperoleh dua receipt pada sesi berbeda. Total lima receipt cocok dengan empat commit unik dan empat baris SQLite, satu duplikat dikenali. |
| Stage 09 reconnect antar-VM | PASS | Uji idle membuat Ubuntu menutup sesi dengan TimeoutError. Client yang sama melihat EOF, retry dengan ID pesan yang sama, menyelesaikan handshake dengan ID sesi baru dan memperoleh receipt pada attempt 2. Dua receipt cocok dengan dua commit dan dua baris SQLite. |
| Pemeriksaan skrip pilot | PASS statis dan mode before | Git Bash memeriksa sintaks skrip dan blok Bash panduan. Fixture memeriksa tiga cabang cleanup (handle pilot, qdisc sudah default, handle asing) dan penolakan tanpa sesi SSH. Debian systemd 257 memvalidasi properti cleanup melalui systemd-analyze verify. Mode before sempat gagal pada 06.07 ketika IP Ubuntu hilang. Sesudah pemulihan, skrip final lulus dengan ping 4/4 dan marker baseline-ok. |
| Pengujian konsol dan impairment | NOT RUN pada checkpoint ini | Operator pernah login konsol Debian dan menggunakan sudo. Konfirmasi ulang konsol saat pilot, apply, rollback aktual dan pemeriksaan sesudahnya masih terbuka. |
| Bukti Windows terdahulu | PASS historis | 80/80 tes. Normal dan outage layanan masing-masing 3 receipt dan 3 baris. Pada outage ada 1 duplicate dan sesi baru. SHA-256 JSON 819460c00b1f1d7ab9fd620505805416f9fec4a77af1269824b04351e223a93f, transkrip b929cd9a6f90d301b5ed5b3b7fe057b119bcf7d33a1db9ffa3f6fe44d2e4d9d6, keduanya dicocokkan pada checkpoint ini. |

Bukti asli tersedia pada [event loopback](../results/stage09/loopback.json) dan [transkrip Windows](../results/stage09/test-results.txt).

Pada 27 November, perintah verifikasi alias yang dijalankan dari konteks agent Windows adalah sebagai berikut.

```powershell
ssh -o BatchMode=yes -o StrictHostKeyChecking=yes -o UpdateHostKeys=no -o ConnectTimeout=5 debian-pqc 'hostname; whoami'
ssh -o BatchMode=yes -o StrictHostKeyChecking=yes -o UpdateHostKeys=no -o ConnectTimeout=5 ubuntu-pqc 'hostname; whoami'
```

Preflight aktual memakai `ip -br link`, `ip -br -4 addr`, `ip -4 route get` untuk sumber SSH, gateway dan peer, `/usr/sbin/tc -V`, `tc qdisc/class/filter show` pada enp0s8, `cat /proc/sys/net/core/default_qdisc`, konfigurasi kernel di /boot, `/usr/sbin/modinfo -F filename sch_netem` dan `ping -I enp0s8 -c 4 -W 2 "$peer"`. Hasil kedua arah direkam sekitar 06.07 WIB. [Debian](../results/stage09b/20261127-0607/debian/network.txt) · [Ubuntu](../results/stage09b/20261127-0607/ubuntu/network.txt)

Run menggunakan `git ls-files --stage -- '*.py' requirements.txt`, `git diff --exit-code HEAD -- '*.py' requirements.txt`, `.venv/bin/python -B smoke_test.py` dan `.venv/bin/python -B -m unittest discover -s tests -v`. Untuk tes interoperabilitas, salinan arsip asli terverifikasi dipakai melalui HPQC_BASELINE_ZIP di direktori privat run. SHA-256 arsip 4c96cd9f4462b5b1a1f1350c4b1fd4ea572c80343f76997b41625e19b381a981. SHA-256 transkrip lokal sesudah penyalinan sama dengan guest. [Regresi Debian](../results/stage09b/20261127-0607/debian/regression.txt) · [Regresi Ubuntu](../results/stage09b/20261127-0607/ubuntu/regression.txt)

Run lanjutan `20261127-0621` memakai perintah bagian F–G dengan port 5055 (transfer), 5059 (normal dan deduplikasi), dan 5060 (idle reconnect dengan inbox terpisah). Listener diikat ke 10.10.30.10 dan diberi batas total 120 detik. Dua PSK acak khusus run disimpan dengan mode 600 di direktori privat guest dan disalurkan lewat SSH terverifikasi. Bukti smoke/regresi dipakai ulang. RTT rata-rata ping 4,512 ms dari Debian dan 2,190 ms dari Ubuntu. [Jalur Debian](../results/stage09b/20261127-0621/debian/network.txt) · [Jalur Ubuntu](../results/stage09b/20261127-0621/ubuntu/network.txt)

Verifikasi di Windows mencocokkan ACK dengan ID DATA peer, hash payload silang, himpunan ID delivered dengan committed dan SQLite, serta urutan event recovery. Sesudah EOF terdeteksi, TCP tersambung pada 209,076 ms, sesi aman siap pada 269,278 ms dan receipt tiba pada 329,178 ms. Pengukuran memakai jam monotonic client dalam satu run dengan penutupan sesi akibat idle timeout. [Transfer Debian](../results/stage09b/20261127-0621/debian/transfer.txt) · [Transfer Ubuntu](../results/stage09b/20261127-0621/ubuntu/transfer.txt) · [Normal client](../results/stage09b/20261127-0621/debian/normal-client.jsonl) · [Inbox normal](../results/stage09b/20261127-0621/ubuntu/normal-inbox.tsv) · [Reconnect client](../results/stage09b/20261127-0621/debian/idle-client.jsonl) · [Inbox idle](../results/stage09b/20261127-0621/ubuntu/idle-inbox.tsv)

`bash -n` dan mode `before` dijalankan pada Debian dengan SHA-256 skrip 107c4692768d1e082a3e0ce39fe81d0a62d682f2ba8e10f8407b188f7926850c, identik dengan workspace. [Baseline qdisc](../results/stage09b/20261127-0621/debian/qdisc) · [Ping sebelum pilot](../results/stage09b/20261127-0621/debian/ping-before)

## D. Preflight guest dan direktori bukti

Masuk melalui endpoint bagian C menggunakan kredensial lab yang telah disetujui. Pada masing-masing guest jalankan Bash berikut. Gunakan direktori baru pada setiap skenario. Catat pasangan nama direktori kedua guest dan identitas run. Pertahankan terminal yang sama atau ekspor ulang variabel ke terminal tambahan. Contoh memakai venv proyek yang sudah tersedia.

```bash
set -euo pipefail
umask 077
cd ~/hpqc_demo
PY=${PY:-./.venv/bin/python}
case "$(hostname -s)" in
  debian-pqc) peer=10.10.30.10 ;;
  ubuntu-pqc) peer=10.10.30.20 ;;
  *) exit 1 ;;
esac
manager=${SSH_CONNECTION%% *}
test -n "$manager"
mkdir -p private-data/stage09b
R=$(mktemp -d "$PWD/private-data/stage09b/$(date -u +%Y%m%dT%H%M%SZ)-XXXXXX")
echo "$R"
{
  date -u --iso-8601=seconds
  hostname; uname -r; cat /etc/os-release
  ip -br link; ip -br -4 addr; ip -4 route show
  for dest in "$peer" 10.10.20.1 "$manager"; do ip -4 route get "$dest"; done
  cat /sys/class/net/enp0s8/address /proc/sys/net/core/default_qdisc
  command -v tc || test -x /usr/sbin/tc
  /usr/sbin/tc -V
  /usr/sbin/tc -d qdisc show dev enp0s8
  /usr/sbin/tc class show dev enp0s8
  /usr/sbin/tc filter show dev enp0s8 root
  if test -r "/boot/config-$(uname -r)"; then grep '^CONFIG_NET_SCH_NETEM=' "/boot/config-$(uname -r)" || true; fi
  if test -r /proc/config.gz; then zgrep '^CONFIG_NET_SCH_NETEM=' /proc/config.gz || true; fi
  if test -d /sys/module/sch_netem; then echo sch_netem-present; fi
  if command -v modinfo >/dev/null; then modinfo -F filename sch_netem || true; fi
  ping -I enp0s8 -c 4 -W 2 "$peer"
  git --no-optional-locks status --short --branch
  git rev-parse HEAD
  "$PY" -B -c 'import sys,pqcrypto,cryptography,psutil; from importlib.metadata import version; print(sys.executable,sys.version,[(p,version(p)) for p in ("pqcrypto","cryptography","psutil")])'
} 2>&1 | tee "$R/preflight.txt"
```

Periksa alamat, MAC dan jalur data/manajemen pada tabel B. Cocokkan HEAD dan perubahan source di kedua guest. Untuk salinan tanpa Git, simpan manifest hash file Python aplikasi, tes, benchmark dan requirements dari ketiga checkout dan cocokkan isi setelah normalisasi CRLF/LF. Jika source atau dependency berbeda, dokumentasikan selisih sebelum mengatribusikan hasil ke revisi ini. Dukungan kernel memerlukan bukti konfigurasi `=y`, atau `=m` dengan modul tersedia untuk kernel aktif, atau modul yang sudah dimuat. Jika bukti tidak dapat diperoleh, beri status BLOCKED. Pemeriksaan ini tidak memuat modul. Bukti operasional pertama berasal dari pemasangan qdisc berizin.

## E. Smoke dan regresi di kedua guest

```bash
unset PYTHONOPTIMIZE
export PYTHONDONTWRITEBYTECODE=1
mkdir "$R/tmp"; export TMPDIR="$R/tmp"
"$PY" -B smoke_test.py 2>&1 | tee "$R/smoke.txt"
"$PY" -B -m unittest discover -s tests -v 2>&1 | tee "$R/regression.txt"
```

Catat exit code dengan `pipefail`, jumlah run, kegagalan dan skip untuk tiap guest. Bila arsip Stage 00 sudah tersedia di jalur lain, set `HPQC_BASELINE_ZIP` ke arsip yang diverifikasi sebelum regresi. Tes interoperabilitas dapat di-skip bila arsip tidak ditemukan.

## F. Baseline Stage 05 dua arah

Gunakan dua PSK biner 32 byte yang sudah diprovisikan, terpisah untuk profil 05 dan 09. Di tiap guest tetapkan `K5` dan `K9` ke path privat lokal dan periksa panjang dengan `test "$(wc -c < "$K5")" -eq 32` serta uji yang sama untuk K9. Gunakan shell tanpa xtrace. Verifikasi port 5055/5059 bebas dengan `ss -ltn`. Jika port sudah dipakai, hentikan run. Semua command berikut dijalankan dari root proyek.

```bash
# Kedua guest, masing-masing menghasilkan berkas sintetis 1 MiB.
"$PY" -B -c 'import os,sys; open(sys.argv[1],"xb").write(os.urandom(1048576))' "$R/send.bin"
X=(--host 10.10.30.10 --port 5055 --suite ml-kem-768 --timeout 5 --psk-file "$K5" --input "$R/send.bin" --output "$R/received.bin")
# Ubuntu dahulu
"$PY" -Bu -m protocol.transfer_cli server "${X[@]}" 2>&1 | tee "$R/transfer.txt"
# Debian saat Ubuntu listening
"$PY" -Bu -m protocol.transfer_cli client "${X[@]}" 2>&1 | tee "$R/transfer.txt"
# Kedua guest sesudah proses berakhir
sha256sum "$R"/{send,received}.bin | tee "$R/transfer-hashes.txt"
```

PASS memerlukan exit 0 pada keduanya, ACK terverifikasi untuk masing-masing ID DATA dan hash kirim Debian = hash terima Ubuntu serta sebaliknya.

## G. Baseline Stage 09, deduplikasi dan fresh handshake

Mulai server Ubuntu, tunggu event listening, lalu jalankan perintah Debian. Gunakan direktori run baru untuk tiap skenario dan inbox baru yang khusus untuk pasangan ini.

```bash
# Kedua guest
A=(--host 10.10.30.10 --port 5059 --suite ml-kem-768 --timeout 3 --psk-file "$K9")
# Ubuntu, terminal khusus. Hentikan dengan Ctrl+C setelah semua receipt skenario dicatat.
"$PY" -Bu -m protocol.resilience_cli server "${A[@]}" --inbox "$R/inbox.sqlite" --idle-timeout 15 | tee "$R/server.jsonl"
# Debian
C=(--text HPQC-09B --retries 8 --backoff 0.2 --backoff-cap 2)
"$PY" -Bu -m protocol.resilience_cli client "${A[@]}" "${C[@]}" --count 3 --interval 1 --heartbeat 0.3 | tee "$R/normal.jsonl"
ID=$("$PY" -B -c 'import secrets; print(secrets.token_hex(16))')
for attempt in 1 2; do
  "$PY" -Bu -m protocol.resilience_cli client "${A[@]}" "${C[@]}" --message-id "$ID" | tee "$R/repeat-$attempt.jsonl"
done
```

Harapkan tiga ID normal dengan receipt dan PONG, lalu dua receipt untuk satu ID eksplisit, satu commit dan satu duplicate untuk ID itu. Dalam run terpisah, mulai lagi server dengan `--idle-timeout 1` dan inbox baru. Jalankan client berikut. Idle tiga detik sebelum pesan kedua memberi kesempatan server menutup sesi. Uji ini menargetkan reconnect otomatis dalam **satu proses client**.

```bash
"$PY" -Bu -m protocol.resilience_cli client "${A[@]}" "${C[@]}" --count 2 --interval 3 --heartbeat 10 | tee "$R/idle-reconnect.jsonl"
```

Untuk PASS, periksa interrupted, retry dengan ID operasi yang sama, tcp_connected, secure_ready dengan session ID berbeda, lalu delivered. Cocokkan dua pesan dengan dua baris. Interval heartbeat 10 detik hanya berlaku untuk uji idle ini.

Pada Ubuntu, buka inbox dengan SQLite mode baca-saja, setelah server berhenti. Simpan hanya ID publik, ukuran dan checksum payload sintetis untuk dicocokkan dengan daftar event client.

```bash
"$PY" -B - "$R/inbox.sqlite" <<'PY' | tee "$R/inbox.tsv"
import hashlib, pathlib, sqlite3, sys
p = pathlib.Path(sys.argv[1]).resolve()
with sqlite3.connect(p.as_uri() + "?mode=ro", uri=True) as db:
    for mid, data in db.execute("select message_id,payload from inbox order by message_id"):
        assert data == b"HPQC-09B"
        print(mid.hex(), len(data), hashlib.sha256(data).hexdigest(), sep="\t")
PY
```

Periksa kesamaan himpunan ID unik delivered, committed dan SQLite. Cocokkan jumlah kiriman yang direncanakan, jumlah receipt, duplicate dan byte. Untuk satu run normal beserta dua kiriman ID eksplisit di atas, harapkan empat baris unik dan lima receipt. Dalam pilot, gunakan payload identik agar pemeriksaan byte yang sama berlaku.

## H. Pilot yang diajukan untuk persetujuan

### Hasil pilot 27 November 2026

**PASS untuk satu pilot delay 50 ms egress Debian.** Run `pilot-delay50-20261127-065141` menggunakan ML-KEM-768 dan port 5061 Ubuntu. Sebelum eksekusi, dua login BatchMode, IP, rute dan qdisc cocok dengan baseline. Ping 4/4 tiap arah. Operator menjalankan `bash "$R/console-reviewed.sh" "$R"` dari konsol Debian dengan otorisasi sudo lokal. Skrip menunggu receipt pertama lalu menjalankan mode `apply` dan `after`. [Preflight Debian](../results/stage09b/pilot-delay50-20261127-065141/debian/preflight.txt) · [Preflight Ubuntu](../results/stage09b/pilot-delay50-20261127-065141/ubuntu/preflight.txt) · [Output konsol](../results/stage09b/pilot-delay50-20261127-065141/debian/console.txt)

| Kriteria | Hasil aktual |
|---|---|
| Impairment terpasang | Pada 06.56.51 WIB, SSH mengamati root `netem 709:` dengan delay 50 ms di Debian enp0s8. Unit aktif, RuntimeMaxUSec 16 detik, dan ExecStopPost terdaftar. Unit melaporkan runtime 12,287 detik dan exit 0. |
| Durasi dan statistik qdisc | Snapshot monotonic membatasi durasi aktif antara 11,464 dan 12,714 detik. Sampel aktif terakhir mencatat 118 paket dan 13.568 byte, nol drop, overlimit dan requeue. Counter mencakup trafik interface selama sampel. |
| Pengiriman dan heartbeat | 45/45 receipt untuk workload utama dan 92 PONG. Di antara sampel aktif pertama dan terakhir terdapat 9 receipt. Ada 3 receipt sebelum, 31 setelah, serta 2 di sela sampel tepi yang belum dapat ditempatkan secara pasti. |
| Kontinuitas sesi | Satu sesi aman untuk 45 pesan. Nol interupsi terdeteksi, retry, dan duplicate. Latensi pemulihan N/A. Uji reconnect akibat idle timeout sebelumnya tercatat terpisah. |
| SSH saat impairment | Login baru sebagai research dan research2 berhasil. Rute SSH tetap memakai enp0s3. Ubuntu tetap memakai pfifo_fast. |
| Rollback qdisc dan rute | `apply_exit=0`, `after_exit=0`. Unit berstatus inactive dan not-found setelah selesai. Snapshot Debian dan Ubuntu masing-masing identik sebelum dan sesudah. Debian kembali ke fq_codel handle 0: dengan semua opsi baseline, root netem 709: hilang. |
| Konektivitas dan delivery sesudah rollback | Login BatchMode baru berhasil pada kedua VM. Ping 4/4 tiap arah. Pesan baru ID `ac4e758a9d5925601da187c37be54c25` memperoleh receipt pada sesi baru dan cocok dengan commit serta baris SQLite. Total 46/46 receipt dan 46 ID unik identik dengan log commit dan inbox. |

Perintah observasi aktual mencakup `systemctl show hpqc-stage09b-delay50.service -p ActiveState -p RuntimeMaxUSec -p ExecStopPost`, `tc -s qdisc show dev enp0s8`, `ss -ti dst 10.10.30.10`, `ip -4 route show table all`, `ip -4 route get`, `ping -I enp0s8 -c 4 -W 2` dan `diff -u before.txt after.txt` pada tiap VM. Hasil memverifikasi pembersihan pada terminasi normal unit. Cabang kedaluwarsa RuntimeMaxSec dan skenario SSH sengaja diputus belum diuji. Jurnal sistem unit tidak terbaca oleh akun research pada run ini. Durasi berasal dari output systemd-run dan batas sampel qdisc. [Unit aktif](../results/stage09b/pilot-delay50-20261127-065141/debian/active-unit.txt) · [Sampel qdisc/TCP](../results/stage09b/pilot-delay50-20261127-065141/debian/samples.txt) · [Ringkasan terverifikasi](../results/stage09b/pilot-delay50-20261127-065141/summary.json) · [Inbox](../results/stage09b/pilot-delay50-20261127-065141/ubuntu/inbox.tsv)

### Persiapan dan prosedur pilot

Operator menyetujui satu pilot delay 50 ms dan mengonfirmasi ulang login serta sudo pada konsol Debian. Preflight 06.35 WIB memverifikasi SSH BatchMode, kedua IP eksperimen, rute manajemen, ping 4/4 per arah, dan qdisc awal yang sesuai. Unit pilot belum aktif atau terdaftar saat preflight. `sudo -n -l` di Debian menjawab `sudo: a password is required`. Gunakan autentikasi lokal konsol untuk eksekusi. [Preflight Debian](../results/stage09b/20261127-pilot-delay50-0635/debian/preflight.txt) · [Preflight Ubuntu](../results/stage09b/20261127-pilot-delay50-0635/ubuntu/preflight.txt)

Run privat `20261127-pilot-delay50-0635` memakai listener Ubuntu port 5061 dan PSK khusus run. Skrip pada guest lulus verifikasi SHA-256, `bash -n`, `systemd-analyze verify` untuk properti unit, serta snapshot dan ping mode `before`. Pada jalur konsol, skrip membatasi eksekusi ke TTY lokal Debian, memeriksa rute ke sumber SSH Windows yang diamati (10.10.20.1), menunggu receipt pertama, mencatat sampel qdisc/rute dan mengirim satu pesan baru setelah rollback berhasil. Perintah diketik sebagai `research` ketika listener siap. [Bukti kesiapan](../results/stage09b/20261127-pilot-delay50-0635/debian/readiness.txt) · [Orkestrasi konsol](../experiments/stage09b_console.sh)

```bash
R="$HOME/hpqc_demo/private-data/stage09b/20261127-pilot-delay50-0635"
bash "$R/console-reviewed.sh" "$R"
```

Jendela `20261127-pilot-delay50-0635` ditutup sekitar 06.41 WIB tanpa langkah konsol. Penanda kesiapan ditarik dan listener berhenti dengan nol baris inbox. Debian saat penutupan tetap menampilkan `fq_codel 0:` dengan opsi awal dan unit pilot `LoadState=not-found`, `ActiveState=inactive`. **BLOCKED** pada autentikasi lokal sudo. Impairment, rollback aktual dan receipt pascarollback **NOT RUN**. Jendela lanjutan memerlukan path baru dan sinyal kesiapan listener sebelum operator menjalankan perintah konsol. [Bukti penutupan](../results/stage09b/20261127-pilot-delay50-0635/closing.txt)

Target tunggal adalah egress Debian enp0s8 menuju Ubuntu pada jaringan internal khusus. Netem menunda semua trafik keluar interface itu, termasuk ACK TCP, selama sekitar 12 detik. Suite aplikasi ML-KEM-768. Pilot memerlukan PASS bagian D–G, sesi manajemen kedua yang berfungsi, konsol VirtualBox Debian yang telah dicoba untuk login dan sudo, kernel dengan netem, systemd aktif sebagai PID 1, serta jendela eksperimen eksklusif. Cocokkan hash skrip di host dan guest setelah tersedia. Konfirmasi izin pengguna untuk satu pilot sebelum menjalankan `apply`.

Blok generik lama di panduan resilience memakai trap EXIT di shell yang memasang qdisc. Skrip pilot baru mengirim satu unit sementara ke systemd. PID 1 menerima batas waktu, perintah pemasangan, dan perintah pembersihan dalam satu permintaan. Unit tetap dikelola systemd saat terminal SSH hilang. [Semua perintah dan guard pilot](../experiments/stage09b_pilot.sh)

```bash
# Debian, melalui SSH, direktori R yang baru untuk pilot
test "$(ps -p 1 -o comm=)" = systemd
command -v systemd-run systemctl journalctl
systemd-run --version
sha256sum experiments/stage09b_pilot.sh
bash experiments/stage09b_pilot.sh before "$R/pilot"
```

Periksa baseline tersimpan dan pastikan manajemen SSH masih dapat membuka sesi baru. Skrip menghentikan operasi bila default kernel, root fq_codel beserta parameternya, class/filter, MAC, IP atau rute berbeda dari prasyarat. Ubuntu mempertahankan qdisc aktualnya sendiri. Jika Debian menampilkan class aktif atau parameter lain, simpan output dan tinjau ulang baseline sebelum izin baru.

```bash
# Ubuntu: server dari bagian G, idle-timeout 15, inbox baru.
# Debian, terminal client: aliran melintasi waktu sebelum, selama dan sesudah impairment.
"$PY" -Bu -m protocol.resilience_cli client "${A[@]}" "${C[@]}" --count 45 --interval 1 --heartbeat 0.3 | tee "$R/pilot-client.jsonl"
# Debian, SSH kedua: ekspor R yang sama. Tunggu receipt pertama dan client masih aktif.
# HANYA SETELAH IZIN EKSPLISIT
set -o pipefail
bash experiments/stage09b_pilot.sh apply "$R/pilot" 2>&1 | tee "$R/unit.txt"
# Jalankan juga jika apply gagal atau terminal harus dibuka kembali.
bash experiments/stage09b_pilot.sh after "$R/pilot"
journalctl -b -u hpqc-stage09b-delay50.service --since "$(cat "$R/pilot/armed-at")" -o short-monotonic | tee "$R/unit-journal.txt"
```

Saat unit berjalan, amati dari sesi ketiga Debian. Ambil status unit dan sampel counter dengan cap waktu monotonic client. Rekam ping dan rute sebelum serta sesudah di kedua VM. Dari Windows, ulangi kedua command hostname bagian C sebelum, selama dan setelah pilot, atau gunakan login operator terverifikasi melalui port yang sama. Simpan hasil, waktu, dan exit code tiap probe. Jika jurnal dibatasi, operator yang berwenang perlu mengekspor jurnal unit spesifik ini.

```bash
systemctl show hpqc-stage09b-delay50.service -p ActiveState -p RuntimeMaxUSec -p ExecStopPost
"$PY" -B -c 'import time; print(time.monotonic_ns())'
/usr/sbin/tc -s qdisc show dev enp0s8
ss -ti dst 10.10.30.10
```

Operasi privileged yang diminta adalah membuat unit sementara, menambah `tc qdisc add dev enp0s8 root handle 709: netem delay 50ms`, lalu otomatis menghapus handle itu dengan `tc qdisc del dev enp0s8 root handle 709:`. Unit tidur 12 detik, memiliki RuntimeMaxSec 16 detik dan TimeoutStopSec 3 detik. Durasi aktual diambil dari jurnal dan observasi qdisc. Pembersihan memeriksa tipe dan handle. Kernel memasang kembali default setelah penghapusan. Skrip membandingkan hasil aktual dengan snapshot; keberhasilan penghapusan saja belum memenuhi kriteria.

## I. Rollback, risiko dan kriteria berhenti

Risiko mencakup tertundanya seluruh trafik egress eksperimen, timeout atau antrean pesan, hasil delivery sementara ambigu, hilangnya SSH, dan kegagalan kernel memasang kembali konfigurasi awal. Bila jalur manajemen bergeser, sesi terputus, tidak ada trafik uji di jendela aktif, atau hasil berbeda, hentikan pilot. Dari konsol Debian, perintah pemulihan berikut hanya berlaku untuk unit dan handle percobaan yang kepemilikannya sudah dipastikan.

```bash
sudo systemctl stop hpqc-stage09b-delay50.service
/usr/sbin/tc qdisc show dev enp0s8
# Hanya bila output masih menunjukkan root netem 709: milik pilot ini.
sudo /usr/sbin/tc qdisc del dev enp0s8 root handle 709:
/usr/sbin/tc -d qdisc show dev enp0s8
```

Dari login SSH baru, jalankan `after` sekali. Jika percobaan pertama gagal, pertahankan direktori after yang sudah terbentuk, ambil snapshot pemulihan tambahan di direktori baru dan pertahankan status FAIL untuk run tersebut. `diff` harus menunjukkan qdisc identik sampai opsi, tidak ada netem, default/class/filter sama, qdisc manajemen dan rute tetap, serta identitas NIC cocok. Periksa hasil ping terikat enp0s8 dua arah dan login SSH baru ke kedua guest. Setelah rollback, kirim satu pesan baru dengan CLI Stage 09 yang sama, `--count 1`, simpan log baru dan cocokkan receipt serta baris baru di inbox. Jika rollback berbeda, beri **FAIL** dan hentikan seluruh eksperimen berikutnya. Pemulihan konsol yang diperlukan di luar prosedur ini membutuhkan diagnosis terhadap baseline yang disimpan.

## J. Bukti, metrik dan sisa matriks

Simpan status proses, log klien/server, versi source/kernel, snapshot qdisc/rute, sampel statistik TCP, hasil SSH dan manifest inbox per run. Catat waktu aktif/nonaktif qdisc di Debian pada sumbu monotonic yang sama dengan client. Gunakan interval ketidakpastian antarobservasi untuk receipt di tepi jendela. Hitung delivery sebagai ID unik dengan receipt valid dibagi ID yang direncanakan, lalu cocokkan dengan inbox. Hitung timeout per attempt dari event interrupted/error, jumlah retry dari nomor attempt, dan duplicate dari server. Laporkan waktu sejak deteksi sampai TCP tersambung, secure_ready dan receipt pertama yang pulih menggunakan since_detection_ns dari client, serta jumlah receipt sebelum/selama/sesudah gangguan. Beri N/A untuk waktu recovery bila koneksi tetap hidup. Laporkan exit code, sampel hilang atau receipt ambigu secara eksplisit.

Matriks berikut adalah rencana setelah pilot dan rollback diterima. Semua gangguan satu arah di Debian enp0s8, satu run dan izin terpisah per profil, baseline baru, dan verifikasi pemulihan bagian I. Untuk semua baris, usulan beban adalah 45 pesan, interval 1 detik, heartbeat 0,3 detik, timeout 3 detik, idle server 15 detik, maksimal 8 retry per operasi, backoff 0,2 hingga 2 detik. Ukur durasi aktual, sisakan pesan setelah pemulihan, dan catat timeout bila batas habis.

| Profil | Jendela target | Status eksperimen guest |
|---|---:|---|
| Normal | 45 pesan tanpa perubahan qdisc | PASS |
| Loss 5%, 10%, 20% | 12 detik masing-masing | PASS |
| Delay 50 ms (pilot) | Unit 12,287 detik | PASS |
| Delay 100 ms | Unit 12,124 detik | PASS |
| Delay 200 ms | 12 detik | PASS |
| Delay 50 ms dengan jitter 10 ms, lalu 20 ms | 12 detik masing-masing | PASS |
| Outage sementara, loss 100% egress eksperimen | 5 detik | PASS |

Skrip pilot dikunci ke delay 50 ms. Setelah hasil pilot ditinjau, tetapkan perintah dan watchdog khusus profil berikutnya sebelum meminta izin.

## K. Keputusan untuk penelitian

### Baseline normal padanan

Run `normal-20261127-070322` memakai Debian sebagai client, Ubuntu pada 10.10.30.10:5061 sebagai server, ML-KEM-768 dan 45 payload UTF-8 sintetis `HPQC-09B` sepanjang 8 byte. Kedua VM memakai revisi 3df1e695a88fb54be7bcd3431cdcbd4bb9b9b969 dan versi dependency sama dengan pilot. Preflight sekitar 07.03 WIB memverifikasi SSH BatchMode, rute data enp0s8, rute manajemen enp0s3, ping 4/4 tiap arah, dan qdisc tanpa netem. RTT ICMP rata-rata dari empat ping sebelum beban adalah 3,016 ms Debian → Ubuntu dan 13,197 ms sebaliknya. Snapshot qdisc sebelum dan sesudah beban identik. [Preflight Debian](../results/stage09b/normal-20261127-070322/debian/preflight.txt) · [Preflight Ubuntu](../results/stage09b/normal-20261127-070322/ubuntu/preflight.txt)

```bash
# Ubuntu, dari root proyek, R adalah direktori privat run pada VM ini.
timeout 150 .venv/bin/python -Bu -m protocol.resilience_cli server --host 10.10.30.10 --port 5061 --suite ml-kem-768 --timeout 3 --idle-timeout 15 --psk-file "$R/resilience.psk" --inbox "$R/normal.sqlite"
# Debian, dari root proyek, R adalah direktori privat run pada VM ini.
timeout 100 .venv/bin/python -Bu -m protocol.resilience_cli client --host 10.10.30.10 --port 5061 --suite ml-kem-768 --timeout 3 --psk-file "$R/resilience.psk" --text HPQC-09B --retries 8 --backoff 0.2 --backoff-cap 2 --count 45 --interval 1 --heartbeat 0.3
```

| Cakupan beban utama | Normal | Pilot delay 50 ms |
|---|---:|---:|
| Receipt terautentikasi | 45/45 (100%) | 45/45 (100%) |
| Heartbeat dengan PONG | 88/88 | 92/92 |
| Sesi aman / reconnect / retry | 1 / 0 / 0 | 1 / 0 / 0 |
| Commit unik / baris SQLite untuk beban utama | 45 / 45 | 45 / 45 |
| Event duplicate | 0 | 0 |
| Waktu recovery | N/A | N/A |
| Durasi dari attempt pertama sampai receipt terakhir | 46,875 s | 48,841 s |
| Latensi delivery median / p95 | 58,732 / 85,627 ms | 58,892 / 231,448 ms |
| Median RTT TCP dari sampel tanpa netem | 21,715 ms (77 sampel) | 21,897 ms (59 sampel) |

Durasi event memakai jam monotonic Debian. Latensi aplikasi adalah selisih `attempt_started` pertama dan `delivered` untuk ID pesan yang sama, sehingga pesan pertama mencakup handshake. p95 memakai nearest rank. Jumlah PONG dapat berbeda walau interval dikonfigurasi sama karena heartbeat mengikuti jadwal jeda dan durasi operasi. RTT TCP berasal dari estimasi `ss -ti` pada koneksi aktif. Median RTT pada 19 sampel qdisc aktif pilot adalah 68,926 ms. Cakupan tersebut dilaporkan sendiri karena baseline tidak mempunyai interval impairment. Dalam pilot terdapat 9 receipt di antara sampel aktif pertama dan terakhir, 2 di sela sampel tepi, 3 sebelum dan 31 sesudahnya. Satu probe pascarollback membuat total pilot 46 baris dan berada di luar tabel. Pembandingan latensi beban utama pilot mencampur fase sebelum, selama dan sesudah delay. Satu run per kondisi memberi observasi deskriptif. Deduplikasi tidak terpicu pada kedua run ini. [Event client normal](../results/stage09b/normal-20261127-070322/debian/client.jsonl) · [Sampel TCP normal](../results/stage09b/normal-20261127-070322/debian/samples.txt) · [Inbox normal](../results/stage09b/normal-20261127-070322/ubuntu/inbox.tsv) · [Ringkasan perbandingan](../results/stage09b/normal-20261127-070322/comparison.json)

### Delay 100 ms — hasil satu run

Run `delay100-20261127-072914` **PASS** dengan ML-KEM-768 dan parameter identik dengan pilot 50 ms, termasuk beban utama 45 payload sintetis 8 byte. Operator menjalankan wrapper dari konsol Debian sebagai research. Verifikasi hash dan unit lulus. SSH BatchMode, rute lewat enp0s8 untuk data dan enp0s3 untuk manajemen, serta ping 4/4 tiap arah lulus sebelum run. Log sumber sebelumnya dipertahankan. [Preflight Debian](../results/stage09b/delay100-20261127-072914/debian/preflight.txt) · [Preflight Ubuntu](../results/stage09b/delay100-20261127-072914/ubuntu/preflight.txt)

Pada 07.32.52 WIB, root `netem 709:` dengan delay 100 ms teramati aktif di enp0s8 Debian. Login SSH baru pada kedua VM lulus ketika impairment aktif. `systemd-run --wait` melaporkan runtime unit 12,124 detik dan exit 0. Selisih antara sampel aktif pertama dan terakhir adalah 11,736 detik. Sampel nonaktif yang membatasi keduanya berjarak 12,870 detik. Rentang ini membatasi interval aktif berdasarkan resolusi sampling. Sampel aktif terakhir mencatat 95 paket dan 10.868 byte, nol drop, overlimit, dan requeue. Counter meliputi egress interface selama pengamatan. [Unit aktif](../results/stage09b/delay100-20261127-072914/debian/active-unit.txt) · [Sampel TCP dan qdisc](../results/stage09b/delay100-20261127-072914/debian/samples.txt)

| Cakupan beban utama | Normal | Delay 50 ms | Delay 100 ms |
|---|---:|---:|---:|
| Receipt terautentikasi | 45/45 | 45/45 | 45/45 |
| Heartbeat dengan PONG | 88/88 | 92/92 | 88/88 |
| Sesi aman / reconnect / retry | 1 / 0 / 0 | 1 / 0 / 0 | 1 / 0 / 0 |
| Commit unik / baris SQLite beban utama | 45 / 45 | 45 / 45 | 45 / 45 |
| Duplikat teramati | 0 | 0 | 0 |
| Waktu recovery | N/A | N/A | N/A |
| Durasi beban | 46,875 s | 48,841 s | 51,126 s |
| Median / p95 latensi delivery | 58,732 / 85,627 ms | 58,892 / 231,448 ms | 58,142 / 502,261 ms |
| Median RTT TCP tanpa netem | 21,715 ms (77 sampel) | 21,897 ms (59 sampel) | 21,954 ms (62 sampel) |

| Di antara sampel qdisc aktif pertama dan terakhir | Delay 50 ms | Delay 100 ms |
|---|---:|---:|
| Receipt / PONG | 9 / 18 | 7 / 15 |
| Latensi delivery median / p95 untuk pesan yang dimulai dan selesai di interval itu | 221,843 / 426,100 ms (9 pesan) | 499,093 / 504,170 ms (7 pesan) |
| Median / p95 RTT TCP | 68,926 / 78,674 ms (19 sampel) | 113,991 / 125,296 ms (21 sampel) |

Pada 100 ms, tiga receipt tercatat sebelum impairment, 33 sesudahnya dan dua di sela sampel tepi. Hitungan receipt aktif memakai waktu penerimaan. Denominator 45 berlaku untuk seluruh beban utama. Latensi delivery adalah waktu dari `attempt_started` pertama sampai `delivered` pada jam monotonic client. Dengan 7 atau 9 pesan, p95 nearest-rank adalah nilai maksimum kelompok. RTT TCP berasal dari estimasi `ss -ti`. Hasil menunjukkan ekor latensi lebih tinggi pada beban utama 100 ms di run ini. Satu run per kondisi membatasi kesimpulan pada deskripsi observasi. [Perbandingan hasil](../results/stage09b/delay100-20261127-072914/summary.json)

**Rollback PASS.** Script mencatat `apply_exit=0` dan `after_exit=0`. Unit kembali inactive/not-found dan netem hilang. Snapshot alamat, rute dan qdisc sebelum/sesudah identik di kedua VM. Debian kembali ke fq_codel dengan opsi awal. Setelah rollback, SSH BatchMode baru dan ping 4/4 per arah berhasil. Pesan probe ID `4781b3fc268b808aca125ed829007203` mendapat receipt pada sesi baru dan memiliki baris commit. Total 46 receipt, 46 commit dan 46 baris SQLite memiliki ID yang sama. Listener ditutup. Jurnal sistem unit tidak tersedia bagi akun research. Bukti runtime memakai output unit dan sampel monotonic. Timeout paksa dan putus SSH sengaja tetap NOT RUN. [Output unit](../results/stage09b/delay100-20261127-072914/debian/unit.txt) · [Snapshot akhir Debian](../results/stage09b/delay100-20261127-072914/debian/after.txt) · [Snapshot akhir Ubuntu](../results/stage09b/delay100-20261127-072914/ubuntu/after.txt) · [Probe pascarollback](../results/stage09b/delay100-20261127-072914/debian/post-client.jsonl) · [Inbox](../results/stage09b/delay100-20261127-072914/ubuntu/inbox.tsv)

### Persiapan dan jendela sebelumnya

Operator menyetujui satu run. Pada jendela `delay100-20261127-071241`, preflight kedua guest, pemeriksaan SHA-256 skrip sumber 50 ms, diff turunan 100 ms, `bash -n`, `systemd-analyze verify`, dan mode `before` lulus. SSH dan gateway melalui enp0s3, rute data melalui enp0s8, dan ping 4/4 di tiap arah. Qdisc awal Debian fq_codel dan Ubuntu pfifo_fast. Listener siap pada 07.14.41 WIB dan perintah konsol disampaikan dengan batas mulai 07.20.00 WIB. Pada 07.21.01 WIB, belum ada eksekusi konsol. Marker kesiapan ditarik, Debian masih menggunakan fq_codel dengan opsi awal dan unit 100 ms inactive/not-found. Listener Ubuntu ditutup dengan nol baris inbox. **Impairment, rollback aktual, dan pengukuran HPQC 100 ms NOT RUN.** [Preflight Debian](../results/stage09b/delay100-20261127-071241/debian/preflight.txt) · [Preflight Ubuntu](../results/stage09b/delay100-20261127-071241/ubuntu/preflight.txt) · [Penutupan](../results/stage09b/delay100-20261127-071241/closing.txt)

Untuk jendela baru, gunakan direktori bukti baru. Nama unit 100 ms membedakan observasi dari pilot 50 ms. Pertahankan handle 709:, batas runtime 16 detik, jeda 12 detik, `ExecStopPost`, dan verifikasi snapshot. Periksa perubahan isi serta hash sebelum menyalurkan skrip.

```bash
# R adalah direktori baru, dari root checkout yang memuat kedua skrip.
set -o noclobber
sed -e 's/hpqc-stage09b-delay50\.service/hpqc-stage09b-delay100.service/g' \
    -e 's/netem delay 50ms/netem delay 100ms/' experiments/stage09b_pilot.sh > "$R/pilot-reviewed.sh"
sed 's/hpqc-stage09b-delay50\.service/hpqc-stage09b-delay100.service/g' \
    experiments/stage09b_console.sh > "$R/console-reviewed.sh"
(cd "$R" && bash -n pilot-reviewed.sh && bash -n console-reviewed.sh && \
  sha256sum pilot-reviewed.sh console-reviewed.sh > pilot.sha256)
```

Jalankan preflight D dan mode `before` dengan sesi BatchMode dan konsol berfungsi. Verifikasi `systemd-analyze verify` untuk unit dan pastikan qdisc awal Debian tetap fq_codel. Mulai listener Ubuntu di 10.10.30.10:5061 dan jalankan wrapper dari konsol Debian sesudah sinyal kesiapan. Setelah receipt awal, unit hanya menambah `tc qdisc add dev enp0s8 root handle 709: netem delay 100ms`. Pembersihan hanya menghapus handle itu. Selama run, ambil statistik qdisc/TCP dan cek login baru ke kedua VM. Setelah run cocokkan qdisc dan rute dengan snapshot, periksa ping dan SSH dua arah, dan verifikasi receipt serta commit untuk satu pesan baru. Jika ada ketidaksesuaian, tandai FAIL dan hentikan. Langkah darurat bagian I memakai nama unit `hpqc-stage09b-delay100.service` untuk run ini.

### Uji jalur rollback fallback

Roadmap mewajibkan bukti rollback dan jalur pengelolaan VM. Pilot 50 ms sudah menguji keduanya pada terminasi normal. Roadmap tidak menyebut simulasi timeout paksa atau putus SSH sebagai kriteria tersendiri. Keduanya diperlukan bila laporan akan menyimpulkan rollback tetap bekerja pada kegagalan tersebut. Rencanakan terpisah dari run pengukuran 100 ms. Pertama, gunakan unit systemd tanpa tc yang melampaui RuntimeMaxSec dan minta `ExecStopPost` menulis marker ke direktori privat. Catat hasil timeout dan marker dari sesi login baru setelah terminal peluncur ditutup. Jika diperlukan bukti dengan qdisc nyata, ajukan izin tersendiri. Uji timeout dan pelepasan sesi peluncur dalam run terpisah dengan konsol serta sesi manajemen cadangan. Verifikasi handle hilang, snapshot awal kembali, rute dan SSH berfungsi, serta receipt dan commit pascapemulihan cocok. Putus sesi peluncur saja melalui penutupan terminal, tanpa mengubah layanan SSH, firewall, interface atau rute.

### Rencana eksekusi matriks tersisa

Baseline padanan, delay 50 ms, delay 100 ms, dan kedua rollback telah **PASS** sebelum batch ini. Urutan berikut adalah rencana yang digunakan untuk tujuh profil. Tiap profil dijalankan satu kali, dengan qdisc aktif berurutan dan bukti yang terpisah. Target hanya egress Debian enp0s8. Ubuntu tetap bertindak sebagai server pada 10.10.30.10:5061.

| Urutan | Profil | Argumen setelah `netem` | Target aktif | Risiko yang diamati |
|---:|---|---|---:|---|
| 1 | delay200 | `delay 200ms` | 12 s | RTT dan latensi delivery meningkat; operasi dapat melewati deadline bila antrean menumpuk. |
| 2 | jitter10 | `delay 50ms 10ms` | 12 s | Variasi RTT dan potensi perubahan urutan paket. |
| 3 | jitter20 | `delay 50ms 20ms` | 12 s | Variasi lebih lebar dan potensi retransmisi akibat perubahan urutan. |
| 4 | loss05 | `loss 5%` | 12 s | Retransmisi; beberapa sampel pendek dapat menampilkan sedikit drop. |
| 5 | loss10 | `loss 10%` | 12 s | Retransmisi lebih sering dapat memperpanjang receipt. |
| 6 | loss20 | `loss 20%` | 12 s | Deadline dan retry lebih mungkin terpicu; delivery bisa parsial. |
| 7 | outage | `loss 100%` | 5 s | Semua paket egress data dibuang, termasuk ACK TCP. Sesi dapat putus, retry, atau selesai dengan delivery parsial. |

Gunakan jitter tanpa parameter korelasi atau distribusi tambahan, dan gunakan random packet loss bawaan netem. Persentase drop teramati bergantung pada sampel paket. Simpan parameter aktual dan counter. Qdisc berlaku untuk seluruh trafik egress interface eksperimen. [Manual netem iproute2](https://github.com/iproute2/iproute2/blob/main/man/man8/tc-netem.8)

Pertahankan ML-KEM-768, 45 payload `HPQC-09B` sepanjang 8 byte, interval kirim 1 detik, heartbeat 0,3 detik, deadline operasi 3 detik, idle server 15 detik, maksimal 8 retry per operasi, backoff awal 0,2 detik dan cap 2 detik. Outage menggunakan jendela 5 detik yang sudah ditetapkan pada panduan resilience. Dengan deadline 3 detik, operasi yang kehilangan respons dapat terputus sebelum qdisc dihapus. Satu percobaan awal dan 8 retry memberi total jeda backoff maksimum 11 detik, di luar waktu connect, handshake dan I/O. Client dibatasi 100 detik untuk seluruh beban. Suatu operasi yang melewati 100 detik dilaporkan terpotong oleh batas proses. Reconnect bergantung pada posisi outage terhadap operasi dan perilaku TCP. Bandingkan 5 detik terhadap profil 12 detik dengan menyebut selisih durasi dan memisahkan receipt aktif dari total beban. [Panduan resilience](resilience.md)

#### Command dan operator

Tampilkan rencana dari checkout host Windows menggunakan PowerShell. Mode ini telah dijalankan secara offline.

```powershell
py -3 -B experiments/stage09b_matrix.py
```

**Hanya sesudah persetujuan eksplisit**, jalankan controller dari PowerShell pengguna yang memiliki alias BatchMode `debian-pqc` dan `ubuntu-pqc`.

```powershell
py -3 -B experiments/stage09b_matrix.py --execute delay200 jitter10 jitter20 loss05 loss10 loss20 outage
```

Controller menampilkan nilai `R` absolut baru dan command untuk dijalankan satu kali dari konsol teks Debian sebagai `research`.

```bash
# Salin nilai R absolut yang dicetak controller.
bash "$R/console.sh" "$R"
```

Konsol memakai `sudo -v` satu kali untuk autentikasi lokal dan `sudo -n -v` pada setiap profil. Konsol harus tetap terbuka. Profil berjalan tanpa input tambahan selama tiket sudo valid. Jika tiket kedaluwarsa, batch berhenti. Setelah penyebab ditinjau, gunakan batch baru untuk profil yang masih menunggu persetujuan eksekusi. Jangan mengulang profil dengan bukti valid. Controller menulis `plan.json`, `checkpoint.txt` dan direktori unik per profil. Manifest memuat ID batch unik ditambah nama profil sebagai run ID. Controller membatasi waktu mulai setiap profil, memberi sinyal abort ketika gagal, dan mengikat listener hanya ke alamat eksperimen. [Controller](../experiments/stage09b_matrix.py) · [Runner konsol](../experiments/stage09b_matrix_console.sh)

#### Guard, rollback, dan batas berhenti

Untuk tiap profil, controller membuka BatchMode baru ke kedua VM, memverifikasi user, revisi source, IP/rute, qdisc awal tanpa netem, ping 4/4 dan port listener. Debian mengulangi guard pilot sebelum mutasi, termasuk opsi fq_codel, MAC, default kernel, class/filter kosong, dan rute data/manajemen. Controller mencatat kecocokan hash, source shell, `bash -n`, ketersediaan modul, serta `systemd-analyze verify` untuk properti unit. Konsol menunggu receipt awal sebelum apply.

Unit yang diturunkan dari pilot memakai command `/usr/sbin/tc qdisc add dev enp0s8 root handle 709: netem <argumen-tabel>`, tidur sesuai durasi, dan memasang `ExecStopPost` melalui PID 1. `RuntimeMaxSec=16s` dan `TimeoutStopSec=3s`. Cleanup menghapus hanya root `netem 709:` pada enp0s8, memeriksa keadaan qdisc, lalu runner membandingkan snapshot dengan baseline. Controller mengulang verifikasi snapshot dan ping dengan koneksi SSH baru. Koneksi manajemen diamati saat qdisc aktif, termasuk sampel Debian tambahan untuk menilai apakah probe Ubuntu terapit oleh dua pengamatan aktif. Setelah rollback, satu probe HPQC harus menghasilkan receipt dan baris commit. [Dokumentasi unit systemd](https://www.freedesktop.org/software/systemd/man/256/systemd.service.html)

Hentikan batch saat preflight berbeda, akses sudo hilang, qdisc atau unit tidak sesuai, netem belum dilepas, opsi qdisc atau rute berubah, listener gagal, ping atau SSH gagal, receipt probe pascarollback gagal, atau bukti instrumentasi tidak cukup. Saat controller berhenti, unit yang sudah aktif tetap dibatasi PID 1. Tutup antrian profil, pertahankan konsol, lalu ikuti langkah verifikasi dan pemulihan bagian I dengan nama unit `hpqc-stage09b-matrix.service`. Delivery parsial atau retry habis adalah hasil yang dapat dilaporkan jika impairment, rollback, probe pascarollback dan bukti tetap valid.

#### Bukti dan acceptance

Untuk tiap profil, log client/server, stderr, exit code, qdisc/TCP dari `tc -s` dan `ss -nti`, SSH, snapshot, durasi unit, dan daftar ID SQLite disalin tanpa PSK atau database mentah. Ringkasan memisahkan 45 pesan terencana, pesan mulai, receipt, dan commit yang belum memiliki receipt. Heartbeat memakai ID operasi unik. Laporkan receipt dan PONG di antara sampel aktif pertama dan terakhir serta receipt di tepi yang tidak pasti. Latensi aktif memakai operasi dengan awal dan akhir dalam jendela aktif. p95 menggunakan nearest rank. Jeda ke TCP baru, sesi aman dan delivery memakai jam monotonic client dari deteksi interupsi. Daftar recovery kosong berarti N/A. Nilai null sesudah interupsi menandakan peristiwa belum teramati. Satu run per kondisi memberi hasil deskriptif. Semua ringkasan matriks menunggu data aktual. [Validasi offline runner](../results/stage09b/matrix-preparation-20261127/validation.txt)

#### Evaluasi jalur timeout dan putus sesi tanpa tc

Pisahkan dari matriks dan minta izin sendiri. Untuk cabang timeout, dari konsol Debian jalankan unit uji tanpa tc, dengan `RuntimeMaxSec=3s`, beban `/bin/sleep 15` dan `ExecStopPost` berupa marker jurnal. Verifikasi hasil timeout dan marker lewat jurnal pada sesi baru. Untuk putus sesi kontrol, gunakan unit uji tanpa tc yang sudah terdaftar pada manager, lalu tutup hanya klien SSH peluncur setelah status aktif. Dari konsol dan login baru, verifikasi jadwal stop dan marker. Jika menggunakan `systemd-run --user` dari SSH untuk simulasi tanpa sudo, dokumentasikan bahwa manager user memberi bukti pendahuluan. Bukti unit sistem yang sebanding memerlukan unit PID 1. Uji ini tidak memerlukan perubahan qdisc, routing, atau konfigurasi SSH. Status **NOT RUN**.

### Hasil batch matriks 27 November 2026

Batch awal `matrix-20261127T005148Z-a077cd4a` berhenti sebelum apply karena proses anak membuka `/dev/tty` dan gagal mengenali path konsol teks aktual. Saat penutupan, qdisc awal dan rute cocok, unit tidak aktif dan inbox kosong. Runner diperbaiki untuk meneruskan path konsol yang sudah lolos guard, lalu batch `matrix-20261127T005747Z-f44d621b` menjalankan tujuh profil sekali sesuai urutan yang disetujui. [Log blocker awal](../results/stage09b/matrix-20261127T005148Z-a077cd4a/delay200/debian/runner.txt) · [Checkpoint batch selesai](../results/stage09b/matrix-20261127T005747Z-f44d621b/checkpoint.txt)

| Beban utama | Status | Receipt / rencana | PONG / operasi heartbeat | Latensi median / p95 (ms) | Durasi (s) | Sesi / reconnect / retry | Commit / SQLite / duplikat termasuk probe |
|---|---|---:|---:|---:|---:|---:|---:|
| [Delay 200 ms](../results/stage09b/matrix-20261127T005747Z-f44d621b/delay200/summary.json) | PASS | 45/45 | 80/80 | 60,889 / 661,200 | 51,332 | 1 / 0 / 0 | 46 / 46 / 0 |
| [Delay 50 ms + jitter 10 ms](../results/stage09b/matrix-20261127T005747Z-f44d621b/jitter10/summary.json) | PASS | 45/45 | 89/89 | 61,578 / 248,844 | 48,802 | 1 / 0 / 0 | 46 / 46 / 0 |
| [Delay 50 ms + jitter 20 ms](../results/stage09b/matrix-20261127T005747Z-f44d621b/jitter20/summary.json) | PASS | 45/45 | 88/88 | 61,055 / 248,200 | 48,711 | 1 / 0 / 0 | 46 / 46 / 0 |
| [Loss 5%](../results/stage09b/matrix-20261127T005747Z-f44d621b/loss05/summary.json) | PASS | 45/45 | 89/89 | 59,271 / 129,751 | 47,376 | 1 / 0 / 0 | 46 / 46 / 0 |
| [Loss 10%](../results/stage09b/matrix-20261127T005747Z-f44d621b/loss10/summary.json) | PASS | 45/45 | 90/90 | 59,587 / 255,795 | 47,776 | 1 / 0 / 0 | 46 / 46 / 0 |
| [Loss 20%](../results/stage09b/matrix-20261127T005747Z-f44d621b/loss20/summary.json) | PASS | 45/45 | 88/88 | 60,965 / 354,262 | 49,372 | 1 / 0 / 0 | 46 / 46 / 0 |
| [Outage 100%](../results/stage09b/matrix-20261127T005747Z-f44d621b/outage/summary.json) | PASS | 45/45 | 88/88 | 58,804 / 83,704 | 54,124 | 2 / 1 / 1 | 46 / 46 / 0 |

| Interval impairment | Runtime unit (s) | Batas durasi aktif teramati (s) | Receipt / PONG / receipt tepi | Latensi aktif median / p95 (ms) | RTT TCP aktif median / p95 (ms) | Paket terkirim / byte / drop |
|---|---:|---:|---:|---:|---:|---:|
| Delay 200 ms | 12,154 | 11,480–12,636 | 7 / 7 / 1 | 661,020 / 693,396 | 204,067 / 219,906 (21) | 63 / 7308 / 0 |
| Delay 50 ms + jitter 10 ms | 12,242 | 11,504–12,724 | 9 / 18 / 2 | 225,538 / 261,327 | 69,144 / 71,720 (20) | 122 / 14013 / 0 |
| Delay 50 ms + jitter 20 ms | 12,210 | 11,746–13,049 | 10 / 19 / 0 | 234,471 / 323,061 | 73,552 / 76,905 (20) | 126 / 14445 / 0 |
| Loss 5% | 12,211 | 11,401–12,664 | 10 / 22 / 1 | 58,443 / 283,779 | 21,500 / 22,786 (20) | 139 / 15858 / 4 |
| Loss 10% | 12,185 | 11,636–13,004 | 11 / 21 / 1 | 60,196 / 282,067 | 21,423 / 23,911 (20) | 141 / 16158 / 5 |
| Loss 20% | 12,229 | 11,228–12,487 | 9 / 16 / 1 | 284,483 / 584,162 | 21,984 / 25,081 (19) | 103 / 12296 / 25 |
| Outage 100% | 5,211 | 4,269–5,517 | 0 / 0 / 0 | N/A / N/A | 21,572 / 21,572 (8) | 0 / 0 / 8 |

Total beban utama batch 315/315 receipt dan tujuh probe pascarollback, masing-masing cocok dengan commit dan ID unik SQLite. Counter di tabel adalah snapshot qdisc aktif terakhir, mencakup egress interface, tanpa overlimit atau requeue pada tujuh profil. Interval aktif dibatasi oleh sampel monotonic Debian. Receipt di tepi tidak dimasukkan ke angka aktif. Latensi delivery aktif memakai operasi yang dimulai dan selesai di interval yang sama. RTT `ss -nti` adalah estimasi TCP yang disampel. RTT outage tetap tercatat saat tidak ada paket keluar; nilai itu dapat membawa estimator dari sebelum outage. Pada sampel aktif kecil, p95 nearest-rank dapat jatuh pada maksimum.

Outage memicu satu `TimeoutError` pada heartbeat, satu retry dan satu reconnect. Dari deteksi, TCP baru tersambung pada 2.236,487 ms, sesi aman baru siap pada 4.424,204 ms, PONG pulih pada 4.481,451 ms, dan receipt pesan pulih pada 4.579,907 ms. Nol receipt selama impairment dan seluruh 45 receipt akhirnya diterima. Waktu recovery enam profil lain N/A. Tidak ada duplikat pada batch ini. Bukti deduplikasi lintas sesi tetap berasal dari run antar-VM sebelumnya. [Log recovery outage](../results/stage09b/matrix-20261127T005747Z-f44d621b/outage/debian/client.jsonl) · [Deduplikasi sebelumnya](../results/stage09b/20261127-0621/ubuntu/normal-server.jsonl)

Terhadap baseline normal, p95 beban utama 85,627 ms. Observasi delay 50/100/200 ms menghasilkan p95 231,448 / 502,261 / 661,200 ms. Pada loss 5/10/20% p95 terukur 129,751 / 255,795 / 354,262 ms. Pada outage, p95 pesan 83,704 ms mengukur attempt pesan ke receipt; jeda recovery heartbeat dilaporkan sendiri dan terlihat pada durasi beban 54,124 detik. Outage berlangsung sekitar 5 detik dan enam profil batch lainnya sekitar 12 detik. Satu run per kondisi, ukuran sampel kecil dan loss/jitter acak membatasi kesimpulan pada observasi deskriptif. Alamat eksperimen bersifat sementara dan perlu dicek ulang setelah reboot.

### Audit acceptance Stage 09

| Kriteria ROADMAP.md | Status | Bukti |
|---|---|---|
| Timeout, heartbeat, retry terbatas, backoff, fresh handshake | PASS | Outage menangkap deadline heartbeat, backoff 0,2 detik dan sesi baru pada percobaan kedua. Suite regresi sebelumnya menguji batas retry, timeout dan proof. |
| ACK dan deduplikasi lintas sesi | PASS | Regresi dan run antar-VM memverifikasi ACK/receipt. Run normal dan replay ID mencatat receipt tambahan dengan satu baris unik dan event duplicate. |
| Recovery TCP/sesi aman dan delivery saat/sesudah gangguan | PASS | Log outage memuat anchor interupsi dan waktu hingga TCP, sesi baru, PONG serta receipt. Qdisc aktif dan client sama-sama disampel pada sumbu monotonic Debian. |
| Seluruh skenario roadmap | PASS | Baseline, loss 5/10/20%, delay 50/100/200 ms, jitter 10/20 ms, dan outage memiliki bukti aktual. |
| Rollback dan jalur manajemen | PASS | Kesembilan run impairment memiliki snapshot cocok sebelum/sesudah, netem hilang, ping 4/4 dua arah, jalur SSH enp0s3, dan receipt probe yang cocok dengan commit. Audit batch mencocokkan ulang tujuh snapshot dan menemukan probe SSH Ubuntu terapit dua sampel Debian aktif pada setiap profil. Penutupan akhir mengonfirmasi listener berhenti dan unit tidak aktif. |

**Stage 09 PASS.** Tidak ada kriteria wajib Stage 09 yang masih terbuka. Pengujian cabang timeout paksa systemd dan pemutusan klien SSH peluncur tetap **NOT RUN** dan memerlukan persetujuan tersendiri. Bukti rollback saat ini mencakup terminasi normal unit. Stage 10 dan 11 menunggu instruksi. [ROADMAP](../ROADMAP.md) · [Audit penutupan](../results/stage09b/matrix-20261127T005747Z-f44d621b/audit-close.txt)
