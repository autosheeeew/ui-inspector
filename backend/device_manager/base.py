"""
Base Device Manager
Abstract interface for device operations
"""
from abc import ABC, abstractmethod
from typing import List, Dict, Optional, Tuple
from enum import Enum


class DevicePlatform(Enum):
    ANDROID = "android"
    IOS = "ios"


class BaseDeviceManager(ABC):
    """Abstract base class for device management"""
    
    @abstractmethod
    def get_devices(self) -> List[Dict[str, str]]:
        """Get list of connected devices"""
        pass
    
    @abstractmethod
    def get_device_info(self, serial: str) -> Dict[str, any]:
        """Get detailed device information"""
        pass
    
    @abstractmethod
    def get_screen_size(self, serial: str) -> Tuple[int, int]:
        """Get device screen resolution"""
        pass
    
    @abstractmethod
    def capture_screenshot(self, serial: str) -> Optional[bytes]:
        """Capture screenshot from device"""
        pass
    
    @abstractmethod
    def dump_ui_hierarchy(self, serial: str) -> Optional[str]:
        """Dump UI hierarchy XML"""
        pass
    
    @abstractmethod
    def tap(self, serial: str, x: int, y: int) -> bool:
        """Simulate tap at coordinates"""
        pass
    
    @abstractmethod
    def swipe(self, serial: str, x1: int, y1: int, x2: int, y2: int, duration: int) -> bool:
        """Simulate swipe gesture"""
        pass
    
    @property
    @abstractmethod
    def platform(self) -> DevicePlatform:
        """Return platform type"""
        pass
