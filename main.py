#!/usr/bin/env python3
"""
Gmail Browser Automation Service
Lightweight service for automated Gmail login and email sending via browser.
"""

import uvicorn
from api import app
from config import API_HOST, API_PORT
from logging_config import log_info, log_error

if __name__ == "__main__":
    try:
        log_info("Starting Gmail Browser Automation Service...")
        log_info(f"API will be available at: http://{API_HOST}:{API_PORT}")
        log_info("Ready to handle Gmail automation requests!")
        uvicorn.run(app, host=API_HOST, port=API_PORT, log_level="info")
    except Exception as e:
        log_error(f"Failed to start service: {e}")
        raise
"""
Gmail Browser Automation Service
Lightweight service for automated Gmail login and email sending via browser.
"""

import uvicorn
from api import app
from config import API_HOST, API_PORT

if __name__ == "__main__":
    print("🚀 Starting Gmail Browser Automation Service...")
    print(f"📡 API will be available at: http://{API_HOST}:{API_PORT}")
    print("📧 Ready to handle Gmail automation requests!")
    uvicorn.run(app, host=API_HOST, port=API_PORT, log_level="info")
