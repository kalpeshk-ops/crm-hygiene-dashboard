"""Business-hours arithmetic in IST (Mon-Fri 07:30-20:30 by default)."""
from datetime import datetime, timedelta, time, timezone
from zoneinfo import ZoneInfo

from . import config as C

TZ = ZoneInfo(C.TIMEZONE)
_HOLIDAYS = {datetime.strptime(d, "%Y-%m-%d").date() for d in C.HOLIDAYS}


def _is_workday(d):
    return d.weekday() in C.BH_WEEKDAYS and d not in _HOLIDAYS


def _window(d):
    start = datetime.combine(d, time(*C.BH_START), TZ)
    end = datetime.combine(d, time(*C.BH_END), TZ)
    return start, end


def business_hours_between(a, b):
    """Business hours between two aware datetimes (0 if b <= a)."""
    if a is None or b is None or b <= a:
        return 0.0
    a, b = a.astimezone(TZ), b.astimezone(TZ)
    total = 0.0
    d = a.date()
    last = b.date()
    while d <= last:
        if _is_workday(d):
            ws, we = _window(d)
            s, e = max(ws, a), min(we, b)
            if e > s:
                total += (e - s).total_seconds() / 3600
        d += timedelta(days=1)
    return total


def business_days_between(a, b):
    return business_hours_between(a, b) / C.BH_PER_DAY


def add_business_hours(a, hours):
    """Datetime reached after `hours` business hours from a."""
    a = a.astimezone(TZ)
    remaining = hours
    d = a.date()
    for _ in range(3660):
        if _is_workday(d):
            ws, we = _window(d)
            s = max(ws, a)
            if s < we:
                avail = (we - s).total_seconds() / 3600
                if remaining <= avail:
                    return s + timedelta(hours=remaining)
                remaining -= avail
        d += timedelta(days=1)
    raise ValueError("business hours out of range")


def ist_date(dt):
    return dt.astimezone(TZ).date()


def utc_now():
    return datetime.now(timezone.utc)
