# Kontrak Crypto Engine Stage 03

Kontrak Stage 03 di bawah mendeskripsikan suite default ML-KEM-768/HKDF-SHA256/AES-256-GCM. Stage 07 menggunakan key schedule dan AEAD yang sama untuk empat pilihan pembentukan secret. Entry point chat menggunakan jalur Stage 02. [Antarmuka dan parameter suite Stage 07](crypto_agility.md)

## Pembentukan secret — modul kem

| Fungsi | Input | Output | Pemeriksaan dan alasan |
|---|---|---|---|
| `generate_keypair()` | Tidak ada | Tuple `(public, private)`, masing-masing 1184 dan 2400 byte | Memanggil `pqcrypto.kem.ml_kem_768.keygen()` untuk pasangan ephemeral baru. Private memakai representasi expanded. |
| `encapsulate(public)` | Public key 1184 byte | Tuple `(ciphertext, shared_secret)`, 1088 dan 32 byte | Memeriksa tipe serta panjang sebelum encapsulation, lalu memeriksa kedua output. Validasi encoding public key dilakukan library. |
| `decapsulate(private, ciphertext)` | Private key 2400 byte dan KEM ciphertext 1088 byte | Shared secret 32 byte | Memeriksa kedua input dan panjang output. Library memeriksa format internal private key. |

Semua input biner API memakai `bytes`. Input dengan tipe atau panjang keliru menghasilkan `ValueError`. Pesan kesalahan wrapper hanya memuat nama parameter atau operasi. Untuk ciphertext yang ukurannya benar, mekanisme implicit rejection ML-KEM dapat menghasilkan secret berbeda. Kecocokan kedua secret pada protokol kelak memerlukan key confirmation. [FIPS 203, §§7–8](https://nvlpubs.nist.gov/nistpubs/FIPS/NIST.FIPS.203.pdf) · [NIST SP 800-227](https://csrc.nist.gov/pubs/sp/800/227/final)

## Key schedule — modul kdf

`derive_keys(shared_secret, *, client_random, server_random, version, suite, transcript_hash) -> SessionKeys`

| Input | Kontrak |
|---|---|
| shared_secret | 32 byte hasil pembentukan secret suite terpilih. |
| client_random, server_random | Masing-masing 32 byte acak baru dari endpoint terkait. Urutan client lalu server tetap. |
| version, suite | Integer unsigned 8 bit masing-masing. Caller menentukan nilai yang disepakati. |
| transcript_hash | SHA-256 sepanjang 32 byte atas byte transcript kanonis yang sama di kedua endpoint. Penyusunan transcript menjadi tanggung jawab handshake pada tahap integrasi. |

Perhitungan berikut memakai konkatenasi byte. String literal diapit tanda petik direpresentasikan sebagai ASCII. `00` adalah satu byte nol.

```text
salt    = SHA256("HPQC/v2/salt" || 00 || client_random || server_random)
context = "HPQC/v2/key" || 00 || uint8(version) || uint8(suite) || transcript_hash
key     = HKDF-SHA256(IKM=shared_secret, salt=salt, info=context || label, length=32)
```

Empat pemanggilan HKDF menghasilkan empat field `bytes` pada objek `SessionKeys`. Label persisnya adalah `aes/c2s` untuk `aes_c2s`, `aes/s2c` untuk `aes_s2c`, `confirm/client` untuk `confirm_client`, dan `confirm/server` untuk `confirm_server`. Ukuran context tetap membuat batas sebelum label jelas. Salt mengikat random kedua endpoint, sementara label membedakan arah dan penggunaan kunci. Caller hanya meneruskan kunci AES arah terkait ke AEAD. Uji memakai RFC 5869 Appendix A.1 pada fungsi derivasi yang dipakai engine. [RFC 5869](https://www.rfc-editor.org/rfc/rfc5869.html)

## Metadata dan enkripsi — modul aead

| Interface | Input dan hasil |
|---|---|
| `DirectionContext(version, suite, session_id, direction)` | Menyimpan konteks immutable. Versi dan suite uint8, session ID 16 byte, direction 0 untuk c2s atau 1 untuk s2c. |
| `context.build_aad(message_type, sequence, nonce, ciphertext_length)` | Menghasilkan tepat 44 byte. Message type uint8, sequence uint64, nonce 12 byte, ciphertext length uint32. Panjang ini mengecualikan tag. |
| `DirectionCipher(key, context, *, limit=65536)` | Membuat satu objek dengan AES key tepat 32 byte dan himpunan nonce kosong. Limit dapat diturunkan hingga 1. |
| `cipher.encrypt(plaintext, *, message_type, sequence)` | Menerima bytes kosong sampai 2.097.092 byte. Menghasilkan `(nonce, sealed)` dengan nonce 12 byte serta `sealed = ciphertext || tag`. Panjang sealed adalah panjang plaintext ditambah 16. |
| `cipher.decrypt(nonce, sealed, *, message_type, sequence)` | Menghitung panjang ciphertext dari sealed, membangun ulang AAD, lalu mengembalikan plaintext setelah verifikasi tag. Ukuran sealed harus antara 16 dan 2.097.108 byte. |

Susunan AAD berurutan adalah versi (1), message type (1), suite (1), session ID (16), direction (1), sequence (8), nonce (12), panjang ciphertext (4). Format `struct` adalah `!BBB16sBQ12sI`, memakai network byte order. Batas data AEAD menyisakan ruang untuk header 44 byte dan tag 16 byte dalam body 2 MiB. Stage 03 hanya menghasilkan byte AAD dan output kriptografi.

### Kepemilikan kunci dan penolakan

- Di setiap endpoint, buat satu `DirectionCipher` untuk setiap directional key dan pertahankan objek itu sepanjang sesi. Pengirim dan penerima di endpoint berlainan memiliki tracker masing-masing. Membuat ulang objek dengan kunci lama, membaginya melalui fork, atau mengembalikan snapshot lama akan kehilangan jaminan riwayat nonce. Saat state hilang, gunakan kunci sesi baru.
- Pengirim mengambil nonce dari `secrets.token_bytes(12)`. Pemeriksaan dan reservasi berada di bawah lock. Reservasi tetap dihitung sekalipun enkripsi gagal. Setelah delapan kandidat berturut-turut bertabrakan, objek menolak operasi berikutnya dengan `SessionExhausted`.
- Batas proyek 65.536 record per kunci membatasi penggunaan kunci dan ukuran tracker. Pada penerima, hanya nonce yang lolos autentikasi mengisi tracker. Saat kuota habis, hentikan penggunaan kunci dan bentuk sesi dengan kunci baru sebelum mengirim lagi. [NIST SP 800-38D, §8](https://csrc.nist.gov/pubs/sp/800/38/d/final)
- Input malformed menghasilkan `ValueError`. Dengan kuota tersedia, tag salah atau nonce yang sudah diterima menghasilkan `cryptography.exceptions.InvalidTag`. Engine tidak mengeluarkan plaintext pada kegagalan verifikasi. Caller bertanggung jawab atas kebijakan kegagalan sesi dan pemeriksaan urutan sequence yang diharapkan. Objek kunci dan plaintext tidak boleh dicatat dalam log.

## Menjalankan verifikasi

Dengan interpreter yang memiliki dependency proyek, jalankan dari root repository:

```text
python -B -m unittest discover -s tests -p test_engine_v2.py -v
python -B -m unittest discover -s tests -v
python -B smoke_test.py
```

Tes pertama memakai engine baru, termasuk pengiriman dua arah dalam memori. Suite lengkap juga menjalankan tes TCP Stage 02. Smoke test memeriksa jalur baseline. Lokasi arsip asli untuk dua tes campuran dijelaskan pada [README](../README.md). Hasil host aktual tercatat pada [PROGRESS.md](../PROGRESS.md).
