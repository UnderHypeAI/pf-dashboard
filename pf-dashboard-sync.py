#!/usr/bin/env python3
"""
Personal Finance Dashboard v2 — Sync Script
Reads data from Google Sheets via exported JSON files, fetches live BTC price,
and exports data.json for the dashboard.

Google Sheet: 1yK2hBwfF4RcAxInxHaGvPJixy-BzdFcTqTzm0F_nKi8
v2 Tabs: Assets, Income Assets, Business Income, Transactions, Monthly Summary, Forecast, Config

Usage (called by Computer with sheet data pre-fetched):
  python3 pf-dashboard-sync.py [--data-dir <path>]

The script reads JSON files from the data directory (default: /tmp/pf-sync-data/):
  - assets.json, income_assets.json, business_income.json,
    transactions.json, monthly_summary.json, forecast.json, config.json
Each file contains a JSON array of arrays (raw sheet values including headers).
"""

import json
import os
import sys
from datetime import datetime, timezone

SHEET_ID = "1yK2hBwfF4RcAxInxHaGvPJixy-BzdFcTqTzm0F_nKi8"
OUTPUT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pf-dashboard", "data.json")
DATA_DIR = "/tmp/pf-sync-data"

# ─── Helpers ───

def parse_float(val):
    """Safely parse a value to float."""
    if val is None or val == "" or val == "—":
        return 0.0
    try:
        if isinstance(val, str):
            val = val.replace("$", "").replace(",", "").replace("%", "").strip()
        return float(val)
    except (ValueError, TypeError):
        return 0.0


def safe_str(val):
    """Safely convert a value to string."""
    if val is None:
        return ""
    return str(val).strip()


def load_sheet_data(filename):
    """Load a pre-fetched sheet JSON file."""
    path = os.path.join(DATA_DIR, filename)
    try:
        with open(path) as f:
            data = json.load(f)
        # Skip header row (first element)
        return data[1:] if len(data) > 1 else []
    except FileNotFoundError:
        print(f"  [warn] {filename} not found, skipping")
        return []
    except Exception as e:
        print(f"  [warn] Error loading {filename}: {e}")
        return []


def fetch_btc_price():
    """Get BTC price from CoinGecko."""
    try:
        import urllib.request
        url = "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd"
        req = urllib.request.Request(url, headers={"User-Agent": "PF-Dashboard/2.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
            return data.get("bitcoin", {}).get("usd", 0)
    except Exception as e:
        print(f"  [warn] BTC price fetch failed: {e}")
        return 0


# ─── Main Sync ───

def sync():
    print("═══ Personal Finance Dashboard v2 Sync ═══")
    print(f"  Sheet: {SHEET_ID}")
    print(f"  Output: {OUTPUT_PATH}")
    print(f"  Data dir: {DATA_DIR}")
    print()

    # 1. Fetch BTC price
    print("  Fetching BTC price...")
    btc_price = fetch_btc_price()
    if btc_price > 0:
        print(f"  BTC = ${btc_price:,.0f}")
    else:
        print("  BTC price unavailable, BTC values will show as $0")

    # 2. Read Assets tab
    print("  Processing Assets...")
    assets_raw = load_sheet_data("assets.json")
    assets_detail = []
    by_category = {}
    total_btc_units = 0

    for row in assets_raw:
        if len(row) < 3:
            continue
        asset = safe_str(row[0]) if len(row) > 0 else ""
        category = safe_str(row[1]) if len(row) > 1 else ""
        institution = safe_str(row[2]) if len(row) > 2 else ""
        ticker = safe_str(row[3]) if len(row) > 3 else ""
        units = parse_float(row[4]) if len(row) > 4 else 0
        unit_price = parse_float(row[5]) if len(row) > 5 else 0
        value_usd = parse_float(row[6]) if len(row) > 6 else 0
        currency = safe_str(row[7]) if len(row) > 7 else "USD"

        if not asset:
            continue

        # For BTC assets, calculate USD value from units * btc_price
        if currency == "BTC" and btc_price > 0:
            usd_value = units * btc_price
            total_btc_units += units
        else:
            usd_value = value_usd
            # If units and unit_price provided and value is 0, calculate
            if usd_value == 0 and units > 0 and unit_price > 0:
                usd_value = units * unit_price

        assets_detail.append({
            "asset": asset,
            "category": category,
            "institution": institution,
            "ticker": ticker,
            "units": units,
            "unit_price": unit_price if currency != "BTC" else btc_price,
            "value": round(usd_value, 2),
            "currency": currency,
        })

        by_category[category] = by_category.get(category, 0) + usd_value

    total_net_worth = sum(by_category.values())
    print(f"  Assets: {len(assets_detail)} | NW: ${total_net_worth:,.0f} | BTC: {total_btc_units:.4f}")

    # 3. Read Income Assets tab
    print("  Processing Income Assets...")
    income_raw = load_sheet_data("income_assets.json")
    income_fixed = []
    income_variable = []
    total_fixed_annual = 0
    total_variable_annual = 0

    for row in income_raw:
        if len(row) < 3:
            continue
        asset = safe_str(row[0]) if len(row) > 0 else ""
        income_type = safe_str(row[1]) if len(row) > 1 else ""
        institution = safe_str(row[2]) if len(row) > 2 else ""
        ticker = safe_str(row[3]) if len(row) > 3 else ""
        value = parse_float(row[4]) if len(row) > 4 else 0
        annual_yield = parse_float(row[5]) if len(row) > 5 else 0
        annual_income = parse_float(row[6]) if len(row) > 6 else 0
        monthly_income = parse_float(row[7]) if len(row) > 7 else 0

        if not asset:
            continue

        # If annual income is 0 but yield and value are set, calculate
        if annual_income == 0 and value > 0 and annual_yield > 0:
            annual_income = value * (annual_yield / 100)
            monthly_income = annual_income / 12

        entry = {
            "asset": asset,
            "institution": institution,
            "ticker": ticker,
            "value": round(value, 2),
            "yield": round(annual_yield, 2),
            "annual": round(annual_income, 2),
            "monthly": round(monthly_income, 2),
        }

        if income_type.lower().startswith("fixed"):
            income_fixed.append(entry)
            total_fixed_annual += annual_income
        else:
            income_variable.append(entry)
            total_variable_annual += annual_income

    print(f"  Fixed: {len(income_fixed)} (${total_fixed_annual:,.0f}/yr) | Variable: {len(income_variable)} (${total_variable_annual:,.0f}/yr)")

    # 4. Read Business Income tab
    print("  Processing Business Income...")
    biz_raw = load_sheet_data("business_income.json")
    by_business = {}
    total_biz_revenue = 0
    total_biz_expenses = 0
    total_biz_net = 0

    # Filter to current month for the summary view
    current_month = datetime.now().strftime("%Y-%m")

    for row in biz_raw:
        if len(row) < 4:
            continue
        month = safe_str(row[0]) if len(row) > 0 else ""
        business = safe_str(row[1]) if len(row) > 1 else ""
        rev_type = safe_str(row[2]) if len(row) > 2 else ""
        revenue = parse_float(row[3]) if len(row) > 3 else 0
        expenses = parse_float(row[4]) if len(row) > 4 else 0
        net = parse_float(row[5]) if len(row) > 5 else 0

        if not business:
            continue

        # Auto-calculate net if not provided
        if net == 0 and (revenue > 0 or expenses > 0):
            net = revenue - expenses

        # Only include current month in summary
        if month == current_month or not month:
            if business not in by_business:
                by_business[business] = {"revenue": 0, "expenses": 0, "net": 0, "types": {}}

            by_business[business]["revenue"] += revenue
            by_business[business]["expenses"] += expenses
            by_business[business]["net"] += net

            if rev_type not in by_business[business]["types"]:
                by_business[business]["types"][rev_type] = {"revenue": 0, "expenses": 0, "net": 0}
            by_business[business]["types"][rev_type]["revenue"] += revenue
            by_business[business]["types"][rev_type]["expenses"] += expenses
            by_business[business]["types"][rev_type]["net"] += net

            total_biz_revenue += revenue
            total_biz_expenses += expenses
            total_biz_net += net

    print(f"  Businesses: {len(by_business)} | Net: ${total_biz_net:,.0f}/mo")

    # 5. Read Transactions tab
    print("  Processing Transactions...")
    tx_raw = load_sheet_data("transactions.json")
    recent_transactions = []
    month_income = 0
    month_expenses = 0

    for row in tx_raw:
        if len(row) < 5:
            continue
        date_str = safe_str(row[0]) if len(row) > 0 else ""
        account = safe_str(row[1]) if len(row) > 1 else ""
        category = safe_str(row[2]) if len(row) > 2 else ""
        description = safe_str(row[3]) if len(row) > 3 else ""
        amount = parse_float(row[4]) if len(row) > 4 else 0
        tx_type = safe_str(row[5]).lower() if len(row) > 5 else "expense"

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

        if date_str.startswith(current_month):
            if tx_type == "income":
                month_income += amount
            else:
                month_expenses += abs(amount)

    recent_transactions.sort(key=lambda x: x["date"], reverse=True)
    net_cf = month_income - month_expenses
    savings_rate = (net_cf / month_income * 100) if month_income > 0 else 0

    print(f"  Transactions: {len(recent_transactions)} | This month: +${month_income:,.0f} / -${month_expenses:,.0f}")

    # 6. Read Monthly Summary tab
    print("  Processing Monthly Summary...")
    monthly_raw = load_sheet_data("monthly_summary.json")
    # Headers: Month, Total Assets, Total Income (Asset), Total Income (Business), Total Income, Total Expenses, Net Cash Flow, Savings Rate %, Fixed Income, Variable Income
    trend_months = []
    trend_income = []
    trend_expenses = []
    trend_net = []
    trend_nw = []

    for row in monthly_raw:
        if len(row) < 4:
            continue
        month = safe_str(row[0])
        total_assets = parse_float(row[1]) if len(row) > 1 else 0
        total_income = parse_float(row[4]) if len(row) > 4 else 0
        total_exp = parse_float(row[5]) if len(row) > 5 else 0
        net_cf_m = parse_float(row[6]) if len(row) > 6 else 0

        if not month:
            continue

        trend_months.append(month)
        trend_income.append(total_income)
        trend_expenses.append(total_exp)
        trend_net.append(net_cf_m)
        trend_nw.append(total_assets)

    print(f"  Monthly history: {len(trend_months)} months")

    # 7. Read Forecast tab
    print("  Processing Forecast...")
    forecast_raw = load_sheet_data("forecast.json")
    fc_months = []
    fc_income = []
    fc_expenses = []
    fc_nw = []

    for row in forecast_raw:
        if len(row) < 4:
            continue
        month = safe_str(row[0])
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

    # 8. Read Config
    print("  Processing Config...")
    config_raw = load_sheet_data("config.json")
    emergency_target = 10000
    savings_goal = 2000

    for row in config_raw:
        if len(row) < 2:
            continue
        setting = safe_str(row[0])
        value = safe_str(row[1])

        if setting == "Emergency Fund Target":
            emergency_target = parse_float(value)
        elif setting == "Monthly Savings Goal":
            savings_goal = parse_float(value)

    # Determine emergency fund current (total cash)
    cash_total = by_category.get("Cash & Banking", 0)

    # 9. Build output
    output = {
        "_meta": {
            "last_synced": datetime.now(timezone.utc).isoformat(),
            "sheet_id": SHEET_ID,
            "version": 2
        },
        "btc_price": btc_price,
        "assets": {
            "total_net_worth": round(total_net_worth, 2),
            "total_btc_units": round(total_btc_units, 8),
            "by_category": {k: round(v, 2) for k, v in by_category.items()},
            "detail": assets_detail
        },
        "income_assets": {
            "fixed": income_fixed,
            "variable": income_variable,
            "total_fixed_annual": round(total_fixed_annual, 2),
            "total_variable_annual": round(total_variable_annual, 2)
        },
        "business_income": {
            "by_business": {k: {
                "revenue": round(v["revenue"], 2),
                "expenses": round(v["expenses"], 2),
                "net": round(v["net"], 2),
                "types": {tk: {kk: round(vv, 2) for kk, vv in tv.items()} for tk, tv in v["types"].items()}
            } for k, v in by_business.items()},
            "total_monthly_revenue": round(total_biz_revenue, 2),
            "total_monthly_expenses": round(total_biz_expenses, 2),
            "total_monthly_net": round(total_biz_net, 2)
        },
        "cashflow": {
            "income": round(month_income, 2),
            "expenses": round(month_expenses, 2),
            "net": round(net_cf, 2),
            "savings_rate": round(savings_rate, 1),
            "recent_transactions": recent_transactions[:20]
        },
        "trends": {
            "months": trend_months,
            "income": trend_income,
            "expenses": trend_expenses,
            "net": trend_net,
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
            "emergency_fund_current": round(cash_total, 2),
            "monthly_savings_goal": savings_goal,
            "monthly_savings_actual": round(net_cf, 2)
        }
    }

    # Also build the master dashboard summary
    master_pf = {
        "status": "live",
        "net_worth": round(total_net_worth, 2),
        "total_assets": round(total_net_worth, 2),
        "total_btc_units": round(total_btc_units, 8),
        "btc_usd": round(total_btc_units * btc_price, 2),
        "total_fixed_annual": round(total_fixed_annual, 2),
        "total_variable_annual": round(total_variable_annual, 2),
        "total_asset_income_annual": round(total_fixed_annual + total_variable_annual, 2),
        "total_biz_income_monthly": round(total_biz_net, 2),
        "cashflow_net": round(net_cf, 2),
        "cashflow_income": round(month_income, 2),
        "cashflow_expenses": round(month_expenses, 2),
        "savings_rate": round(savings_rate, 1),
        "by_category": {k: round(v, 2) for k, v in by_category.items()},
    }

    # Write output
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w") as f:
        json.dump(output, f, indent=2)

    # Write master dashboard PF summary
    master_path = os.path.join(os.path.dirname(OUTPUT_PATH), "..", "master-dashboard-pf.json")
    with open(os.path.abspath(master_path), "w") as f:
        json.dump(master_pf, f, indent=2)

    print()
    print(f"  ✓ data.json written to {OUTPUT_PATH}")
    print(f"  ✓ Net Worth: ${total_net_worth:,.0f}")
    print(f"  ✓ BTC: {total_btc_units:.8f} BTC (${total_btc_units * btc_price:,.0f})")
    print(f"  ✓ Fixed Income: ${total_fixed_annual:,.0f}/yr | Variable: ${total_variable_annual:,.0f}/yr")
    print(f"  ✓ Business Income: ${total_biz_net:,.0f}/mo")
    print(f"  ✓ Cash Flow: +${month_income:,.0f} / -${month_expenses:,.0f} = ${net_cf:,.0f}")
    print("═══ Sync Complete ═══")

    return output, master_pf


if __name__ == "__main__":
    # Parse optional --data-dir argument
    if "--data-dir" in sys.argv:
        idx = sys.argv.index("--data-dir")
        if idx + 1 < len(sys.argv):
            DATA_DIR = sys.argv[idx + 1]

    sync()
