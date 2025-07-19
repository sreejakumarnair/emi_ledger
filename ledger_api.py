from datetime import datetime
import pandas as pd
from ledger_copilot import OverdraftLedger, DATE_FMT

def simulate_ledger(principal, rate, tenure, disburse_date_str, events):
    """Simulate EMI and generate ledger as DataFrame"""
    try:
        disburse_date = datetime.strptime(disburse_date_str, DATE_FMT)
        ledger = OverdraftLedger(principal, rate, tenure, disburse_date, ui_mode=True)

        for ev in events:
            ev_date = datetime.strptime(ev['date'], DATE_FMT)
            ev_type = ev['type']
            ev_amt = float(ev['amount'])
            ledger.add_event(ev_date, ev_type, ev_amt)

        ledger.process()
        df = pd.DataFrame(ledger.ledger)
        return ledger.emi, df
    except Exception as e:
        return str(e), pd.DataFrame()

def get_loan_closure_date(df):
    """Return the first date when outstanding principal hits zero"""
    for _, row in df.iterrows():
        if row["Outstanding Principal"] <= 0:
            return row["Date"]
    return "Loan not yet repaid"

def query_total(df, qtype, start_date_str, end_date_str):
    """Return total interest/principal/deposit/withdrawals over date range"""
    start = datetime.strptime(start_date_str, DATE_FMT)
    end = datetime.strptime(end_date_str, DATE_FMT)

    df["parsed_date"] = pd.to_datetime(df["Date"], format="%d-%m-%Y")
    mask = (df["parsed_date"] >= start) & (df["parsed_date"] <= end)
    subset = df[mask]

    if qtype == "Total Interest Paid":
        return round(subset["Interest"].sum(), 2)
    elif qtype == "Total Principal Paid":
        return round(subset["Principal"].sum(), 2)
    elif qtype == "Total Deposits":
        return round(subset[subset["Type"] == "Deposit"]["Amount"].sum(), 2)
    elif qtype == "Total Withdrawals":
        return round(subset[subset["Type"] == "Withdraw"]["Amount"].sum(), 2)
    else:
        return None