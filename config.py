import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Configuration settings
BROWSER_HEADLESS = os.getenv("BROWSER_HEADLESS", "false").lower() == "true"
MAX_CONCURRENT_BROWSERS = int(os.getenv("MAX_CONCURRENT_BROWSERS", "5"))
COOKIE_STORAGE_PATH = "cookies/"  # Directory to store cookies
SMS_API_KEY = os.getenv("SMS_API_KEY", "")  # For smspva.com integration
SMS_API_URL = os.getenv("SMS_API_URL", "https://smspva.com/priemnik.php")

# API Server Configuration
API_HOST = os.getenv("API_HOST", "0.0.0.0")
API_PORT = int(os.getenv("API_PORT", "8010"))

# Debug Configuration
DEBUG_MODE = os.getenv("DEBUG_MODE", "true").lower() == "true"
SAVE_SCREENSHOTS = os.getenv("SAVE_SCREENSHOTS", "true").lower() == "true"

# Logging Configuration
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
LOG_FILE = os.getenv("LOG_FILE", "logs/gmail_api.log")
LOG_MAX_SIZE = int(os.getenv("LOG_MAX_SIZE", "10485760"))  # 10MB default
LOG_BACKUP_COUNT = int(os.getenv("LOG_BACKUP_COUNT", "5"))

# Proxy settings
USE_PROXY = os.getenv("USE_PROXY", "false").lower() == "true"
USE_FIREFOX_FOR_SOCKS5 = os.getenv("USE_FIREFOX_FOR_SOCKS5", "false").lower() == "true"

# Login optimization settings
SMART_LOGIN_DETECTION = os.getenv("SMART_LOGIN_DETECTION", "true").lower() == "true"

# Gmail selectors (may need updates if Gmail changes UI)
GMAIL_LOGIN_URL = "https://accounts.google.com/signin"
GMAIL_EMAIL_INPUT = "input[type='email']"
GMAIL_PASSWORD_INPUT = "input[type='password']"
GMAIL_NEXT_BUTTON = "#identifierNext"
GMAIL_SIGNIN_BUTTON = "#passwordNext"

# 2FA selectors
GMAIL_TRY_ANOTHER_WAY = "button[data-value='recoveryOptions']"
GMAIL_BACKUP_CODE_OPTION = "li[data-value='backupCode']"
GMAIL_BACKUP_CODE_INPUT = "input[type='tel'][aria-label='Enter a backup code']"
GMAIL_BACKUP_CODE_INPUT_ALT1 = "input[id='backupCodePin']"
GMAIL_BACKUP_CODE_INPUT_ALT2 = "input[name='Pin']"
GMAIL_BACKUP_CODE_INPUT_ALT3 = "input[aria-label='Enter a backup code']"
GMAIL_BACKUP_CODE_INPUT_ALT4 = "input[type='tel']"
GMAIL_BACKUP_CODE_INPUT_ALT5 = "input[placeholder*='code']"
GMAIL_2FA_INPUT = "input[type='tel']"  # For phone verification

# Alternative selectors (text-based - will use get_by_text)
GMAIL_TRY_ANOTHER_WAY_TEXT = "Try another way"
GMAIL_BACKUP_CODE_OPTION_TEXT = "Backup codes"

# Device approval selectors (for when Gmail recognizes the device)
GMAIL_CHECK_PHONE_TEXT = "Check your phone"
GMAIL_APPROVE_DEVICE_TEXT = "Approve this device"
GMAIL_CONTINUE_BUTTON = "button:contains('Continue')"
GMAIL_NEXT_BUTTON_ALT = "button:contains('Next')"
GMAIL_DEVICE_APPROVED_TEXT = "Device approved"

# Gmail main interface
GMAIL_COMPOSE_BUTTON = "div[role='button'][aria-label*='Compose']"
GMAIL_COMPOSE_BUTTON_ALT1 = "[data-tooltip*='Compose']"
GMAIL_COMPOSE_BUTTON_ALT2 = "div[role='button']:has-text('Compose')"
GMAIL_COMPOSE_BUTTON_ALT3 = ".T-I.T-I-KE.L3"
GMAIL_TO_INPUT = "input[aria-label='To']"
GMAIL_SUBJECT_INPUT = "input[aria-label='Subject']"
GMAIL_BODY_INPUT = "div[aria-label='Message Body']"
GMAIL_SEND_BUTTON = "div[role='button'][aria-label*='Send']"
