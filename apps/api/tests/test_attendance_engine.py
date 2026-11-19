"""Pure attendance rules: lateness policies, overnight shifts, punches, daylight saving."""
from datetime import date, datetime, time, timezone
from zoneinfo import ZoneInfo

from app.modules.attendance import engine as e

KHI = ZoneInfo("Asia/Karachi")
LON = ZoneInfo("Europe/London")
UTC = timezone.utc
D = date(2026, 3, 4)  # a Wednesday
SHIFT = e.ShiftSpec(time(9, 30), time(18, 0), break_minutes=30)


def at(h, m, d=D, tz=KHI):
    return datetime.combine(d, time(h, m), tzinfo=tz).astimezone(UTC)


def day(events, policy=None, shift=SHIFT, tz=KHI, d=D, **kw):
    return e.compute_day(d, shift, policy or e.PolicySpec(10, "grace_exempt"), tz, events, **kw)


def test_arrival_inside_grace_is_not_late_in_either_mode():
    for mode in ("grace_exempt", "full"):
        r = day([(at(9, 38), "in"), (at(18, 0), "out")], e.PolicySpec(10, mode))
        assert r.late_minutes == 0


def test_spec_example_945_with_ten_minute_grace_full_vs_grace_exempt():
    events = [(at(9, 45), "in"), (at(18, 0), "out")]
    assert day(events, e.PolicySpec(10, "full")).late_minutes == 15  # whole lateness counted once grace is exceeded
    assert day(events, e.PolicySpec(10, "grace_exempt")).late_minutes == 5  # grace minutes are excused


def test_shift_level_grace_overrides_policy_grace():
    s = e.ShiftSpec(time(9, 30), time(18, 0), 30, grace_minutes=20)
    assert day([(at(9, 45), "in"), (at(18, 0), "out")], shift=s).late_minutes == 0


def test_worked_time_subtracts_unpunched_break_once():
    r = day([(at(9, 30), "in"), (at(18, 0), "out")])
    assert r.worked_minutes == 8 * 60 + 30 - 30
    assert r.status == "present" and r.overtime_minutes == 0


def test_multiple_punches_gap_is_the_break():
    r = day([(at(9, 30), "in"), (at(13, 0), "out"), (at(14, 0), "in"), (at(18, 0), "out")])
    assert r.worked_minutes == 210 + 240
    assert r.first_in == at(9, 30) and r.last_out == at(18, 0)


def test_missing_out_punch_is_incomplete_not_zero_hours_present():
    r = day([(at(9, 30), "in")])
    assert r.status == "incomplete" and r.worked_minutes == 0


def test_duplicate_biometric_reads_collapse():
    r = day([(at(9, 30), "in"), (datetime.combine(D, time(9, 30, 40), tzinfo=KHI).astimezone(UTC), "in"),
             (at(18, 0), "out")])
    assert r.worked_minutes == 480


def test_overtime_and_early_leave():
    assert day([(at(9, 30), "in"), (at(20, 0), "out")]).overtime_minutes == 120
    r = day([(at(9, 30), "in"), (at(16, 0), "out")])
    assert r.early_leave_minutes == 120 and r.overtime_minutes == 0


def test_overtime_threshold():
    policy = e.PolicySpec(10, "full", overtime_threshold_minutes=15)
    assert day([(at(9, 30), "in"), (at(18, 10), "out")], policy).overtime_minutes == 0  # 10 min over: under threshold
    assert day([(at(9, 30), "in"), (at(18, 30), "out")], policy).overtime_minutes == 30


def test_weekend_or_holiday_work_is_all_overtime_and_never_late():
    r = day([(at(11, 0), "in"), (at(15, 0), "out")], non_working=True)
    assert r.late_minutes == 0 and r.early_leave_minutes == 0
    assert r.overtime_minutes == r.worked_minutes == 240 - 30


def test_overnight_shift_window_and_lateness():
    night = e.ShiftSpec(time(22, 0), time(6, 0), break_minutes=0)
    assert night.overnight
    start, end = e.scheduled_window(D, night, KHI)
    assert (end - start).total_seconds() == 8 * 3600
    next_day = date(2026, 3, 5)
    r = e.compute_day(D, night, e.PolicySpec(10, "full"), KHI, [(at(22, 20), "in"), (at(6, 0, next_day), "out")])
    assert r.late_minutes == 20 and r.worked_minutes == 7 * 60 + 40 and r.status == "present"


def test_daylight_saving_spring_forward_shortens_the_shift():
    """London clocks jump 01:00 -> 02:00 on 2026-03-29, so a 00:00-08:00 night shift is only 7 real hours."""
    night = e.ShiftSpec(time(0, 0), time(8, 0))
    # 00:00 to 08:00 on the same date (start before the jump, end after)
    d = date(2026, 3, 29)
    start, end = e.scheduled_window(d, night, LON)
    assert (end - start).total_seconds() == 7 * 3600
    assert e.scheduled_minutes(night, d, LON) == 7 * 60


def test_time_zone_matters_for_lateness():
    karachi_arrival = datetime(2026, 3, 4, 5, 0, tzinfo=UTC)  # 10:00 in Karachi (UTC+5)
    r = day([(karachi_arrival, "in"), (at(18, 0), "out")], e.PolicySpec(10, "full"))
    assert r.late_minutes == 30


def test_no_events_is_absent():
    assert day([]).status == "absent"
