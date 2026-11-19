"""Pure payroll calculation. All money is Decimal; rounding is half-up to 2 places, applied once per line.

Salary amounts on a revision are amounts per pay period. When several revisions fall inside one period each
interval is charged pro rata, so a mid-period raise pays the old rate until the day before it takes effect.

This module knows nothing about any country. Statutory deductions are computed by the adapters in
payroll/statutory and appended to the result by the payroll service.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

CENT = Decimal("0.01")
ZERO = Decimal("0")


def money(v: Decimal) -> Decimal:
    return v.quantize(CENT, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class Line:
    name: str
    kind: str  # earning | deduction
    calc: str  # fixed | percent_of_basic
    value: Decimal  # amount per period, or percent
    taxable: bool = True
    # For a taxable earning: the part up to this percent of basic salary is exempt from income tax.
    exempt_percent_of_basic: Decimal | None = None


@dataclass(frozen=True)
class Revision:
    effective_from: date
    basic: Decimal
    lines: tuple[Line, ...] = ()


@dataclass
class LineResult:
    name: str
    kind: str
    source: str
    taxable: bool
    amount: Decimal
    taxable_amount: Decimal = ZERO


@dataclass
class EntryResult:
    lines: list[LineResult] = field(default_factory=list)
    unpaid_days: Decimal = ZERO
    exceptions: list[str] = field(default_factory=list)

    @property
    def gross(self) -> Decimal:
        return sum((x.amount for x in self.lines if x.kind == "earning"), ZERO)

    @property
    def deductions(self) -> Decimal:
        return sum((x.amount for x in self.lines if x.kind == "deduction"), ZERO)

    @property
    def net(self) -> Decimal:
        return self.gross - self.deductions

    @property
    def taxable_income(self) -> Decimal:
        """Taxable earnings less pay lost to unpaid leave."""
        earned = sum((x.taxable_amount for x in self.lines if x.kind == "earning"), ZERO)
        lost = sum((x.amount for x in self.lines if x.source == "unpaid_leave"), ZERO)
        return max(ZERO, earned - lost)


DayCounter = Callable[[date, date], int]  # inclusive count of countable days between two dates


def calendar_days(a: date, b: date) -> int:
    return (b - a).days + 1 if b >= a else 0


def line_amount(ln: Line, basic: Decimal) -> Decimal:
    return ln.value if ln.calc == "fixed" else basic * ln.value / Decimal(100)


def line_exempt(ln: Line, basic: Decimal, amount: Decimal) -> Decimal:
    if ln.kind != "earning":
        return ZERO
    if not ln.taxable:
        return amount
    if ln.exempt_percent_of_basic is not None:
        return min(amount, basic * ln.exempt_percent_of_basic / Decimal(100))
    return ZERO


def regular_taxable(rev: Revision) -> Decimal:
    """Taxable pay for one full period at this revision, used to project the rest of a tax year."""
    total = rev.basic
    for ln in rev.lines:
        if ln.kind == "earning":
            amount = line_amount(ln, rev.basic)
            total += amount - line_exempt(ln, rev.basic, amount)
    return money(total)


def intervals(period_start: date, period_end: date, revisions: list[Revision], active_start: date,
              active_end: date) -> list[tuple[Revision, date, date]]:
    """Splits the part of the period the employee was on the payroll into (revision, from, to) segments."""
    revs = sorted(revisions, key=lambda r: r.effective_from)
    lo, hi = max(period_start, active_start), min(period_end, active_end)
    out = []
    for i, r in enumerate(revs):
        seg_start = max(r.effective_from, lo)
        seg_end = (revs[i + 1].effective_from - timedelta(days=1)) if i + 1 < len(revs) else hi
        seg_end = min(seg_end, hi)
        if seg_start <= seg_end:
            out.append((r, seg_start, seg_end))
    return out


def flag_negative(res: EntryResult) -> None:
    if res.net < 0 and "negative_net_pay" not in res.exceptions:
        res.exceptions.append("negative_net_pay")


def calculate(period_start: date, period_end: date, revisions: list[Revision], *, count_days: DayCounter,
              working_days_in_period: int, active_start: date, active_end: date,
              unpaid_days: Decimal = ZERO) -> EntryResult:
    """count_days selects the proration basis (calendar days or working days)."""
    res = EntryResult(unpaid_days=unpaid_days)
    divisor = count_days(period_start, period_end)
    if divisor <= 0:
        res.exceptions.append("period_has_no_countable_days")
        return res
    segs = intervals(period_start, period_end, revisions, active_start, active_end)
    if not segs:
        res.exceptions.append("no_salary_in_period")
        return res

    totals: dict[tuple[str, str, str, bool], list[Decimal]] = {}

    def add(key: tuple[str, str, str, bool], amount: Decimal, exempt: Decimal) -> None:
        cur = totals.setdefault(key, [ZERO, ZERO])
        cur[0] += amount
        cur[1] += exempt

    for rev, a, b in segs:
        frac = Decimal(count_days(a, b)) / Decimal(divisor)
        add(("Basic salary", "earning", "basic", True), rev.basic * frac, ZERO)
        for ln in rev.lines:
            amount = line_amount(ln, rev.basic)
            add((ln.name, ln.kind, "component", ln.taxable), amount * frac, line_exempt(ln, rev.basic, amount) * frac)
    for (name, kind, source, taxable), (amount, exempt) in totals.items():
        amt = money(amount)
        res.lines.append(LineResult(name, kind, source, taxable, amt,
                                    max(ZERO, amt - money(exempt)) if kind == "earning" else ZERO))

    if unpaid_days > 0:
        last = segs[-1][0]
        full_gross = last.basic + sum((line_amount(ln, last.basic) for ln in last.lines if ln.kind == "earning"), ZERO)
        if working_days_in_period <= 0:
            res.exceptions.append("no_working_days_for_unpaid_leave")
        else:
            # Unpaid leave days are working days, so the daily rate is a working-day rate.
            res.lines.append(LineResult("Unpaid leave", "deduction", "unpaid_leave", True,
                                        money(full_gross / Decimal(working_days_in_period) * unpaid_days)))
    flag_negative(res)
    return res
