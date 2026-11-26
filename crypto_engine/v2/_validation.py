"""Validate binary inputs without including their contents in exceptions."""


def require_bytes(value: bytes, name: str, size: int) -> None:
    if type(value) is not bytes or len(value) != size:
        raise ValueError(f"{name} must be {size} bytes")


def require_uint(value: int, name: str, bits: int) -> None:
    if type(value) is not int or not 0 <= value < 1 << bits:
        raise ValueError(f"{name} must be an unsigned {bits}-bit integer")
