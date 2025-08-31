# Gmail Browser Automation Service

A lightweight Python service for automated Gmail login and email sending using browser automation. Designed to run on low-end machines with 2-4GB RAM and 2 cores.

## Features

- **Browser Automation**: Uses Playwright for headless Chrome automation
- **Multi-Account Support**: Handle multiple Gmail accounts in parallel
- **Proxy Integration**: Per-session proxy support
- **Cookie Persistence**: Store and reuse login sessions
- **2FA Handling**: Support for backup codes and manual verification
- **SMS Verification**: Optional integration with smspva.com for automated phone verification
- **REST API**: FastAPI-based service for integration with Python SaaS

## Requirements

- Python 3.8+
- Low-end machine compatible (2-4GB RAM, 2 cores)

## Installation

1. Clone or download the project
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   playwright install chromium
   ```

3. **Environment Setup** (Recommended):
   ```bash
   # Copy the example environment file
   cp .env.example .env

   # Edit .env with your actual values
   nano .env  # or use your preferred editor
   ```

4. Set environment variables (optional):
   ```bash
   export SMS_API_KEY="your_smspva_api_key"
   ```

## Environment Configuration

The service uses environment variables for configuration. Copy `.env.example` to `.env` and customize:

```bash
# SMS API Configuration
SMS_API_KEY=your_sms_api_key_here
SMS_API_URL=https://smspva.com/priemnik.php

# Browser Configuration
BROWSER_HEADLESS=false
MAX_CONCURRENT_BROWSERS=5

# API Server Configuration
API_HOST=0.0.0.0
API_PORT=8010

# Debug Configuration
DEBUG_MODE=true
SAVE_SCREENSHOTS=true
```

## GitHub Deployment

### Setup for Repository

1. **Initialize Git Repository**:
   ```bash
   git init
   git add .
   git commit -m "Initial commit"
   ```

2. **Create GitHub Repository**:
   - Go to GitHub and create a new repository
   - Copy the repository URL

3. **Push to GitHub**:
   ```bash
   git remote add origin https://github.com/yourusername/your-repo-name.git
   git push -u origin main
   ```

### Important: Security Files

The following files are automatically ignored by `.gitignore`:
- `.env` (contains sensitive API keys)
- `cookies/` (contains session data)
- `screenshots/` (debug images)
- `__pycache__/` (Python cache files)

**Never commit these files to GitHub!** They contain sensitive information.

### Deployment Checklist

- [ ] Copy `.env.example` to `.env` (don't commit `.env`)
- [ ] Update `.env` with your actual configuration
- [ ] Test locally before pushing
- [ ] Ensure all sensitive data is in `.env` or environment variables
- [ ] Verify `.gitignore` excludes sensitive files

## Usage

### Start the Service

```bash
python main.py
```

The API will be available at the configured host and port (default: `http://localhost:8010`)

### API Endpoints

#### POST /login_accounts
Login multiple Gmail accounts.

**Request Body:**
```json
[
  {
    "first_from_name": "John",
    "last_from_name": "Doe",
    "email": "john.doe@gmail.com",
    "email_pass": "app_password",
    "proxy_host": "proxy.example.com",
    "proxy_port": 8080,
    "proxy_user": "username",
    "proxy_pass": "password",
    "browser_pass": "browser_password",
    "backup_code": "12345678"
  }
]
```

#### POST /send_emails
Send emails from logged-in accounts.

**Request Body:**
```json
{
  "accounts": [...],
  "emails": [
    {
      "to": "recipient@example.com",
      "subject": "Test Subject",
      "body": "Test Body"
    }
  ]
}
```

#### POST /upload_sheet
Upload Excel sheet with account data.

**Form Data:**
- `file`: Excel file with columns: FIRSTFROMNAME, LASTFROMNAME, EMAIL, EMAIL_PASS, PROXY:PORT, PROXY_USER, PROXY_PASS, BROWSER_PASS, BACKUP_CODE

## Excel Sheet Format

The service expects an Excel file with the following columns:

- FIRSTFROMNAME
- LASTFROMNAME
- EMAIL
- EMAIL_PASS (App password for SMTP)
- PROXY:PORT (e.g., "proxy.com:8080")
- PROXY_USER
- PROXY_PASS
- BROWSER_PASS (Browser login password)
- BACKUP_CODE (Optional, for 2FA)

## Configuration

The service is configured through environment variables in the `.env` file. Key settings include:

- **Browser Settings**: Headless mode, concurrent browser limits
- **API Configuration**: Host, port, and server settings
- **Security**: SMS API keys for automated verification
- **Debug Options**: Screenshot saving, debug logging
- **Proxy Settings**: Per-session proxy configuration

Edit `.env` to customize these settings. The `config.py` file loads these environment variables automatically.

## Logging

The service includes comprehensive logging for monitoring and debugging:

### Log Files
- **Main Log**: `logs/gmail_api.log` - All application events and errors
- **Auto Rotation**: Logs rotate at 10MB with 5 backup files
- **Security**: Log files are excluded from Git (contains sensitive info)

### Log Levels
- **DEBUG**: Detailed debugging information
- **INFO**: General application events
- **WARNING**: Warning messages for potential issues
- **ERROR**: Error messages for failures
- **CRITICAL**: Critical errors requiring immediate attention

### Log Viewer

Use the built-in log viewer to monitor and analyze logs:

```bash
# View last 50 log entries
python log_viewer.py

# View last 100 entries
python log_viewer.py --lines 100

# Search for specific text
python log_viewer.py --search "login"

# Filter by log level
python log_viewer.py --level error

# Show log statistics
python log_viewer.py --stats

# Clear logs (creates backup)
python log_viewer.py --clear
```

### Log Configuration

Configure logging through environment variables in `.env`:

```bash
# Logging Configuration
LOG_LEVEL=INFO
LOG_FILE=logs/gmail_api.log
LOG_MAX_SIZE=10485760  # 10MB
LOG_BACKUP_COUNT=5
```

## SOCKS5 Proxy Configuration

The service supports SOCKS5 proxies with Firefox for enhanced privacy and DNS protection:

### Your Current Configuration

- **Proxy Host**: 195.35.113.44
- **Proxy Port**: 4005
- **Username**: slpPJ73G3XhC
- **Password**: J4J0Ai5jUvQE
- **Email**: hichemmoussa6677@gmail.com

### Firefox + SOCKS5 Setup

1. **Option 1: System-Level Proxy (Recommended)**
   ```bash
   # Configure Windows system proxy
   python setup_system_proxy.py

   # Configure Firefox to use system proxy
   # Firefox Settings > Network Settings > Use system proxy settings

   # Update .env file
   USE_PROXY=false
   USE_FIREFOX_FOR_SOCKS5=false
   ```

2. **Option 2: Manual Firefox Profile**
   ```bash
   # Test with manual Firefox configuration
   python test_manual_firefox_proxy.py
   ```

3. **Option 3: Test System Proxy**
   ```bash
   # Test Gmail automation with system proxy
   python test_system_proxy_gmail.py
   ```

### Quick Test Your Proxy

```bash
# Test SOCKS5 proxy (may show authentication limitation)
python test_socks5_proxy.py

# Test HTTP proxy (if supported by your provider)
python test_http_proxy.py

# Setup system proxy (recommended)
python setup_system_proxy.py

# Test Gmail with system proxy
python test_system_proxy_gmail.py
```

### Security Benefits

- **Anonymous Browsing**: All traffic routed through SOCKS5 proxy
- **DNS Privacy**: DNS queries never leak to ISP
- **IP Protection**: Real IP address never exposed
- **Multi-hop Support**: Can be combined with VPN for extra security

### Firefox-Specific Features

When using Firefox with SOCKS5:
- Automatic proxy authentication
- DNS resolution through proxy
- WebRTC disabled for IP leak prevention
- Enhanced fingerprinting protection
- Better SOCKS5 protocol support

### Troubleshooting

- **Connection Issues**: Verify proxy credentials and server status
- **DNS Leaks**: Check that `USE_FIREFOX_FOR_SOCKS5=true`
- **Slow Performance**: SOCKS5 may be slower than HTTP proxies
- **Authentication Errors**: Ensure proxy username/password are correct

## License

This project is for educational purposes. Use responsibly and in accordance with Gmail's terms of service.
