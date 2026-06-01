"""
Loan amortization — Pack 7.41.

Generates a quarterly linear repayment schedule for a single loan from
its date_get, date_due, debt_usd, and debt_currency.

Algorithm:
  N = number of full quarters between date_get and date_due
  per_quarter_usd = debt_usd / N
  per_quarter_currency = debt_currency / N
  status = "paid" if quarter is in the past, "scheduled" otherwise
  is_custom_schedule = False (this is auto-generated)

Custom schedules (parsed from loan.notes) are handled separately by the
admin. This service only generates the default linear schedule.

Run on:
  • initial seed for all existing loans (runtime_migrations.py)
  • new loan inserted into cp_loans (trigger via API hook)
  • loan dates changed (recalculate schedule)
"""
from datetime import date
from decimal import Decimal
from typing import Optional

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.credit import CreditPortfolioLoan
from app.models.loan_repayments import LoanRepayment


def quarters_between(d_start: date, d_end: date) -> list[tuple[int, int]]:
    """Return list of (year, quarter) tuples between two dates, inclusive.

    Empty if d_end <= d_start.
    """
    if d_end <= d_start:
        return []
    result: list[tuple[int, int]] = []
    y = d_start.year
    q = (d_start.month - 1) // 3 + 1
    end_y = d_end.year
    end_q = (d_end.month - 1) // 3 + 1
    while (y, q) <= (end_y, end_q):
        result.append((y, q))
        q += 1
        if q > 4:
            q = 1
            y += 1
    return result


def quarter_end_date(year: int, quarter: int) -> date:
    """Last day of the given (year, quarter)."""
    if quarter == 1:
        return date(year, 3, 31)
    if quarter == 2:
        return date(year, 6, 30)
    if quarter == 3:
        return date(year, 9, 30)
    return date(year, 12, 31)


def generate_schedule_for_loan(
    loan: CreditPortfolioLoan,
    as_of: date,
) -> list[dict]:
    """Pure function: from a loan, generate list of repayment dicts.

    Doesn't touch DB. Returns rows ready to insert into loan_repayments.
    """
    if not loan.date_get or not loan.date_due:
        return []
    if not loan.debt_usd or float(loan.debt_usd) <= 0:
        return []

    quarters = quarters_between(loan.date_get, loan.date_due)
    if not quarters:
        return []

    n = len(quarters)
    debt_usd = Decimal(str(loan.debt_usd))
    per_usd = (debt_usd / Decimal(n)).quantize(Decimal("0.01"))

    debt_cur = Decimal(str(loan.debt_currency)) if loan.debt_currency else None
    per_cur = (
        (debt_cur / Decimal(n)).quantize(Decimal("0.01"))
        if debt_cur
        else None
    )

    rows: list[dict] = []
    for (y, q) in quarters:
        q_end = quarter_end_date(y, q)
        status = "paid" if q_end < as_of else "scheduled"
        rows.append(
            {
                "loan_id": loan.id,
                "period_year": y,
                "period_quarter": q,
                "scheduled_amount_usd": per_usd,
                "scheduled_amount_currency": per_cur,
                "actual_paid_amount_usd": per_usd if status == "paid" else None,
                "actual_paid_amount_currency": (
                    per_cur if status == "paid" else None
                ),
                "status": status,
                "is_custom_schedule": False,
                "payment_date": q_end if status == "paid" else None,
            }
        )
    return rows


async def rebuild_schedule_for_loan(
    db: AsyncSession,
    loan_id,
    as_of: Optional[date] = None,
) -> int:
    """Delete existing auto-generated rows for one loan and rebuild.

    Custom-schedule rows (is_custom_schedule=True) are preserved.
    Returns count of new rows inserted.
    """
    res = await db.execute(
        select(CreditPortfolioLoan).where(CreditPortfolioLoan.id == loan_id)
    )
    loan = res.scalar_one_or_none()
    if not loan:
        return 0
    if as_of is None:
        as_of = date.today()

    # Delete only auto-generated rows for this loan
    await db.execute(
        delete(LoanRepayment).where(
            LoanRepayment.loan_id == loan_id,
            LoanRepayment.is_custom_schedule.is_(False),
        )
    )

    rows = generate_schedule_for_loan(loan, as_of)
    if not rows:
        await db.commit()
        return 0

    db.add_all([LoanRepayment(**r) for r in rows])
    await db.commit()
    return len(rows)


async def seed_schedules_for_all_loans(
    db: AsyncSession, as_of: Optional[date] = None
) -> int:
    """Seed auto-generated schedules for all loans that don't have any yet.

    Used by runtime_migrations during pack install. Doesn't touch loans
    that already have rows in loan_repayments (assumes those are intentional).
    """
    if as_of is None:
        as_of = date.today()
    # Find loans with no repayment rows
    res = await db.execute(
        select(CreditPortfolioLoan).where(
            CreditPortfolioLoan.deleted_at.is_(None),
            CreditPortfolioLoan.date_get.isnot(None),
            CreditPortfolioLoan.date_due.isnot(None),
            CreditPortfolioLoan.debt_usd.isnot(None),
        )
    )
    loans = res.scalars().all()
    inserted = 0
    for loan in loans:
        # Check if any repayment rows exist for this loan
        existing = await db.execute(
            select(LoanRepayment.id).where(LoanRepayment.loan_id == loan.id).limit(1)
        )
        if existing.first() is not None:
            continue
        rows = generate_schedule_for_loan(loan, as_of)
        if rows:
            db.add_all([LoanRepayment(**r) for r in rows])
            inserted += len(rows)
    await db.commit()
    return inserted
