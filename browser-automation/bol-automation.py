import os
import httpx
from datetime import datetime, timedelta
from dotenv import load_dotenv
from pathlib import Path

load_dotenv()

downloads_dir = Path("downloads")
downloads_dir.mkdir(exist_ok=True)

API_BASE = "https://api.bol.com/retailer"
TOKEN_URL = "https://login.bol.com/token"

def get_access_token(client_id, client_secret):
    response = httpx.post(
        TOKEN_URL,
        data={"grant_type": "client_credentials"},
        auth=(client_id, client_secret),
        headers={"Accept": "application/json"},
    )
    response.raise_for_status()
    token = response.json()["access_token"]
    print("🔐 Access token retrieved.")
    return token

def get_last_month_period():
    today = datetime.today()
    # Get the first day of current month, then subtract 1 day to get last day of previous month
    first_day_current_month = today.replace(day=1)
    last_day_previous_month = first_day_current_month - timedelta(days=1)
    # Get the first day of previous month
    first_day_previous_month = last_day_previous_month.replace(day=1)
    
    return (
        first_day_previous_month.strftime("%Y-%m-%d"),
        last_day_previous_month.strftime("%Y-%m-%d"),
    )

def get_month_name_from_date(date_str):
    """Convert date string to month name for filename"""
    try:
        date_obj = datetime.strptime(date_str, "%Y-%m-%d")
        return date_obj.strftime("%B_%Y")  # e.g., "July_2025"
    except:
        return "unknown_month"

def fetch_invoices(token, start_date, end_date):
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.retailer.v10+json",
    }
    url = f"{API_BASE}/invoices?period={start_date}/{end_date}"
    response = httpx.get(url, headers=headers)
    response.raise_for_status()
    return response.json().get("invoiceListItems", [])

def download_specification(token, invoice_id, filename):
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.retailer.v10+openxmlformats-officedocument.spreadsheetml.sheet",
    }
    url = f"{API_BASE}/invoices/{invoice_id}/specification"
    response = httpx.get(url, headers=headers, timeout=60.0)  # 60 second timeout
    response.raise_for_status()
    with open(filename, "wb") as f:
        f.write(response.content)
    print(f"📥 Saved XLSX: {filename}")

def process_account(i):
    username = os.getenv(f"BOL_USERNAME_{i}")
    client_id = os.getenv(f"BOL_CLIENT_ID_{i}")
    client_secret = os.getenv(f"BOL_API_SECRET_{i}")

    if not all([username, client_id, client_secret]):
        print(f"⚠️ Missing credentials for account {i}")
        return

    print(f"\n🚀 Processing account {username}")
    
    try:
        token = get_access_token(client_id, client_secret)
    except Exception as e:
        print(f"❌ Failed to get access token: {e}")
        return

    start_date, end_date = get_last_month_period()
    print(f"📆 Fetching invoices for {start_date} to {end_date}")

    try:
        invoices = fetch_invoices(token, start_date, end_date)
    except Exception as e:
        print(f"❌ Failed to fetch invoices: {e}")
        return

    if not invoices:
        print("⚠️ No invoices found.")
        return

    # Get the month name for the period we're fetching
    period_month_name = get_month_name_from_date(start_date)

    for invoice in invoices:
        invoice_id = invoice["invoiceId"]
        invoice_start_date = invoice.get("startDate", "")
        invoice_end_date = invoice.get("endDate", "")
        
        # Use the month from the invoice dates if available, otherwise use the period we're fetching
        if invoice_start_date and invoice_end_date:
            month_name = get_month_name_from_date(invoice_start_date)
        else:
            # Fallback to the period we're fetching
            month_name = period_month_name
        
        filename = downloads_dir / f"Bol.com - {username} - {month_name} - {invoice_id}.xlsx"
        
        # Try up to 3 times with increasing delays
        for attempt in range(3):
            try:
                download_specification(token, invoice_id, filename)
                break  # Success, exit retry loop
            except Exception as e:
                if attempt < 2:  # Not the last attempt
                    print(f"⚠️ Attempt {attempt + 1} failed for invoice {invoice_id}: {e}")
                    import time
                    time.sleep(2 ** attempt)  # Exponential backoff: 1s, 2s, 4s
                else:  # Last attempt
                    print(f"❌ Failed to download invoice {invoice_id} after 3 attempts: {e}")

def main():
    # Process all accounts
    for i in range(1, 5):
        process_account(i)
    print("\n✅ All done!")

if __name__ == "__main__":
    main()
