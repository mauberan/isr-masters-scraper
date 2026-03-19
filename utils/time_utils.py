# utils/time_utils.py
#
# Converts swim time strings from the scraper into milliseconds for storage.
#
# Why milliseconds?
#   Storing times as integers enables sorting, arithmetic, and aggregation
#   without any parsing at query time. "25.43" as a string cannot be compared
#   or averaged. 25430 as an integer can.
#
# Examples:
#   "25.43"   → 25430
#   "1:25.43" → 85430
#   "DSQ"     → None
#   "DNS"     → None
#   ""        → None


NON_TIMES = {"DSQ", "DQ", "DNS", "DNF", "—", "-", ""}


def time_str_to_ms(time_str: str | None) -> int | None:
    """
    Convert a swim time string to milliseconds.
    Returns None for disqualifications, did-not-starts, or missing values.
    """
    if time_str is None:
        return None

    cleaned = time_str.strip().upper()

    if cleaned in NON_TIMES:
        return None

    try:
        if ":" in cleaned:
            minutes, rest = cleaned.split(":", 1)
            seconds = float(rest)
            return int((int(minutes) * 60 + seconds) * 1000)
        else:
            return int(float(cleaned) * 1000)
    except ValueError:
        return None


def ms_to_time_str(ms: int | None) -> str | None:
    """
    Convert milliseconds back to a human-readable time string.
    Useful for display and debugging.

    Examples:
        25430  → "25.43"
        85430  → "1:25.43"
    """
    if ms is None:
        return None

    total_seconds = ms / 1000
    minutes = int(total_seconds // 60)
    seconds = total_seconds % 60

    if minutes > 0:
        return f"{minutes}:{seconds:05.2f}"
    else:
        return f"{seconds:.2f}"


def is_non_time(time_str: str | None) -> tuple[bool, bool]:
    """
    Returns (is_dsq, is_dns) booleans from a raw time string.
    """
    if time_str is None:
        return False, False
    cleaned = time_str.strip().upper()
    is_dsq = cleaned in {"DSQ", "DQ"}
    is_dns = cleaned in {"DNS", "DNF"}
    return is_dsq, is_dns
