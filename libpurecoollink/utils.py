"""Utilities for Dyson Pure Hot+Cool link devices.

Removed everything but unpad and decrypt_password.
"""
import json
import base64
from Crypto.Cipher import AES


def unpad(string):
    """Un pad string."""
    return string[:-ord(string[len(string) - 1:])]


def decrypt_password(encrypted_password):
    """Decrypt password.
    :param encrypted_password: Encrypted password
    """
    key = b'\x01\x02\x03\x04\x05\x06\x07\x08\t\n\x0b\x0c\r\x0e\x0f\x10' \
          b'\x11\x12\x13\x14\x15\x16\x17\x18\x19\x1a\x1b\x1c\x1d\x1e\x1f '
    init_vector = b'\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00' \
                  b'\x00\x00\x00\x00'
    cipher = AES.new(key, AES.MODE_CBC, init_vector)
    json_password = json.loads(unpad(cipher.decrypt(base64.b64decode(encrypted_password)).decode('utf-8')))
    return json_password["apPasswordHash"]
