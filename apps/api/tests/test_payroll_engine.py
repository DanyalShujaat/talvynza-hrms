"""Pure payroll rules. Expected values are worked out by hand in the comments."""
from datetime import date
from decimal import Decimal as Dec

from app.modules.payroll import engine as p

FAR = date(9999, 12, 31)
OCT = (date(2026, 10, 1), date(2026, 10, 31))


def calc(revisions, start=OCT[0], end=OCT[1], counter=p.calendar_days, working=22, joined=date(2020, 1, 1),
         left=FAR, unpaid=Dec("0")):
    return p.calculate(start, end, revisions, count_days=counter, working_days_in_period=working,
                       active_start=joined, active_end=left, unpaid_days=unpaid)


def amount(res, name):
    return next(x.amount for x in res.lines if x.name == name)


def test_flat_salary_full_month():
    r = calc([p.Revision(date(2026, 1, 1), Dec("100000"))])
    assert r.gross == r.net == Dec("100000.00") and r.exceptions == []


def test_spec_example_mid_month_raise_100k_until_oct_14_then_110k():
    """14 days at 100,000 and 17 days at 110,000 over a 31 day month:
    100000*14/31 = 45161.2903, 110000*17/31 = 60322.5806, sum 105483.8709 -> 105483.87"""
    r = calc([p.Revision(date(2026, 1, 1), Dec("100000")), p.Revision(date(2026, 10, 15), Dec("110000"))])
    assert amount(r, "Basic salary") == Dec("105483.87")


def test_working_day_proration_for_the_same_raise():
    """Oct 2026 has 22 weekdays; Oct 1-14 has 10 of them, Oct 15-31 has 12.
    100000*10/22 + 110000*12/22 = 45454.5454 + 60000 = 105454.5454 -> 105454.55"""
    def weekdays(a, b):
        return sum(1 for i in range((b - a).days + 1) if date.fromordinal(a.toordinal() + i).weekday() < 5)

    assert weekdays(*OCT) == 22
    r = calc([p.Revision(date(2026, 1, 1), Dec("100000")), p.Revision(date(2026, 10, 15), Dec("110000"))],
             counter=weekdays)
    assert amount(r, "Basic salary") == Dec("105454.55")


def test_calendar_vs_working_day_methods_differ_and_neither_is_hardcoded():
    revs = [p.Revision(date(2026, 1, 1), Dec("100000")), p.Revision(date(2026, 10, 15), Dec("110000"))]
    cal = calc(revs)
    work = calc(revs, counter=lambda a, b: sum(1 for i in range((b - a).days + 1)
                                               if date.fromordinal(a.toordinal() + i).weekday() < 5))
    assert amount(cal, "Basic salary") != amount(work, "Basic salary")


def test_joining_mid_month_prorates_by_days_employed():
    # joined Oct 11: 21 of 31 days
    r = calc([p.Revision(date(2026, 1, 1), Dec("31000"))], joined=date(2026, 10, 11))
    assert amount(r, "Basic salary") == Dec("21000.00")


def test_leaving_mid_month_stops_pay_at_the_exit_date():
    r = calc([p.Revision(date(2026, 1, 1), Dec("31000"))], left=date(2026, 10, 10))
    assert amount(r, "Basic salary") == Dec("10000.00")


def test_components_percent_fixed_and_deductions():
    lines = (p.Line("House rent", "earning", "percent_of_basic", Dec("40")),
             p.Line("Transport", "earning", "fixed", Dec("5000")),
             p.Line("Provident fund", "deduction", "percent_of_basic", Dec("5"), taxable=False))
    r = calc([p.Revision(date(2026, 1, 1), Dec("100000"), lines)])
    assert amount(r, "House rent") == Dec("40000.00")
    assert r.gross == Dec("145000.00")
    assert r.deductions == Dec("5000.00")
    assert r.net == Dec("140000.00")


def test_components_prorate_across_a_revision_boundary():
    old = p.Revision(date(2026, 1, 1), Dec("100000"), (p.Line("Transport", "earning", "fixed", Dec("3100")),))
    new = p.Revision(date(2026, 10, 16), Dec("100000"), (p.Line("Transport", "earning", "fixed", Dec("6200")),))
    r = calc([old, new])  # 15 days old rate, 16 days new rate: 3100*15/31 + 6200*16/31 = 1500 + 3200
    assert amount(r, "Transport") == Dec("4700.00")


def test_unpaid_leave_deducts_a_working_day_rate():
    # gross 22000 over 22 working days = 1000/day; 2 unpaid days
    r = calc([p.Revision(date(2026, 1, 1), Dec("22000"))], working=22, unpaid=Dec("2"))
    assert amount(r, "Unpaid leave") == Dec("2000.00")
    assert r.net == Dec("20000.00")


def test_half_day_unpaid_leave():
    r = calc([p.Revision(date(2026, 1, 1), Dec("22000"))], working=22, unpaid=Dec("0.5"))
    assert amount(r, "Unpaid leave") == Dec("500.00")


def test_rounding_is_half_up_once_per_line_not_cumulative():
    r = calc([p.Revision(date(2026, 1, 1), Dec("100.005"))])
    assert amount(r, "Basic salary") == Dec("100.01")
    assert p.money(Dec("2.675")) == Dec("2.68")  # float based rounding would give 2.67


def test_no_float_in_results():
    r = calc([p.Revision(date(2026, 1, 1), Dec("100000"), (p.Line("A", "earning", "percent_of_basic", Dec("12.5")),))])
    assert all(isinstance(x.amount, Dec) for x in r.lines) and isinstance(r.net, Dec)


def test_revision_in_the_future_is_ignored_and_missing_salary_is_flagged():
    assert calc([p.Revision(date(2027, 1, 1), Dec("100"))]).exceptions == ["no_salary_in_period"]
    assert calc([]).exceptions == ["no_salary_in_period"]


def test_negative_net_is_flagged_for_review():
    lines = (p.Line("Loan", "deduction", "fixed", Dec("150000")),)
    assert "negative_net_pay" in calc([p.Revision(date(2026, 1, 1), Dec("100000"), lines)]).exceptions


def test_result_is_reproducible():
    revs = [p.Revision(date(2026, 1, 1), Dec("123456.78")), p.Revision(date(2026, 10, 9), Dec("130000"))]
    a, b = calc(revs), calc(list(reversed(revs)))
    assert [(x.name, x.amount) for x in a.lines] == [(x.name, x.amount) for x in b.lines]
