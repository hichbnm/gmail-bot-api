from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional, List
import pandas as pd
import asyncio
from gmail_automation import GmailAutomation
from config import GMAIL_COMPOSE_BUTTON
from logging_config import log_info, log_error, log_warning

app = FastAPI(title="Gmail Browser Automation Service")

automation = GmailAutomation()

class AccountCredentials(BaseModel):
    first_from_name: str
    last_from_name: str
    email: str
    email_pass: str  # App password for SMTP, but we use browser_pass for login
    proxy_host: Optional[str] = None
    proxy_port: Optional[int] = None
    proxy_user: Optional[str] = None
    proxy_pass: Optional[str] = None
    browser_pass: str
    backup_code: Optional[str] = None

class EmailContent(BaseModel):
    to: str
    subject: str
    body: str

class SendRequest(BaseModel):
    accounts: List[AccountCredentials]
    emails: List[EmailContent]

@app.on_event("startup")
async def startup_event():
    await automation.start()

@app.on_event("shutdown")
async def shutdown_event():
    await automation.stop()

@app.post("/login_accounts")
async def login_accounts(accounts: List[AccountCredentials]):
    log_info(f"📧 Processing login request for {len(accounts)} account(s)")
    results = []

    for account in accounts:
        log_info(f"🔐 Attempting login for: {account.email}")
        proxy = {
            "type": "socks5",  # Specify SOCKS5 proxy type
            "host": account.proxy_host,
            "port": account.proxy_port,
            "username": account.proxy_user,
            "password": account.proxy_pass
        } if account.proxy_host else None

        try:
            success = await automation.login_gmail(
                account.email,
                account.browser_pass,
                account.backup_code,
                proxy
            )

            if success:
                log_info(f"✅ Login successful for: {account.email}")
            else:
                log_error(f"❌ Login failed for: {account.email}")

            results.append({"email": account.email, "login_success": success})
        except Exception as e:
            log_error(f"💥 Exception during login for {account.email}: {e}")
            results.append({"email": account.email, "login_success": False, "error": str(e)})

    log_info(f"📊 Login process completed. Success: {sum(1 for r in results if r['login_success'])}/{len(results)}")
    return {"results": results}

@app.post("/send_emails")
async def send_emails(request: SendRequest):
    results = []

    for i, account in enumerate(request.accounts):
        if i >= len(request.emails):
            results.append({"email": account.email, "status": "No email to send"})
            continue

        email_content = request.emails[i]

        try:
            # Check if we have an active session for this account
            if account.email not in automation.contexts:
                print(f"🔄 Loading session for {account.email}")

                # Create context and load cookies
                proxy = {
                    "type": "socks5",  # Specify SOCKS5 proxy type
                    "host": account.proxy_host,
                    "port": account.proxy_port,
                    "username": account.proxy_user,
                    "password": account.proxy_pass
                } if account.proxy_host else None

                context = await automation.create_context(account.email, proxy)

                # Check if cookies were loaded
                cookies = await automation.load_cookies(account.email)
                if cookies:
                    await context.add_cookies(cookies)
                    print(f"✅ Cookies loaded for {account.email}")
                else:
                    results.append({"email": account.email, "status": "No cookies found - please login first"})
                    continue

            print(f"✅ Session ready for {account.email}")

            # Send the email (send_email method will handle session validation internally)
            success = await automation.send_email(
                account.email,
                email_content.to,
                email_content.subject,
                email_content.body
            )

            if success:
                results.append({"email": account.email, "status": "Email sent successfully"})
            else:
                results.append({"email": account.email, "status": "Failed to send email"})

        except Exception as e:
            results.append({"email": account.email, "status": f"Error: {str(e)}"})

    return {"results": results}

@app.post("/upload_sheet")
async def upload_sheet(file: bytes):
    # Save and process Excel sheet
    with open("accounts.xlsx", "wb") as f:
        f.write(file)

    df = pd.read_excel("accounts.xlsx")
    # Process the sheet to extract accounts
    accounts = []
    for _, row in df.iterrows():
        accounts.append(AccountCredentials(
            first_from_name=row.get("FIRSTFROMNAME", ""),
            last_from_name=row.get("LASTFROMNAME", ""),
            email=row["EMAIL"],
            email_pass=row["EMAIL_PASS"],
            proxy_host=row["PROXY:PORT"].split(":")[0] if ":" in str(row["PROXY:PORT"]) else "",
            proxy_port=int(row["PROXY:PORT"].split(":")[1]) if ":" in str(row["PROXY:PORT"]) else 0,
            proxy_user=row.get("PROXY_USER"),
            proxy_pass=row.get("PROXY_PASS"),
            browser_pass=row.get("BROWSER_PASS", ""),
            backup_code=row.get("BACKUP_CODE")
        ))

    return {"accounts": accounts}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
