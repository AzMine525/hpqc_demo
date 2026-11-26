# Aturan pengembangan HPQC

Proyek penelitian D4 ini memakai ML-KEM untuk membentuk shared secret dan AES-256-GCM untuk melindungi payload. Pisahkan bukti keamanan kriptografi, kinerja transport, dan pemulihan aplikasi dalam laporan.

## Lingkup dan version control

- Kerjakan hanya stage yang diotorisasi pengguna. Gunakan [ROADMAP.md](ROADMAP.md) untuk kriteria penerimaan dan [PROGRESS.md](PROGRESS.md) untuk hasil aktual. Berhenti setelah stage yang diotorisasi diperiksa.
- Periksa Git status, perubahan pengguna, dan baseline yang dapat dipulihkan sebelum mengedit. Pertahankan file atau pekerjaan pengguna yang berada di luar lingkup. Instalasi paket, commit, push, deployment, dan perubahan konfigurasi sistem atau jaringan memerlukan persetujuan terpisah.
- Pada Stage 00–01, pertahankan keempat file prototipe asli. Pada Stage 02, pertahankan entry point `chat.py`, perilaku kriptografi, dan format wire. Uji interoperabilitas dengan baseline pada kedua kombinasi client/server. Perlakukan versi antara Stage 03 dan 05 sebagai versi pengembangan.

## Implementasi dan keamanan

- Gunakan library kriptografi yang tersedia. Verifikasi versi, signature API, urutan argumen, dan ukuran objek pada interpreter yang digunakan. Penggantian `pqcrypto` memerlukan alasan teknis terverifikasi dan persetujuan pengguna.
- Ikuti spesifikasi stage sebelum mengubah KDF, nonce, AAD, handshake, atau framing. Gunakan keypair ephemeral untuk tiap handshake. Jangan membuat fallback plaintext atau downgrade suite otomatis.
- Simpan private key, PSK, shared secret, dan session key di luar log, source, capture beranotasi, dan Git. Tinjau staged diff sebelum commit. Gunakan data sintetis dalam pengujian.
- Pertahankan kompatibilitas Windows dan Linux. Pisahkan eksperimen Linux dari aplikasi inti. Jalankan pengujian hanya pada loopback atau lab milik sendiri. Perubahan interface, firewall, dan `tc netem` memerlukan persetujuan eksplisit, jalur manajemen yang aman, serta langkah verifikasi dan rollback.

## Pengujian dan bukti

- Tambahkan modul saat dibutuhkan oleh stage. Gunakan type hint dan docstring yang menjelaskan kontrak fungsi. Utamakan `unittest`; uji perilaku keamanan positif maupun negatif dan jalankan regresi setelah refactor.
- Catat tanggal, host, interpreter, versi dependency, identitas source, command, status, error aktual, dan lokasi bukti. Bedakan hasil penerima dari keberhasilan `sendall()`. Labeli hasil yang diharapkan sebagai prediksi sampai terukur.
- Laporkan dalam bahasa Indonesia dengan bagian A–K sesuai kesepakatan, dari tujuan hingga rekomendasi berikutnya. Tandai stage selesai hanya setelah seluruh kriteria penerimaannya memiliki bukti. Klaim sertifikasi, performa, dan resilience harus didukung bukti yang sesuai.
