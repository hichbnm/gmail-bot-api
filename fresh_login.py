import asyncio
from gmail_automation import GmailAutomation

async def fresh_automated_login():
    """Fresh automated login now that security prompt is approved"""
    automation = GmailAutomation()
    await automation.start()

    email = input("Enter Gmail email: ")
    password = input("Enter Gmail password (leave empty if using device approval): ")
    backup_code = input("Enter backup code (leave empty if not using): ")

    print(f"\n🔄 Starting fresh login for {email}...")
    print("Note: If you see 'Check your phone', approve the login on your device")

    success = await automation.login_gmail(
        email=email,
        browser_pass=password if password else "",
        backup_code=backup_code if backup_code else None
    )

    if success:
        print(f"✅ Login successful for {email}")
        print("Cookies have been saved for future use")
    else:
        print(f"❌ Login failed for {email}")

    await automation.stop()

if __name__ == "__main__":
    asyncio.run(fresh_automated_login())
