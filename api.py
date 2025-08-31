from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional, List
import pandas as pd
import asyncio
import json
from gmail_automation import GmailAutomation
from config import GMAIL_COMPOSE_BUTTON, USE_PROXY
from logging_config import log_info, log_error, log_warning
from proxy_manager import get_proxy_for_account, update_proxy_performance, get_proxy_statistics

app = FastAPI(title="Gmail Browser Automation Service")

automation = GmailAutomation()

class AccountCredentials(BaseModel):
    first_from_name: Optional[str] = None
    last_from_name: Optional[str] = None
    email: str
    email_pass: Optional[str] = None  # App password for SMTP, but we use browser_pass for login
    proxy_host: Optional[str] = None
    proxy_port: Optional[int] = None
    proxy_user: Optional[str] = None
    proxy_pass: Optional[str] = None
    browser_pass: Optional[str] = None
    backup_code: Optional[str] = None

class EmailContent(BaseModel):
    to: str
    subject: str
    body: str
    proxy_host: Optional[str] = None
    proxy_port: Optional[int] = None
    proxy_user: Optional[str] = None
    proxy_pass: Optional[str] = None

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
async def login_accounts(request: dict):
    """Login to Gmail accounts"""
    if "accounts" not in request:
        raise HTTPException(status_code=400, detail="Missing 'accounts' field in request body")

    accounts = request["accounts"]
    if not isinstance(accounts, list):
        raise HTTPException(status_code=400, detail="'accounts' field must be a list")

    log_info(f"Processing login request for {len(accounts)} account(s)")
    results = []

    for account_data in accounts:
        try:
            # Validate required fields
            required_fields = ["email", "browser_pass"]
            for field in required_fields:
                if field not in account_data:
                    results.append({
                        "email": account_data.get("email", "unknown"),
                        "login_success": False,
                        "error": f"Missing required field: {field}"
                    })
                    continue

            # Create AccountCredentials object
            account = AccountCredentials(**account_data)

            proxy = None
            if account.proxy_host:
                proxy = {
                    "type": "http",  # Use HTTP for better compatibility
                    "host": account.proxy_host,
                    "port": account.proxy_port,
                    "username": account.proxy_user,
                    "password": account.proxy_pass
                }

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
            log_error(f"Exception during login for {account_data.get('email', 'unknown')}: {e}")
            results.append({
                "email": account_data.get("email", "unknown"),
                "login_success": False,
                "error": str(e)
            })

    log_info(f"Login process completed. Success: {sum(1 for r in results if r['login_success'])}/{len(results)}")
    return {"results": results}

@app.post("/send_emails")
async def send_emails(request: SendRequest):
    """
    Send emails using Gmail accounts with automatic distribution.
    
    Distribution Logic:
    - Emails are distributed sequentially across accounts
    - If you have 3 emails and 2 accounts: Account 1 gets emails #1-2, Account 2 gets email #3
    - Each result includes 'email_index' to show which input email it corresponds to
    - The summary shows the complete mapping of accounts to email indices
    """
    log_info(f"Processing email send request: {len(request.accounts)} accounts, {len(request.emails)} emails")
    results = []

    # If we have more emails than accounts, distribute emails across accounts
    # If we have more accounts than emails, each account gets one email (current behavior)
    emails_per_account = len(request.emails) // len(request.accounts)
    extra_emails = len(request.emails) % len(request.accounts)

    log_info(f"📊 Email Distribution Plan:")
    log_info(f"   Total emails: {len(request.emails)}")
    log_info(f"   Total accounts: {len(request.accounts)}")
    log_info(f"   Base emails per account: {emails_per_account}")
    log_info(f"   Extra emails to distribute: {extra_emails}")

    email_index = 0

    for account_idx, account in enumerate(request.accounts):
        # Calculate how many emails this account should send
        emails_for_this_account = emails_per_account
        if account_idx < extra_emails:
            emails_for_this_account += 1

        # Show which emails this account will handle
        assigned_emails = []
        temp_index = email_index
        for i in range(emails_for_this_account):
            if temp_index < len(request.emails):
                assigned_emails.append(f"#{temp_index + 1} ({request.emails[temp_index].to})")
                temp_index += 1
        
        log_info(f"   👤 {account.email} → {emails_for_this_account} email(s): {', '.join(assigned_emails)}")

    for account_idx, account in enumerate(request.accounts):
        # Calculate how many emails this account should send
        emails_for_this_account = emails_per_account
        if account_idx < extra_emails:
            emails_for_this_account += 1

        # Initialize account_proxy - it will be set regardless of session status
        account_proxy = None

        # Check session ONCE per account, not per email
        session_ready = False
        if account.email not in automation.contexts:
            log_info(f"Loading session for {account.email}")

            # Auto-assign proxy if not specified and USE_PROXY is enabled
            if not account.proxy_host and USE_PROXY:
                log_info(f"🔄 Auto-assigning proxy for {account.email}")
                auto_proxy = get_proxy_for_account(account.email)
                if auto_proxy:
                    account_proxy = {
                        "type": auto_proxy.get("type", "http"),  # Use actual proxy type
                        "host": auto_proxy["host"],
                        "port": auto_proxy["port"],
                        "username": auto_proxy["username"],
                        "password": auto_proxy["password"]
                    }
                    log_info(f"✅ Assigned proxy {auto_proxy['id']} to {account.email}")
                else:
                    log_error(f"❌ No proxy available for {account.email}")
                    # Skip all emails for this account
                    for _ in range(emails_for_this_account):
                        if email_index < len(request.emails):
                            email_content = request.emails[email_index]
                            results.append({
                                "email_index": email_index + 1,
                                "email": account.email,
                                "to": email_content.to,
                                "status": "No proxy available for account"
                            })
                            email_index += 1
                    continue
            elif not account.proxy_host and not USE_PROXY:
                log_info(f"🌐 Proxy usage disabled - using direct connection for {account.email}")
            else:
                # Use manually specified proxy (default to HTTP since we're using HTTP proxies)
                account_proxy = {
                    "type": "http",
                    "host": account.proxy_host,
                    "port": account.proxy_port,
                    "username": account.proxy_user,
                    "password": account.proxy_pass
                }

            context = await automation.create_context(account.email, account_proxy)

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
                            "email_index": email_index + 1,
                            "email": account.email,
                            "to": email_content.to,
                            "status": "No cookies found - please login first"
                        })
                        email_index += 1
                continue
        else:
            session_ready = True
            print(f"Session ready for {account.email}")
            # For existing sessions, try to get the proxy that was used previously
            # This is a best-effort attempt since we don't store proxy info with sessions
            if not account.proxy_host and USE_PROXY:
                auto_proxy = get_proxy_for_account(account.email)
                if auto_proxy:
                    account_proxy = {
                        "type": auto_proxy.get("type", "http"),
                        "host": auto_proxy["host"],
                        "port": auto_proxy["port"],
                        "username": auto_proxy["username"],
                        "password": auto_proxy["password"]
                    }
            elif not account.proxy_host and not USE_PROXY:
                log_info(f"🌐 Proxy usage disabled - using direct connection for existing session {account.email}")
            else:
                # Use manually specified proxy for existing session
                account_proxy = {
                    "type": "http",
                    "host": account.proxy_host,
                    "port": account.proxy_port,
                    "username": account.proxy_user,
                    "password": account.proxy_pass
                }

        if not session_ready:
            continue

        # Now send all emails for this account
        for _ in range(emails_for_this_account):
            if email_index >= len(request.emails):
                break

            email_content = request.emails[email_index]
            log_info(f"Sending email {email_index + 1}/{len(request.emails)} from {account.email} to {email_content.to}")

            try:
                # Prepare proxy for this specific email
                email_proxy = None
                if email_content.proxy_host:
                    # Use email-specific proxy (default to HTTP since we're using HTTP proxies)
                    email_proxy = {
                        "type": "http",
                        "host": email_content.proxy_host,
                        "port": email_content.proxy_port,
                        "username": email_content.proxy_user,
                        "password": email_content.proxy_pass
                    }
                elif account_proxy:
                    # Use account's auto-assigned proxy
                    email_proxy = account_proxy

                # Send the email with the specific proxy for this email
                success = await automation.send_email(
                    account.email,
                    email_content.to,
                    email_content.subject,
                    email_content.body,
                    email_proxy
                )

                # Update proxy performance metrics
                if email_proxy and account_proxy:
                    proxy_address = f"{email_proxy['host']}:{email_proxy['port']}"
                    proxy_id = f"proxy_{hash(proxy_address) % 1000:03d}"
                    update_proxy_performance(proxy_id, success)

                if success:
                    log_info(f"Email sent successfully from {account.email} to {email_content.to}")
                    results.append({
                        "email_index": email_index + 1,
                        "email": account.email,
                        "to": email_content.to,
                        "status": "Email sent successfully",
                        "proxy_used": f"{email_proxy['host']}:{email_proxy['port']}" if email_proxy else "No proxy"
                    })
                else:
                    log_error(f"Failed to send email from {account.email} to {email_content.to}")
                    results.append({
                        "email_index": email_index + 1,
                        "email": account.email,
                        "to": email_content.to,
                        "status": "Failed to send email",
                        "proxy_used": f"{email_proxy['host']}:{email_proxy['port']}" if email_proxy else "No proxy"
                    })

            except Exception as e:
                log_error(f"Exception sending email from {account.email} to {email_content.to}: {e}")
                results.append({
                    "email_index": email_index + 1,
                    "email": account.email,
                    "to": email_content.to,
                    "status": f"Error: {str(e)}"
                })

            email_index += 1

    successful_sends = sum(1 for r in results if r['status'] == 'Email sent successfully')
    log_info(f"Email sending completed. Success: {successful_sends}/{len(request.emails)}")
    
    # Close all browser contexts to free up resources
    log_info("🧹 Cleaning up browser contexts...")
    for account in request.accounts:
        await automation.close_context(account.email)
    
    # Create a summary of email distribution
    distribution_summary = []
    for account in request.accounts:
        account_results = [r for r in results if r['email'] == account.email]
        email_indices = [str(r['email_index']) for r in account_results]
        distribution_summary.append({
            "account": account.email,
            "emails_assigned": len(account_results),
            "email_indices": email_indices,
            "successful_sends": sum(1 for r in account_results if r['status'] == 'Email sent successfully')
        })
    
    return {
        "results": results,
        "summary": {
            "total_emails": len(request.emails),
            "total_accounts": len(request.accounts),
            "successful_sends": successful_sends,
            "distribution": distribution_summary
        }
    }

@app.get("/proxy_stats")
async def get_proxy_stats():
    """Get proxy usage statistics"""
    stats = get_proxy_statistics()
    return {
        "proxy_stats": stats,
        "timestamp": str(asyncio.get_event_loop().time())
    }

@app.post("/add_proxy")
async def add_proxy(proxy: dict):
    """Add a new proxy to the pool"""
    required_fields = ["host", "port", "username", "password"]
    if not all(field in proxy for field in required_fields):
        raise HTTPException(status_code=400, detail="Missing required proxy fields")

    # Generate proxy ID
    proxy_address = f"{proxy['host']}:{proxy['port']}"
    proxy_id = f"proxy_{hash(proxy_address) % 1000:03d}"

    new_proxy = {
        "id": proxy_id,
        "host": proxy["host"],
        "port": proxy["port"],
        "username": proxy["username"],
        "password": proxy["password"],
        "type": proxy.get("type", "socks5"),
        "country": proxy.get("country", "Unknown"),
        "status": "active",
        "last_used": None,
        "success_rate": 1.0
    }

    # Load current config and add new proxy
    try:
        with open("proxy_pool.json", 'r') as f:
            config = json.load(f)
    except FileNotFoundError:
        config = {"proxies": [], "account_mapping": {}}

    # Check if proxy already exists
    existing_proxy = next((p for p in config["proxies"] if p["host"] == proxy["host"] and p["port"] == proxy["port"]), None)
    if existing_proxy:
        raise HTTPException(status_code=400, detail="Proxy already exists")

    config["proxies"].append(new_proxy)

    with open("proxy_pool.json", 'w') as f:
        json.dump(config, f, indent=2)

    log_info(f"Added new proxy: {proxy_id} ({proxy['host']}:{proxy['port']})")
    return {"message": "Proxy added successfully", "proxy_id": proxy_id}

@app.delete("/remove_proxy/{proxy_id}")
async def remove_proxy(proxy_id: str):
    """Remove a proxy from the pool"""
    try:
        with open("proxy_pool.json", 'r') as f:
            config = json.load(f)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Proxy configuration not found")

    # Find and remove proxy
    proxy_to_remove = next((p for p in config["proxies"] if p["id"] == proxy_id), None)
    if not proxy_to_remove:
        raise HTTPException(status_code=404, detail="Proxy not found")

    config["proxies"].remove(proxy_to_remove)

    # Remove from account mappings
    accounts_to_remove = [email for email, pid in config["account_mapping"].items() if pid == proxy_id]
    for email in accounts_to_remove:
        del config["account_mapping"][email]

    with open("proxy_pool.json", 'w') as f:
        json.dump(config, f, indent=2)

    log_info(f"Removed proxy: {proxy_id}")
    return {"message": "Proxy removed successfully", "accounts_reassigned": len(accounts_to_remove)}

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

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "Gmail Browser Automation API",
        "version": "1.0.0"
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
