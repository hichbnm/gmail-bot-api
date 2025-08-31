import asyncio
import json
import os
from pathlib import Path
from typing import Dict, Optional

from playwright.async_api import async_playwright, Browser, Page, BrowserContext
import requests

# Bridge imports
import threading
import socketserver
import http.server
import socket
import socks
import select
import logging

from config import (
    BROWSER_HEADLESS, COOKIE_STORAGE_PATH, SMS_API_KEY, SMS_API_URL,
    GMAIL_LOGIN_URL, GMAIL_EMAIL_INPUT, GMAIL_PASSWORD_INPUT,
    GMAIL_NEXT_BUTTON, GMAIL_SIGNIN_BUTTON, GMAIL_TRY_ANOTHER_WAY,
    GMAIL_BACKUP_CODE_OPTION, GMAIL_BACKUP_CODE_INPUT, 
    GMAIL_BACKUP_CODE_INPUT_ALT1, GMAIL_BACKUP_CODE_INPUT_ALT2,
    GMAIL_BACKUP_CODE_INPUT_ALT3, GMAIL_BACKUP_CODE_INPUT_ALT4,
    GMAIL_BACKUP_CODE_INPUT_ALT5, GMAIL_2FA_INPUT,
    GMAIL_TRY_ANOTHER_WAY_TEXT, GMAIL_BACKUP_CODE_OPTION_TEXT,
    GMAIL_COMPOSE_BUTTON, GMAIL_COMPOSE_BUTTON_ALT1, GMAIL_COMPOSE_BUTTON_ALT2, GMAIL_COMPOSE_BUTTON_ALT3,
    GMAIL_TO_INPUT, GMAIL_SUBJECT_INPUT,
    GMAIL_BODY_INPUT, GMAIL_SEND_BUTTON, GMAIL_CHECK_PHONE_TEXT,
    GMAIL_APPROVE_DEVICE_TEXT, GMAIL_CONTINUE_BUTTON, GMAIL_NEXT_BUTTON_ALT,
    GMAIL_DEVICE_APPROVED_TEXT, USE_PROXY, USE_FIREFOX_FOR_SOCKS5, SMART_LOGIN_DETECTION
)

# HTTP-to-SOCKS5 Bridge Handler
class ProxyHTTPRequestHandler(http.server.BaseHTTPRequestHandler):
    def __init__(self, proxy_host, proxy_port, proxy_username, proxy_password, *args, **kwargs):
        self.proxy_host = proxy_host
        self.proxy_port = proxy_port
        self.proxy_username = proxy_username
        self.proxy_password = proxy_password
        super().__init__(*args, **kwargs)

    def do_CONNECT(self):
        logging.info(f'CONNECT request for {self.path}')
        # Parse the host and port
        try:
            host, port = self.path.split(':')
            port = int(port)
        except ValueError:
            self.send_error(400, 'Invalid CONNECT request')
            logging.error(f'Invalid CONNECT request: {self.path}')
            return
        # Establish connection to the target through SOCKS5
        try:
            sock = socks.socksocket()
            sock.set_proxy(socks.SOCKS5, self.proxy_host, self.proxy_port, username=self.proxy_username, password=self.proxy_password)
            sock.settimeout(10)  # Add timeout
            logging.info(f'Attempting to connect to {host}:{port} via SOCKS5')
            sock.connect((host, port))
            logging.info(f'Connected to {host}:{port} via SOCKS5')
        except Exception as e:
            self.send_error(502, f'Failed to connect: {e}')
            logging.error(f'Failed to connect to {host}:{port}: {e}')
            return
        # Send 200 Connection established
        self.send_response(200, 'Connection established')
        self.end_headers()
        # Tunnel the data
        conns = [self.connection, sock]
        try:
            while True:
                try:
                    r, w, e = select.select(conns, [], conns, 1)
                    if e:
                        logging.warning(f'Error in select for {host}:{port}')
                        break
                    if not r:
                        continue
                    for s in r:
                        other = sock if s is self.connection else self.connection
                        data = s.recv(4096)
                        if not data:
                            logging.info(f'No data received, closing tunnel for {host}:{port}')
                            break
                        other.send(data)
                    else:
                        continue
                    break
                except ConnectionResetError:
                    logging.warning(f'Connection reset for {host}:{port}')
                    break
                except Exception as e:
                    logging.error(f'Error during tunneling for {host}:{port}: {e}')
                    break
        finally:
            sock.close()
            logging.info(f'Closed connection to {host}:{port}')

    def do_GET(self):
        # For HTTP requests, use requests with socks
        import requests
        try:
            if self.path.startswith('http://'):
                url = self.path
            else:
                url = 'http://' + self.path
            logging.info(f'Proxying GET request to {url}')
            proxies = {
                'http': f'socks5h://{self.proxy_username}:{self.proxy_password}@{self.proxy_host}:{self.proxy_port}',
                'https': f'socks5h://{self.proxy_username}:{self.proxy_password}@{self.proxy_host}:{self.proxy_port}'
            }
            resp = requests.get(url, proxies=proxies, timeout=10)
            self.send_response(resp.status_code)
            for k, v in resp.headers.items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(resp.content)
            logging.info(f'Successfully proxied GET to {url}, status: {resp.status_code}')
        except Exception as e:
            self.send_error(502, f'Proxy error: {e}')
            logging.error(f'Proxy error for {url}: {e}')

# Threading HTTP Server
class ThreadingHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True

# Function to run the bridge server
def run_bridge_server(proxy_host, proxy_port, proxy_username, proxy_password):
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    
    def handler_factory(*args, **kwargs):
        return ProxyHTTPRequestHandler(proxy_host, proxy_port, proxy_username, proxy_password, *args, **kwargs)
    
    # Find an available port starting from 8888
    import socket
    port = 8888
    max_attempts = 100
    server = None
    
    for attempt in range(max_attempts):
        try:
            server = ThreadingHTTPServer(('127.0.0.1', port), handler_factory)
            print(f'HTTP-to-SOCKS5 bridge running on 127.0.0.1:{port}')
            break
        except OSError as e:
            if e.errno == 98 or e.errno == 10048:  # Address already in use
                port += 1
                continue
            else:
                raise
    
    if server is None:
        raise RuntimeError(f"Could not find an available port after {max_attempts} attempts")
    
    # Start server in a thread
    import threading
    server_thread = threading.Thread(target=server.serve_forever)
    server_thread.daemon = True
    server_thread.start()
    
    # Store the port in the server object for later retrieval
    server.bridge_port = port
    
    return server

class GmailAutomation:
    def __init__(self):
        self.playwright = None
        self.browser_direct = None  # Browser for direct connections
        self.browser_proxy = None   # Browser for proxy connections
        self.contexts: Dict[str, BrowserContext] = {}
        self.cookies_dir = Path(COOKIE_STORAGE_PATH)
        self.cookies_dir.mkdir(exist_ok=True)
        self.screenshots_dir = Path("screenshots")
        self.screenshots_dir.mkdir(exist_ok=True)
        self.bridge_server = None

    async def start(self):
        self.playwright = await async_playwright().start()

        # Launch browser for direct connections (no proxy)
        print("🌐 Launching Chromium browser for direct connections")
        direct_config = {
            "headless": BROWSER_HEADLESS,
            "args": [
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--disable-blink-features=AutomationControlled",
                "--disable-web-security",
                "--disable-features=VizDisplayCompositor",
                "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "--accept-lang=en-US,en",
                "--disable-extensions",
                "--disable-plugins",
                "--disable-images",
                "--disable-javascript-harmony-shipping",
            ],
            "proxy": None
        }
        self.browser_direct = await self.playwright.chromium.launch(**direct_config)

        # Launch browser for proxy connections
        print("🌐 Launching Chromium browser for proxy connections")
        proxy_config = {
            "headless": BROWSER_HEADLESS,
            "args": [
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--disable-blink-features=AutomationControlled",
                "--disable-web-security",
                "--disable-features=VizDisplayCompositor",
                "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "--accept-lang=en-US,en",
                "--disable-extensions",
                "--disable-plugins",
                "--disable-images",
                "--disable-javascript-harmony-shipping",
            ],
            "proxy": {"server": "http://example.com:8080"}  # Dummy global proxy for per-context support
        }
        self.browser_proxy = await self.playwright.chromium.launch(**proxy_config)

    async def stop(self):
        for context in self.contexts.values():
            await context.close()
        if self.browser_direct:
            await self.browser_direct.close()
        if self.browser_proxy:
            await self.browser_proxy.close()
        if self.playwright:
            await self.playwright.stop()

    def get_cookie_path(self, email: str) -> Path:
        return self.cookies_dir / f"{email.replace('@', '_').replace('.', '_')}.json"

    async def close_context(self, email: str):
        """Close a specific browser context for an email and any proxy-specific contexts"""
        contexts_to_close = []
        
        # Find the main context for this email
        if email in self.contexts:
            contexts_to_close.append(email)
        
        # Find any proxy-specific contexts for this email
        for context_key in list(self.contexts.keys()):
            if context_key.startswith(f"{email}_proxy_"):
                contexts_to_close.append(context_key)
        
        # Close all found contexts
        for context_key in contexts_to_close:
            try:
                await self.contexts[context_key].close()
                del self.contexts[context_key]
                print(f"✅ Closed context: {context_key}")
            except Exception as e:
                print(f"❌ Error closing context {context_key}: {e}")

    async def load_cookies(self, email: str) -> Optional[Dict]:
        cookie_file = self.get_cookie_path(email)
        if cookie_file.exists():
            with open(cookie_file, 'r') as f:
                return json.load(f)
        return None

    async def save_cookies(self, email: str, context: BrowserContext):
        cookies = await context.cookies()
        cookie_file = self.get_cookie_path(email)
        with open(cookie_file, 'w') as f:
            json.dump(cookies, f)

    async def create_context(self, email: str, proxy: Optional[Dict] = None) -> BrowserContext:
        if email in self.contexts:
            return self.contexts[email]

        context_options = {}
        
        # Choose browser based on proxy
        if proxy:
            browser = self.browser_proxy
            # Handle proxy configuration
            proxy_type = proxy.get("type", "socks5")
            print(f"🔧 Configuring {proxy_type.upper()} proxy: {proxy['host']}:{proxy['port']}")
            print(f"👤 Username: {proxy.get('username', 'None')}")

            if proxy_type.lower() == "socks5":
                print(f"🌉 Using HTTP-to-SOCKS5 bridge for proxy: {proxy['host']}:{proxy['port']}")
                # Start the bridge server
                self.bridge_server = run_bridge_server(proxy['host'], proxy['port'], proxy.get('username'), proxy.get('password'))
                # Wait for bridge to start
                import time
                time.sleep(2)
                # Configure proxy to use the bridge
                bridge_port = getattr(self.bridge_server, 'bridge_port', 8888)
                context_options["proxy"] = {
                    "server": f"http://127.0.0.1:{bridge_port}"
                }
                print(f"🌐 Bridge proxy configuration: {context_options['proxy']}")
            elif proxy_type.lower() == "http":
                print(f"🌐 Using HTTP proxy with Chromium browser")
                # Configure HTTP proxy for Playwright
                server_url = f"http://{proxy['host']}:{proxy['port']}"
                context_options["proxy"] = {
                    "server": server_url,
                    "username": proxy.get("username"),
                    "password": proxy.get("password")
                }
                print(f"🌐 HTTP proxy configuration: {context_options['proxy']}")
            else:
                print(f"⚠️  Unknown proxy type: {proxy_type}")
        else:
            browser = self.browser_direct
            print(f"🌐 Using direct connection (no proxy)")

        try:
            context = await browser.new_context(**context_options)
            print(f"✅ Browser context created successfully")
        except Exception as e:
            print(f"❌ Failed to create context: {e}")
            raise

        # Add browser-specific scripts to hide automation indicators
        await context.add_init_script("""
            // Hide automation indicators
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined,
            });
        """)

        # Load existing cookies
        # For proxy contexts, use the base email for cookie loading
        cookie_email = email.split("_proxy_")[0] if "_proxy_" in email else email
        cookies = await self.load_cookies(cookie_email)
        if cookies:
            await context.add_cookies(cookies)
            print(f"✅ Loaded {len(cookies)} cookies for {cookie_email}")
        else:
            print(f"⚠️  No cookies found for {cookie_email}")

        # Store context for reuse (except for proxy contexts)
        if "_proxy_" not in email:
            self.contexts[email] = context
        return context

    def stop_bridge(self):
        if self.bridge_server:
            print("Stopping HTTP-to-SOCKS5 bridge...")
            self.bridge_server.shutdown()
            self.bridge_server = None
            print("Bridge stopped.")

    async def login_gmail(self, email: str, browser_pass: str, backup_code: Optional[str] = None,
                         proxy: Optional[Dict] = None) -> bool:
        context = await self.create_context(email, proxy)
        page = await context.new_page()

        try:
            print(f"  🌐 Navigating to Gmail login page...")
            await page.goto(GMAIL_LOGIN_URL)
            await page.wait_for_timeout(2000)  # Wait for page to load

            # Debug: Take screenshot of initial page
            await page.screenshot(path=f"screenshots/debug_initial_page_{email}.png")

            # 🔍 Check if account is already logged in (redirects to myaccount.google.com)
            current_url = page.url
            print(f"  📍 Initial URL: {current_url}")

            if "myaccount.google.com" in current_url:
                print(f"  🔍 Detected Google Account page - checking if Gmail access is available...")
                print(f"  📧 Account {email} might be authenticated - verifying Gmail access")

                # Instead of assuming logged in, actually verify Gmail access
                print(f"  📧 Testing Gmail access...")
                await page.goto("https://mail.google.com")
                await page.wait_for_timeout(3000)

                gmail_url = page.url
                if "mail.google.com" in gmail_url:
                    print(f"  ✅ Successfully accessed Gmail - checking interface...")

                    # Check multiple Gmail compose button selectors
                    compose_selectors = [
                        GMAIL_COMPOSE_BUTTON,
                        GMAIL_COMPOSE_BUTTON_ALT1,
                        GMAIL_COMPOSE_BUTTON_ALT2,
                        GMAIL_COMPOSE_BUTTON_ALT3
                    ]

                    compose_count = 0
                    for selector in compose_selectors:
                        try:
                            count = await page.locator(selector).count()
                            if count > 0:
                                compose_count = count
                                print(f"  ✅ Found compose button with selector: {selector} ({count})")
                                break
                        except:
                            pass

                    if compose_count > 0:
                        print(f"  ✅ Gmail interface confirmed - account was already logged in")
                        await page.screenshot(path=f"screenshots/already_logged_in_success_{email}.png")
                        await self.save_cookies(email, context)
                        return True
                    else:
                        print(f"  ⚠️ Gmail URL reached but compose button not found - not fully logged in")
                        # Continue with normal login flow
                        print(f"  🔄 Proceeding with normal login flow...")
                else:
                    print(f"  ❌ Could not access Gmail, current URL: {gmail_url}")
                    print(f"  🔄 Proceeding with normal login flow...")
                    # Continue with normal login flow

            # Check if email input field is present (normal login flow)
            email_input_count = await page.locator(GMAIL_EMAIL_INPUT).count()
            if email_input_count == 0:
                print(f"  ⚠️ Email input field not found - unexpected page")
                await page.screenshot(path=f"screenshots/no_email_input_{email}.png")
                return False

            # Check if email is already pre-filled (account might be partially logged in)
            try:
                email_value = await page.locator(GMAIL_EMAIL_INPUT).first.input_value()
                if email_value and email_value.strip():
                    print(f"  📧 Email already pre-filled: {email_value}")
                    if email_value != email:
                        print(f"  ⚠️ Pre-filled email ({email_value}) doesn't match target email ({email})")
                        # Clear and re-enter the correct email
                        await page.locator(GMAIL_EMAIL_INPUT).first.clear()
                        await page.fill(GMAIL_EMAIL_INPUT, email)
                        print(f"  ✏️ Corrected email to: {email}")
            except:
                pass

            print(f"  ✉️ Starting normal login flow...")
            await page.fill(GMAIL_EMAIL_INPUT, email)
            await page.click(GMAIL_NEXT_BUTTON)
            await page.wait_for_timeout(3000)

            # Debug: Take screenshot after email entry
            await page.screenshot(path=f"screenshots/debug_after_email_{email}.png")

            # 🔍 SMART LOGIN DETECTION: Check if already logged in
            print(f"  🔍 Checking if account is already logged in...")
            await page.wait_for_timeout(2000)  # Brief wait for any redirect

            current_url = page.url
            print(f"  📍 URL after email entry: {current_url}")

            # Check if redirected to Google Account page (might be logged in)
            if "myaccount.google.com" in current_url:
                print(f"  🔍 Detected Google Account page after email entry - verifying Gmail access...")

                # Instead of assuming logged in, actually verify Gmail access
                try:
                    print(f"  📧 Testing Gmail access...")
                    await page.goto("https://mail.google.com")
                    await page.wait_for_timeout(5000)  # Increased wait time

                    # Take screenshot to see what's loaded
                    await page.screenshot(path=f"screenshots/gmail_loaded_{email}.png")

                    gmail_url = page.url
                    if "mail.google.com" in gmail_url:
                        print(f"  ✅ Successfully accessed Gmail - checking interface...")

                        # Check multiple Gmail compose button selectors
                        compose_selectors = [
                            GMAIL_COMPOSE_BUTTON,
                            GMAIL_COMPOSE_BUTTON_ALT1,
                            GMAIL_COMPOSE_BUTTON_ALT2,
                            GMAIL_COMPOSE_BUTTON_ALT3
                        ]

                        compose_count = 0
                        for selector in compose_selectors:
                            try:
                                count = await page.locator(selector).count()
                                if count > 0:
                                    compose_count = count
                                    print(f"  ✅ Found compose button with selector: {selector} ({count})")
                                    break
                            except:
                                pass

                        if compose_count > 0:
                            print(f"  ✅ Gmail interface confirmed - account was already logged in")
                            await page.screenshot(path=f"screenshots/already_logged_in_success_{email}.png")
                            await self.save_cookies(email, context)
                            return True
                        else:
                            print(f"  ⚠️ Gmail URL reached but compose button not found - not fully logged in")
                            # Check for other Gmail indicators
                            inbox_indicators = [
                                "[role='main']",
                                "[data-message-store]",
                                "text=/Inbox/i",
                                "[aria-label*='Inbox']"
                            ]

                            gmail_confirmed = False
                            for indicator in inbox_indicators:
                                try:
                                    if "text=" in indicator:
                                        text = indicator.replace("text=", "").replace("/i", "")
                                        count = await page.get_by_text(text).count()
                                        print(f"  📊 Text indicator '{text}': {count}")
                                    else:
                                        count = await page.locator(indicator).count()
                                        print(f"  📊 Selector indicator '{indicator}': {count}")
                                    if count > 0:
                                        gmail_confirmed = True
                                        print(f"  ✅ Found Gmail indicator: {indicator}")
                                        break
                                except Exception as e:
                                    print(f"  ⚠️ Error checking indicator {indicator}: {e}")

                            if gmail_confirmed:
                                print(f"  ✅ Gmail interface confirmed via indicators - account was already logged in")
                                await page.screenshot(path=f"screenshots/already_logged_in_success_{email}.png")
                                await self.save_cookies(email, context)
                                return True
                            else:
                                print(f"  ⚠️ Gmail URL reached but interface not fully loaded - continuing with login")
                                await page.screenshot(path=f"screenshots/already_logged_in_no_interface_{email}.png")
                                # Continue with normal login flow
                    else:
                        print(f"  ❌ Could not access Gmail, current URL: {gmail_url}")
                        await page.screenshot(path=f"screenshots/already_logged_in_no_gmail_{email}.png")
                        # Continue with normal login flow
                except Exception as e:
                    print(f"  ❌ Error testing Gmail access: {e}")
                    await page.screenshot(path=f"screenshots/already_logged_in_error_{email}.png")
                    # Continue with normal login flow

            # Check if directly redirected to Gmail (already logged in)
            elif "mail.google.com" in current_url:
                print(f"  🎉 DIRECT GMAIL ACCESS!")
                print(f"  📧 Account {email} has direct Gmail access")

                # Verify Gmail interface
                compose_selectors = [
                    GMAIL_COMPOSE_BUTTON,
                    GMAIL_COMPOSE_BUTTON_ALT1,
                    GMAIL_COMPOSE_BUTTON_ALT2,
                    GMAIL_COMPOSE_BUTTON_ALT3
                ]

                compose_found = False
                for selector in compose_selectors:
                    try:
                        count = await page.locator(selector).count()
                        if count > 0:
                            compose_found = True
                            print(f"  ✅ Found compose button with selector: {selector}")
                            break
                    except:
                        pass

                if compose_found:
                    print(f"  ✅ Gmail interface confirmed - saving cookies")
                    await page.screenshot(path=f"screenshots/direct_gmail_success_{email}.png")
                    await self.save_cookies(email, context)
                    return True
                else:
                    print(f"  ⚠️ Gmail URL detected but compose button not found")
                    await page.screenshot(path=f"screenshots/direct_gmail_no_compose_{email}.png")

            # If not already logged in, proceed with password entry
            print(f"  🔄 Account not already logged in, proceeding with password entry...")

            # Enhanced password field detection with multiple attempts
            print(f"  🔍 Looking for password field...")
            password_found = False
            max_attempts = 3

            for attempt in range(max_attempts):
                print(f"  🔄 Password field detection attempt {attempt + 1}/{max_attempts}")

                # Wait for page to stabilize
                await page.wait_for_timeout(2000)

                # Check current URL to understand what page we're on
                current_url = page.url
                print(f"  📍 Current URL: {current_url}")

                # Take screenshot for debugging
                await page.screenshot(path=f"screenshots/debug_password_attempt_{attempt + 1}_{email}.png")

                # Check if password field appears
                password_field_count = await page.locator(GMAIL_PASSWORD_INPUT).count()
                print(f"  🔑 Password field count: {password_field_count}")

                if password_field_count > 0:
                    password_found = True
                    print(f"  ✅ Password field found on attempt {attempt + 1}")
                    break
                else:
                    print(f"  ❌ Password field not found on attempt {attempt + 1}")

                    # Check if we're on a different page that might need handling
                    if "challenge" in current_url or "verify" in current_url:
                        print(f"  ⚠️ Detected verification/challenge page: {current_url}")
                        print(f"  💡 This might require manual intervention or different handling")
                        await page.screenshot(path=f"screenshots/verification_page_{email}.png")
                        return False

                    # Check for "Forgot password?" or other recovery options
                    recovery_selectors = [
                        "text=/Forgot password/i",
                        "text=/Reset password/i",
                        "text=/Recover account/i",
                        "[href*='recovery']",
                        "[href*='forgot']"
                    ]

                    recovery_found = False
                    for selector in recovery_selectors:
                        try:
                            if "text=" in selector:
                                text = selector.replace("text=", "").replace("/i", "")
                                count = await page.get_by_text(text).count()
                            else:
                                count = await page.locator(selector).count()

                            if count > 0:
                                print(f"  ⚠️ Recovery option found: {selector}")
                                recovery_found = True
                                break
                        except:
                            pass

                    if recovery_found:
                        print(f"  ❌ Account recovery required - cannot proceed automatically")
                        await page.screenshot(path=f"screenshots/recovery_required_{email}.png")
                        return False

                    # If not the last attempt, wait longer and try again
                    if attempt < max_attempts - 1:
                        print(f"  ⏳ Waiting longer for password field to appear...")
                        await page.wait_for_timeout(3000)

            if not password_found:
                print(f"  ❌ Password field not found after {max_attempts} attempts")
                print(f"  💡 This might indicate:")
                print(f"     - Account requires additional verification")
                print(f"     - Gmail UI has changed")
                print(f"     - Network/proxy issues")
                await page.screenshot(path=f"screenshots/password_field_not_found_{email}.png")
                return False

            # Check if it's device approval flow
            check_phone_count = await page.get_by_text(GMAIL_CHECK_PHONE_TEXT).count()
            approve_device_count = await page.get_by_text(GMAIL_APPROVE_DEVICE_TEXT).count()

            print(f"Login flow detection for {email}:")
            print(f"  Password field: ✅ Found")
            print(f"  Check phone text: {check_phone_count}")
            print(f"  Approve device text: {approve_device_count}")

            if check_phone_count > 0 or approve_device_count > 0:
                print(f"  📱 Device approval required for {email}")
                print(f"  💡 Please approve the device on your phone")
                await page.screenshot(path=f"screenshots/device_approval_required_{email}.png")
                return False

            # Traditional login flow: email -> password -> 2FA
            print(f"  → Traditional login flow detected")
            print(f"  🔑 Entering password...")

            # Take screenshot before password entry
            await page.screenshot(path=f"screenshots/debug_before_password_{email}.png")

            # Wait for password field to be ready
            try:
                await page.wait_for_selector(GMAIL_PASSWORD_INPUT, timeout=10000)
                print(f"  ✅ Password field is ready")
            except:
                print(f"  ❌ Password field not found or not ready")
                await page.screenshot(path=f"screenshots/debug_password_field_missing_{email}.png")
                return False

            # Enter password
            try:
                await page.fill(GMAIL_PASSWORD_INPUT, browser_pass)
                print(f"  ✅ Password entered")
                await page.screenshot(path=f"screenshots/debug_after_password_{email}.png")
            except Exception as e:
                print(f"  ❌ Failed to enter password: {e}")
                await page.screenshot(path=f"screenshots/debug_password_error_{email}.png")
                return False

            # Click sign in button
            try:
                await page.click(GMAIL_SIGNIN_BUTTON)
                print(f"  ✅ Sign in button clicked")
                await page.screenshot(path=f"screenshots/debug_after_signin_click_{email}.png")
            except Exception as e:
                print(f"  ❌ Failed to click sign in: {e}")
                await page.screenshot(path=f"screenshots/debug_signin_error_{email}.png")
                return False

            # Wait for next page to load (either 2FA or success)
            print(f"  ⏳ Waiting for next page...")
            await page.wait_for_timeout(5000)

            # Take screenshot of what comes next
            await page.screenshot(path=f"screenshots/debug_after_password_submit_{email}.png")

            # Check for error messages
            error_selectors = [
                "[role='alert']",
                ".error",
                ".errormsg",
                "[aria-label*='error']",
                "[aria-label*='Error']",
                "text=/error/i",
                "text=/invalid/i",
                "text=/wrong/i",
                "text=/incorrect/i"
            ]

            error_found = False
            for selector in error_selectors:
                try:
                    if "text=" in selector:
                        text = selector.replace("text=", "").replace("/i", "")
                        count = await page.get_by_text(text).count()
                    else:
                        count = await page.locator(selector).count()

                    if count > 0:
                        print(f"  ❌ Error found with selector '{selector}': {count}")
                        error_found = True
                        # Get the error text
                        if "text=" in selector:
                            error_text = await page.get_by_text(text).text_content()
                        else:
                            error_text = await page.locator(selector).first.text_content()
                        print(f"     Error message: {error_text}")
                        await page.screenshot(path=f"screenshots/debug_password_error_{email}.png")
                        return False
                except:
                    pass

            if not error_found:
                print(f"  ✅ No password errors found")

            # 🔍 DIRECT LOGIN DETECTION: Check if Gmail opens immediately after password
            if SMART_LOGIN_DETECTION:
                print(f"  🔍 Checking for direct Gmail access...")
                await page.wait_for_timeout(2000)  # Brief wait for redirect

                current_url = page.url
                print(f"  📍 Current URL after password: {current_url}")

                # Check if we've been redirected directly to Gmail (no 2FA required)
                if "mail.google.com" in current_url:
                    print(f"  🎉 DIRECT LOGIN SUCCESS! Gmail opened without 2FA")
                    print(f"  📧 Account {email} logged in directly")

                    # Verify we're actually in Gmail by checking for Gmail elements
                    compose_count = await page.locator(GMAIL_COMPOSE_BUTTON).count()
                    inbox_indicators = [
                        "[role='main']",
                        "[data-message-store]",
                        "text=/Inbox/i",
                        "[aria-label*='Inbox']"
                    ]

                    gmail_confirmed = compose_count > 0
                    if not gmail_confirmed:
                        for indicator in inbox_indicators:
                            try:
                                if "text=" in indicator:
                                    text = indicator.replace("text=", "").replace("/i", "")
                                    count = await page.get_by_text(text).count()
                                else:
                                    count = await page.locator(indicator).count()
                                if count > 0:
                                    gmail_confirmed = True
                                    break
                            except:
                                pass

                    if gmail_confirmed:
                        print(f"  ✅ Gmail interface confirmed - saving cookies")
                        await page.screenshot(path=f"screenshots/direct_login_success_{email}.png")
                        await self.save_cookies(email, context)
                        return True
                    else:
                        print(f"  ⚠️ Redirected to Gmail URL but Gmail interface not loaded yet")
                        # Continue with normal flow

                # Check for Google Account page redirect after password
                elif "myaccount.google.com" in current_url:
                    print(f"  🔄 Redirected to Google Account page after password")
                    print(f"  📧 Attempting to navigate to Gmail...")

                    try:
                        await page.goto("https://mail.google.com")
                        await page.wait_for_timeout(5000)  # Increased wait time

                        gmail_url = page.url
                        if "mail.google.com" in gmail_url:
                            print(f"  ✅ Successfully navigated to Gmail from account page")

                            # Take screenshot to see what's loaded
                            await page.screenshot(path=f"screenshots/gmail_loaded_{email}.png")

                            # Wait a bit more and check again
                            await page.wait_for_timeout(3000)

                            # Check multiple Gmail compose button selectors
                            compose_selectors = [
                                GMAIL_COMPOSE_BUTTON,
                                GMAIL_COMPOSE_BUTTON_ALT1,
                                GMAIL_COMPOSE_BUTTON_ALT2,
                                GMAIL_COMPOSE_BUTTON_ALT3
                            ]

                            compose_count = 0
                            for selector in compose_selectors:
                                try:
                                    count = await page.locator(selector).count()
                                    if count > 0:
                                        compose_count = count
                                        print(f"  ✅ Found compose button with selector: {selector} ({count})")
                                        break
                                except:
                                    pass

                            print(f"  📊 Compose button count: {compose_count}")

                            # Initialize gmail_loaded based on compose button
                            gmail_loaded = compose_count > 0

                            # If compose button not found, check other Gmail indicators
                            if not gmail_loaded:
                                inbox_indicators = [
                                    "[role='main']",
                                    "[data-message-store]",
                                    "text=/Inbox/i",
                                    "[aria-label*='Inbox']",
                                    "text=/Compose/i",
                                    "[href*='compose']",
                                    ".bkK"
                                ]

                                for indicator in inbox_indicators:
                                    try:
                                        if "text=" in indicator:
                                            text = indicator.replace("text=", "").replace("/i", "")
                                            count = await page.get_by_text(text).count()
                                            print(f"  📊 Text indicator '{text}': {count}")
                                        else:
                                            count = await page.locator(indicator).count()
                                            print(f"  📊 Selector indicator '{indicator}': {count}")
                                        if count > 0:
                                            gmail_loaded = True
                                            print(f"  ✅ Found Gmail indicator: {indicator}")
                                            break
                                    except Exception as e:
                                        print(f"  ⚠️ Error checking indicator {indicator}: {e}")

                            if gmail_loaded:
                                print(f"  ✅ Gmail interface confirmed - saving cookies")
                                await page.screenshot(path=f"screenshots/password_account_page_success_{email}.png")
                                await self.save_cookies(email, context)
                                return True
                            else:
                                print(f"  ⚠️ Gmail URL reached but interface not fully loaded")
                                print(f"  💡 This might be a loading issue or UI change")
                                # Don't return False here, let it continue to 2FA check
                        else:
                            print(f"  ❌ Failed to reach Gmail, current URL: {gmail_url}")
                    except Exception as e:
                        print(f"  ❌ Error navigating to Gmail: {e}")
                else:
                    print(f"  🚫 Smart login detection disabled")

                # Check for 2FA if direct login didn't succeed
                print(f"  🔐 Checking for 2FA requirements...")
                await page.wait_for_timeout(3000)  # Wait for 2FA screen to load

                # Debug: Take screenshot to see what's on the page
                await page.screenshot(path=f"screenshots/debug_2fa_{email}.png")

                # Look for 2FA challenge
                try_another_way_count = await page.locator(GMAIL_TRY_ANOTHER_WAY).count()
                try_another_way_text_count = await page.get_by_text(GMAIL_TRY_ANOTHER_WAY_TEXT).count()
                phone_input_count = await page.locator(GMAIL_2FA_INPUT).count()

                print(f"2FA Debug for {email}:")
                print(f"  Try another way button: {try_another_way_count}")
                print(f"  Try another way text: {try_another_way_text_count}")
                print(f"  Phone input: {phone_input_count}")

                if try_another_way_count > 0 or try_another_way_text_count > 0:
                    print(f"2FA required for {email}, trying backup code...")

                    # Try primary selector first, then text-based
                    if try_another_way_count > 0:
                        await page.click(GMAIL_TRY_ANOTHER_WAY)
                    else:
                        await page.get_by_text(GMAIL_TRY_ANOTHER_WAY_TEXT).click()

                    await page.wait_for_timeout(2000)

                    # Take screenshot after clicking
                    await page.screenshot(path=f"screenshots/debug_options_{email}.png")

                    # Take screenshot after clicking "Try another way"
                    await page.screenshot(path=f"screenshots/after_try_another_way_{email}.png")

                    # Debug: Look for all clickable elements that might be backup code options
                    print(f"  🔍 Looking for backup code option elements...")

                    # Try multiple selectors for backup code option
                    backup_option_selectors = [
                        GMAIL_BACKUP_CODE_OPTION,  # "li[data-value='backupCode']"
                        "[data-value='backupCode']",
                        "[data-challengetype='backupCode']",
                        "li:contains('Backup codes')",
                        "div:contains('Backup codes')",
                        "button:contains('Backup codes')",
                        "[role='button']:contains('Backup codes')",
                        "[role='option']:contains('Backup codes')"
                    ]

                    backup_option_found = False
                    clicked_element = None

                    for selector in backup_option_selectors:
                        try:
                            if ":contains(" in selector:
                                # Text-based selector
                                text = selector.split(":contains('")[1].rstrip("')")
                                count = await page.get_by_text(text).count()
                                print(f"  📊 Text selector '{selector}': {count}")
                                if count > 0:
                                    print(f"  ✅ Found backup code option with text selector: {selector}")
                                    await page.get_by_text(text).first.click()
                                    backup_option_found = True
                                    clicked_element = f"text: {text}"
                                    break
                            else:
                                # CSS selector
                                count = await page.locator(selector).count()
                                print(f"  📊 CSS selector '{selector}': {count}")
                                if count > 0:
                                    print(f"  ✅ Found backup code option with CSS selector: {selector}")
                                    await page.locator(selector).first.click()
                                    backup_option_found = True
                                    clicked_element = f"css: {selector}"
                                    break
                        except Exception as e:
                            print(f"  ⚠️ Error with selector {selector}: {e}")

                    if not backup_option_found:
                        print(f"  ❌ No backup code option found with any selector")
                        print(f"  � Available clickable elements:")

                        # Debug: Find all clickable elements
                        clickable_selectors = [
                            "button",
                            "[role='button']",
                            "a",
                            "[role='link']",
                            "li",
                            "[role='option']"
                        ]

                        for clickable in clickable_selectors:
                            try:
                                elements = await page.locator(clickable).all()
                                if len(elements) > 0:
                                    print(f"  � {len(elements)} {clickable} elements found")
                                    for i, elem in enumerate(elements[:5]):  # Show first 5
                                        try:
                                            text = await elem.text_content()
                                            if text and text.strip():
                                                print(f"    {i+1}. {clickable}: '{text.strip()}'")
                                        except:
                                            pass
                            except:
                                pass

                        await page.screenshot(path=f"screenshots/no_backup_option_found_{email}.png")
                        return False

                    print(f"  ✅ Clicked backup code option using: {clicked_element}")
                    print(f"  ⏳ Waiting for backup code input page to load...")
                    await page.wait_for_timeout(3000)  # Increased wait time

                    # Take screenshot after clicking backup code option
                    await page.screenshot(path=f"screenshots/after_backup_option_click_{email}.png")

                    # Check current URL after clicking
                    current_url = page.url
                    print(f"  📍 URL after clicking backup code option: {current_url}")

                    # Check if the page actually changed (we should no longer see "Try another way")
                    try_another_way_after_click = await page.get_by_text(GMAIL_TRY_ANOTHER_WAY_TEXT).count()
                    print(f"  📊 'Try another way' still visible after click: {try_another_way_after_click}")

                    if try_another_way_after_click > 0:
                        print(f"  ℹ️ 'Try another way' still visible - this is normal when backup code page loads")
                    # Take screenshot for debugging but don't fail
                    await page.screenshot(path=f"screenshots/backup_option_clicked_{email}.png")

                    # Try different selectors for backup code input (be more specific)
                    backup_selectors = [
                        GMAIL_BACKUP_CODE_INPUT,  # "input[type='tel'][aria-label='Enter a backup code']" - PRIMARY
                        GMAIL_BACKUP_CODE_INPUT_ALT1,  # "input[id='backupCodePin']" - BACKUP
                        GMAIL_BACKUP_CODE_INPUT_ALT2,  # "input[name='Pin']" - BACKUP
                        GMAIL_BACKUP_CODE_INPUT_ALT3,  # "input[aria-label='Enter a backup code']" - BACKUP
                        GMAIL_BACKUP_CODE_INPUT_ALT4,  # "input[type='tel']" - FALLBACK
                        "input[type='password']",  # Sometimes backup codes use password field
                        "input[placeholder*='backup']",
                        "input[placeholder*='code']",
                        "input[name*='backup']",
                        "input[name*='code']",
                        "input[id*='backup']",
                        "input[id*='code']",
                        "input[aria-label*='backup']",
                        "input[aria-label*='code']",
                        "input[data-initial-value]",  # Gmail sometimes uses this
                        "input[type='text']:not([type='hidden'])",  # Explicit text inputs only
                        "input:not([type='hidden']):not([type='tel']):not([type='checkbox']):not([type='radio']):not([type='submit']):not([type='button'])"  # Last resort, exclude more types
                    ]

                    print(f"  🔍 Looking for backup code input field...")
                    print(f"  📋 Will try {len(backup_selectors)} different selectors")
                    
                    # DEBUG: List all input fields on the page for analysis
                    print(f"  🔧 DEBUG: Analyzing all input fields on backup code page...")
                    all_inputs = await page.locator("input").all()
                    print(f"  📊 Total input fields found: {len(all_inputs)}")
                    
                    for i, inp in enumerate(all_inputs):
                        input_type = await inp.get_attribute("type") or "text"
                        input_id = await inp.get_attribute("id") or ""
                        input_name = await inp.get_attribute("name") or ""
                        input_placeholder = await inp.get_attribute("placeholder") or ""
                        input_class = await inp.get_attribute("class") or ""
                        input_aria_label = await inp.get_attribute("aria-label") or ""
                        input_data_value = await inp.get_attribute("data-initial-value") or ""
                        is_visible = await inp.is_visible()
                        is_enabled = await inp.is_enabled()
                        
                        print(f"  🔍 Input {i}: type='{input_type}' id='{input_id}' name='{input_name}' placeholder='{input_placeholder}'")
                        print(f"      class='{input_class}' aria-label='{input_aria_label}' data-initial-value='{input_data_value}'")
                        print(f"      visible={is_visible} enabled={is_enabled}")
                    
                    # Take a detailed screenshot for manual inspection
                    await page.screenshot(path=f"screenshots/backup_page_analysis_{email}.png")
                    print(f"  📸 Screenshot saved: screenshots/backup_page_analysis_{email}.png")
                    
                    backup_input = None
                    for selector in backup_selectors:
                        count = await page.locator(selector).count()
                        print(f"  📊 Selector '{selector}': {count} elements found")
                        if count > 0:
                            print(f"  ✅ Found input with selector '{selector}': {count}")
                            candidate_input = page.locator(selector).first

                            # Validate the candidate input
                            input_type = await candidate_input.get_attribute("type")
                            input_tag = await candidate_input.evaluate("el => el.tagName")

                            if input_type in ["checkbox", "radio", "submit", "button"]:
                                print(f"  ⚠️ Skipping {input_type} input - not fillable")
                                continue
                            elif input_tag != "INPUT":
                                print(f"  ⚠️ Skipping {input_tag} element - not an input")
                                continue
                            else:
                                is_visible = await candidate_input.is_visible()
                                is_enabled = await candidate_input.is_enabled()

                                if is_visible and is_enabled:
                                    backup_input = candidate_input
                                    print(f"  ✅ Selected valid backup input with selector: {selector}")

                                    # 🎯 DIRECT BACKUP CODE ENTRY - Enter immediately after finding valid input
                                    if backup_code and selector == GMAIL_BACKUP_CODE_INPUT:
                                        print(f"  🎯 DIRECT ENTRY: Found primary selector, entering backup code immediately!")
                                        print(f"  🔑 Entering backup code: {backup_code}")

                                        try:
                                            await backup_input.focus()
                                            await page.wait_for_timeout(300)
                                            await backup_input.clear()
                                            await page.wait_for_timeout(200)

                                            # Type each character with small delay
                                            for char in backup_code:
                                                await backup_input.type(char)
                                                await page.wait_for_timeout(100)

                                            await page.wait_for_timeout(500)
                                            print(f"  ✅ Backup code entered, pressing Enter...")
                                            await page.keyboard.press("Enter")
                                            await page.wait_for_timeout(3000)

                                            # Check if login successful
                                            current_url = page.url
                                            print(f"  📍 URL after backup code: {current_url}")

                                            if "mail.google.com" in current_url:
                                                print(f"  ✅ Successfully logged in with backup code!")
                                                await self.save_cookies(email, context)
                                                return True
                                            elif "myaccount.google.com" in current_url:
                                                print(f"  🔄 Redirected to account page, navigating to Gmail...")
                                                await page.goto("https://mail.google.com")
                                                await page.wait_for_timeout(3000)
                                                if "mail.google.com" in page.url:
                                                    print(f"  ✅ Successfully navigated to Gmail!")
                                                    await self.save_cookies(email, context)
                                                    return True

                                            # Take screenshot for debugging
                                            await page.screenshot(path=f"screenshots/backup_code_entered_{email}.png")

                                        except Exception as e:
                                            print(f"  ❌ Error entering backup code: {e}")
                                            await page.screenshot(path=f"screenshots/backup_code_error_{email}.png")
                                            return False

                                    break
                                else:
                                    print(f"  ⚠️ Input not visible/enabled - trying next selector")
                                    continue

                        # If no valid input found with specific selectors, try a broader search
                        if not backup_input:
                            print(f"  🔄 No valid backup input found with specific selectors - trying broader search")
                            all_text_inputs = await page.locator("input[type='text'], input[type='password'], input:not([type])").all()

                            for i, input_elem in enumerate(all_text_inputs):
                                input_type = await input_elem.get_attribute("type") or "text"
                                input_placeholder = await input_elem.get_attribute("placeholder") or ""
                                input_name = await input_elem.get_attribute("name") or ""

                                print(f"  Checking input {i}: type={input_type}, placeholder='{input_placeholder}', name='{input_name}'")

                                if input_type in ["text", "password", ""]:
                                    is_visible = await input_elem.is_visible()
                                    is_enabled = await input_elem.is_enabled()

                                    if is_visible and is_enabled:
                                        backup_input = input_elem
                                        print(f"  ✅ Found valid backup input: type={input_type}, placeholder='{input_placeholder}'")
                                        break

                        # Check if we ended up on a phone verification page instead of backup code page
                        if not backup_input:
                            print(f"  🔍 Checking if this is actually a phone verification page...")
                            phone_input_count = await page.locator("input[type='tel']").count()
                            pin_input_count = await page.locator("input[name='Pin']").count()
                            
                            print(f"  📊 Phone inputs: {phone_input_count}, PIN inputs: {pin_input_count}")
                            
                            # Only consider it phone verification if we have phone inputs AND no backup-related elements
                            backup_related_elements = await page.locator("input[aria-label='Enter a backup code'], input[id='backupCodePin'], input[name='Pin'][aria-label='Enter a backup code']").count()
                            print(f"  � Backup-related inputs: {backup_related_elements}")
                            
                            if phone_input_count > 0 and pin_input_count > 0 and backup_related_elements == 0:
                                print(f"  📱 Detected phone verification page after clicking backup code option")
                                print(f"  ❌ Phone verification required - cannot proceed with backup code")
                                print(f"  💡 Please complete phone verification manually or use a different account")
                                await page.screenshot(path=f"screenshots/phone_verification_required_{email}.png")
                                return False
                            elif phone_input_count > 0 and backup_related_elements > 0:
                                print(f"  ℹ️ Found phone input with backup attributes - this is the backup code field, continuing...")
                            else:
                                print(f"  ℹ️ Found phone/PIN inputs but also backup-related elements - likely backup code page")

                        if backup_input:
                            # Validate that we have a proper input field
                            input_type = await backup_input.get_attribute("type")
                            input_tag = await backup_input.evaluate("el => el.tagName")
                            input_name = await backup_input.get_attribute("name") or ""
                            input_id = await backup_input.get_attribute("id") or ""

                            print(f"  📝 Selected input - Type: {input_type}, Tag: {input_tag}, Name: '{input_name}', ID: '{input_id}'")

                            # Check if this is actually a fillable input
                            if input_type in ["checkbox", "radio", "submit", "button"]:
                                print(f"  ❌ Cannot fill input of type '{input_type}' - looking for another input")
                                backup_input = None
                            elif input_tag != "INPUT":
                                print(f"  ❌ Selected element is not an INPUT tag ({input_tag}) - looking for another input")
                                backup_input = None
                            else:
                                # Get the input element and check if it's visible
                                is_visible = await backup_input.is_visible()
                                is_enabled = await backup_input.is_enabled()

                                print(f"  Backup input visible: {is_visible}")
                                print(f"  Backup input enabled: {is_enabled}")

                                if not is_visible or not is_enabled:
                                    print(f"  ❌ Backup input not visible/enabled - looking for another input")
                                    backup_input = None

                        # Check if we ended up on a phone verification page instead of backup code page
                        # Check if we ended up on a phone verification page instead of backup code page
                else:
                    print(f"Backup code option not found for {email}")
                    # Check for phone verification as fallback
                    if phone_input_count > 0:
                        print(f"Phone verification required for {email} (no backup code option found)")
                        return False
                    return False

                # Success check for traditional login flow (password + 2FA)
            print(f"  Checking login success for traditional flow...")
            await page.wait_for_timeout(3000)

            current_url = page.url
            print(f"  Current URL: {current_url}")

            # Check if redirected to Google Account page
            if "myaccount.google.com" in current_url:
                print(f"  🔄 Redirected to Google Account page, navigating to Gmail...")
                await page.goto("https://mail.google.com")
                await page.wait_for_timeout(3000)

                # Check if Gmail loaded successfully
                gmail_url = page.url
                if "mail.google.com" in gmail_url:
                    print(f"  ✅ Successfully navigated to Gmail: {gmail_url}")
                    await self.save_cookies(email, context)
                    return True
                else:
                    print(f"  ❌ Failed to navigate to Gmail, current URL: {gmail_url}")

            # Check if already on Gmail
            if "mail.google.com" in current_url:
                print(f"  ✅ Already on Gmail: {current_url}")
                await self.save_cookies(email, context)
                return True

                # Check for Gmail elements
                compose_count = await page.locator(GMAIL_COMPOSE_BUTTON).count()
                if compose_count > 0:
                    print(f"  ✅ Found compose button - login successful!")
                    await self.save_cookies(email, context)
                    return True
                # Device approval flow: email -> approve on phone -> continue
                print(f"  → Device approval flow detected")
                print(f"  ⏳ Waiting for device approval... (you can approve on your phone now)")

                # Wait for approval and automatic redirect to Gmail
                max_wait_time = 120000  # 2 minutes for user to approve
                wait_interval = 2000   # Check every 2 seconds
                elapsed = 0

                while elapsed < max_wait_time:
                    try:
                        current_url = page.url

                        # Check if we've been automatically redirected to Gmail (approval successful)
                        if "mail.google.com" in current_url:
                            print(f"  ✅ Auto-detected Gmail redirect - approval successful!")
                            print(f"  📍 Current URL: {current_url}")
                            await self.save_cookies(email, context)
                            return True

                        # Check for Gmail-specific elements that appear after login
                        gmail_indicators = [
                            GMAIL_COMPOSE_BUTTON,  # Compose button
                            "[role='main']",  # Main Gmail content area
                            "[data-message-store]",  # Gmail message store
                            "[aria-label*='Inbox']",  # Inbox aria label
                            "text=/Inbox/i",  # Inbox text
                        ]

                        for indicator in gmail_indicators:
                            try:
                                if "text=" in indicator:
                                    text = indicator.replace("text=", "").replace("/i", "")
                                    count = await page.get_by_text(text).count()
                                else:
                                    count = await page.locator(indicator).count()

                                if count > 0:
                                    print(f"  ✅ Found Gmail element: {indicator} ({count})")
                                    print(f"  💾 Saving cookies for {email}")
                                    await self.save_cookies(email, context)
                                    return True
                            except:
                                pass

                        # Check for continue/next buttons (in case approval happened but redirect didn't)
                        continue_buttons = [
                            GMAIL_CONTINUE_BUTTON,
                            GMAIL_NEXT_BUTTON_ALT,
                            "button[data-primary-action-label*='Continue']",
                            "button[data-primary-action-label*='Next']",
                            "[role='button']:contains('Continue')",
                            "[role='button']:contains('Next')"
                        ]

                        for button_selector in continue_buttons:
                            try:
                                if ":contains(" in button_selector:
                                    text = button_selector.split(":contains('")[1].rstrip("')")
                                    count = await page.get_by_text(text).count()
                                else:
                                    count = await page.locator(button_selector).count()

                                if count > 0:
                                    print(f"  ✅ Found continue button, clicking: '{button_selector}'")
                                    if ":contains(" in button_selector:
                                        text = button_selector.split(":contains('")[1].rstrip("')")
                                        await page.get_by_text(text).click()
                                    else:
                                        await page.locator(button_selector).first.click()

                                    await page.wait_for_timeout(3000)
                                    break
                            except:
                                pass

                        await page.wait_for_timeout(wait_interval)
                        elapsed += wait_interval

                        # Progress indicator every 10 seconds
                        if elapsed % 10000 == 0:
                            print(f"  ⏳ Still waiting for approval... ({elapsed//1000}s)")

                    except Exception as e:
                        print(f"  Error during approval wait: {e}")
                        break

                if elapsed >= max_wait_time:
                    print(f"  ❌ Timeout waiting for device approval (2 minutes)")
                    await page.screenshot(path=f"screenshots/debug_approval_timeout_{email}.png")
                    return False

            else:
                # Unknown login flow
                print(f"  ❌ Unknown login flow - neither password nor device approval detected")
                await page.screenshot(path=f"screenshots/debug_unknown_flow_{email}.png")
                return False

        except Exception as e:
            print(f"Login error for {email}: {e}")
            return False
        finally:
            self.stop_bridge()
            await page.close()

    async def check_session_validity(self, email: str) -> bool:
        """Check if the session is still valid by verifying Gmail access"""
        if email not in self.contexts:
            return False

        context = self.contexts[email]

        # Get existing pages in the context
        pages = context.pages
        if not pages:
            return False

        # Use the first available page to check session
        page = pages[0]

        try:
            # Navigate to Gmail to check if we have valid access
            print(f"  🔍 Checking Gmail access for session validation...")
            await page.goto("https://mail.google.com")
            await page.wait_for_timeout(3000)

            current_url = page.url
            if "mail.google.com" not in current_url:
                print(f"  ❌ Not on Gmail - session invalid (URL: {current_url})")
                return False

            # Check for Gmail-specific elements to confirm interface is loaded
            compose_selectors = [
                GMAIL_COMPOSE_BUTTON,
                GMAIL_COMPOSE_BUTTON_ALT1,
                GMAIL_COMPOSE_BUTTON_ALT2,
                GMAIL_COMPOSE_BUTTON_ALT3
            ]

            compose_found = False
            for selector in compose_selectors:
                try:
                    count = await page.locator(selector).count()
                    if count > 0:
                        compose_found = True
                        print(f"  ✅ Found compose button: {selector}")
                        break
                except:
                    pass

            if compose_found:
                print(f"  ✅ Session valid - Gmail interface accessible")
                return True

            # Check for other Gmail indicators if compose button not found
            gmail_indicators = [
                "[data-message-store]",
                "[role='main']",
                "text=/Inbox/i",
                "[aria-label*='Inbox']"
            ]

            for indicator in gmail_indicators:
                try:
                    if "text=" in indicator:
                        text = indicator.replace("text=", "").replace("/i", "")
                        count = await page.get_by_text(text).count()
                    else:
                        count = await page.locator(indicator).count()

                    if count > 0:
                        print(f"  ✅ Session valid - found Gmail indicator: {indicator}")
                        return True
                except:
                    pass

            print(f"  ❌ Session invalid - Gmail interface not accessible")
            return False

        except Exception as e:
            print(f"  ❌ Session validity check error for {email}: {e}")
            return False

    async def send_email(self, email: str, to: str, subject: str, body: str, proxy: Optional[Dict] = None) -> bool:
        # If a proxy is specified, create a new context with that proxy
        # Otherwise, use the existing context for this email
        if proxy:
            print(f"🔄 Creating new context with proxy for {email}")
            print(f"   Proxy: {proxy['host']}:{proxy['port']} (user: {proxy.get('username', 'None')})")
            context = await self.create_context(f"{email}_proxy_{hash(str(proxy))}", proxy)
        elif email not in self.contexts:
            print(f"No active session for {email}")
            return False
        else:
            context = self.contexts[email]

        # Use existing page from context if available, otherwise create new one
        pages = context.pages
        if pages:
            page = pages[0]
            print(f"📧 Using existing page for {email}")
        else:
            page = await context.new_page()
            print(f"📧 Created new page for {email}")

        try:
            print(f"📧 Starting email send process for {email}")
            print(f"   To: {to}")
            print(f"   Subject: {subject}")

            # Step 1: Navigate to Gmail (always navigate to ensure we're on Gmail)
            print(f"   Step 1: Navigating to Gmail...")
            await page.goto("https://mail.google.com/mail/u/0/#inbox", timeout=120000)
            await page.wait_for_load_state('domcontentloaded')
            await page.wait_for_timeout(1000)  # Wait for page to load
            await page.screenshot(path=f"screenshots/send_email_step1_navigate_{email}.png")

            # Check if we're actually on Gmail or redirected to login
            current_url = page.url
            if "mail.google.com" not in current_url or "accounts.google.com" in current_url:
                print(f"   ❌ Session expired or cookies invalid - redirected to: {current_url}")
                print(f"   Please login again to refresh the session")
                return False

            # Step 2: Wait for Gmail to fully load and find compose button
            print(f"   Step 2: Waiting for Gmail to load...")
            
            max_wait_time = 120000  # 60 seconds for compose button detection
            print(f"   Looking for compose button (will timeout in {max_wait_time//1000} seconds)...")
            wait_interval = 200   # Check every 0.2 seconds
            elapsed = 0
            compose_found = False

            while elapsed < max_wait_time and not compose_found:
                try:
                    # Check multiple compose button selectors
                    compose_selectors = [
                        GMAIL_COMPOSE_BUTTON,  # Primary selector
                        "[role='button'][aria-label*='Compose']",
                        "[role='button'][data-tooltip*='Compose']",
                        "div[role='button']:has-text('Compose')",
                        "[gh='cm']",  # Gmail's internal compose button class
                        "button:contains('Compose')",
                        "[aria-label='Compose']",
                        "[data-tooltip='Compose']"
                    ]

                    for selector in compose_selectors:
                        try:
                            if ":contains(" in selector:
                                text = selector.split(":contains('")[1].rstrip("')")
                                count = await page.get_by_text(text).count()
                            else:
                                count = await page.locator(selector).count()

                            if count > 0:
                                print(f"   ✅ Found compose button with selector: {selector} ({count})")
                                compose_found = True

                                # Get the element for clicking
                                if ":contains(" in selector:
                                    compose_button = page.get_by_text(text).first
                                else:
                                    compose_button = page.locator(selector).first

                                # Check if it's visible and enabled
                                is_visible = await compose_button.is_visible()
                                is_enabled = await compose_button.is_enabled()

                                print(f"      Visible: {is_visible}, Enabled: {is_enabled}")

                                if is_visible and is_enabled:
                                    print(f"   Step 3: Clicking compose button...")
                                    await compose_button.click()
                                    await page.screenshot(path=f"screenshots/send_email_step3_compose_clicked_{email}.png")
                                    break
                                else:
                                    print(f"      Compose button not ready, waiting...")
                        except Exception as e:
                            print(f"      Error checking selector {selector}: {e}")

                    if not compose_found:
                        await page.wait_for_timeout(wait_interval)
                        elapsed += wait_interval

                        if elapsed % 5000 == 0:  # Progress every 5 seconds
                            print(f"      Still waiting for compose button... ({elapsed//1000}s)")
                            await page.screenshot(path=f"screenshots/send_email_waiting_{elapsed//1000}s_{email}.png")

                except Exception as e:
                    print(f"   Error during compose button wait: {e}")
                    break

            if not compose_found:
                print(f"   ❌ Compose button not found within {max_wait_time//1000} seconds")
                await page.screenshot(path=f"screenshots/send_email_compose_timeout_{email}.png")
                return False

            # Step 4: Wait for compose window to appear
            print(f"   Step 4: Waiting for compose window...")
            await page.wait_for_timeout(3000)  # Increased wait time for compose window to load
            
            # Take screenshot of compose window
            await page.screenshot(path=f"screenshots/send_email_step4_compose_window_{email}.png")

            # Step 5: Find and fill TO field
            print(f"   Step 5: Finding TO field...")
            to_selectors = [
                GMAIL_TO_INPUT,  # Primary selector
                "input[aria-label='To']",
                "input[aria-label='To recipients']",
                "input[placeholder*='To']",
                "input[name='to']",
                "textarea[aria-label='To']",
                "div[aria-label='To'] input",
                "div[data-tooltip='Recipients'] input",
                "input[aria-label*='To']",  # More flexible aria-label matching
                "input[placeholder*='recipients']",
                "input[placeholder*='email']",
                "div[role='combobox'] input",  # Gmail's recipient input might use combobox
                "[data-initial-value] input",  # Gmail sometimes uses this
                "input[type='text']:not([aria-label='Subject']):not([aria-label*='Body'])",  # Fallback for text inputs
                "textarea[role='textbox']",  # Sometimes TO field is a textarea
                ".agP.aFw input",  # Gmail's internal class for recipient fields
                ".vO input"  # Another Gmail internal class
            ]

            to_field = None
            for selector in to_selectors:
                try:
                    count = await page.locator(selector).count()
                    if count > 0:
                        print(f"   ✅ Found TO field with selector: {selector} ({count})")
                        to_field = page.locator(selector).first
                        break
                except Exception as e:
                    print(f"      Error checking TO selector {selector}: {e}")

            # If no TO field found with specific selectors, debug all input fields
            if not to_field:
                print(f"   🔍 Debug: Analyzing all input fields in compose window...")
                all_inputs = await page.locator("input, textarea").all()
                print(f"   📊 Total input/textarea fields found: {len(all_inputs)}")
                
                for i, inp in enumerate(all_inputs):
                    try:
                        input_type = await inp.get_attribute("type") or "text"
                        input_placeholder = await inp.get_attribute("placeholder") or ""
                        input_aria_label = await inp.get_attribute("aria-label") or ""
                        input_name = await inp.get_attribute("name") or ""
                        input_class = await inp.get_attribute("class") or ""
                        is_visible = await inp.is_visible()
                        
                        print(f"   🔍 Field {i}: type='{input_type}' placeholder='{input_placeholder}' aria-label='{input_aria_label}' name='{input_name}' class='{input_class}' visible={is_visible}")
                    except Exception as e:
                        print(f"   🔍 Field {i}: Error getting attributes - {e}")
                
                await page.screenshot(path=f"screenshots/send_email_to_field_debug_{email}.png")

            if not to_field:
                print(f"   ❌ TO field not found")
                await page.screenshot(path=f"screenshots/send_email_to_field_missing_{email}.png")
                return False

            # Check if TO field is ready
            # Wait for TO field to be visible and ready
            print(f"   Waiting for TO field to be ready...")
            try:
                await to_field.wait_for(state='visible', timeout=5000)
                await to_field.wait_for(state='attached', timeout=5000)
                # Additional wait to ensure it's fully interactive
                await page.wait_for_timeout(1000)
            except Exception as e:
                print(f"   ⚠️  TO field wait failed: {e}")
            
            is_visible = await to_field.is_visible()
            is_enabled = await to_field.is_enabled()
            print(f"      TO field visible: {is_visible}, enabled: {is_enabled}")

            if is_visible and is_enabled:
                print(f"   Filling TO field with: {to}")
                await to_field.clear()
                await to_field.fill(to)
                await page.wait_for_timeout(500)
                await page.screenshot(path=f"screenshots/send_email_step5_to_filled_{email}.png")
            else:
                print(f"   ❌ TO field not ready")
                return False

            # Step 6: Find and fill SUBJECT field
            print(f"   Step 6: Finding SUBJECT field...")
            subject_selectors = [
                GMAIL_SUBJECT_INPUT,  # Primary selector
                "input[aria-label='Subject']",
                "input[placeholder*='Subject']",
                "input[name='subject']",
                "input[name='subjectbox']"
            ]

            subject_field = None
            for selector in subject_selectors:
                try:
                    count = await page.locator(selector).count()
                    if count > 0:
                        print(f"   ✅ Found SUBJECT field with selector: {selector} ({count})")
                        subject_field = page.locator(selector).first
                        break
                except Exception as e:
                    print(f"      Error checking SUBJECT selector {selector}: {e}")

            if subject_field:
                # Wait for SUBJECT field to be ready
                try:
                    await subject_field.wait_for(state='visible', timeout=3000)
                    await page.wait_for_timeout(500)
                except Exception as e:
                    print(f"   ⚠️  SUBJECT field wait failed: {e}")
                
                is_visible = await subject_field.is_visible()
                is_enabled = await subject_field.is_enabled()
                print(f"      SUBJECT field visible: {is_visible}, enabled: {is_enabled}")

                if is_visible and is_enabled:
                    print(f"   Filling SUBJECT field with: {subject}")
                    await subject_field.clear()
                    await subject_field.fill(subject)
                    await page.wait_for_timeout(500)
                    await page.screenshot(path=f"screenshots/send_email_step6_subject_filled_{email}.png")

            # Step 7: Find and fill BODY field
            print(f"   Step 7: Finding BODY field...")
            body_selectors = [
                GMAIL_BODY_INPUT,  # Primary selector
                "div[aria-label='Message Body']",
                "div[aria-label='Message body']",
                "div[role='textbox']",
                "div[contenteditable='true']",
                "div[data-tooltip='Message body']",
                "[aria-label*='Message']",
                "[aria-label*='Body']"
            ]

            body_field = None
            for selector in body_selectors:
                try:
                    count = await page.locator(selector).count()
                    if count > 0:
                        print(f"   ✅ Found BODY field with selector: {selector} ({count})")
                        body_field = page.locator(selector).first
                        break
                except Exception as e:
                    print(f"      Error checking BODY selector {selector}: {e}")

            if not body_field:
                print(f"   ❌ BODY field not found")
                await page.screenshot(path=f"screenshots/send_email_body_field_missing_{email}.png")
                return False

            # Check if BODY field is ready
            # Wait for BODY field to be ready
            try:
                await body_field.wait_for(state='visible', timeout=3000)
                await page.wait_for_timeout(500)
            except Exception as e:
                print(f"   ⚠️  BODY field wait failed: {e}")
            
            is_visible = await body_field.is_visible()
            is_enabled = await body_field.is_enabled()
            print(f"      BODY field visible: {is_visible}, enabled: {is_enabled}")

            if is_visible and is_enabled:
                print(f"   Filling BODY field with: {body[:50]}...")
                await body_field.clear()
                await body_field.fill(body)
                await page.wait_for_timeout(500)
                await page.screenshot(path=f"screenshots/send_email_step7_body_filled_{email}.png")
            else:
                print(f"   ❌ BODY field not ready")
                return False

            # Step 8: Find and click SEND button
            print(f"   Step 8: Finding SEND button...")
            send_selectors = [
                GMAIL_SEND_BUTTON,  # Primary selector
                "div[role='button'][aria-label*='Send']",
                "div[role='button'][data-tooltip*='Send']",
                "button:contains('Send')",
                "[aria-label='Send']",
                "[data-tooltip='Send']",
                "[gh='sd']"  # Gmail's internal send button class
            ]

            send_button = None
            for selector in send_selectors:
                try:
                    if ":contains(" in selector:
                        text = selector.split(":contains('")[1].rstrip("')")
                        count = await page.get_by_text(text).count()
                    else:
                        count = await page.locator(selector).count()

                    if count > 0:
                        print(f"   ✅ Found SEND button with selector: {selector} ({count})")
                        if ":contains(" in selector:
                            send_button = page.get_by_text(text).first
                        else:
                            send_button = page.locator(selector).first
                        break
                except Exception as e:
                    print(f"      Error checking SEND selector {selector}: {e}")

            if not send_button:
                print(f"   ❌ SEND button not found")
                await page.screenshot(path=f"screenshots/send_email_send_button_missing_{email}.png")
                return False

            # Check if SEND button is ready
            is_visible = await send_button.is_visible()
            is_enabled = await send_button.is_enabled()
            print(f"      SEND button visible: {is_visible}, enabled: {is_enabled}")

            if is_visible and is_enabled:
                print(f"   Clicking SEND button...")
                await send_button.click()
                await page.wait_for_timeout(2000)  # Wait for send to process
                await page.screenshot(path=f"screenshots/send_email_step8_sent_{email}.png")
                print(f"   ✅ Email sent successfully!")
                return True
            else:
                print(f"   ❌ SEND button not ready")
                await page.screenshot(path=f"screenshots/send_email_send_button_not_ready_{email}.png")
                return False

        except Exception as e:
            print(f"Send email error for {email}: {e}")
            await page.screenshot(path=f"screenshots/send_email_error_{email}.png")
            if proxy:
                await context.close()
            return False
        finally:
            # Close proxy contexts since they are not reused
            if proxy:
                self.stop_bridge()
                await context.close()

    def get_sms_number(self, service: str = "google") -> Optional[str]:
        if not SMS_API_KEY:
            return None

        params = {
            "metod": "getnumber",
            "service": service,
            "apikey": SMS_API_KEY
        }
        response = requests.get(SMS_API_URL, params=params)
        if response.status_code == 200:
            data = response.json()
            if data.get("response") == "1":
                return data.get("number")
        return None

    def get_sms_code(self, number_id: str) -> Optional[str]:
        if not SMS_API_KEY:
            return None

        params = {
            "metod": "getsms",
            "id": number_id,
            "apikey": SMS_API_KEY
        }
        response = requests.get(SMS_API_URL, params=params)
        if response.status_code == 200:
            data = response.json()
            if data.get("response") == "1":
                return data.get("sms")
        return None
