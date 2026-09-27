import secrets
import time

def generate_numeric_id() -> str:

    epoch_part = int(time.time() * 1000) % 1_000_000
    time_str = f"{epoch_part:06d}"

    random_part = secrets.randbelow(100_000)
    rand_str = f"{random_part:05d}"

    raw_11 = f"{time_str}{rand_str}"

    checksum = calculate_luhn_checksum(raw_11)

    full_id = f"{raw_11}{checksum}"
    return full_id

def calculate_luhn_checksum(number_str: str) -> int:

    digits = [int(d) for d in number_str]
    odd_digits = digits[-1::-2]
    even_digits = digits[-2::-2]
    total = sum(odd_digits)
    for d in even_digits:
        doubled = d * 2
        total += doubled if doubled < 10 else (doubled - 9)
    return (10 - (total % 10)) % 10

def format_id_display(numeric_id: str) -> str:

    cleaned = "".join(ch for ch in str(numeric_id) if ch.isdigit())
    if len(cleaned) == 12:
        return f"{cleaned[0:4]}-{cleaned[4:8]}-{cleaned[8:12]}"
    return cleaned

def validate_numeric_id(numeric_id_str: str) -> bool:

    cleaned = "".join(ch for ch in str(numeric_id_str) if ch.isdigit())
    if len(cleaned) != 12:
        return False
    raw_11 = cleaned[:11]
    expected_check = calculate_luhn_checksum(raw_11)
    return int(cleaned[11]) == expected_check
