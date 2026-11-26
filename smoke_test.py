from pqcrypto.kem.ml_kem_768 import keygen, encaps, decaps
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
import os
import time

t0 = time.perf_counter_ns()
pk, sk = keygen()
t1 = time.perf_counter_ns()
ct, ss1 = encaps(pk)
t2 = time.perf_counter_ns()
ss2 = decaps(sk, ct)
t3 = time.perf_counter_ns()
assert ss1 == ss2
key = HKDF(algorithm=hashes.SHA512(), length=32, salt=None, info=b'HPQC-LAB-smoke-test').derive(ss1)
nonce = os.urandom(12)
plaintext = 'Halo dari simulasi HPQC'.encode()
encrypted = AESGCM(key).encrypt(nonce, plaintext, None)
assert AESGCM(key).decrypt(nonce, encrypted, None) == plaintext
print('ML-KEM shared secret cocok:', ss1 == ss2)
print('AES-256-GCM dekripsi benar: True')
print('Waktu KeyGen / Encaps / Decaps (ms):', *[round((b-a)/1e6, 3) for a,b in [(t0,t1),(t1,t2),(t2,t3)]])
