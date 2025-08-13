import os
import asyncio
import smtplib
import ssl
from email.message import EmailMessage
from pathlib import Path
from datetime import datetime, timedelta
from dotenv import load_dotenv
import shutil
import subprocess

load_dotenv()

# === Config ===
DOWNLOADS_DIR = Path(__file__).parent / "downloads"

SMTP_SERVER = os.getenv("SMTP_SERVER")
SMTP_PORT = int(os.getenv("SMTP_PORT", 587))
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
MAIL_TO = os.getenv("MAIL_TO")


def clear_downloads():
    print("🧹 Clearing downloads folder…")
    if DOWNLOADS_DIR.exists():
        shutil.rmtree(DOWNLOADS_DIR)
    DOWNLOADS_DIR.mkdir(exist_ok=True)
    print("✅ Downloads folder is clean.")


def collect_files():
    downloads = list(DOWNLOADS_DIR.glob("*"))
    return downloads

def collect_debug_files():
    """Collect debug screenshots and HTML files for email attachment"""
    debug_files = []
    
    # Look for debug screenshots
    for debug_file in Path(".").glob("debug_*.png"):
        debug_files.append(debug_file)
    
    # Look for debug HTML files
    for debug_file in Path(".").glob("debug_*.html"):
        debug_files.append(debug_file)
    
    return debug_files


def send_email_with_attachments(files, debug_files=None, failure_mode=False):
    today = datetime.today()
    first_of_this_month = today.replace(day=1)
    last_month_date = first_of_this_month - timedelta(days=1)
    last_month_str = last_month_date.strftime("%B %Y")
    current_datetime_str = today.strftime("%Y-%m-%d %H:%M")

    msg = EmailMessage()
    msg["From"] = SMTP_USER
    msg["To"] = MAIL_TO
    
    if failure_mode:
        msg["Subject"] = f"⚠️ Automation Failure - {last_month_str}"
        content = (
            f"Hi,\n\n"
            f"The monthly automation encountered an error while processing {last_month_str} reports.\n\n"
            f"Error occurred on {current_datetime_str}.\n\n"
            f"Debug screenshots and HTML files are attached to help diagnose the issue.\n\n"
            f"Best regards,\n"
            f"Automation Script"
        )
    else:
        msg["Subject"] = f"Monthly Reports - {last_month_str}"
        content = (
            f"Hi,\n\n"
            f"Please find attached the monthly reports from {last_month_str}.\n\n"
            f"Reports retrieved on {current_datetime_str}.\n\n"
            f"Best regards,\n"
            f"Automation Script"
        )
    
    msg.set_content(content)

    # Attach report files
    for file_path in files:
        with open(file_path, "rb") as f:
            data = f.read()
            msg.add_attachment(
                data,
                maintype="application",
                subtype="octet-stream",
                filename=file_path.name
            )
        print(f"📎 Attached report: {file_path.name}")
    
    # Attach debug files if provided
    if debug_files:
        for debug_file in debug_files:
            try:
                with open(debug_file, "rb") as f:
                    data = f.read()
                    msg.add_attachment(
                        data,
                        maintype="application",
                        subtype="octet-stream",
                        filename=debug_file.name
                    )
                print(f"📎 Attached debug file: {debug_file.name}")
            except Exception as e:
                print(f"⚠️ Could not attach debug file {debug_file.name}: {e}")

    print("✉️ Sending email…")
    context = ssl.create_default_context()
    with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
        server.starttls(context=context)
        server.login(SMTP_USER, SMTP_PASSWORD)
        server.send_message(msg)

    print(f"✅ Email sent to: {MAIL_TO}")


def run_script(script: Path):
    print(f"🚀 Running {script} …")
    # Use sys.executable to get the current Python interpreter (from virtual environment)
    import sys
    result = subprocess.run(
        [sys.executable, str(script)],
        capture_output=False,
        text=True,
    )
    if result.returncode != 0:
        print(f"❌ Script {script} failed with return code {result.returncode}")
    else:
        print(f"✅ Finished {script}")


async def main():
    clear_downloads()
    amazon_failed = False

    run_script(Path("browser-automation/bol-automation.py"))
    
    # Check if Amazon automation failed
    try:
        run_script(Path("browser-automation/amazon-automation.py"))
    except Exception as e:
        print(f"❌ Amazon automation failed: {e}")
        amazon_failed = True
    
    # Also check for failure marker file
    if Path("amazon_automation_failed.txt").exists():
        amazon_failed = True
        print("⚠️ Amazon automation failure marker detected")

    files = collect_files()
    debug_files = collect_debug_files()
    
    if not files and not debug_files:
        print("⚠️ No report files or debug files found to attach.")
    else:
        # Send email with debug files if Amazon failed
        send_email_with_attachments(files, debug_files, failure_mode=amazon_failed)

    print("🎉 All tasks completed. Exiting.")


if __name__ == "__main__":
    asyncio.run(main())
