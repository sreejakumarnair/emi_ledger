from datetime import datetime
from dateutil.relativedelta import relativedelta
import pandas as pd

DATE_FMT = "%d-%m-%y"

class LedgerEvent:
    def __init__(self, date, type_, amount):
        self.date = date
        self.type = type_
        self.amount = amount

class OverdraftLedger:
    def __init__(self, principal, annual_rate, tenure_years, disbursement_date,
                 custom_emi=None, test_mode=False, ui_mode=False):
        self.test_mode = test_mode
        self.ui_mode = ui_mode

        # --- Validation ---
        if not isinstance(principal, (int, float)) or principal <= 0:
            raise ValueError("Loan principal must be a positive number.")
        if not isinstance(annual_rate, (int, float)) or annual_rate <= 0:
            raise ValueError("Interest rate must be a positive number.")
        if not isinstance(tenure_years, (int, float)) or tenure_years <= 0:
            raise ValueError("Tenure must be a positive number.")

        # --- Parameters ---
        self.principal = principal
        self.outstanding = principal
        self.deposit_balance = 0
        self.rate_day = annual_rate / 365 / 100
        self.tenure_months = int(tenure_years * 12)
        self.disbursement_date = disbursement_date
        self.custom_emi = custom_emi
        self.emi = custom_emi or self.compute_emi(annual_rate, tenure_years)

        # --- State ---
        self.events = []
        self.ledger = []
        self.loan_closure_flag = False
        self.entry_log = []

    def compute_emi(self, annual_rate, tenure_years):
        r = annual_rate / 100
        n = tenure_years
        p = self.principal
        denominator = (1 + r)**n - 1
        if denominator == 0:
            raise ValueError("Invalid EMI calculation.")
        yearly_emi = p * r * (1 + r)**n / denominator
        monthly_emi = yearly_emi / 12
        return round(monthly_emi, 2)

    def add_event(self, date, type_, amount):
        self.events.append(LedgerEvent(date, type_, amount))

    def entry(self, date, type_, amount, principal, interest):
        adjusted = max(self.outstanding - self.deposit_balance, 0)
        self.entry_log.append({
            "date": date,
            "type": type_,
            "adjusted": adjusted,
            "outstanding": self.outstanding,
            "deposit_balance": self.deposit_balance
        })
        return {
            "Date": date.strftime("%d-%m-%Y"),
            "Type": type_,
            "Amount": round(amount, 2),
            "Principal": round(principal, 2),
            "Interest": round(interest, 2),
            "Outstanding Principal": round(self.outstanding, 2),
            "Deposit Balance": round(self.deposit_balance, 2),
            "Adjusted Principal": round(adjusted, 2)
        }

    def process(self):
        self.events.append(LedgerEvent(self.disbursement_date, "Start", 0))

        # EMI Schedule
        for i in range(self.tenure_months):
            emi_date = self.disbursement_date + relativedelta(months=i+1)
            self.events.append(LedgerEvent(emi_date, "EMI", self.emi))

        self.events.sort(key=lambda x: x.date)
        prev_date = self.events[0].date
        accrued_interest = 0
        prev_adjusted = max(self.outstanding - self.deposit_balance, 0)

        for ev in self.events:
            days = (ev.date - prev_date).days
            adjusted = max(self.outstanding - self.deposit_balance, 0)
            interest = adjusted * self.rate_day * days
            accrued_interest += interest

            if adjusted <= 0 and prev_adjusted > 0 and not self.loan_closure_flag:
                if self.ui_mode:
                    print(f"💡 Adjusted principal zero on {ev.date.strftime('%d-%m-%Y')}")
                self.loan_closure_flag = True

            if self.outstanding <= 0 and not self.loan_closure_flag:
                self.loan_closure_flag = True
                if self.ui_mode:
                    print(f"🎉 Loan closed on {ev.date.strftime('%d-%m-%Y')}")

            if ev.type == "Deposit":
                self.deposit_balance += ev.amount
                self.ledger.append(self.entry(ev.date, "Deposit", ev.amount, 0, 0))
            elif ev.type == "Withdraw":
                self.deposit_balance -= ev.amount
                self.ledger.append(self.entry(ev.date, "Withdraw", ev.amount, 0, 0))
            elif ev.type == "Pre-Pay":
                self.outstanding -= ev.amount
                self.ledger.append(self.entry(ev.date, "Pre-Pay", ev.amount, ev.amount, 0))
            elif ev.type == "EMI":
                if self.outstanding <= 0:
                    self.ledger.append(self.entry(ev.date, "EMI", 0.00, 0.00, 0.00))
                else:
                    int_part = min(accrued_interest, ev.amount)
                    princ_part = ev.amount - int_part
                    accrued_interest -= int_part
                    self.outstanding -= princ_part
                    self.ledger.append(self.entry(ev.date, "EMI", ev.amount, princ_part, int_part))

            prev_date = ev.date
            prev_adjusted = adjusted

    def get_dataframe(self):
        return pd.DataFrame(self.ledger)

    def get_closure_date(self):
        df = self.get_dataframe()
        zero_row = df[df["Adjusted Principal"] <= 0]
        return zero_row.iloc[0]["Date"] if not zero_row.empty else None