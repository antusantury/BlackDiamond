import json
import os
from datetime import datetime
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict
from pathlib import Path

@dataclass
class Service:
    """Service configuration"""
    key: str
    name: str
    description: str
    is_enabled: bool = True
    maintenance_message: str = ""
    last_updated: str = ""
    
    def __post_init__(self):
        if not self.last_updated:
            self.last_updated = datetime.now().isoformat()

class ServiceManager:
    """Manages service status and configuration"""
    
    def __init__(self, config_file: str = "data/services.json"):
        self.config_file = config_file
        self.services: Dict[str, Service] = {}
        self._ensure_data_directory()
        self._load_config()
        self._initialize_default_services()
    
    def _ensure_data_directory(self):
        """Ensure the data directory exists"""
        data_dir = Path(self.config_file).parent
        data_dir.mkdir(parents=True, exist_ok=True)
    
    def _load_config(self):
        """Load service configuration from file"""
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    for service_data in data.get('services', []):
                        service = Service(**service_data)
                        self.services[service.key] = service
            except Exception as e:
                print(f"Error loading service config: {e}")
    
    def _save_config(self):
        """Save service configuration to file"""
        try:
            data = {
                'services': [asdict(service) for service in self.services.values()],
                'last_updated': datetime.now().isoformat()
            }
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Error saving service config: {e}")
    
    def _initialize_default_services(self):
        """Initialize default services if none exist"""
        if not self.services:
            default_services = [
                # Main Services
                Service(
                    key='telegram_bot',
                    name='Telegram Bot',
                    description='Main Telegram bot functionality',
                    is_enabled=True,
                    maintenance_message="Telegram bot is temporarily under maintenance. Please try again later."
                ),
                Service(
                    key='web_interface',
                    name='Web Interface',
                    description='Web application interface',
                    is_enabled=True,
                    maintenance_message="Web interface is temporarily under maintenance. Please try again later."
                ),
                
                # Telegram Bot Features
                Service(
                    key='bot_deal_creation',
                    name='Bot: Deal Creation',
                    description='Deal creation via Telegram bot',
                    is_enabled=True,
                    maintenance_message="Deal creation via Telegram bot is temporarily disabled."
                ),
                Service(
                    key='bot_deal_joining',
                    name='Bot: Deal Joining',
                    description='Deal joining via Telegram bot',
                    is_enabled=True,
                    maintenance_message="Deal joining via Telegram bot is temporarily disabled."
                ),
                Service(
                    key='bot_profile_view',
                    name='Bot: Profile Viewing',
                    description='Profile viewing via Telegram bot',
                    is_enabled=True,
                    maintenance_message="Profile viewing via Telegram bot is temporarily disabled."
                ),
                Service(
                    key='bot_support',
                    name='Bot: Support Chat',
                    description='Support chat via Telegram bot',
                    is_enabled=True,
                    maintenance_message="Support chat via Telegram bot is temporarily disabled."
                ),
                
                # Web Interface Features
                Service(
                    key='web_deal_creation',
                    name='Web: Deal Creation',
                    description='Deal creation via web interface',
                    is_enabled=True,
                    maintenance_message="Deal creation via web interface is temporarily disabled."
                ),
                Service(
                    key='web_deal_joining',
                    name='Web: Deal Joining',
                    description='Deal joining via web interface',
                    is_enabled=True,
                    maintenance_message="Deal joining via web interface is temporarily disabled."
                ),
                Service(
                    key='web_deal_viewing',
                    name='Web: Deal Viewing',
                    description='Deal detail viewing via web interface',
                    is_enabled=True,
                    maintenance_message="Deal viewing via web interface is temporarily disabled."
                ),
                Service(
                    key='web_profile',
                    name='Web: Profile Management',
                    description='Profile management via web interface',
                    is_enabled=True,
                    maintenance_message="Profile management via web interface is temporarily disabled."
                ),
                Service(
                    key='web_support',
                    name='Web: Support Chat',
                    description='Support chat via web interface',
                    is_enabled=True,
                    maintenance_message="Support chat via web interface is temporarily disabled."
                ),
                Service(
                    key='web_admin_panel',
                    name='Web: Admin Panel',
                    description='Admin panel access via web interface',
                    is_enabled=True,
                    maintenance_message="Admin panel access is temporarily disabled."
                ),
                Service(
                    key='web_statistics',
                    name='Web: Statistics',
                    description='Statistics and analytics viewing',
                    is_enabled=True,
                    maintenance_message="Statistics viewing is temporarily disabled."
                ),
                
                # Core Systems
                Service(
                    key='payments',
                    name='Payment System',
                    description='Cryptocurrency payment processing',
                    is_enabled=True,
                    maintenance_message="Payment system is temporarily under maintenance. Please try again later."
                ),
                Service(
                    key='notifications',
                    name='Notifications',
                    description='User notification system',
                    is_enabled=True,
                    maintenance_message="Notification system is temporarily under maintenance. Please try again later."
                ),
                Service(
                    key='api',
                    name='API Services',
                    description='REST API endpoints',
                    is_enabled=True,
                    maintenance_message="API services are temporarily under maintenance. Please try again later."
                )
            ]
            
            for service in default_services:
                self.services[service.key] = service
            
            self._save_config()
    
    def get_service(self, service_key: str) -> Optional[Service]:
        """Get service by key"""
        return self.services.get(service_key)
    
    def get_all_services(self) -> List[Service]:
        """Get all services"""
        return list(self.services.values())
    
    def get_enabled_services(self) -> List[Service]:
        """Get enabled services"""
        return [service for service in self.services.values() if service.is_enabled]
    
    def get_disabled_services(self) -> List[Service]:
        """Get disabled services"""
        return [service for service in self.services.values() if not service.is_enabled]
    
    def is_service_enabled(self, service_key: str) -> bool:
        """Check if service is enabled"""
        service = self.get_service(service_key)
        return service.is_enabled if service else False
    
    def set_service_status(self, service_key: str, enabled: bool) -> bool:
        """Enable or disable a service"""
        service = self.get_service(service_key)
        if service:
            service.is_enabled = enabled
            service.last_updated = datetime.now().isoformat()
            self._save_config()
            return True
        return False
    
    def update_service_message(self, service_key: str, message: str) -> bool:
        """Update maintenance message for a service"""
        service = self.get_service(service_key)
        if service:
            service.maintenance_message = message
            service.last_updated = datetime.now().isoformat()
            self._save_config()
            return True
        return False
    
    def get_maintenance_message(self, service_key: str) -> str:
        """Get maintenance message for a service"""
        service = self.get_service(service_key)
        return service.maintenance_message if service else ""
    
    def enable_all_services(self):
        """Enable all services"""
        for service in self.services.values():
            service.is_enabled = True
            service.last_updated = datetime.now().isoformat()
        self._save_config()
    
    def disable_all_services(self):
        """Disable all services"""
        for service in self.services.values():
            service.is_enabled = False
            service.last_updated = datetime.now().isoformat()
        self._save_config()
    
    def get_services_status_summary(self) -> Dict:
        """Get summary of all services status"""
        total = len(self.services)
        enabled = len(self.get_enabled_services())
        disabled = len(self.get_disabled_services())
        
        return {
            'total': total,
            'enabled': enabled,
            'disabled': disabled,
            'is_maintenance_mode': disabled == total,
            'is_all_enabled': enabled == total,
            'last_updated': max([s.last_updated for s in self.services.values()], default="")
        }
    
    def get_services_for_template(self) -> List[Dict]:
        """Get services data formatted for template rendering"""
        return [
            {
                'key': service.key,
                'name': service.name,
                'description': service.description,
                'is_enabled': service.is_enabled,
                'maintenance_message': service.maintenance_message,
                'last_updated': service.last_updated
            }
            for service in self.services.values()
        ]

# Global service manager instance
service_manager = ServiceManager()

def is_service_available(service_key: str) -> bool:
    """Check if a service is available (enabled)"""
    return service_manager.is_service_enabled(service_key)

def get_service_message(service_key: str) -> str:
    """Get maintenance message for a service"""
    return service_manager.get_maintenance_message(service_key)

def get_unavailable_services() -> List[str]:
    """Get list of unavailable (disabled) services"""
    return [service.key for service in service_manager.get_disabled_services()]

def get_maintenance_mode_status() -> bool:
    """Check if system is in maintenance mode (all services disabled)"""
    return service_manager.get_services_status_summary()['is_maintenance_mode']