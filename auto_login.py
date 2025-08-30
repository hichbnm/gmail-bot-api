import asyncio
from gmail_automation import GmailAutomation

async def auto_login_test():
    """Fully automated login test - detects success automatically"""
    automation = GmailAutomation()
    await automation.start()

    # Replace with your email
    email = "hichemmoussa189@gmail.com"
    password = ""  # Leave empty for device approval flow
    backup_code = ""  # Leave empty if not needed

    print(f"🚀 Starting automated login for {email}")
    print("📱 If device approval is needed, approve on your phone")
    print("🔄 Automation will handle Google Account redirects automatically")
    print("⏳ Please wait...")

    success = await automation.login_gmail(
        email=email,
        browser_pass=password,
        backup_code=backup_code if backup_code else None
    )

    if success:
        print(f"\n✅ SUCCESS: Login completed and cookies saved for {email}")
        print("💾 Cookies are stored in cookies/ directory")
        print("📧 Ready to send emails!")
        print("🌐 Gmail should be accessible at: https://mail.google.com")
    else:
        print(f"\n❌ FAILED: Login failed for {email}")
        print("🔍 Check debug screenshots for details")
        print("📁 Look for files: screenshots/debug_*.png in the screenshots folder")

    await automation.stop()

if __name__ == "__main__":
    asyncio.run(auto_login_test())
