"""
Device Manager Module
Handles ADB device detection and management
"""
from typing import List, Dict, Optional
from adbutils import adb
import logging
import io
from PIL import Image

logger = logging.getLogger(__name__)


class DeviceManager:
    """Manages ADB device connections and operations"""
    
    @staticmethod
    def get_devices() -> List[Dict[str, str]]:
        """
        Get list of connected Android devices
        
        Returns:
            List of device info dictionaries
        """
        try:
            devices = adb.device_list()
            device_list = []
            
            for device in devices:
                try:
                    # Get device properties
                    model = device.shell("getprop ro.product.model").strip()
                    android_version = device.shell("getprop ro.build.version.release").strip()
                    
                    device_info = {
                        "serial": device.serial,
                        "model": model or "Unknown",
                        "android_version": android_version or "Unknown",
                        "state": "device"
                    }
                    device_list.append(device_info)
                except Exception as e:
                    logger.error(f"Error getting device info for {device.serial}: {e}")
                    device_list.append({
                        "serial": device.serial,
                        "model": "Unknown",
                        "android_version": "Unknown",
                        "state": "error"
                    })
            
            return device_list
        except Exception as e:
            logger.error(f"Error listing devices: {e}")
            return []
    
    @staticmethod
    def get_device(serial: str):
        """Get specific device by serial"""
        try:
            return adb.device(serial=serial)
        except Exception as e:
            logger.error(f"Device {serial} not found: {e}")
            return None
    
    @staticmethod
    def get_screen_size(serial: str) -> tuple:
        """
        Get device screen resolution
        
        Returns:
            Tuple of (width, height)
        """
        try:
            device = adb.device(serial=serial)
            size_output = device.shell("wm size").strip()
            # Output format: "Physical size: 1080x1920"
            if ":" in size_output:
                size_str = size_output.split(":")[-1].strip()
                width, height = map(int, size_str.split("x"))
                return (width, height)
            return (1080, 1920)  # Default fallback
        except Exception as e:
            logger.error(f"Error getting screen size: {e}")
            return (1080, 1920)
    
    @staticmethod
    def capture_screenshot(serial: str) -> Optional[bytes]:
        """
        Capture screenshot from device
        
        Returns:
            PNG image bytes
        """
        try:
            device = adb.device(serial=serial)
            
            # Method 1: Try using adbutils screenshot
            try:
                screenshot = device.screenshot()
                
                # Check if it's already bytes
                if isinstance(screenshot, bytes):
                    return screenshot
                
                # If it's a PIL Image, convert to bytes
                if hasattr(screenshot, 'save'):
                    buffer = io.BytesIO()
                    screenshot.save(buffer, format='PNG')
                    return buffer.getvalue()
                
                logger.warning("Screenshot returned unexpected type, trying method 2...")
                
            except Exception as e:
                logger.warning(f"Method 1 failed: {e}, trying method 2...")
            
            # Method 2: Use shell command (more reliable)
            try:
                # Capture screenshot using screencap
                png_data = device.shell("screencap -p", encoding=None)
                
                # Verify it's valid PNG data
                if png_data and len(png_data) > 100:
                    # Check PNG header
                    if png_data[:8] == b'\x89PNG\r\n\x1a\n':
                        return png_data
                    
                    # Try to open and convert
                    try:
                        img = Image.open(io.BytesIO(png_data))
                        buffer = io.BytesIO()
                        img.save(buffer, format='PNG')
                        return buffer.getvalue()
                    except:
                        pass
                
            except Exception as e:
                logger.error(f"Method 2 failed: {e}")
            
            # Method 3: Save to device then pull
            try:
                device.shell("screencap -p /sdcard/screenshot_temp.png")
                png_data = device.sync.read_bytes("/sdcard/screenshot_temp.png")
                device.shell("rm /sdcard/screenshot_temp.png")
                
                if png_data and len(png_data) > 100:
                    return png_data
                    
            except Exception as e:
                logger.error(f"Method 3 failed: {e}")
            
            logger.error("All screenshot methods failed")
            return None
            
        except Exception as e:
            logger.error(f"Error capturing screenshot: {e}")
            return None

    
    @staticmethod
    def dump_ui_hierarchy(serial: str) -> Optional[str]:
        """
        Dump UI hierarchy XML from device
        
        Returns:
            XML string content
        """
        try:
            device = adb.device(serial=serial)
            
            # Dump UI hierarchy to device storage
            result = device.shell("uiautomator dump /sdcard/window_dump.xml")
            
            # Check if dump was successful
            if "ERROR" in result or "Exception" in result:
                logger.error(f"UI dump failed: {result}")
                return None
            
            # Pull the XML file
            xml_content = device.shell("cat /sdcard/window_dump.xml")
            
            # Clean up
            device.shell("rm /sdcard/window_dump.xml")
            
            return xml_content
        except Exception as e:
            logger.error(f"Error dumping UI hierarchy: {e}")
            return None
