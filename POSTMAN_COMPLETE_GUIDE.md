# 📮 Complete Gmail API - Postman Collection Guide

## 🚀 Overview
This comprehensive Postman collection includes **ALL API endpoints** from your Gmail automation system, covering login, email sending, proxy management, and system health monitoring.

## 📦 What's Included

### **1. Authentication & Login** 🔐
- **Login Single Account** - Authenticate one Gmail account
- **Login Multiple Accounts** - Bulk login for multiple accounts

### **2. Email Sending** 📧
- **Send Single Email** - Send one email from one account
- **Send Multiple Emails** - Distribute emails across multiple accounts
- **Send Email with Manual Proxy** - Use specific proxy per account
- **Send Email with Auto Proxy Assignment** - Automatic proxy selection

### **3. Proxy Management** 🌐
- **Get Proxy Statistics** - View proxy usage and performance
- **Add HTTP Proxy** - Add HTTP proxy to pool
- **Add SOCKS5 Proxy** - Add SOCKS5 proxy to pool
- **Remove Proxy** - Remove proxy from pool

### **4. File Upload & Processing** 📄
- **Upload Excel Sheet** - Upload account data from Excel

### **5. System Health** ❤️
- **Health Check** - Verify API status

## 🛠️ How to Use

### **Step 1: Import Collection**
1. Open Postman
2. Click **Import** → **File**
3. Select `postman_complete_api.json`
4. Click **Import**

### **Step 2: Set Variables**
Update these variables in Postman:
- `email` - Your Gmail address
- `app_password` - Gmail app password
- `browser_password` - Gmail login password
- `proxy_host` - Proxy server address
- `proxy_port` - Proxy server port
- `proxy_username` - Proxy username
- `proxy_password` - Proxy password
- `backup_code` - Gmail backup code (if needed)

### **Step 3: Start the API Server**
```bash
python main.py
```

## 📋 Complete Workflow Example

### **1. Login First** 🔐
Use **"Login Single Account"** or **"Login Multiple Accounts"** to authenticate your Gmail accounts. This creates browser sessions and saves cookies.

### **2. Send Emails** 📧
Choose from various email sending options:
- **Send Single Email** - Basic email sending
- **Send Email with Auto Proxy Assignment** - Automatic proxy selection
- **Send Email with Manual Proxy** - Specify exact proxy

### **3. Monitor Proxies** 📊
Use **"Get Proxy Statistics"** to monitor:
- Proxy usage distribution
- Success/failure rates
- Active proxy count

### **4. Manage Proxies** ⚙️
- **Add HTTP Proxy** - Add new HTTP proxies
- **Remove Proxy** - Remove failing proxies
- **Get Proxy Statistics** - Monitor performance

## 📝 Request Details

### **Login Requests**
```json
{
  "accounts": [
    {
      "first_from_name": "John",
      "last_from_name": "Doe",
      "email": "{{email}}",
      "email_pass": "{{app_password}}",
      "browser_pass": "{{browser_password}}",
      "proxy_host": "{{proxy_host}}",
      "proxy_port": {{proxy_port}},
      "proxy_user": "{{proxy_username}}",
      "proxy_pass": "{{proxy_password}}",
      "backup_code": "{{backup_code}}"
    }
  ]
}
```

### **Email Sending Requests**
```json
{
  "accounts": [
    {
      "first_from_name": "John",
      "last_from_name": "Doe",
      "email": "{{email}}",
      "email_pass": "{{app_password}}",
      "browser_pass": "{{browser_password}}",
      "backup_code": null
    }
  ],
  "emails": [
    {
      "to": "recipient@example.com",
      "subject": "Test Email",
      "body": "This is a test email"
    }
  ]
}
```

### **Proxy Management**
```json
// Add HTTP Proxy
{
  "host": "{{proxy_host}}",
  "port": {{proxy_port}},
  "username": "{{proxy_username}}",
  "password": "{{proxy_password}}",
  "type": "http",
  "country": "US"
}

// Add SOCKS5 Proxy
{
  "host": "{{proxy_host}}",
  "port": 4005,
  "username": "{{proxy_username}}",
  "password": "{{proxy_password}}",
  "type": "socks5",
  "country": "US"
}
```

## 🎯 Key Features

### **🔄 Auto Proxy Assignment**
- Accounts without proxies get them automatically
- Load balancing across available proxies
- Performance-based proxy selection

### **🌐 Multiple Proxy Types**
- **HTTP Proxies**: Full authentication support
- **SOCKS5 Proxies**: DNS protection (Firefox only)
- **Auto Detection**: System detects proxy type

### **📊 Smart Distribution**
- Multiple emails distributed across accounts
- One email per account when more accounts than emails
- Even distribution with remainder handling

### **🛡️ Error Handling**
- Graceful fallback when proxies fail
- Detailed error messages
- Session recovery and cookie management

## 🚨 Important Notes

### **Login Required First**
- **Always login first** before sending emails
- Login creates browser sessions and saves cookies
- Cookies are reused for subsequent requests

### **Proxy Configuration**
- **HTTP proxies work with Chromium** (recommended)
- **SOCKS5 proxies require Firefox** (set `USE_FIREFOX_FOR_SOCKS5=true`)
- **Auto-assignment** works for both proxy types

### **Backup Codes**
- Required for accounts with 2FA
- One-time use codes from Google
- Store securely and update when used

## 📈 Monitoring & Troubleshooting

### **Check System Health**
```bash
GET /health
```

### **Monitor Proxy Performance**
```bash
GET /proxy_stats
```

### **Common Issues**
- **"No cookies found"** → Login first
- **"Proxy not reachable"** → Check proxy credentials
- **"Compose button not found"** → Gmail UI changed, may need updates

## 🔧 Advanced Usage

### **Bulk Operations**
- Use **"Login Multiple Accounts"** for bulk login
- Use **"Send Multiple Emails"** for bulk sending
- Monitor with **"Get Proxy Statistics"**

### **Proxy Rotation**
- Add multiple proxies with **"Add HTTP Proxy"**
- System automatically rotates between them
- Remove failing proxies with **"Remove Proxy"**

### **Excel Upload**
- Upload account data via **"Upload Excel Sheet"**
- Format: Email, Password, Proxy details
- Automatic processing and validation

## 🎉 Success Workflow

1. ✅ **Import collection** into Postman
2. ✅ **Set variables** with your credentials
3. ✅ **Start API server** with `python main.py`
4. ✅ **Login accounts** using login endpoints
5. ✅ **Send emails** using send endpoints
6. ✅ **Monitor performance** with stats endpoints
7. ✅ **Scale up** by adding more proxies/accounts

---

**🎯 Ready to automate your Gmail operations?** Import the collection and start testing! 🚀

**Need help?** Check the response examples and error messages for guidance.
