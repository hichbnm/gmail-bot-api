#!/usr/bin/env python3
"""
Automated Proxy Management System for Gmail API
Manages proxy rotation and assignment per account
"""

import json
import random
import asyncio
from typing import Dict, List, Optional
from pathlib import Path
import logging

class ProxyManager:
    """Manages proxy pool and automatic assignment to accounts"""

    def __init__(self, proxy_config_file: str = "proxy_pool.json"):
        self.proxy_config_file = Path(proxy_config_file)
        self.proxy_pool: List[Dict] = []
        self.account_proxy_map: Dict[str, Dict] = {}
        self.used_proxies: set = set()
        self.logger = logging.getLogger(__name__)

        # Load proxy configuration
        self.load_proxy_config()

    def load_proxy_config(self):
        """Load proxy pool from configuration file"""
        if self.proxy_config_file.exists():
            try:
                with open(self.proxy_config_file, 'r') as f:
                    config = json.load(f)
                    self.proxy_pool = config.get('proxies', [])
                    self.account_proxy_map = config.get('account_mapping', {})
                self.logger.info(f"Loaded {len(self.proxy_pool)} proxies from config")
            except Exception as e:
                self.logger.error(f"Failed to load proxy config: {e}")
                self.create_default_config()
        else:
            self.create_default_config()

    def create_default_config(self):
        """Create default proxy configuration"""
        default_config = {
            "proxies": [
                {
                    "id": "proxy_001",
                    "host": "195.35.113.44",
                    "port": 8080,
                    "username": "proxyuser1",
                    "password": "proxypass1",
                    "type": "http",
                    "country": "US",
                    "status": "active",
                    "last_used": None,
                    "success_rate": 1.0
                },
                {
                    "id": "proxy_002",
                    "host": "195.35.113.45",
                    "port": 8080,
                    "username": "proxyuser2",
                    "password": "proxypass2",
                    "type": "http",
                    "country": "US",
                    "status": "active",
                    "last_used": None,
                    "success_rate": 1.0
                },
                {
                    "id": "proxy_003",
                    "host": "195.35.113.46",
                    "port": 8080,
                    "username": "proxyuser3",
                    "password": "proxypass3",
                    "type": "http",
                    "country": "US",
                    "status": "active",
                    "last_used": None,
                    "success_rate": 1.0
                }
            ],
            "account_mapping": {},
            "rotation_strategy": "round_robin",
            "max_accounts_per_proxy": 3
        }

        with open(self.proxy_config_file, 'w') as f:
            json.dump(default_config, f, indent=2)

        self.proxy_pool = default_config['proxies']
        self.account_proxy_map = default_config['account_mapping']
        self.logger.info("Created default proxy configuration")

    def get_available_proxies(self) -> List[Dict]:
        """Get list of available proxies"""
        return [p for p in self.proxy_pool if p['status'] == 'active']

    def assign_proxy_to_account(self, account_email: str, strategy: str = "auto") -> Optional[Dict]:
        """Assign a proxy to an account based on strategy"""

        # Check if account already has a proxy assigned
        if account_email in self.account_proxy_map:
            proxy_id = self.account_proxy_map[account_email]
            proxy = next((p for p in self.proxy_pool if p['id'] == proxy_id), None)
            if proxy and proxy['status'] == 'active':
                return proxy

        available_proxies = self.get_available_proxies()
        if not available_proxies:
            self.logger.warning("No available proxies!")
            return None

        if strategy == "random":
            proxy = random.choice(available_proxies)
        elif strategy == "round_robin":
            # Simple round-robin based on account email hash
            proxy_index = hash(account_email) % len(available_proxies)
            proxy = available_proxies[proxy_index]
        elif strategy == "least_used":
            # Choose proxy with lowest usage count
            proxy_usage = {}
            for acc_email, proxy_id in self.account_proxy_map.items():
                proxy_usage[proxy_id] = proxy_usage.get(proxy_id, 0) + 1

            # Find proxy with minimum usage
            min_usage = min(proxy_usage.values()) if proxy_usage else 0
            least_used_proxies = [p for p in available_proxies if proxy_usage.get(p['id'], 0) == min_usage]

            if least_used_proxies:
                proxy = random.choice(least_used_proxies)  # Random among least used
            else:
                proxy = random.choice(available_proxies)
        else:  # auto
            proxy = self._auto_select_proxy(account_email, available_proxies)

        # Assign proxy to account
        self.account_proxy_map[account_email] = proxy['id']
        self.save_config()

        self.logger.info(f"Assigned proxy {proxy['id']} to account {account_email}")
        return proxy

    def _auto_select_proxy(self, account_email: str, available_proxies: List[Dict]) -> Dict:
        """Auto-select best proxy for account"""
        # Count current assignments
        proxy_usage = {}
        for acc_email, proxy_id in self.account_proxy_map.items():
            proxy_usage[proxy_id] = proxy_usage.get(proxy_id, 0) + 1

        # Find proxies with space available
        max_accounts = 3  # Max accounts per proxy
        available_with_space = [
            p for p in available_proxies
            if proxy_usage.get(p['id'], 0) < max_accounts
        ]

        if available_with_space:
            # Choose based on success rate and usage
            best_proxy = max(available_with_space,
                           key=lambda p: (p.get('success_rate', 0.5),
                                        -proxy_usage.get(p['id'], 0)))
            return best_proxy
        else:
            # All proxies at capacity, choose least loaded
            return min(available_proxies,
                      key=lambda p: proxy_usage.get(p['id'], 0))

    def release_proxy(self, account_email: str):
        """Release proxy assignment for account"""
        if account_email in self.account_proxy_map:
            proxy_id = self.account_proxy_map[account_email]
            del self.account_proxy_map[account_email]
            self.save_config()
            self.logger.info(f"Released proxy {proxy_id} from account {account_email}")

    def update_proxy_status(self, proxy_id: str, success: bool):
        """Update proxy success rate and status"""
        proxy = next((p for p in self.proxy_pool if p['id'] == proxy_id), None)
        if proxy:
            # Update success rate (simple moving average)
            current_rate = proxy.get('success_rate', 1.0)
            if success:
                proxy['success_rate'] = min(1.0, current_rate + 0.1)
            else:
                proxy['success_rate'] = max(0.0, current_rate - 0.2)

            # Mark as inactive if success rate too low
            if proxy['success_rate'] < 0.3:
                proxy['status'] = 'inactive'
                self.logger.warning(f"Proxy {proxy_id} marked inactive (low success rate)")

            proxy['last_used'] = str(asyncio.get_event_loop().time())
            self.save_config()

    def save_config(self):
        """Save current configuration to file"""
        config = {
            "proxies": self.proxy_pool,
            "account_mapping": self.account_proxy_map,
            "rotation_strategy": "auto",
            "max_accounts_per_proxy": 3
        }

        with open(self.proxy_config_file, 'w') as f:
            json.dump(config, f, indent=2)

    def get_proxy_stats(self) -> Dict:
        """Get proxy usage statistics"""
        total_proxies = len(self.proxy_pool)
        active_proxies = len(self.get_available_proxies())
        assigned_accounts = len(self.account_proxy_map)

        proxy_usage = {}
        for acc_email, proxy_id in self.account_proxy_map.items():
            proxy_usage[proxy_id] = proxy_usage.get(proxy_id, 0) + 1

        return {
            "total_proxies": total_proxies,
            "active_proxies": active_proxies,
            "assigned_accounts": assigned_accounts,
            "proxy_usage": proxy_usage
        }

# Global proxy manager instance
proxy_manager = ProxyManager()

def get_proxy_for_account(account_email: str) -> Optional[Dict]:
    """Get proxy for account (main interface function)"""
    return proxy_manager.assign_proxy_to_account(account_email)

def release_account_proxy(account_email: str):
    """Release proxy for account"""
    proxy_manager.release_proxy(account_email)

def update_proxy_performance(proxy_id: str, success: bool):
    """Update proxy performance metrics"""
    proxy_manager.update_proxy_status(proxy_id, success)

def get_proxy_statistics() -> Dict:
    """Get proxy usage statistics"""
    return proxy_manager.get_proxy_stats()

if __name__ == "__main__":
    # Test the proxy manager
    print("🧪 Testing Proxy Manager...")

    # Test proxy assignment
    accounts = ["user1@gmail.com", "user2@gmail.com", "user3@gmail.com"]

    for account in accounts:
        proxy = get_proxy_for_account(account)
        if proxy:
            print(f"✅ {account} → {proxy['id']} ({proxy['host']}:{proxy['port']})")
        else:
            print(f"❌ No proxy available for {account}")

    # Show statistics
    stats = get_proxy_statistics()
    print(f"\n📊 Statistics: {stats}")

    # Test proxy release
    release_account_proxy("user1@gmail.com")
    print("✅ Released proxy for user1@gmail.com")
