# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: Copyright 2024 Sam Blenny
#
# Related Docs
# - https://datatracker.ietf.org/doc/html/rfc2202  (RFC2202: HMAC test vectors)
# - https://www.rfc-editor.org/errata/rfc2202   (RFC2202 Errata: see case #7)
#
from sb_hmac import hmac_sha1


# RFC 2202 Test Cases for HMAC-SHA-1
bfh = bytes.fromhex
TEST_CASES = (
    {
        # 1: key_len=20, data_len=8
        'key': bfh('0b0b0b0b0b0b0b0b0b0b0b0b0b0b0b0b0b0b0b0b'),
        'data': "Hi There",
        'digest': bfh('b617318655057264e28bc0b6fb378c8ef146be00'),
    },{
        # 2: key_len=4, data_len=28
        'key': "Jefe",
        'data': "what do ya want for nothing?",
        'digest': bfh('effcdf6ae5eb2fa2d27416d5f184df9c259a7c79'),
    },{
        # 3: key_len=20, data_len=50
        'key': bfh('aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'),
        'data': b'\xdd' * 50,
        'digest': bfh('125d7342b9ac11cd91a39af48aa17b4f63f175d3'),
    },{
        # 4: key_len=25, data_len=50
        'key': bfh('0102030405060708090a0b0c0d0e0f10111213141516171819'),
        'data': b'\xcd' * 50,
        'digest': bfh('4c9007f4026250c6bc8414f9bf50c86c2d7235da'),
    },{
        # 5: key_len=20, data_len=20
        'key': bfh('0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c'),
        'data': "Test With Truncation",
        'digest': bfh('4c1a03424b55e07fe7f27be1d58bb9324a9a5a04'),
        'digest_96': bfh('4c1a03424b55e07fe7f27be1'),
    },{
        # 6: key_len=80, data_len=54
        'key': b'\xaa' * 80,
        'data': "Test Using Larger Than Block-Size Key - Hash Key First",
        'digest': bfh('aa4ae5e15272d00e95705637ce8a3b55ed402112'),
    },{
        # 7: key_len=80, data_len=73
        # CAUTION: Test case 7 of RFC2202 was corrected by an erratum.
        # See: https://www.rfc-editor.org/rfc/inline-errata/rfc2202.html
        'key': b'\xaa' * 80,
        'data':
            "Test Using Larger Than Block-Size Key and Larger"
            " Than One Block-Size Data",
        'digest': bfh('e8e99d0f45237d786d6bbaa7965c7808bbff1a91'),
    },{
        # 8: key_len=80, data_len=54
        'key': b'\xaa' * 80,
        'data': "Test Using Larger Than Block-Size Key - Hash Key First",
        'digest': bfh('aa4ae5e15272d00e95705637ce8a3b55ed402112'),
    },{
        # 9: key_len=80, data_len=73
        'key': b'\xaa' * 80,
        'data':
            "Test Using Larger Than Block-Size Key and Larger"
            " Than One Block-Size Data",
        'digest': bfh('e8e99d0f45237d786d6bbaa7965c7808bbff1a91'),
    }
)

print("Testing sb_hmac_sha1.hmac_sha1 against RFC2202 test cases...")
for i, tc in enumerate(TEST_CASES):
    if (digest := hmac_sha1(tc['key'], tc['data'])) != tc['digest']:
        wanted = tc['digest'].hex()
        got = digest.hex()
        print(f"Test Case {i+1}: FAIL wanted {wanted}, got {got}")
    else:
        print(f"Test Case {i+1}: OK")


# Result of running tests should look like this:
"""
$ python3 test_sb_hmac.py
Testing sb_hmac_sha1.hmac_sha1 against RFC2202 test cases...
Test Case 1: OK
Test Case 2: OK
Test Case 3: OK
Test Case 4: OK
Test Case 5: OK
Test Case 6: OK
Test Case 7: OK
Test Case 8: OK
Test Case 9: OK
"""
