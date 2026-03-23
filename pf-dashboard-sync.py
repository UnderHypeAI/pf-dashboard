#!/usr/bin/env python3
"""
Personal Finance Dashboard — Sync Script
Reads data from Google Sheets, fetches live BTC price,
and exports data.json for the dashboard.

Google Sheet: 1yK2hBwfF4RcAxInxHaGvPJixy-BzdFcTqTzm0F_nKi8
Tabs: Accounts, Transactions, Income, Monthly Summary, Forecast, Config
"""

import json
import os
import subprocess
import sys
from datetime import datetime, timezone

SHEET_ID = "1yK2hBwfF4RcAxInxHaGvPJixy-BzdFcTqTzm0F_nKi8"
OUTPUT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pf-dashboard", "data.json")

# ─── Helpers ───

def gws_read(sheet_range):
    """Read a range from Google Sheets using gws CLI."""
    cmd = [
        "gws", "sheets", "spreadsheets", "values", "get",
        "--params", json.dumps({
            "spreadsheetId": SHEET_ID,
            "range": sheet_range,
            "valueRenderOption": "UNFORMATTED_VALUE"
        }),
        "--format", "json"
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            print(f"  [warn] gws error for {sheet_range}: {result.stderr.strip()}")
            return []
        data = json.loads(result.stdout)
        return data.get("values", [])
    except Exception as e:
        print(f"  [warn] Failed to read {sheet_range}: {e}")
        return []


def fetch_btc_price():
    """Get BTC price from CoinGecko."""
    try:
        import urllib.request
        url = "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd"
        req = urllib.request.Request(url, headers={"User-Agent": "PF-Dashboard/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
            return data.get("bitcoin", {}).get("usd", 0)
    except Exception as e:
        print(f"  [warn] BTC price fetch failed: {e}")
        return 0


def parse_float(val):
    """Safely parse a value to float."""
    if val is None or val == "" or val == "—":
        return 0.0
    try:
        if isinstance(val, str):
            val = val.replace("$", "").replace(",", "").strip()
        return float(val)
    except (ValueError, TypeError):
        return 0.0


# ─── Main Sync ───

def sync():
    print("═══ Personal Finance Dashboard Sync ═══")
    print(f"  Sheet: {SHEET_ID}")
    print(f"  Output: {OUTPUT_PATH}")
    print()

    # 1. Fetch BTC price
    print("  Fetching BTC price...")
    btc_price = fetch_btc_price()
    print(f"  BTC = ${btc_price:,.0f}")

    # 2. Read Accounts tab
    print("  Reading Accounts...")
    accounts_raw = gws_read("Accounts!A2:H100")
    accounts_detail = []
    total_cash = 0
    total_investments = 0
    total_btc_btc = 0
    total_crypto_other = 0

    for row in accounts_raw:
        if len(row) < 5:
            continue
        account = str(row[0]) if len(row) > 0 else ""
        institution = str(row[1]) if len(row) > 1 else ""
        acct_type = str(row[2]) if len(row) > 2 else ""
        category = str(row[3]) if len(row) > 3 else ""
        balance = parse_float(row[4]) if len(row) > 4 else 0
        currency = str(row[5]) if len(row) > 5 else "USD"
        last_updated = str(row[6]) if len(row) > 6 else ""
        notes = str(row[7]) if len(row) > 7 else ""

        if not account:
            continue

        accounts_detail.append({
            "account": account,
            "institution": institution,
            "type": acct_type,
            "category": category,
            "balance": balance,
            "currency": currency,
            "last_updated": last_updated,
            "notes": notes
        })

        # Aggregate by category
        if category == "Cash":
            total_cash += balance  # Already USD
        elif category == "Investments":
            total_investments += balance
        elif category == "Bitcoin":
            if currency == "BTC":
                total_btc_btc += balance
            else:
                total_btc_btc += balance / btc_price if btc_price > 0 else 0
        elif category == "Crypto":
            total_crypto_other += balance

    total_btc_usd = total_btc_btc * btc_price
    total_net_worth = total_cash + total_investments + total_btc_usd + total_crypto_other

    print(f"  Accounts: {len(accounts_detail)} | Net Worth: ${total_net_worth:,.0f}")

    # 3. Read Transactions tab
    print("  Reading Transactions...")
    tx_raw = gws_read("Transactions!A2:H1000")
    recent_transactions = []
    expense_by_cat = {}
    month_income = 0
    month_expenses = 0

    now = datetime.now()
    current_month_str = now.strftime("%Y-%m")

    for row in tx_raw:
        if len(row) < 5:
            continue
        date_str = str(row[0]) if len(row) > 0 else ""
        account = str(row[1]) if len(row) > 1 else ""
        category = str(row[2]) if len(row) > 2 else ""
        description = str(row[3]) if len(row) > 3 else ""
        amount = parse_float(row[4]) if len(row) > 4 else 0
        tx_type = str(row[5]).lower() if len(row) > 5 else "expense"
        tags = str(row[6]) if len(row) > 6 else ""
        notes = str(row[7]) if len(row) > 7 else ""

        if not date_str:
            continue

        recent_transactions.append({
            "date": date_str,
            "account": account,
            "category": category,
            "description": description,
            "amount": amount,
            "type": tx_type,
        })

        # Current month aggregation
        if date_str.startswith(current_month_str):
            if tx_type == "income":
                month_income += amount
            else:
                month_expenses += abs(amount)
                expense_by_cat[category] = expense_by_cat.get(category, 0) + abs(amount)

    # Sort transactions by date descending
    recent_transactions.sort(key=lambda x: x["date"], reverse=True)

    net_cf = month_income - month_expenses
    savings_rate = (net_cf / month_income * 100) if month_income > 0 else 0

    print(f"  Transactions: {len(recent_transactions)} | This month: +${month_income:,.0f} / -${month_expenses:,.0f}")

    # 4. Read Income tab
    print("  Reading Income...")
    income_raw = gws_read("Income!A2:G500")
    income_by_source = {}
    ytd_income = 0
    recurring_monthly = 0

    for row in income_raw:
        if len(row) < 4:
            continue
        date_str = str(row[0]) if len(row) > 0 else ""
        source = str(row[1]) if len(row) > 1 else ""
        category = str(row[2]) if len(row) > 2 else ""
        amount = parse_float(row[3]) if len(row) > 3 else 0
        recurring = str(row[4]).lower() if len(row) > 4 else "no"
        frequency = str(row[5]) if len(row) > 5 else ""

        if not date_str or not source:
            continue

        # YTD
        if date_str.startswith(str(now.year)):
            ytd_income += amount

        # By source (all time)
        income_by_source[source] = income_by_source.get(source, 0) + amount

        # Recurring monthly estimate
        if recurring in ("yes", "true", "1"):
            if frequency.lower() in ("monthly", "month"):
                recurring_monthly += amount
            elif frequency.lower() in ("weekly", "week"):
                recurring_monthly += amount * 4.33
            elif frequency.lower() in ("biweekly", "bi-weekly"):
                recurring_monthly += amount * 2.17

    print(f"  Income sources: {len(income_by_source)} | YTD: ${ytd_income:,.0f}")

    # 5. Read Monthly Summary tab
    print("  Reading Monthly Summary...")
    monthly_raw = gws_read("'Monthly Summary'!A2:J100")
    trend_months = []
    trend_income = []
    trend_expenses = []
    trend_net = []
    trend_nw = []

    for row in monthly_raw:
        if len(row) < 4:
            continue
        month = str(row[0]) if len(row) > 0 else ""
        m_income = parse_float(row[1]) if len(row) > 1 else 0
        m_expenses = parse_float(row[2]) if len(row) > 2 else 0
        m_net = parse_float(row[3]) if len(row) > 3 else 0
        m_nw = parse_float(row[5]) if len(row) > 5 else 0

        if not month:
            continue

        trend_months.append(month)
        trend_income.append(m_income)
        trend_expenses.append(m_expenses)
        trend_net.append(m_net)
        trend_nw.append(m_nw)

    print(f"  Monthly history: {len(trend_months)} months")

    # 6. Read Forecast tab
    print("  Reading Forecast...")
    forecast_raw = gws_read("Forecast!A2:F20")
    fc_months = []
    fc_income = []
    fc_expenses = []
    fc_nw = []

    for row in forecast_raw:
        if len(row) < 4:
            continue
        month = str(row[0]) if len(row) > 0 else ""
        p_income = parse_float(row[1]) if len(row) > 1 else 0
        p_expenses = parse_float(row[2]) if len(row) > 2 else 0
        p_nw = parse_float(row[4]) if len(row) > 4 else 0

        if not month:
            continue

        fc_months.append(month)
        fc_income.append(p_income)
        fc_expenses.append(p_expenses)
        fc_nw.append(p_nw)

    print(f"  Forecast months: {len(fc_months)}")

    # 7. Read Config for goals
    print("  Reading Config...")
    config_raw = gws_read("Config!A2:C20")
    emergency_target = 10000
    savings_goal = 2000

    for row in config_raw:
        if len(row) < 2:
            continue
        setting = str(row[0]).strip()
        value = str(row[1]).strip()

        if setting == "Emergency Fund Target":
            emergency_target = parse_float(value)
        elif setting == "Monthly Savings Goal":
            savings_goal = parse_float(value)

    # 8. Build output
    output = {
        "_meta": {
            "last_synced": datetime.now(timezone.utc).isoformat(),
            "sheet_id": SHEET_ID
        },
        "btc_price": btc_price,
        "accounts": {
            "summary": {
                "total_net_worth": round(total_net_worth, 2),
                "total_cash": round(total_cash, 2),
                "total_investments": round(total_investments, 2),
                "total_bitcoin_usd": round(total_btc_usd, 2),
                "total_bitcoin_btc": round(total_btc_btc, 8),
                "total_crypto_other": round(total_crypto_other, 2)
            },
            "detail": accounts_detail
        },
        "cashflow": {
            "current_month": {
                "income": round(month_income, 2),
                "expenses": round(month_expenses, 2),
                "net": round(net_cf, 2),
                "savings_rate": round(savings_rate, 1)
            },
            "by_category": {k: round(v, 2) for k, v in sorted(expense_by_cat.items(), key=lambda x: -x[1])},
            "recent_transactions": recent_transactions[:20]
        },
        "income": {
            "current_month": round(month_income, 2),
            "ytd": round(ytd_income, 2),
            "by_source": {k: round(v, 2) for k, v in sorted(income_by_source.items(), key=lambda x: -x[1])},
            "recurring_monthly": round(recurring_monthly, 2)
        },
        "trends": {
            "months": trend_months,
            "income": trend_income,
            "expenses": trend_expenses,
            "net_cash_flow": trend_net,
            "net_worth": trend_nw
        },
        "forecast": {
            "months": fc_months,
            "projected_income": fc_income,
            "projected_expenses": fc_expenses,
            "projected_net_worth": fc_nw
        },
        "goals": {
            "emergency_fund_target": emergency_target,
            "emergency_fund_current": total_cash,
            "monthly_savings_goal": savings_goal,
            "monthly_savings_actual": round(net_cf, 2)
        }
    }

    # Write output
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w") as f:
        json.dump(output, f, indent=2)

    print()
    print(f"  ✓ data.json written to {OUTPUT_PATH}")
    print(f"  ✓ Net Worth: ${total_net_worth:,.0f}")
    print(f"  ✓ BTC: {total_btc_btc:.8f} BTC (${total_btc_usd:,.0f})")
    print(f"  ✓ Cash Flow: +${month_income:,.0f} / -${month_expenses:,.0f} = ${net_cf:,.0f}")
    print("═══ Sync Complete ═══")


if __name__ == "__main__":
    sync()
