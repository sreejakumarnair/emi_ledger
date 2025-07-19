import csv
from datetime import datetime
from dateutil.relativedelta import relativedelta

DATE_FMT = "%d-%m-%y"

class LedgerEvent:
    def __init__(self, date, type_, amount):
        self.date = date
        self.type = type_
        self.amount = amount

class OverdraftLedger:
    def __init__(self, principal, annual_rate, tenure_years, disbursement_date, test_mode=False, ui_mode=False):
        self.test_mode = test_mode
        self.ui_mode = ui_mode

        if not isinstance(principal, (int, float)) or principal <= 0:
            raise ValueError("Loan principal must be a positive number.")
        if not isinstance(annual_rate, (int, float)) or annual_rate <= 0:
            raise ValueError("Interest rate must be a positive number.")
        if not isinstance(tenure_years, (int, float)) or tenure_years <= 0:
            raise ValueError("Tenure must be a positive number of years.")

        self.principal = principal
        self.outstanding = principal
        self.deposit_balance = 0
        self.rate_day = annual_rate / 365 / 100
        self.tenure_months = int(tenure_years * 12)
        self.disbursement_date = disbursement_date
        self.emi = self.compute_emi(annual_rate, tenure_years)
        self.events = []
        self.ledger = []
        self.loan_closure_flag = False
        self.entry_log = []

    def compute_emi(self, annual_rate, tenure_years):
        r = annual_rate / 100
        n = tenure_years
        if r <= 0 or n <= 0:
            raise ValueError("Cannot compute EMI with zero or negative interest rate or tenure.")
        p = self.principal
        denominator = (1 + r)**n - 1
        if denominator == 0:
            raise ValueError("Invalid EMI denominator calculation.")
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

    def get_additional_events(self):
        if self.test_mode or self.ui_mode:
            print("🎯 UI/Test Mode: Suppressing additional input prompts.")
            return

        print("\n📥 Enter more entries or type 'esc' to skip:")
        for ev_type in ["Deposit", "Pre-Pay", "Withdraw"]:
            while True:
                response = input(f"Any {ev_type}s? (y/n or esc): ").strip().lower()
                if response == "esc":
                    return
                elif response == "y":
                    count = int(input(f"How many {ev_type}s? "))
                    for i in range(count):
                        ev_date = datetime.strptime(input(f"Enter {ev_type} {i+1} date (dd-mm-yy): "), DATE_FMT)
                        ev_amt = float(input(f"Enter {ev_type} {i+1} amount: "))
                        self.add_event(ev_date, ev_type, ev_amt)
                    break
                elif response == "n":
                    break
                else:
                    print("⚠️ Please enter 'y', 'n', or 'esc'.")

    def process(self):
        self.events.append(LedgerEvent(self.disbursement_date, "Start", 0))

        # EMI starts one month after disbursement
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
                print(f"\n💡 Adjusted principal reached zero on {ev.date.strftime('%d-%m-%Y')}.")
                print("👉 Would you like to act now?")
                self.get_additional_events()
                self.events.sort(key=lambda x: x.date)

            if self.outstanding <= 0 and not self.loan_closure_flag:
                self.loan_closure_flag = True
                print(f"\n🎉 Loan fully repaid by {ev.date.strftime('%d-%m-%Y')}")
                print("✅ All future EMIs will be zero.")

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

    def display(self):
        for row in self.ledger:
            print(row)

    def export_csv(self, filename="loan_ledger.csv"):
        with open(filename, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=self.ledger[0].keys())
            writer.writeheader()
            writer.writerows(self.ledger)