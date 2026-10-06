import hashlib
import hmac
import secrets


_SCRYPT_N = 2**14
_SCRYPT_R = 8
_SCRYPT_P = 1
_SCRYPT_KEY_LENGTH = 32
_SCRYPT_MAX_MEMORY = 64 * 1024 * 1024


def hash_password(password: str) -> str:
    if not 12 <= len(password) <= 128:
        raise ValueError("Password must contain between 12 and 128 characters.")
    salt = secrets.token_bytes(16)
    derived_key = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=_SCRYPT_N,
        r=_SCRYPT_R,
        p=_SCRYPT_P,
        dklen=_SCRYPT_KEY_LENGTH,
        maxmem=_SCRYPT_MAX_MEMORY,
    )
    return f"scrypt${_SCRYPT_N}${_SCRYPT_R}${_SCRYPT_P}${salt.hex()}${derived_key.hex()}"


def verify_password(password: str, password_hash: str) -> bool:
    try:
        scheme, n_value, r_value, p_value, salt_hex, expected_hex = password_hash.split("$")
        n_value_int = int(n_value)
        r_value_int = int(r_value)
        p_value_int = int(p_value)
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(expected_hex)
        if (
            scheme != "scrypt"
            or n_value_int != _SCRYPT_N
            or r_value_int != _SCRYPT_R
            or p_value_int != _SCRYPT_P
            or len(salt) != 16
            or len(expected) != _SCRYPT_KEY_LENGTH
        ):
            return False
        candidate = hashlib.scrypt(
            password.encode("utf-8"),
            salt=salt,
            n=n_value_int,
            r=r_value_int,
            p=p_value_int,
            dklen=_SCRYPT_KEY_LENGTH,
            maxmem=_SCRYPT_MAX_MEMORY,
        )
    except (ValueError, TypeError, UnicodeEncodeError):
        return False
    return hmac.compare_digest(candidate, expected)
