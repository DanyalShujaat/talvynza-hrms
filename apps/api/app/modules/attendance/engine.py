"""Pure attendance calculation. No database access, so every rule is unit-testable.

Timestamps in and out are UTC instants; the work date and shift times are interpreted in the tenant time zone,
which makes daylight-saving changes and overnight shifts behave correctly.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

UTC = timezone.utc
DEDUPE_SECONDS = 60  # duplicate biometric reads of the same kind inside this window collapse into one


@dataclass(frozen=True)
class ShiftSpec:
    start: time
    end: time
    break_minutes: int = 0
    grace_minutes: int | None = None

    @property
    def overnight(self) -> bool:
        return self.end <= self.start


@dataclass(frozen=True)
class PolicySpec:
    grace_minutes: int = 10
    late_mode: str = "grace_exempt"  # or "full"
    overtime_threshold_minutes: int = 0


@dataclass
class DayResult:
    first_in: datetime | None = None
    last_out: datetime | None = None
    worked_minutes: int = 0
    late_minutes: int = 0
    early_leave_minutes: int = 0
    overtime_minutes: int = 0
    status: str = "absent"


def _local(d: date, t: time, tz: ZoneInfo) -> datetime:
    return datetime.combine(d, t, tzinfo=tz).astimezone(UTC)


def scheduled_window(work_date: date, shift: ShiftSpec, tz: ZoneInfo) -> tuple[datetime, datetime]:
    start = _local(work_date, shift.start, tz)
    end_date = work_date + timedelta(days=1) if shift.overnight else work_date
    return start, _local(end_date, shift.end, tz)


def collection_window(work_date: date, shift: ShiftSpec, tz: ZoneInfo) -> tuple[datetime, datetime]:
    """Punches that belong to this work date: from 4h before the shift starts to 5h after it ends."""
    start, end = scheduled_window(work_date, shift, tz)
    return start - timedelta(hours=4), end + timedelta(hours=5)


def scheduled_minutes(shift: ShiftSpec, work_date: date, tz: ZoneInfo) -> int:
    start, end = scheduled_window(work_date, shift, tz)
    return max(0, int((end - start).total_seconds() // 60) - shift.break_minutes)


def _minutes(delta: timedelta) -> int:
    return int(delta.total_seconds() // 60)


def pair_punches(events: list[tuple[datetime, str]]) -> tuple[list[tuple[datetime, datetime]], bool]:
    """Returns closed (in, out) intervals and whether a trailing 'in' is still open (missing punch)."""
    ordered: list[tuple[datetime, str]] = []
    for t, kind in sorted(events):
        if ordered and ordered[-1][1] == kind and (t - ordered[-1][0]).total_seconds() <= DEDUPE_SECONDS:
            continue  # duplicate read
        ordered.append((t, kind))
    intervals: list[tuple[datetime, datetime]] = []
    open_at: datetime | None = None
    for t, kind in ordered:
        if kind == "in":
            if open_at is None:
                open_at = t
        elif open_at is not None:
            intervals.append((open_at, t))
            open_at = None
    return intervals, open_at is not None


def compute_day(work_date: date, shift: ShiftSpec, policy: PolicySpec, tz: ZoneInfo,
                events: list[tuple[datetime, str]], *, non_working: bool = False) -> DayResult:
    """non_working: weekend or public holiday. Lateness and early leave do not apply and all worked time is overtime."""
    res = DayResult()
    if not events:
        return res
    intervals, dangling = pair_punches(events)
    ins = sorted(t for t, k in events if k == "in")
    res.first_in = ins[0] if ins else None
    if not intervals:
        res.status = "incomplete"
        return res
    res.last_out = intervals[-1][1]
    worked = sum(_minutes(b - a) for a, b in intervals)
    if len(intervals) == 1 and shift.break_minutes and worked > shift.break_minutes:
        worked -= shift.break_minutes  # one continuous span: the unpaid break was not punched out
    res.worked_minutes = worked
    res.status = "incomplete" if dangling else "present"

    start, end = scheduled_window(work_date, shift, tz)
    if non_working:
        res.overtime_minutes = worked
        return res
    grace = shift.grace_minutes if shift.grace_minutes is not None else policy.grace_minutes
    late_raw = max(0, _minutes(res.first_in - start)) if res.first_in else 0
    if late_raw <= grace:
        res.late_minutes = 0
    elif policy.late_mode == "full":
        res.late_minutes = late_raw
    else:
        res.late_minutes = late_raw - grace
    if res.last_out and not dangling and res.last_out < end:
        res.early_leave_minutes = _minutes(end - res.last_out)
    extra = worked - scheduled_minutes(shift, work_date, tz)
    res.overtime_minutes = extra if extra > policy.overtime_threshold_minutes else 0
    return res
