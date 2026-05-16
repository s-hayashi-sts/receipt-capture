import re

def validate_password(password: str) -> bool:
    has_upper = re.search(r"[A-Z]", password)
    has_lower = re.search(r"[a-z]", password)
    has_number = re.search(r"[0-9]", password)
    has_symbol = re.search(r"[^A-Za-z0-9]", password)

    return all([has_upper, has_lower, has_number, has_symbol])

def is_allowed_characters(password: str) -> bool:
    # 半角英数字と記号（ASCII printable）だけ許可
    return bool(re.fullmatch(r"[\x20-\x7E]+", password))

