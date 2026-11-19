"""Pakistan: income tax withholding on salary (Income Tax Ordinance 2001, section 149).

Rates come from the First Schedule, Part I, Division I, clause (2): the table for individuals whose salary income
exceeds 75% of taxable income. Each tax year is a separate, versioned rule set with its source. A pay period whose
tax year has no rule set here gets no income tax and the run says so. Rates are never guessed.

Tax year N runs from 1 July (N-1) to 30 June N.

What this does not handle (it must be handled by a tax adviser or configured outside the system): tax credits and
reductions (teachers and researchers, donations, pension fund contributions), income from a previous employer in the
same tax year, non-salary income, and valuation of perquisites such as vehicles and accommodation.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

D = Decimal
RUPEE = D("1")


@dataclass(frozen=True)
class Slab:
    over: Decimal  # taxable income above this amount...
    fixed: Decimal  # ...pays this fixed amount...
    rate: Decimal  # ...plus this share of the excess


@dataclass(frozen=True)
class TaxYear:
    year: int
    slabs: tuple[Slab, ...]
    surcharge_over: Decimal | None
    surcharge_rate: Decimal | None
    law: str
    verification: str
    sources: tuple[str, ...]

    @property
    def start(self) -> date:
        return date(self.year - 1, 7, 1)

    @property
    def end(self) -> date:
        return date(self.year, 6, 30)


def _slabs(*rows: tuple[int, int, str]) -> tuple[Slab, ...]:
    return tuple(Slab(D(o), D(f), D(r)) for o, f, r in rows)


TAX_YEARS: dict[int, TaxYear] = {
    2026: TaxYear(
        year=2026,
        slabs=_slabs((600_000, 0, "0.01"), (1_200_000, 6_000, "0.11"), (2_200_000, 116_000, "0.23"),
                     (3_200_000, 346_000, "0.30"), (4_100_000, 616_000, "0.35")),
        surcharge_over=D(10_000_000), surcharge_rate=D("0.09"),
        law="Finance Act 2025",
        verification="Secondary sources only (two published summaries that agree). Not checked against the Gazette.",
        sources=("https://www.ict.edu.pk/blogs/income-tax-slabs-salaried-individuals-pakistan",
                 "https://taxsummaries.pwc.com/pakistan/individual"),
    ),
    2027: TaxYear(
        year=2027,
        slabs=_slabs((600_000, 0, "0.01"), (1_200_000, 6_000, "0.11"), (2_200_000, 116_000, "0.20"),
                     (3_200_000, 316_000, "0.25"), (4_100_000, 541_000, "0.29"), (5_600_000, 976_000, "0.32"),
                     (7_000_000, 1_424_000, "0.35")),
        surcharge_over=None, surcharge_rate=None,  # section 4AB proviso: "no surcharge shall be payable"
        law="Finance Act 2026",
        verification="Checked on 2026-11-14 against the Gazette of Pakistan, Extraordinary, 26 June 2026, "
                     "Part I, pages 558 and 580 (Finance Act 2026, section 4AB proviso and First Schedule table).",
        sources=("https://download1.fbr.gov.pk/Docs/20266291261044366FinanceAct2026.pdf",),
    ),
}


def tax_year_of(d: date) -> int:
    return d.year + 1 if d.month >= 7 else d.year


def months_left(d: date) -> int:
    """Pay months remaining in the tax year, counting the month of d. July is 12, June is 1."""
    return ((6 - d.month) % 12) + 1


def rupees(v: Decimal) -> Decimal:
    return v.quantize(RUPEE, rounding=ROUND_HALF_UP)


def annual_tax(taxable: Decimal, ty: TaxYear) -> Decimal:
    tax = D("0")
    for slab in reversed(ty.slabs):
        if taxable > slab.over:
            tax = slab.fixed + (taxable - slab.over) * slab.rate
            break
    if ty.surcharge_over is not None and taxable > ty.surcharge_over:
        tax += tax * ty.surcharge_rate
    return rupees(tax)


def monthly_withholding(ty: TaxYear, *, ytd_taxable: Decimal, ytd_tax: Decimal, current_taxable: Decimal,
                        future_monthly_taxable: Decimal, months_remaining: int) -> Decimal:
    """Tax to deduct this month.

    Project the year's taxable salary from what has been paid so far, this month and the months still to come,
    compute the year's tax, subtract what was already withheld and spread the rest over the remaining months.
    A raise, a bonus or a mid-year start therefore corrects itself over the rest of the year, and the last month
    settles exactly. Whole rupees, never negative.
    """
    months_remaining = max(1, months_remaining)
    projected = ytd_taxable + current_taxable + future_monthly_taxable * (months_remaining - 1)
    due = (annual_tax(projected, ty) - ytd_tax) / D(months_remaining)
    return max(D("0"), rupees(due))


def describe(ty: TaxYear) -> dict:
    bounds = [s.over for s in ty.slabs]
    rows = [{"from": "0", "to": str(bounds[0]), "fixed": "0", "rate_percent": "0"}]
    for i, s in enumerate(ty.slabs):
        rows.append({"from": str(s.over), "to": str(bounds[i + 1]) if i + 1 < len(bounds) else None,
                     "fixed": str(s.fixed), "rate_percent": str(s.rate * 100)})
    return {"tax_year": ty.year, "period": f"{ty.start.isoformat()} to {ty.end.isoformat()}", "law": ty.law,
            "verification": ty.verification, "sources": list(ty.sources), "slabs": rows,
            "surcharge": None if ty.surcharge_over is None else
            {"over": str(ty.surcharge_over), "rate_percent": str(ty.surcharge_rate * 100)}}
