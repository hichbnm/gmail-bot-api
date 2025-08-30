import asyncio
import json
from pathlib import Path
from gmail_automation import GmailAutomation

async def export_browser_cookies():
    """Export cookies from Chrome browser to our automation system"""
    automation = GmailAutomation()
    await automation.start()

    # You'll need to manually copy cookies from Chrome DevTools
    # 1. Open Chrome and go to mail.google.com
    # 2. Press F12 to open DevTools
    # 3. Go to Application tab > Cookies > https://mail.google.com
    # 4. Copy all cookies and paste them below

    email = input("Enter your Gmail email: ")
    print(f"\nTo export cookies from Chrome:")
    print(f"1. Open Chrome and make sure you're logged into {email}")
    print(f"2. Go to https://mail.google.com")
    print(f"3. Press F12 to open DevTools")
    print(f"4. Go to Application tab > Storage > Cookies > https://mail.google.com")
    print(f"5. Right-click and 'Copy all' the cookies")
    print(f"6. Paste them here (as JSON array):")

    cookies_json = input("\nPaste cookies JSON here: ")

    try:
        cookies = json.loads(cookies_json)

        # Create context and add cookies
        context = await automation.create_context(email)
        await context.add_cookies(cookies)

        # Save cookies to our system
        await automation.save_cookies(email, context)

        print(f"✅ Cookies saved for {email}")

        # Test the session
        page = await context.new_page()
        await page.goto('https://mail.google.com')
        await page.wait_for_timeout(3000)

        try:
            await page.wait_for_selector('[data-message-store]', timeout=10000)
            print("✅ Session is working!")
        except:
            print("❌ Session test failed")

        await page.close()

    except json.JSONDecodeError:
        print("❌ Invalid JSON format")
    except Exception as e:
        print(f"❌ Error: {e}")

    await automation.stop()

if __name__ == "__main__":
    asyncio.run(export_browser_cookies())
