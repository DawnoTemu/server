import re


EMAIL_REGEX = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def is_valid_email(email: str) -> bool:
    if not email:
        return False
    return bool(EMAIL_REGEX.match(email.strip()))


def validate_password(password: str, min_length: int = 8) -> bool:
    if not password:
        return False
    return len(password) >= min_length
