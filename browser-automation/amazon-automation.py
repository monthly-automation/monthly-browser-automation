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
        
        try:
            await page.goto(URL)
            print("✅ Navigated to Amazon Seller Central")
            
            # Take screenshot of initial page
            await page.screenshot(path="debug_01_initial_page.png", full_page=True)
            print("📷 Screenshot saved: debug_01_initial_page.png")

            # === LOGIN ===
            print("🔐 Starting login process...")
            
            try:
                await page.fill('input[name="email"]', EMAIL)
                print("✅ Email filled")
                await page.screenshot(path="debug_02_after_email.png", full_page=True)
                print("📷 Screenshot saved: debug_02_after_email.png")
                
                await page.click('input#continue')
                print("✅ Continue button clicked")
                await page.wait_for_load_state("networkidle")
                await page.screenshot(path="debug_03_after_continue.png", full_page=True)
                print("📷 Screenshot saved: debug_03_after_continue.png")
                
                await page.fill('input[name="password"]', PASSWORD)
                print("✅ Password filled")
                await page.screenshot(path="debug_04_after_password.png", full_page=True)
                print("📷 Screenshot saved: debug_04_after_password.png")
                
                await page.click('input#signInSubmit')
                print("✅ Sign in button clicked")
                await page.wait_for_load_state("networkidle")
                await page.screenshot(path="debug_05_after_signin.png", full_page=True)
                print("📷 Screenshot saved: debug_05_after_signin.png")
                
                await page.fill('input[name="otpCode"]', pyotp.TOTP(TOTP_SECRET).now())
                print("✅ TOTP code filled")
                await page.screenshot(path="debug_06_after_totp.png", full_page=True)
                print("📷 Screenshot saved: debug_06_after_totp.png")
                
                await page.click('input#auth-signin-button')
                print("✅ TOTP submit button clicked")
                await page.wait_for_load_state("networkidle")
                await page.screenshot(path="debug_07_after_totp_submit.png", full_page=True)
                print("📷 Screenshot saved: debug_07_after_totp_submit.png")
                
                print("✅ Logged in successfully")
                
            except Exception as login_error:
                print(f"❌ Login failed: {login_error}")
                await page.screenshot(path="debug_login_failed.png", full_page=True)
                print("📷 Screenshot saved: debug_login_failed.png")
                
                # Try to get page content for debugging
                try:
                    page_content = await page.content()
                    with open("debug_login_page.html", "w", encoding="utf-8") as f:
                        f.write(page_content)
                    print("📄 Page HTML saved: debug_login_page.html")
                except Exception as e:
                    print(f"⚠️ Could not save page HTML: {e}")
                
                raise login_error

            # === Belgium first ===
            try:
                await select_belgium(page)
                print("✅ Belgium selection completed")
            except Exception as belgium_error:
                print(f"❌ Belgium selection failed: {belgium_error}")
                await page.screenshot(path="debug_belgium_selection_failed.png", full_page=True)
                print("📷 Screenshot saved: debug_belgium_selection_failed.png")
                raise belgium_error

            # === Back to account switcher ===
            try:
                await page.goto("https://sellercentral.amazon.com.be/account-switcher/default/merchantMarketplace")
                await page.wait_for_load_state("networkidle")
                print("✅ Navigated to account switcher")
            except Exception as nav_error:
                print(f"❌ Navigation to account switcher failed: {nav_error}")
                await page.screenshot(path="debug_account_switcher_nav_failed.png", full_page=True)
                print("📷 Screenshot saved: debug_account_switcher_nav_failed.png")
                raise nav_error

            # === Loop over countries ===
            try:
                tcf_button = page.locator(".full-page-account-switcher-account-label", has_text="TCF Trading").first
                await tcf_button.wait_for()
                print("✅ TCF Trading button found")

                while True:
                    countries = await get_country_buttons(page, tcf_button)
                    if len(countries) == 0:
                        print("⚠️ No countries found — re-expanding TCF Trading.")
                        await tcf_button.click()
                        await asyncio.sleep(1)
                    else:
                        break

                print(f"✅ Found {len(countries)} countries to process")

                for i, btn in enumerate(countries):
                    try:
                        country = (await btn.locator(".full-page-account-switcher-account-label").inner_text()).strip()
                        print(f"🔄 Processing country {i+1}/{len(countries)}: {country}")
                        
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
                                
                        print(f"✅ Completed processing for {country}")
                        
                    except Exception as country_error:
                        print(f"❌ Failed to process country {country}: {country_error}")
                        await page.screenshot(path=f"debug_country_{country.replace(' ', '_')}_failed.png", full_page=True)
                        print(f"📷 Screenshot saved: debug_country_{country.replace(' ', '_')}_failed.png")
                        # Continue with next country instead of failing completely
                        continue

                print("✅ All countries processed")

            except Exception as countries_error:
                print(f"❌ Country processing failed: {countries_error}")
                await page.screenshot(path="debug_countries_processing_failed.png", full_page=True)
                print("📷 Screenshot saved: debug_countries_processing_failed.png")
                raise countries_error

            print("✅ All done, exiting.")
            
        except Exception as main_error:
            print(f"❌ Main execution failed: {main_error}")
            await page.screenshot(path="debug_main_execution_failed.png", full_page=True)
            print("📷 Screenshot saved: debug_main_execution_failed.png")
            
            # Try to get page content for debugging
            try:
                page_content = await page.content()
                with open("debug_main_failed_page.html", "w", encoding="utf-8") as f:
                    f.write(page_content)
                print("📄 Page HTML saved: debug_main_failed_page.html")
            except Exception as e:
                print(f"⚠️ Could not save page HTML: {e}")
            
            raise main_error


if __name__ == "__main__":
    asyncio.run(main())
