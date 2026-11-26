# Inventaris environment baseline

Tanggal pemeriksaan host 26 November 2026 (Asia/Jakarta). Identitas arsip dan hash sumber tercantum di [PROGRESS.md](../PROGRESS.md).

## Windows

| Item | Hasil observasi host |
|---|---|
| OS dan shell | Registry Windows melaporkan CoreSingleLanguage, 26H2, build 26300.9974. PowerShell 5.1.26100.9818. |
| Python | CPython 3.11.9 AMD64 dan 3.15.0 AMD64. Keduanya interpreter dasar (`sys.prefix == sys.base_prefix`). Executable masing-masing berada di `%LOCALAPPDATA%\Python\pythoncore-3.11-64\python.exe` dan `%LOCALAPPDATA%\Python\pythoncore-3.15-64\python.exe`. |
| Dependency aktual | 3.11.9 memiliki psutil 7.2.2. Pada 3.15.0 psutil tidak terdeteksi. Pada keduanya, metadata dan import pqcrypto serta cryptography tidak tersedia. |
| Dependency yang diminta | pqcrypto==1.0.0, cryptography>=44,<50, psutil>=6,<9. Chat dan smoke test mengimpor pqcrypto dan cryptography. psutil disiapkan untuk pengukuran resource. |
| Pemilihan interpreter | WindowsApps muncul pertama pada resolusi perintah python/py. Pemeriksaan memakai path executable langsung. Venv lokal proyek dan variabel VIRTUAL_ENV/CONDA_PREFIX tidak ditemukan pada sesi ini. |
| Git | 2.56.0.windows.2, branch master, tanpa commit dan remote. Index kosong saat pemeriksaan. |
| VirtualBox | Versi executable VBoxManage 7.2.22.175245. XML host mendaftarkan NAT Network PQC-LAB aktif secara konfigurasi, 10.10.20.0/24, serta adapter kedua VM pada jaringan itu. |

## Guest

| Item | Ubuntu-PQC | Debian-PQC |
|---|---|---|
| Peran dan port rencana | Client TCP ke port 5050 | Server TCP pada port 5050 |
| Nama VM dan adapter dari XML host | Ubuntu-PQC, PQC-LAB | Debian-PQC, PQC-LAB |
| Release OS, kernel, arsitektur guest | NOT RUN | NOT RUN. README menyebut Debian 13 sebagai target. |
| IP aktif, interface, versi Python dan path venv | NOT RUN | NOT RUN |
| Versi pqcrypto/cryptography/psutil, import, smoke test | NOT RUN | NOT RUN |
| Pengiriman/penerimaan, shutdown, packet capture | NOT RUN | NOT RUN |

Saat menjalankan [panduan pengujian](testing_guide.md), catat hasil tiap VM secara terpisah, termasuk tanggal, IP lab, path interpreter, versi library, hash file, dan exit status. Status jaringan yang tersimpan di host belum mengukur reachability antar-guest.
