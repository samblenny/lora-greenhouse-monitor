# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: Copyright 2024 Sam Blenny
#
# Related Docs:
# - https://datatracker.ietf.org/doc/html/rfc2104  (HMAC RFC)
# - https://nvlpubs.nist.gov/nistpubs/fips/nist.fips.198-1.pdf (FIPS PUB 198-1)
#
import hashlib


def hmac(K, text, hash_fn, B, L):
    # Return HMAC digest for key and text using the named hash algorithm.
    #
    # The non-pythonic parameter names correspond to the notation used in
    # RFC 2104 and FIPS 198-1. The point of doing it this way is to make
    # it easier to compare this implementation against the specs.
    # Params:
    #   K: secret key (UTF-8 string or bytes)
    #   text: hash function input data (UTF-8 string or bytes)
    #   hash_fn: name of hash function for use with hashlib.new()
    #   B: block size in bytes of hash function input
    #   L: byte-length of hash function output
    # FIPS 198-1 Crypto Math Notation:
    #   ⨁: plus sign in a circle means bitwise XOR
    #   ||: two vertical bars means concatenate bitstreams

    # Convert text from string to bytes if needed
    if isinstance(text, str):
        text = text.encode('utf-8')
    # Convert key from string to bytes if needed
    if isinstance(K, str):
        K = K.encode('utf-8')
    # Prepare key as block sized byte buffer (hash or pad as needed)
    if len(K) == B:
        K0 = K
    elif len(K) > B:
        H = hashlib.new('sha1')
        H.update(K)
        K0 = H.digest() + (b'\x00' * (B - L))
    elif len(K) < B:
        K0 = K + (b'\x00' * (B - len(K)))
    # Calculate inner hash: H((K₀ ⨁ ipad)||text)
    K0_xored = bytearray([b ^ 0x36 for b in K0])
    H = hashlib.new('sha1')
    H.update(K0_xored)
    H.update(text)
    inner_hash = H.digest()
    # Calculate outer hash: H((K₀ ⨁ opad)||inner_digest)
    K0_xored = bytearray([b ^ 0x5c for b in K0])
    H = hashlib.new('sha1')
    H.update(K0_xored)
    H.update(inner_hash)
    return H.digest()


def hmac_sha1(key, data):
    # HMAC-SHA1 digest for key and data
    return hmac(K=key, text=data, hash_fn='sha1', B=64, L=20)


