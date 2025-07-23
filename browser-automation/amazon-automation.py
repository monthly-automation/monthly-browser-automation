import asyncio
from playwright.async_api import async_playwright, TimeoutError
import os, pyotp
from dotenv import load_dotenv
from pathlib import Path

load_dotenv()
EMAIL = os.getenv("AMAZON_SELLER_EMAIL")
PASSWORD = os.getenv("AMAZON_SELLER_PASSWORD")
TOTP_SECRET = os.getenv("AMAZON_SELLER_TOTP_SECRET")
URL = "https://sellercentral.amazon.com.be/payments/reports-repository"


async def dismiss_tutorial(page):
    try:
        tutorial_selector = '.react-joyride__tooltip'
        await page.wait_for_selector(tutorial_selector, timeout=2000)
        if await page.is_visible('button[data-action="skip"]'):
            await page.click('button[data-action="skip"]')
        elif await page.is_visible('button[data-action="close"]'):
            await page.click('button[data-action="close"]')
        else:
            await page.keyboard.press("Escape")
        print("✅ Tutorial dismissed.")
        await asyncio.sleep(1)
    except TimeoutError:
        print("ℹ️ No tutorial popup detected.")


async def select_belgium(page):
    print("🇧🇪 Selecting Belgium account…")
    await page.goto("https://sellercentral.amazon.com.be/account-switcher/default/merchantMarketplace")
    await page.wait_for_selector(".full-page-account-switcher-accounts", timeout=5000)

    tcf_button = page.locator(".full-page-account-switcher-account-label", has_text="TCF Trading").first
    await tcf_button.wait_for()
    await tcf_button.click()
    await asyncio.sleep(1)

    countries = await get_country_buttons(page, tcf_button)

    for btn in countries:
        name = (await btn.locator(".full-page-account-switcher-account-label").inner_text()).strip()
        if name == "Belgium":
            print(f"✅ Found Belgium: {name}")
            await btn.click()
            # Find and click the confirm button by exact text
            found = False
            buttons = await page.locator('button').all()
            for btn_elem in buttons:
                try:
                    text = (await btn_elem.inner_text()).strip()
                except Exception:
                    text = ""
                if text == "Select account":
                    print(f"✅ Found confirm button: '{text}'")
                    await btn_elem.click()
                    found = True
                    break
            if not found:
                print("❌ Could not find the confirm button by text. Printing all button texts for debugging:")
                for idx, btn_elem in enumerate(buttons):
                    try:
                        text = await btn_elem.inner_text()
                    except Exception:
                        text = "<error>"
                    class_name = await btn_elem.get_attribute('class')
                    print(f"Button {idx}: '{text}' | class='{class_name}'")
                await page.screenshot(path="debug_confirm_button_not_found.png", full_page=True)
                print("📷 Screenshot saved as debug_confirm_button_not_found.png")
                raise Exception("Could not find the confirm button by text")
            await page.wait_for_load_state("networkidle")
            print(f"🎉 Belgium selected: {name}")
            return
    raise Exception("❌ Could not find Belgium account.")


async def get_country_buttons(page, tcf_button):
    tcf_container = tcf_button.locator("xpath=../../..")
    inner_accounts = tcf_container.locator(".full-page-account-switcher-accounts")
    buttons = await inner_accounts.locator(".full-page-account-switcher-account > button").all()
    return buttons


async def set_filters_and_request(page):
    print("🎛 Setting filters…")
    dropdowns = page.locator(".kat-select-container")
    count = await dropdowns.count()

    for i in range(count):
        dropdown = dropdowns.nth(i)
        header = dropdown.locator(".select-header")
        await header.click()
        options = dropdown.locator(".standard-option-name")
        for j in range(await options.count()):
            option = options.nth(j)
            if (await option.inner_text()).strip().lower() == "transaction":
                await option.click()
                print("✅ Selected 'Transaction'.")
                break
        else:
            await header.click()
            continue
        break

    monthly_radio = page.locator("input#katal-id-9")
    await monthly_radio.wait_for(state="visible")
    if not await monthly_radio.is_checked():
        await page.evaluate("(el) => el.click()", await monthly_radio.element_handle())
        print("✅ Selected 'Monthly'.")
    else:
        print("ℹ️ 'Monthly' already selected.")

    request_button = page.locator("button span", has_text="Request Report")
    await request_button.first.click()
    print("📄 Clicked 'Request Report'.")


async def wait_for_report_and_download(page, country):
    print(f"📊 Waiting for report for {country}…")
    await page.locator("kat-table").wait_for()

    while True:
        rows = page.locator("kat-table-row")
        if await rows.count() == 0:
            await asyncio.sleep(3)
            continue

        for i in range(await rows.count()):
            row = rows.nth(i)
            report_type = (await row.locator(".header-cell-report-type").inner_text()).strip()
            if report_type.lower() != "transaction":
                continue

            action_button = row.locator(".header-cell-report-action kat-button")
            if await action_button.count() == 0:
                continue

            label = (await action_button.first.get_attribute("label")).strip()
            if label.lower() == "download csv":
                print("📥 Downloading…")
                async with page.expect_download() as download_info:
                    await action_button.first.click()
                download = await download_info.value
                Path("downloads").mkdir(exist_ok=True)
                save_as = Path("downloads") / f"Amazon - {country} - {download.suggested_filename}"
                await download.save_as(save_as)
                print(f"✅ Downloaded: {save_as}")
                return
            elif label.lower() == "refresh":
                print("🔄 Refreshing…")
                await action_button.first.click()
                await asyncio.sleep(3)
                break
        else:
            await asyncio.sleep(3)


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True  # 👈 headless!
        )
        # Set Accept-Language to English
        context = await browser.new_context(locale="en-US", extra_http_headers={"Accept-Language": "en-US,en;q=0.9"})
        page = await context.new_page()
        await page.goto(URL)

        # === LOGIN ===
        await page.fill('input[name="email"]', EMAIL)
        await page.click('input#continue')
        await page.fill('input[name="password"]', PASSWORD)
        await page.click('input#signInSubmit')
        await page.fill('input[name="otpCode"]', pyotp.TOTP(TOTP_SECRET).now())
        await page.click('input#auth-signin-button')
        await page.wait_for_load_state("networkidle")
        print("✅ Logged in")

        # === Belgium first ===
        await select_belgium(page)

        # === Back to account switcher ===
        await page.goto("https://sellercentral.amazon.com.be/account-switcher/default/merchantMarketplace")
        await page.wait_for_load_state("networkidle")

        # === Loop over countries ===
        tcf_button = page.locator(".full-page-account-switcher-account-label", has_text="TCF Trading").first
        await tcf_button.wait_for()

        while True:
            countries = await get_country_buttons(page, tcf_button)
            if len(countries) == 0:
                print("⚠️ No countries found — re-expanding TCF Trading.")
                await tcf_button.click()
                await asyncio.sleep(1)
            else:
                break

        for btn in countries:
            country = (await btn.locator(".full-page-account-switcher-account-label").inner_text()).strip()
            await btn.click()
            is_current = country.endswith("(current)")
            if not is_current:
                select_button = page.locator("button", has_text="Select account")
                if await select_button.count() > 0 and await select_button.is_enabled():
                    await select_button.click()
                    await page.wait_for_load_state("networkidle")
            primary_button = page.locator('button.kat-button--primary')
            if await primary_button.count() > 0 and await primary_button.is_visible():
                await primary_button.click()
            await page.wait_for_load_state("networkidle")

            await dismiss_tutorial(page)

            await page.goto(URL)
            await page.wait_for_load_state("networkidle")
            await dismiss_tutorial(page)

            await set_filters_and_request(page)
            await wait_for_report_and_download(page, country)

            await page.goto("https://sellercentral.amazon.com.be/account-switcher/default/merchantMarketplace")
            await page.wait_for_load_state("networkidle")

            # Ensure TCF is expanded again
            while True:
                countries = await get_country_buttons(page, tcf_button)
                if len(countries) == 0:
                    await tcf_button.click()
                    await asyncio.sleep(1)
                else:
                    break

        print("✅ All done. Press Enter to exit…")


if __name__ == "__main__":
    asyncio.run(main())
