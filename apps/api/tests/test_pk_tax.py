"""Pakistan salary withholding. Expected figures are worked out by hand from the Finance Act tables."""
from datetime import date
from decimal import Decimal as D

import pytest

from app.modules.payroll.statutory import pk

TY27, TY26 = pk.TAX_YEARS[2027], pk.TAX_YEARS[2026]


@pytest.mark.parametrize("income,tax", [
    (600_000, 0),            # at the threshold: nil
    (1_200_000, 6_000),      # 1% of 600,000
    (1_800_000, 72_000),     # 6,000 + 11% of 600,000
    (2_400_000, 156_000),    # 116,000 + 20% of 200,000
    (3_200_000, 316_000),    # top of the 20% band
    (5_000_000, 802_000),    # 541,000 + 29% of 900,000
    (6_000_000, 1_104_000),  # 976,000 + 32% of 400,000
    (8_000_000, 1_774_000),  # 1,424,000 + 35% of 1,000,000
    (12_000_000, 3_174_000),  # no surcharge in tax year 2027
])
def test_annual_tax_tax_year_2027(income, tax):
    assert pk.annual_tax(D(income), TY27) == D(tax)


@pytest.mark.parametrize("income,tax", [
    (600_000, 0), (1_200_000, 6_000), (2_400_000, 162_000),  # 116,000 + 23% of 200,000
    (4_100_000, 616_000), (5_000_000, 931_000),              # 616,000 + 35% of 900,000
    (12_000_000, 3_685_290),                                 # (616,000 + 35% of 7,900,000) plus 9% surcharge
])
def test_annual_tax_tax_year_2026(income, tax):
    assert pk.annual_tax(D(income), TY26) == D(tax)


@pytest.mark.parametrize("ty", [TY26, TY27])
def test_slab_table_is_continuous(ty):
    """At each bracket boundary the lower bracket's formula must give the next bracket's fixed amount."""
    for lower, upper in zip(ty.slabs, ty.slabs[1:], strict=False):
        assert lower.fixed + (upper.over - lower.over) * lower.rate == upper.fixed


def test_tax_year_and_months_left():
    assert pk.tax_year_of(date(2026, 6, 30)) == 2026 and pk.tax_year_of(date(2026, 7, 1)) == 2027
    assert pk.months_left(date(2026, 7, 31)) == 12 and pk.months_left(date(2026, 11, 30)) == 8
    assert pk.months_left(date(2027, 6, 30)) == 1
    assert TY27.start == date(2026, 7, 1) and TY27.end == date(2027, 6, 30)


def simulate(monthly: list[int], ty=TY27, start_month=7, regular: list[int] | None = None) -> list[D]:
    """Runs the withholding month by month, feeding each result back in as year-to-date.
    `regular` is the recurring monthly pay used to project the months still to come."""
    regular = regular or monthly
    ytd_taxable, ytd_tax, out = D(0), D(0), []
    for i, pay in enumerate(monthly):
        month = (start_month - 1 + i) % 12 + 1
        left = pk.months_left(date(2026 if month >= 7 else 2027, month, 28))
        tax = pk.monthly_withholding(ty, ytd_taxable=ytd_taxable, ytd_tax=ytd_tax, current_taxable=D(pay),
                                     future_monthly_taxable=D(regular[i]), months_remaining=left)
        out.append(tax)
        ytd_taxable += D(pay)
        ytd_tax += tax
    return out


def test_steady_salary_is_one_twelfth_each_month():
    taxes = simulate([200_000] * 12)
    assert taxes == [D(13_000)] * 12 and sum(taxes) == pk.annual_tax(D(2_400_000), TY27)


def test_mid_year_raise_catches_up_and_the_year_total_is_exact():
    taxes = simulate([200_000] * 6 + [300_000] * 6)
    assert taxes[0] == D(13_000) and taxes[6] > taxes[5]
    assert sum(taxes) == pk.annual_tax(D(3_000_000), TY27) == D(276_000)


def test_one_off_bonus_is_spread_over_the_rest_of_the_year():
    pays = [150_000] * 12
    pays[3] = 650_000  # a 500,000 bonus in October; regular pay stays 150,000
    taxes = simulate(pays, regular=[150_000] * 12)
    assert sum(taxes) == pk.annual_tax(D(sum(pays)), TY27) == D(136_000)  # 116,000 + 20% of 100,000
    assert taxes[3] > taxes[2] and taxes[4] == taxes[3]  # the extra tax is spread evenly, no single spike


def test_joining_in_january_only_projects_the_remaining_months():
    taxes = simulate([200_000] * 6, start_month=1)  # 1,200,000 in the tax year -> 6,000
    assert taxes == [D(1_000)] * 6


def test_income_under_the_threshold_pays_nothing_and_tax_is_never_negative():
    assert simulate([45_000] * 12) == [D(0)] * 12
    assert pk.monthly_withholding(TY27, ytd_taxable=D(2_000_000), ytd_tax=D(900_000), current_taxable=D(10_000),
                                  future_monthly_taxable=D(10_000), months_remaining=3) == D(0)


def test_final_month_settles_on_actual_income():
    """In June (or the month someone leaves) nothing is projected: the year's tax on actual pay less tax already paid."""
    tax = pk.monthly_withholding(TY27, ytd_taxable=D(2_200_000), ytd_tax=D(140_000), current_taxable=D(200_000),
                                 future_monthly_taxable=D(200_000), months_remaining=1)
    assert tax == pk.annual_tax(D(2_400_000), TY27) - D(140_000) == D(16_000)


def test_rule_sets_carry_their_source_and_verification():
    for ty in (TY26, TY27):
        d = pk.describe(ty)
        assert d["law"] and d["sources"] and d["verification"]
        assert d["slabs"][0] == {"from": "0", "to": "600000", "fixed": "0", "rate_percent": "0"}
        assert d["slabs"][-1]["to"] is None
    assert pk.describe(TY27)["surcharge"] is None and pk.describe(TY26)["surcharge"]["rate_percent"] == "9.00"
    assert "Gazette" in TY27.verification
