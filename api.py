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
    log_info("Starting Gmail API service...")
    await automation.start()
    log_info("Gmail API service started successfully")

@app.on_event("shutdown")
async def shutdown_event():
    log_info("Shutting down Gmail API service...")
    await automation.stop()
    log_info("Gmail API service shut down successfully")

@app.post("/login_accounts")
async def login_accounts(accounts: List[AccountCredentials]):
    log_info(f"Processing login request for {len(accounts)} account(s)")
    results = []

    for account in accounts:
        log_info(f"Attempting login for: {account.email}")
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
                log_info(f"Login successful for: {account.email}")
            else:
                log_error(f"Login failed for: {account.email}")

            results.append({"email": account.email, "login_success": success})
        except Exception as e:
            log_error(f"Exception during login for {account.email}: {e}")
            results.append({"email": account.email, "login_success": False, "error": str(e)})

    log_info(f"Login process completed. Success: {sum(1 for r in results if r['login_success'])}/{len(results)}")
    return {"results": results}

@app.post("/send_emails")
async def send_emails(request: SendRequest):
    log_info(f"Processing email send request: {len(request.accounts)} accounts, {len(request.emails)} emails")
    results = []

    # If we have more emails than accounts, distribute emails across accounts
    # If we have more accounts than emails, each account gets one email (current behavior)
    emails_per_account = len(request.emails) // len(request.accounts)
    extra_emails = len(request.emails) % len(request.accounts)

    email_index = 0

    for account_idx, account in enumerate(request.accounts):
        # Calculate how many emails this account should send
        emails_for_this_account = emails_per_account
        if account_idx < extra_emails:
            emails_for_this_account += 1

        # Check session ONCE per account, not per email
        session_ready = False
        if account.email not in automation.contexts:
            log_info(f"Loading session for {account.email}")

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
                print(f"Cookies loaded for {account.email}")
                session_ready = True
            else:
                log_error(f"No cookies found for {account.email} - please login first")
                # Skip all emails for this account
                for _ in range(emails_for_this_account):
                    if email_index < len(request.emails):
                        email_content = request.emails[email_index]
                        results.append({
                            "email": account.email,
                            "to": email_content.to,
                            "status": "No cookies found - please login first"
                        })
                        email_index += 1
                continue
        else:
            session_ready = True
            print(f"Session ready for {account.email}")

        if not session_ready:
            continue

        # Now send all emails for this account
        for _ in range(emails_for_this_account):
            if email_index >= len(request.emails):
                break

            email_content = request.emails[email_index]
            log_info(f"Sending email {email_index + 1}/{len(request.emails)} from {account.email} to {email_content.to}")

            try:
                # Send the email (send_email method will handle session validation internally)
                success = await automation.send_email(
                    account.email,
                    email_content.to,
                    email_content.subject,
                    email_content.body
                )

                if success:
                    log_info(f"Email sent successfully from {account.email} to {email_content.to}")
                    results.append({
                        "email": account.email,
                        "to": email_content.to,
                        "status": "Email sent successfully"
                    })
                else:
                    log_error(f"Failed to send email from {account.email} to {email_content.to}")
                    results.append({
                        "email": account.email,
                        "to": email_content.to,
                        "status": "Failed to send email"
                    })

            except Exception as e:
                log_error(f"Exception sending email from {account.email} to {email_content.to}: {e}")
                results.append({
                    "email": account.email,
                    "to": email_content.to,
                    "status": f"Error: {str(e)}"
                })

            email_index += 1

    successful_sends = sum(1 for r in results if r['status'] == 'Email sent successfully')
    log_info(f"Email sending completed. Success: {successful_sends}/{len(request.emails)}")
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
