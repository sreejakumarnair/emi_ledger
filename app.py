import streamlit as st
from datetime import datetime
import pandas as pd
from ledger_copilot import OverdraftLedger, DATE_FMT
from io import BytesIO
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

st.set_page_config(page_title="EMI Ledger", layout="centered")
st.title("📘 Overdraft EMI Ledger")

# --- Session State ---
if "event_log" not in st.session_state:
    st.session_state.event_log = []
if "ledger_df" not in st.session_state:
    st.session_state.ledger_df = pd.DataFrame()
if "emi" not in st.session_state:
    st.session_state.emi = None
if "zero_date" not in st.session_state:
    st.session_state.zero_date = None
if "custom_emi" not in st.session_state:
    st.session_state.custom_emi = None

# --- Helpers ---
def convert_amount(value, unit):
    multiplier = {"K": 1_000, "L": 1_00_000, "Cr": 1_00_00_000}
    return value * multiplier.get(unit, 1)

def format_short(value):
    if value >= 1_00_00_000:
        return f"\u20B9{value/1_00_00_000:.2f} Cr"
    elif value >= 1_00_000:
        return f"\u20B9{value/1_00_000:.2f} L"
    elif value >= 1_000:
        return f"\u20B9{value/1_000:.2f} K"
    else:
        return f"\u20B9{value:.2f}"

# --- Loan Input ---
st.subheader("📥 Loan Details")
col1, col2, col3 = st.columns(3)
cr = col1.number_input("Crores", min_value=0, value=0)
l = col2.number_input("Lakhs", min_value=0, max_value=99, value=0)
k = col3.number_input("Thousands", min_value=0, max_value=999, value=0)
principal = cr * 1_00_00_000 + l * 1_00_000 + k * 1_000
st.write(f"Constructed Principal: {format_short(principal)}")

rate = st.number_input("Interest Rate (%)", min_value=0.1, value=8.5, step=0.1)
tenure = st.number_input("Tenure (Years)", min_value=1, value=10)
disburse_date = st.date_input("Disbursement Date", value=datetime.today())

# --- Event Entry ---
with st.expander("➕ Add Optional Event"):
    with st.form("event_form"):
        ev_type = st.selectbox("Type", ["Deposit", "Pre-Pay", "Withdraw"])
        ev_date = st.date_input("Event Date", value=datetime.today())
        col1, col2 = st.columns(2)
        ev_val = col1.number_input("Amount", min_value=0.0, value=10.0)
        ev_unit = col2.selectbox("Unit", ["K", "L", "Cr"])
        ev_amt = convert_amount(ev_val, ev_unit)
        st.write(f"Event Amount: {format_short(ev_amt)}")
        ev_submit = st.form_submit_button("Add Event")

    if ev_submit:
        if ev_amt > 0:
            st.session_state.event_log.append({
                "type": ev_type,
                "date": ev_date.strftime(DATE_FMT),
                "amount": ev_amt
            })
            st.success(f"{ev_type} of {format_short(ev_amt)} added.")
        else:
            st.warning("Amount must be positive.")

# --- Event Log with Per-Entry Delete ---
if st.session_state.event_log:
    st.subheader("🗓️ Event Log")
    for i, ev in enumerate(st.session_state.event_log):
        col1, col2 = st.columns([8, 1])
        col1.write(f"{ev['date']} | {ev['type']} {format_short(ev['amount'])}")
        if col2.button(f"❌", key=f"del_{i}"):
            st.session_state.event_log.pop(i)
            st.rerun()

# --- Calculate EMI First ---
disburse_str = disburse_date.strftime(DATE_FMT)
temp_ledger = OverdraftLedger(
    principal, rate, tenure,
    datetime.strptime(disburse_str, DATE_FMT),
    ui_mode=True
)
emi_calc = temp_ledger.compute_emi(rate, tenure)
st.session_state.emi = emi_calc

# --- Allow EMI Override Before Simulation ---
st.subheader("📈 EMI Configuration")
st.session_state.custom_emi = st.number_input(
    "Monthly EMI (Optional Override)",
    min_value=emi_calc,
    value=emi_calc,
    step=100.0,
    help="Enter a custom EMI if you wish to pay more than the calculated minimum"
)

# --- Run Simulation ---
if st.button("▶️ Simulate Ledger"):
    ledger = OverdraftLedger(
        principal, rate, tenure,
        datetime.strptime(disburse_str, DATE_FMT),
        custom_emi=st.session_state.custom_emi,
        ui_mode=True
    )

    for e in st.session_state.event_log:
        ledger.add_event(datetime.strptime(e["date"], DATE_FMT), e["type"], e["amount"])

    ledger.process()
    df = ledger.get_dataframe()
    closure_date = ledger.get_closure_date()

    st.session_state.ledger_df = df
    st.session_state.zero_date = closure_date
# --- Display Result ---
if not st.session_state.ledger_df.empty:
    st.subheader("📊 Simulation Result")

    final_emi = st.session_state.custom_emi or st.session_state.emi

    if st.session_state.custom_emi and st.session_state.custom_emi > st.session_state.emi:
        st.info(
            f"Custom EMI used: {format_short(final_emi)} "
            f"(Min required: {format_short(st.session_state.emi)})"
        )
    else:
        st.success(f"Monthly EMI: {format_short(st.session_state.emi)}")

    if st.session_state.zero_date:
        st.warning(
            f"💡 Adjusted principal reached zero on {st.session_state.zero_date}. "
            f"You may consider closing or withdrawing."
        )

    st.dataframe(st.session_state.ledger_df, use_container_width=True)

    # --- CSV Download ---
    csv = st.session_state.ledger_df.to_csv(index=False).encode("utf-8")
    st.download_button("📥 Download CSV", data=csv, file_name="loan_ledger.csv", mime="text/csv")

    # --- PDF Generation ---
    def generate_pdf(df, final_emi):
        buffer = BytesIO()
        c = canvas.Canvas(buffer, pagesize=A4)
        width, height = A4
        pdfmetrics.registerFont(TTFont("DejaVu", "fonts/DejaVuSans.ttf"))

        def draw_header(y):
            try:
                c.drawImage("sreeja.png", x=2*cm, y=height - y - 2*cm,
                            width=2*cm, height=2*cm, mask='auto')
            except Exception:
                pass
            c.setFont("DejaVu", 12)
            c.drawString(5*cm, height - y - 0.5*cm, "Powered by Sreejakumar Technologies")
            c.setFont("DejaVu", 16)
            c.drawString(5*cm, height - y - 1.5*cm, "Overdraft EMI Ledger Report")
            c.setFont("DejaVu", 10)
            c.drawString(2*cm, height - y - 3.2*cm, f"Principal: {format_short(principal)}")
            c.drawString(2*cm, height - y - 4.0*cm, f"Rate: {rate}% | Tenure: {tenure} yrs")
            emi_text = (
                f"EMI: {format_short(final_emi)} (Min: {format_short(st.session_state.emi)})"
                if final_emi > st.session_state.emi else
                f"EMI: {format_short(final_emi)}"
            )
            c.drawString(2*cm, height - y - 4.8*cm, emi_text)
            c.drawString(2*cm, height - y - 5.6*cm, f"Disbursement: {disburse_date.strftime(DATE_FMT)}")
            timestamp = datetime.now().strftime("%d-%m-%Y %H:%M")
            c.drawString(2*cm, height - y - 6.4*cm, f"Generated on: {timestamp}")

        def draw_table(df, start_y):
            y = start_y
            headers = ["Date", "Type", "Amount", "Principal", "Interest",
                       "Outstanding", "Deposit", "Adj. Principal"]
            x_positions = [2.0*cm, 4.2*cm, 6.4*cm, 8.6*cm, 10.8*cm, 13.0*cm, 15.2*cm, 17.4*cm]

            box_height = 0.6*cm
            box_center = y

            c.setFillColorRGB(0.9, 0.9, 0.9)
            c.rect(x_positions[0] - 0.2*cm, box_center - box_height/2,
                   width - 3*cm, box_height, fill=1)

            c.setFont("DejaVu", 9)
            c.setFillColorRGB(0, 0, 0)
            for i, h in enumerate(headers):
                c.drawString(x_positions[i], y - 0.2*cm, h)
            y -= box_height + 0.2*cm

            c.setFont("DejaVu", 8)
            for _, row in df.iterrows():
                if y < 2*cm:
                    c.showPage()
                    draw_header(2*cm)
                    y = height - 9*cm

                    box_center = y
                    c.setFillColorRGB(0.9, 0.9, 0.9)
                    c.rect(x_positions[0] - 0.2*cm, box_center - box_height/2,
                           width - 3*cm, box_height, fill=1)
                    c.setFont("DejaVu", 9)
                    c.setFillColorRGB(0, 0, 0)
                    for i, h in enumerate(headers):
                        c.drawString(x_positions[i], y - 0.2*cm, h)
                    y -= box_height + 0.2*cm
                    c.setFont("DejaVu", 8)

                values = [
                    row["Date"], row["Type"], format_short(row["Amount"]),
                    format_short(row["Principal"]), format_short(row["Interest"]),
                    format_short(row["Outstanding Principal"]),
                    format_short(row["Deposit Balance"]),
                    format_short(row["Adjusted Principal"])
                ]
                for i, val in enumerate(values):
                    c.drawString(x_positions[i], y, str(val))
                y -= 0.4*cm
                c.drawRightString(width - 2*cm, 1.5*cm, f"Page {c.getPageNumber()}")

        draw_header(2*cm)
        draw_table(df, height - 9*cm)
        c.setFont("DejaVu", 8)
        c.drawString(2*cm, 1.5*cm, "Generated by EMI Ledger Tool | www.sreejakumar.dev")
        c.save()
        buffer.seek(0)
        return buffer

    pdf_buffer = generate_pdf(st.session_state.ledger_df, final_emi)
    st.download_button("📄 Download PDF Report", data=pdf_buffer,
                       file_name="loan_ledger.pdf", mime="application/pdf")

    # --- Query Section ---
    from ledger_api import query_total

    with st.expander("📊 Query Ledger"):
        qtype = st.selectbox("Query Type", [
            "Loan Closure Date", "Total Interest Paid", "Total Principal Paid",
            "Total Deposits", "Total Withdrawals"
        ])
        col1, col2 = st.columns(2)
        from_date = col1.date_input("From Date", disburse_date)
        to_date = col2.date_input("To Date", datetime.today())

        if st.button("Run Query"):
            from_str = from_date.strftime(DATE_FMT)
            to_str = to_date.strftime(DATE_FMT)

            if qtype == "Loan Closure Date":
                result = st.session_state.zero_date or "Not yet closed"
            else:
                result = query_total(st.session_state.ledger_df, qtype, from_str, to_str)

            st.success(f"Result: {result}")