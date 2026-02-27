"""
Unified Device Manager
Automatically detects and manages both Android and iOS devices
"""
from typing import List, Dict, Optional
import logging
from .base import BaseDeviceManager, DevicePlatform
from .android_manager import AndroidDeviceManager
from .ios_manager import IOSDeviceManager

logger = logging.getLogger(__name__)


class UnifiedDeviceManager:
    """Unified manager for both Android and iOS devices"""
    
    def __init__(self):
        self.android_manager = AndroidDeviceManager()
        self.ios_manager = IOSDeviceManager()
        self._managers = {
            DevicePlatform.ANDROID: self.android_manager,
            DevicePlatform.IOS: self.ios_manager
        }
    
    def get_all_devices(self) -> List[Dict[str, str]]:
        """Get all connected devices (Android + iOS)"""
        devices = []
        
        # Get Android devices
        try:
            android_devices = self.android_manager.get_devices()
            devices.extend(android_devices)
        except Exception as e:
            logger.error(f"Error getting Android devices: {e}")
        
        # Get iOS devices
        try:
            ios_devices = self.ios_manager.get_devices()
            devices.extend(ios_devices)
        except Exception as e:
            logger.error(f"Error getting iOS devices: {e}")
        
        return devices
    
    def get_manager_for_device(self, serial: str) -> Optional[BaseDeviceManager]:
        """Get the appropriate manager for a device"""
        # iOS WDA virtual serials (e.g. ios-wda-8100) can be temporarily absent
        # from get_devices() while wdaproxy is restarting. Route them directly.
        if serial.startswith("ios-wda-"):
            return self.ios_manager
        ios_cache = getattr(self.ios_manager, "_serial_to_url", {})
        if isinstance(ios_cache, dict) and serial in ios_cache:
            return self.ios_manager

        # Check Android devices
        try:
            android_devices = self.android_manager.get_devices()
            if any(d['serial'] == serial for d in android_devices):
                return self.android_manager
        except Exception as e:
            logger.warning(f"Android device lookup failed for {serial}: {e}")
        
        # Check iOS devices
        try:
            ios_devices = self.ios_manager.get_devices()
            if any(d['serial'] == serial for d in ios_devices):
                return self.ios_manager
        except Exception as e:
            logger.warning(f"iOS device lookup failed for {serial}: {e}")
        
        return None
    
    def get_device_info(self, serial: str) -> Optional[Dict]:
        """Get device info (auto-detect platform)"""
        manager = self.get_manager_for_device(serial)
        if manager:
            return manager.get_device_info(serial)
        return None
    
    def capture_screenshot(self, serial: str) -> Optional[bytes]:
        """Capture screenshot (auto-detect platform)"""
        manager = self.get_manager_for_device(serial)
        if manager:
            return manager.capture_screenshot(serial)
        return None
    
    def dump_ui_hierarchy(self, serial: str) -> Optional[str]:
        """Dump UI hierarchy (auto-detect platform)"""
        manager = self.get_manager_for_device(serial)
        if manager:
            return manager.dump_ui_hierarchy(serial)
        return None
    
    def tap(self, serial: str, x: int, y: int) -> bool:
        """Tap (auto-detect platform)"""
        manager = self.get_manager_for_device(serial)
        if manager:
            return manager.tap(serial, x, y)
        return False
    
    def swipe(self, serial: str, x1: int, y1: int, x2: int, y2: int, duration: int) -> bool:
        """Swipe (auto-detect platform)"""
        manager = self.get_manager_for_device(serial)
        if manager:
            return manager.swipe(serial, x1, y1, x2, y2, duration)
        return False


# Singleton instance
device_manager = UnifiedDeviceManager()
