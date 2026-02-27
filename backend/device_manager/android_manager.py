"""
Android Device Manager
Handles Android device operations using adbutils
"""
from typing import List, Dict, Optional, Tuple
import logging
import re
import time
import io
import subprocess
import requests
from PIL import Image
from adbutils import adb
from .base import BaseDeviceManager, DevicePlatform

logger = logging.getLogger(__name__)


class AndroidDeviceManager(BaseDeviceManager):
    """Manages Android device connections and operations"""

    def __init__(self):
        # Cache adb device handles to avoid re-establishing connections on every screenshot.
        self._device_cache: Dict[str, object] = {}
        # Cache uiautomator2 connections (ATX agent HTTP, much faster screenshots).
        self._u2_cache: Dict[str, object] = {}
        # Persistent HTTP session per device for ATX agent direct calls (connection reuse).
        self._http_session_cache: Dict[str, Tuple[requests.Session, str]] = {}

    def _get_device(self, serial: str):
        if serial not in self._device_cache:
            self._device_cache[serial] = adb.device(serial=serial)
        return self._device_cache[serial]

    # Sentinel to mark a serial as permanently unavailable via u2 (e.g. import error).
    _U2_UNAVAILABLE = object()

    def _get_u2(self, serial: str):
        """Return a cached uiautomator2 connection, or None if unavailable."""
        cached = self._u2_cache.get(serial)
        if cached is AndroidDeviceManager._U2_UNAVAILABLE:
            return None
        if cached is not None:
            return cached
        try:
            import uiautomator2 as u2
            d = u2.connect(serial)
            self._u2_cache[serial] = d
            logger.info(f"[u2] Connected to {serial} via ATX agent")
            return d
        except ImportError as e:
            # Mark permanently unavailable so we don't retry the import every call.
            logger.warning(f"[u2] uiautomator2 import error (run: pip install setuptools): {e}")
            self._u2_cache[serial] = AndroidDeviceManager._U2_UNAVAILABLE
            return None
        except Exception as e:
            logger.warning(f"[u2] Cannot connect to {serial}: {e}")
            return None

    def _get_atx_session(self, serial: str) -> Optional[Tuple[requests.Session, str]]:
        """Return a (session, base_url) for direct HTTP calls to the ATX agent.

        ATX agent always listens on device port 7912.  We set up an explicit
        adb forward without waiting for u2 to succeed — if the agent is already
        running on the device we can reach it directly.
        Uses a persistent requests.Session for HTTP keepalive (avoids TCP setup per call).
        """
        if serial in self._http_session_cache:
            return self._http_session_cache[serial]

        ATX_DEVICE_PORT = 7912
        ATX_LOCAL_PORT  = 7912

        try:
            # Forward regardless of u2 status — atx-agent may already be running.
            ret = subprocess.run(
                ["adb", "-s", serial, "forward", f"tcp:{ATX_LOCAL_PORT}", f"tcp:{ATX_DEVICE_PORT}"],
                capture_output=True, timeout=5,
            )
            if ret.returncode != 0:
                raise RuntimeError(f"adb forward failed: {ret.stderr.decode().strip()}")

            base_url = f"http://127.0.0.1:{ATX_LOCAL_PORT}"
            session = requests.Session()
            resp = session.get(f"{base_url}/info", timeout=3)
            if resp.status_code == 200:
                logger.info(f"[atx] Direct HTTP session to {serial} at {base_url}")
                self._http_session_cache[serial] = (session, base_url)
                return (session, base_url)
            # Agent not responding — try starting it via u2.
            logger.warning(f"[atx] /info returned {resp.status_code}, trying u2 to start agent")
        except Exception as e:
            logger.warning(f"[atx] forward/info failed for {serial}: {e}, trying u2 to start agent")

        # Fallback: use u2.connect() which will start the ATX agent if needed.
        d = self._get_u2(serial)
        if d is None:
            return None

        # Retry the session now that u2 has (re-)started the agent.
        try:
            ret = subprocess.run(
                ["adb", "-s", serial, "forward", f"tcp:{ATX_LOCAL_PORT}", f"tcp:{ATX_DEVICE_PORT}"],
                capture_output=True, timeout=5,
            )
            base_url = f"http://127.0.0.1:{ATX_LOCAL_PORT}"
            session = requests.Session()
            resp = session.get(f"{base_url}/info", timeout=3)
            if resp.status_code == 200:
                logger.info(f"[atx] Direct HTTP session established after u2 start: {base_url}")
                self._http_session_cache[serial] = (session, base_url)
                return (session, base_url)
            logger.warning(f"[atx] /info still {resp.status_code} after u2 start for {serial}")
        except Exception as e:
            logger.warning(f"[atx] Session retry failed for {serial}: {e}")
        return None

    @property
    def platform(self) -> DevicePlatform:
        return DevicePlatform.ANDROID

    def get_devices(self) -> List[Dict[str, str]]:
        """Get list of connected Android devices"""
        try:
            devices = adb.device_list()
            device_list = []

            for device in devices:
                try:
                    model = device.shell("getprop ro.product.model").strip()
                    android_version = device.shell("getprop ro.build.version.release").strip()

                    device_info = {
                        "serial": device.serial,
                        "model": model or "Unknown",
                        "android_version": android_version or "Unknown",
                        "state": "device",
                        "platform": "android"
                    }
                    device_list.append(device_info)
                except Exception as e:
                    logger.error(f"Error getting device info for {device.serial}: {e}")

            return device_list
        except Exception as e:
            logger.error(f"Error listing devices: {e}")
            return []

    def get_device_info(self, serial: str) -> Dict[str, any]:
        """Get detailed Android device information"""
        try:
            width, height = self.get_screen_size(serial)

            return {
                "serial": serial,
                "width": width,
                "height": height,
                "platform": "android"
            }
        except Exception as e:
            logger.error(f"Error getting device info: {e}")
            return None

    def get_screen_size(self, serial: str) -> Tuple[int, int]:
        """Get Android device screen resolution"""
        try:
            device = self._get_device(serial)
            size_output = device.shell("wm size").strip()
            if ":" in size_output:
                size_str = size_output.split(":")[-1].strip()
                width, height = map(int, size_str.split("x"))
                return (width, height)
            return (1080, 1920)
        except Exception as e:
            logger.error(f"Error getting screen size: {e}")
            return (1080, 1920)

    def capture_screenshot(self, serial: str) -> Optional[bytes]:
        """Capture screenshot from Android device, returned as JPEG bytes.

        Priority:
          1. ATX agent direct HTTP  — fast    (~700ms, PNG over USB port-forward)
          2. uiautomator2 SDK       — fallback
          3. adbutils screencap     — last resort (~1000-1800ms, PNG over ADB)
          4. adb shell screencap    — emergency fallback
        """
        import time as _time

        # ── Method 1: ATX agent direct HTTP (persistent session, connection reuse) ───
        atx = self._get_atx_session(serial)
        if atx is not None:
            session, base_url = atx
            try:
                t0 = _time.monotonic()
                resp = session.get(f"{base_url}/screenshot/0", timeout=5)
                elapsed_ms = (_time.monotonic() - t0) * 1000
                if resp.status_code == 200 and len(resp.content) > 100:
                    logger.debug(f"[atx] screenshot ok {elapsed_ms:.0f}ms {len(resp.content)//1024}KB")
                    content_type = resp.headers.get('Content-Type', '')
                    if 'jpeg' in content_type:
                        return resp.content
                    # PNG response — re-encode to JPEG.
                    img = Image.open(io.BytesIO(resp.content))
                    buf = io.BytesIO()
                    img.save(buf, format='JPEG', quality=80)
                    return buf.getvalue()
                else:
                    logger.warning(f"[atx] screenshot returned {resp.status_code}, len={len(resp.content)} — evicting session")
                    self._http_session_cache.pop(serial, None)
            except Exception as e:
                logger.warning(f"[atx] screenshot failed for {serial}: {e} — evicting session")
                self._http_session_cache.pop(serial, None)
        else:
            logger.warning(f"[atx] no session for {serial}, falling back to u2")

        # ── Method 2: uiautomator2 SDK screenshot ────────────────────────────────────
        d = self._get_u2(serial)
        if d is not None:
            try:
                logger.info(f"[u2] using SDK screenshot for {serial}")
                img = d.screenshot()
                if img is not None and hasattr(img, 'save'):
                    buf = io.BytesIO()
                    img.save(buf, format='JPEG', quality=80)
                    return buf.getvalue()
            except Exception as e:
                logger.warning(f"[u2] Screenshot failed for {serial}: {e} — evicting cache")
                self._u2_cache.pop(serial, None)

        # ── Method 3: adbutils screencap ─────────────────────────────────────────────
        logger.warning(f"[adb] falling back to adbutils screencap for {serial}")
        try:
            device = self._get_device(serial)
            screenshot = device.screenshot()
            if isinstance(screenshot, bytes):
                return screenshot
            if hasattr(screenshot, 'save'):
                buf = io.BytesIO()
                screenshot.save(buf, format='JPEG', quality=80)
                return buf.getvalue()
        except Exception as e:
            logger.warning(f"[adb] adbutils screenshot failed for {serial}: {e}")
            self._device_cache.pop(serial, None)

        # ── Method 4: raw shell screencap ─────────────────────────────────────────────
        try:
            device = self._get_device(serial)
            png_data = device.shell("screencap -p", encoding=None)
            if png_data and len(png_data) > 100:
                return png_data
        except Exception as e:
            logger.error(f"[adb] Shell screencap failed for {serial}: {e}")
            self._device_cache.pop(serial, None)

        return None

    def _read_xml_via_sync(self, device, target: str) -> Optional[str]:
        """Read a remote file via adb sync."""
        try:
            buf = b""
            for chunk in device.sync.iter_content(target):
                buf += chunk
            return buf.decode("utf-8", errors="replace")
        except Exception as e:
            logger.warning(f"Sync read failed for {target}: {e}")
            return None

    def _native_uiautomator_dump(self, device, target: str) -> Tuple[Optional[str], Optional[str]]:
        """Run uiautomator dump and read result via sync."""
        result = device.shell(f"rm -f {target}; uiautomator dump {target} && echo __ok__")
        if "ERROR" in result or "Exception" in result or "__ok__" not in result:
            return None, result.strip()

        xml_content = self._read_xml_via_sync(device, target)
        device.shell(f"rm -f {target}")

        if xml_content and len(xml_content) > 100 and xml_content.strip().startswith("<?xml"):
            return xml_content, None
        return None, f"invalid XML (len={len(xml_content or '')})"

    def dump_ui_hierarchy(self, serial: str) -> Optional[str]:
        """Dump UI hierarchy from Android device, with multiple fallbacks."""
        device = self._get_device(serial)

        # --- Method 0: ATX agent — JSONRPC dumpWindowHierarchy + REST /dump/0 ---
        atx = self._get_atx_session(serial)
        logger.info(f"[dump] ATX session available: {atx is not None} for {serial}")
        if atx is not None:
            session, base_url = atx

            # 0a: JSON-RPC dumpWindowHierarchy (same path uiautomator2 SDK uses internally)
            try:
                payload = {
                    "method": "dumpWindowHierarchy",
                    "id": 1,
                    "jsonrpc": "2.0",
                    "params": [True, None],
                }
                resp = session.post(f"{base_url}/jsonrpc/0", json=payload, timeout=30)
                if resp.status_code == 200:
                    data = resp.json()
                    xml = data.get("result") or ""
                    if xml and len(xml) > 100 and "<?xml" in xml:
                        logger.info(f"✅ [dump] ATX JSONRPC dumpWindowHierarchy: {len(xml)} bytes")
                        return xml
                    logger.warning(f"[dump] ATX JSONRPC returned unexpected: status={resp.status_code} result_len={len(xml)}")
            except Exception as e:
                logger.warning(f"[dump] ATX JSONRPC failed: {e}")

            # 0b: REST /dump/* endpoints (available in some ATX versions)
            for endpoint in ("/dump/0", "/dump/hierarchy"):
                try:
                    resp = session.get(f"{base_url}{endpoint}", timeout=15)
                    if resp.status_code == 200 and len(resp.content) > 100:
                        text = resp.text
                        if text.strip().startswith("<?xml") or text.strip().startswith("<hierarchy"):
                            logger.info(f"✅ [dump] ATX REST {endpoint}: {len(text)} bytes")
                            return text
                    logger.debug(f"[dump] ATX REST {endpoint}: status={resp.status_code} len={len(resp.content)}")
                except Exception as e:
                    logger.debug(f"[dump] ATX REST {endpoint} failed: {e}")

        # --- Method 1: uiautomator2 SDK dump_hierarchy ---
        try:
            logger.info(f"[dump] Trying uiautomator2 for {serial}")
            d = self._get_u2(serial)
            if d:
                xml_content = d.dump_hierarchy()
                if xml_content and len(xml_content) > 100:
                    logger.info(f"✅ [dump] uiautomator2 succeeded: {len(xml_content)} bytes")
                    return xml_content
                logger.warning(f"[dump] uiautomator2 returned empty/short content")
        except Exception as e:
            logger.warning(f"[dump] uiautomator2 failed: {e}")

        # --- Method 2: adbutils built-in dump_hierarchy ---
        try:
            if hasattr(device, "dump_hierarchy"):
                logger.info(f"[dump] Trying adbutils dump_hierarchy for {serial}")
                xml_content = device.dump_hierarchy()
                if xml_content and len(xml_content) > 100:
                    logger.info(f"✅ [dump] adbutils dump_hierarchy succeeded: {len(xml_content)} bytes")
                    return xml_content
        except Exception as e:
            logger.warning(f"[dump] adbutils dump_hierarchy failed: {e}")

        # --- Method 3: uiautomator dump /dev/stdout (avoids file I/O, less likely to be killed) ---
        try:
            logger.info(f"[dump] Trying uiautomator dump /dev/stdout for {serial}")
            output = device.shell("uiautomator dump /dev/stdout", timeout=20)
            if output and len(output) > 100 and "<?xml" in output:
                xml_start = output.find("<?xml")
                xml_content = output[xml_start:].strip()
                if xml_content:
                    logger.info(f"✅ [dump] uiautomator /dev/stdout succeeded: {len(xml_content)} bytes")
                    return xml_content
        except Exception as e:
            logger.warning(f"[dump] uiautomator /dev/stdout failed: {e}")

        # --- Method 4: Native uiautomator dump to tmp file ---
        target = "/data/local/tmp/window_dump.xml"
        for attempt in range(1, 3):
            logger.info(f"[dump] Native uiautomator dump attempt {attempt}/2 for {serial}")
            try:
                xml_content, err = self._native_uiautomator_dump(device, target)
                if xml_content:
                    logger.info(f"✅ [dump] Native uiautomator dump succeeded: {len(xml_content)} bytes")
                    return xml_content
                logger.warning(f"[dump] Attempt {attempt} failed: {err}")
                if attempt < 2:
                    time.sleep(1.0)
            except Exception as e:
                logger.warning(f"[dump] Attempt {attempt} exception: {e}")
                if attempt < 2:
                    time.sleep(1.0)

        logger.error(f"[dump] All dump methods failed for {serial}")
        return None

    def tap(self, serial: str, x: int, y: int) -> bool:
        """Simulate tap on Android device"""
        try:
            device = self._get_device(serial)
            device.shell(f"input tap {x} {y}")
            return True
        except Exception as e:
            logger.error(f"Error tapping: {e}")
            return False

    def swipe(self, serial: str, x1: int, y1: int, x2: int, y2: int, duration: int) -> bool:
        """Simulate swipe on Android device"""
        try:
            device = self._get_device(serial)
            device.shell(f"input swipe {x1} {y1} {x2} {y2} {duration}")
            return True
        except Exception as e:
            logger.error(f"Error swiping: {e}")
            return False
