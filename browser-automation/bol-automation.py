import asyncio
from playwright.async_api import async_playwright, TimeoutError
import os
from dotenv import load_dotenv
from pathlib import Path
import calendar
from datetime import datetime

load_dotenv()

URL = "https://partner.bol.com/sdd/cashboard/finances"

async def save_debug_info(page, username, reason):
    """Save debug information when something goes wrong"""
    try:
        content = await page.content()
        with open(f"debug_{username}_{reason}.html", "w", encoding="utf-8") as f:
            f.write(content)
        
        await page.screenshot(path=f"debug_{username}_{reason}.png", full_page=True)
        print(f"📷 Debug saved: debug_{username}_{reason}.html and debug_{username}_{reason}.png")
    except Exception as e:
        print(f"⚠️ Could not save debug info: {e}")

async def login_if_needed(page, email, password, username):
    print(f"🌐 Navigating to finances page for {username}…")
    await page.goto(URL)
    await page.wait_for_load_state("networkidle")

    try:
        await page.wait_for_selector("css=table", timeout=10000)
        print(f"✅ Already logged in as {username}.")
        return
    except TimeoutError:
        print(f"🔑 Not logged in — logging in as {username}…")
        await save_debug_info(page, username, "before_login")

    await page.wait_for_selector('input[name="j_username"]', timeout=10000)  # Increased for CI
    await page.fill('input[name="j_username"]', email)
    await page.fill('input[name="j_password"]', password)

    await page.click('button[type="submit"]')
    await page.wait_for_load_state("networkidle")

    try:
        await page.wait_for_selector("css=table", timeout=15000)  # Increased for CI
        print(f"🎉 Logged in as {username}")
    except TimeoutError:
        await save_debug_info(page, username, "login_failed")
        raise Exception(f"❌ Login failed for {username}. Saved debug info for investigation.")


async def logout_if_needed(page):
    print("🔒 Logging out…")
    try:
        triggers = page.locator('button[data-slot="navigation-menu-trigger"]')
        count = await triggers.count()
        target_trigger = None

        for i in range(count):
            button = triggers.nth(i)
            svg_content = await button.locator("svg").first.inner_html()
            if "M12 3C10.3431 3 9 4.34315" in svg_content:
                target_trigger = button
                break

        if not target_trigger:
            raise Exception("❌ Could not find the correct user menu trigger.")

        await target_trigger.click()
        await page.wait_for_selector('div[data-slot="navigation-menu-content"]', timeout=5000)

        logout_link = page.locator('a', has_text="Uitloggen")
        await logout_link.wait_for(timeout=5000)
        await logout_link.click()

        await page.goto(URL)
        try:
            await page.wait_for_selector('input[name="j_username"]', timeout=10000)
            print("✅ Successfully logged out.")
        except TimeoutError:
            print("⚠️ Logout might have failed — login form not detected.")
    except Exception as e:
        print(f"⚠️ Logout encountered an error: {e}")


async def download_current_specification(page, username, downloads_dir: Path):
    try:
        print(f"🔍 Looking for specification link for {username}...")
        link = page.locator('a[data-test="specification-link"]')
        await link.wait_for(timeout=5000)  # Increased timeout for CI

        async with page.expect_download() as download_info:
            await link.click()

        download = await download_info.value

        orig_filename = download.suggested_filename
        target_filename = downloads_dir / f"Bol.com - {username} - {orig_filename}"

        await download.save_as(target_filename)

        print(f"📥 Saved Specificatie: {target_filename}")
    except Exception as e:
        print(f"⚠️ Could not download 'Specificatie' for {username}: {e}")


async def download_invoices_for_last_month(page, username, downloads_dir: Path):
    today = datetime.today()
    last_month = today.month - 1 if today.month > 1 else 12
    year = today.year if today.month > 1 else today.year - 1
    first_day = datetime(year, last_month, 1)
    last_day = datetime(year, last_month, calendar.monthrange(year, last_month)[1])

    print(f"📆 Checking for invoices in period: {first_day.strftime('%d-%m-%Y')} to {last_day.strftime('%d-%m-%Y')}")

    await page.wait_for_selector("puik-list-row", timeout=5000)

    rows = page.locator("puik-list-row")
    row_count = await rows.count()

    if row_count == 0:
        print("⚠️ No invoice rows found!")
        return

    for i in range(row_count):
        row = rows.nth(i)

        try:
            period_text = (await row.locator('[data-test="span-invoice-with-period"]').inner_text()).strip()
        except TimeoutError:
            print(f"ℹ️ Row {i+1} has no period — skipping.")
            continue

        try:
            if "t/m" in period_text:
                start_str, end_str = [s.strip() for s in period_text.split("t/m")]
            elif "until" in period_text:
                start_str, end_str = [s.strip() for s in period_text.split("until")]
            else:
                raise ValueError("Unknown separator in period text")

            start_date = datetime.strptime(start_str, "%d-%m-%Y")
            end_date = datetime.strptime(end_str, "%d-%m-%Y")
        except Exception as e:
            print(f"❌ Could not parse period in row {i+1}: {period_text} — {e}")
            continue

        if end_date < first_day or start_date > last_day:
            print(f"⏭ Row {i+1}: period {start_str} to {end_str} — outside last month.")
            continue

        print(f"✅ Row {i+1}: period {start_str} to {end_str} — downloading XLSX…")

        filename_date = f"{start_date.strftime('%Y-%m-%d')}_to_{end_date.strftime('%Y-%m-%d')}"

        try:
            menu_btn = row.locator('.puik-more-options__button[data-test="puik-more-options__button"]')
            await menu_btn.wait_for()
            await menu_btn.scroll_into_view_if_needed()
            await menu_btn.click()
        except Exception as e:
            print(f"⚠️ Could not find/click 3-dot menu in row {i+1}, skipping. ({e})")
            continue

        try:
            option = row.locator(".puik-more-options__dropdown-option", has_text="Download specificatie")
            await option.wait_for(timeout=3000)

            async with page.expect_download() as download_info:
                await option.click()

            download = await download_info.value

            orig_filename = download.suggested_filename
            target_filename = downloads_dir / f"Bol.com - {username} - {filename_date} - {orig_filename}"

            await download.save_as(target_filename)

            print(f"📥 Saved XLSX: {target_filename}")
        except Exception as e:
            print(f"❌ Failed to download XLSX in row {i+1}: {e}")
            continue

    print("🎉 Done checking all rows.")


async def main():
    downloads_dir = Path("downloads")
    downloads_dir.mkdir(exist_ok=True)

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-dev-shm-usage'
            ]
        )
        context = await browser.new_context(
            locale="nl-NL",
            extra_http_headers={"Accept-Language": "nl-NL,nl;q=0.9"}
        )
        page = await context.new_page()
        
        # Add debugging info
        print(f"🔧 Browser launched with viewport: {page.viewport_size}")
        print(f"🔧 User agent: {await page.evaluate('() => navigator.userAgent')}")

        for i in range(1, 5):
            username = os.getenv(f"BOL_USERNAME{i}")
            email = os.getenv(f"BOL_EMAIL_{i}")
            password = os.getenv(f"BOL_PASSWORD_{i}")

            if not all([username, email, password]):
                print(f"⚠️ Missing credentials for user {i}, skipping.")
                continue

            print(f"\n=== 🚀 Processing {username} ===")
            print(f"🔧 Environment check: {username} credentials present: {bool(username and email and password)}")
            await login_if_needed(page, email, password, username)

            await page.goto(URL)
            await page.wait_for_load_state("networkidle")
            await page.wait_for_timeout(2000)  # Extra wait for CI

            try:
                await page.wait_for_selector("puik-list-row", timeout=10000)  # Increased for CI
            except TimeoutError:
                print(f"⚠️ Could not find puik-list-row for {username}, saving debug...")
                await save_debug_info(page, username, "no_puik_list_row")
                print(f"⚠️ Skipping {username}")
                continue

            print("🔍 Checking for current specification…")
            await download_current_specification(page, username, downloads_dir)

            print(f"📂 Ready to download files for {username}…")
            try:
                await download_invoices_for_last_month(page, username, downloads_dir)
            except Exception as e:
                print(f"❌ Error during invoice download for {username}: {e}")
                await save_debug_info(page, username, "invoice_download_error")

            await logout_if_needed(page)

        print("\n✅ All done with all users.")


if __name__ == "__main__":
    asyncio.run(main())
