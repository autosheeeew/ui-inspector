"""iOS device manager using WebDriverAgent (WDA)."""
from typing import Callable, Dict, List, Optional, Tuple
import io
import logging
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
import xml.etree.ElementTree as ET

import requests
from PIL import Image

try:
    import wda
    WDA_AVAILABLE = True
except ImportError:
    WDA_AVAILABLE = False
    logging.warning("facebook-wda not installed. iOS support disabled.")

from .base import BaseDeviceManager, DevicePlatform

logger = logging.getLogger(__name__)


def _as_int(value, default: int = 0) -> int:
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        m = re.search(r"-?\d+(?:\.\d+)?", value)
        if m:
            try:
                return int(float(m.group(0)))
            except ValueError:
                return default
    return default


def _as_bool_str(value, default: str = "false") -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return "true" if value else "false"
    if isinstance(value, str):
        val = value.strip().lower()
        if val in {"1", "true", "yes", "enabled"}:
            return "true"
        if val in {"0", "false", "no", "disabled"}:
            return "false"
    return default


class IOSDeviceManager(BaseDeviceManager):
    """iOS manager backed by WDA HTTP endpoints."""

    def __init__(self):
        self._serial_to_url: Dict[str, str] = {}
        self._autostart_enabled = _as_bool_str(os.getenv("IOS_WDA_AUTOSTART", "true"), "true") == "true"
        self._autostart_tool = os.getenv("IOS_WDA_AUTOSTART_TOOL", "auto").strip().lower()
        self._autostart_retries = max(1, _as_int(os.getenv("IOS_WDA_RETRIES", "10"), 10))
        self._autostart_retry_interval = max(0.2, float(os.getenv("IOS_WDA_RETRY_INTERVAL", "3.0")))
        self._autostart_boot_wait = max(5.0, float(os.getenv("IOS_WDA_BOOT_WAIT", "45.0")))
        self._wda_port = max(1, _as_int(os.getenv("IOS_WDA_LOCAL_PORT", "8100"), 8100))
        self._wda_bundle_id = os.getenv(
            "IOS_WDA_BUNDLE_ID",
            "com.qiaotong.wda.runner",
        ).strip()
        self._wda_processes: Dict[str, subprocess.Popen] = {}
        self._wda_process_log_paths: Dict[str, str] = {}
        self._wda_process_log_files: Dict[str, object] = {}
        self._wda_process_lock = threading.Lock()
        self._wda_process_log_dir: str = (
            os.getenv("IOS_WDA_PROCESS_LOG_DIR", "").strip()
            or os.path.join(tempfile.gettempdir(), "android-ui-inspector")
        )
        # Health cache: avoids probing /status on every API call when WDA is stable.
        self._wda_healthy_ts: Dict[str, float] = {}
        self._wda_healthy_ttl: float = 8.0
        # Pixel scale cache: logical WDA points → physical pixels ratio.
        self._pixel_scale_cache: Dict[str, float] = {}
        # Screenshot failure control: only restart WDA after N consecutive failures.
        self._screenshot_fail_streak: Dict[str, int] = {}
        self._screenshot_fail_restart_threshold: int = max(
            1, _as_int(os.getenv("IOS_WDA_SCREENSHOT_FAIL_RESTART_THRESHOLD", "5"), 5)
        )
        self._screenshot_attempts: int = max(
            1, _as_int(os.getenv("IOS_WDA_SCREENSHOT_ATTEMPTS", "1"), 1)
        )
        self._screenshot_retry_interval: float = max(
            0.05, float(os.getenv("IOS_WDA_SCREENSHOT_RETRY_INTERVAL", "0.15"))
        )
        if WDA_AVAILABLE:
            logger.info("iOS support enabled via WDA")
        else:
            logger.warning("facebook-wda unavailable. iOS features disabled.")

    @property
    def platform(self) -> DevicePlatform:
        return DevicePlatform.IOS

    def _env_device_map(self) -> Dict[str, str]:
        # IOS_WDA_DEVICE_MAP: serial1=http://127.0.0.1:8100,serial2=http://127.0.0.1:8200
        raw = os.getenv("IOS_WDA_DEVICE_MAP", "").strip()
        mapping: Dict[str, str] = {}
        if not raw:
            return mapping
        for entry in raw.split(","):
            if "=" not in entry:
                continue
            serial, url = entry.split("=", 1)
            serial = serial.strip()
            url = url.strip().rstrip("/")
            if serial and url:
                mapping[serial] = url
        return mapping

    def _candidate_urls(self) -> List[str]:
        raw = os.getenv("IOS_WDA_URLS", "").strip()
        if raw:
            urls = [x.strip().rstrip("/") for x in raw.split(",") if x.strip()]
            if urls:
                return urls
        return ["http://127.0.0.1:8100"]

    def _wda_status(self, url: str) -> Optional[dict]:
        try:
            resp = requests.get(f"{url}/status", timeout=1.5)
            if resp.ok:
                payload = resp.json()
                if isinstance(payload, dict):
                    return payload
        except Exception:
            return None
        return None

    def _derive_serial(self, url: str, status: dict) -> str:
        value = status.get("value", {}) if isinstance(status.get("value"), dict) else {}
        for key in ("udid", "deviceUDID", "deviceId", "DeviceIdentifier"):
            if isinstance(value.get(key), str) and value[key].strip():
                return value[key].strip()
        m = re.search(r":(\d+)$", url)
        return f"ios-wda-{m.group(1) if m else '8100'}"

    def _find_url_for_serial(self, serial: str) -> Optional[str]:
        if serial in self._serial_to_url:
            return self._serial_to_url[serial]
        env_map = self._env_device_map()
        if serial in env_map:
            return env_map[serial]
        for dev in self.get_devices():
            if dev["serial"] == serial:
                return self._serial_to_url.get(serial)
        fallback = f"http://127.0.0.1:{self._wda_port}"
        self._serial_to_url[serial] = fallback
        return fallback

    def _url_port(self, url: str) -> int:
        m = re.search(r":(\d+)(?:/)?$", url.strip())
        return int(m.group(1)) if m else self._wda_port

    def _mark_healthy(self, url: str) -> None:
        self._wda_healthy_ts[url] = time.monotonic()

    def _status_ready(self, url: str) -> bool:
        last_ok = self._wda_healthy_ts.get(url, 0.0)
        if time.monotonic() - last_ok < self._wda_healthy_ttl:
            return True
        ok = self._wda_status(url) is not None
        if ok:
            self._mark_healthy(url)
        return ok

    # Known WDA bundle ID suffixes used by different build configurations.
    _WDA_BUNDLE_SUFFIXES = (
        "WebDriverAgentRunner.xctrunner",
        "wda.runner.xctrunner",
        "wda.runner",
        "WebDriverAgentRunner",
        "xctrunner",
    )

    @staticmethod
    def _is_derived_serial(serial: str) -> bool:
        """Return True if serial is our internal derived ID (e.g. ios-wda-8100), not a real UDID."""
        return serial.startswith("ios-wda-")

    def _detect_wda_bundle(self, serial: str) -> Optional[str]:
        """Query tidevice applist to find the installed WDA bundle ID."""
        tidevice_bin = shutil.which(
            os.getenv("IOS_TIDEVICE_BIN", "tidevice").strip() or "tidevice"
        )
        if not tidevice_bin:
            return None
        try:
            cmd = [tidevice_bin]
            if serial:
                cmd += ["-u", serial]
            cmd.append("applist")
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=15
            )
            for line in result.stdout.splitlines():
                parts = line.split()
                if not parts:
                    continue
                bid = parts[0]
                if any(bid.endswith(sfx) for sfx in self._WDA_BUNDLE_SUFFIXES):
                    logger.info(f"[iOS WDA] Detected WDA bundle ID: {bid}")
                    return bid
        except Exception as e:
            logger.debug(f"[iOS WDA] Bundle auto-detect failed: {e}")
        return None

    def _resolve_wda_bundle(self, serial: str) -> str:
        """Return configured bundle ID, falling back to auto-detection."""
        configured = os.getenv("IOS_WDA_BUNDLE_ID", "").strip()
        if configured:
            return configured
        detected = self._detect_wda_bundle(serial)
        if detected:
            return detected
        return self._wda_bundle_id

    def _build_autostart_commands(self, serial: str, url: str) -> List[List[str]]:
        port = self._url_port(url)
        tidevice_bin = os.getenv("IOS_TIDEVICE_BIN", "tidevice").strip() or "tidevice"
        real_serial = serial if (serial and not self._is_derived_serial(serial)) else ""
        bundle = self._resolve_wda_bundle(real_serial)
        commands: List[List[str]] = []

        if real_serial:
            commands.append([tidevice_bin, "-u", real_serial, "wdaproxy", "-B", bundle, "--port", str(port)])
            commands.append([tidevice_bin, "-u", real_serial, "wdaproxy", "-B", bundle])
        else:
            commands.append([tidevice_bin, "wdaproxy", "-B", bundle, "--port", str(port)])
            commands.append([tidevice_bin, "wdaproxy", "-B", bundle])

        return commands

    def _start_wda_process(self, serial: str, url: str) -> bool:
        key = serial or url
        if not self._autostart_enabled:
            return False

        with self._wda_process_lock:
            existing = self._wda_processes.get(key)
            if existing and existing.poll() is None:
                return True
            if existing and existing.poll() is not None:
                code = existing.poll()
                log_path = self._wda_process_log_paths.get(key, "")
                logger.warning(
                    f"[iOS WDA] Previous proxy process exited (code={code})"
                    + (f", log={log_path}" if log_path else "")
                )
                old_f = self._wda_process_log_files.pop(key, None)
                if old_f:
                    try:
                        old_f.close()
                    except Exception:
                        pass

            tried_any = False
            for cmd in self._build_autostart_commands(serial, url):
                if not shutil.which(cmd[0]):
                    continue
                tried_any = True
                log_f = None
                try:
                    os.makedirs(self._wda_process_log_dir, exist_ok=True)
                    port = self._url_port(url)
                    log_path = os.path.join(self._wda_process_log_dir, f"wda-proxy-{port}.log")
                    log_f = open(log_path, "ab")
                    proc = subprocess.Popen(
                        cmd,
                        stdout=log_f,
                        stderr=log_f,
                        start_new_session=True,
                    )
                    self._wda_processes[key] = proc
                    self._wda_process_log_paths[key] = log_path
                    self._wda_process_log_files[key] = log_f
                    logger.info(f"[iOS WDA] Auto-start command launched: {' '.join(cmd)}")
                    logger.info(f"[iOS WDA] Proxy log: {log_path}")
                    return True
                except Exception as e:
                    if log_f:
                        try:
                            log_f.close()
                        except Exception:
                            pass
                    logger.warning(f"[iOS WDA] Failed to launch {' '.join(cmd)}: {e}")
                    continue
            if not tried_any:
                logger.warning(
                    "[iOS WDA] Auto-start tool not found. Install tidevice, "
                    "or set IOS_WDA_AUTOSTART_TOOL/IOS_TIDEVICE_BIN."
                )
        return False

    def _ensure_wda_ready(self, serial: str, url: str) -> bool:
        if self._status_ready(url):
            return True
        if not self._autostart_enabled:
            return False

        self._start_wda_process(serial, url)
        deadline = time.monotonic() + self._autostart_boot_wait
        interval = self._autostart_retry_interval
        while time.monotonic() < deadline:
            time.sleep(interval)
            if self._status_ready(url):
                return True
            interval = min(interval * 1.3, 5.0)
        return self._status_ready(url)

    def stop_wda_proxy(self, serial: Optional[str] = None) -> None:
        """Stop the WDA proxy process for a given serial (or all if serial is None)."""
        with self._wda_process_lock:
            keys = [serial] if serial else list(self._wda_processes.keys())
            for key in keys:
                proc = self._wda_processes.pop(key, None)
                if proc and proc.poll() is None:
                    try:
                        proc.terminate()
                        logger.info(f"[iOS WDA] Stopped proxy process for {key}")
                    except Exception as e:
                        logger.warning(f"[iOS WDA] Failed to stop proxy for {key}: {e}")
                log_f = self._wda_process_log_files.pop(key, None)
                if log_f:
                    try:
                        log_f.close()
                    except Exception:
                        pass
                self._wda_process_log_paths.pop(key, None)
                url = self._serial_to_url.get(key, "")
                if url:
                    self._wda_healthy_ts.pop(url, None)

    def _client_for_serial(self, serial: str):
        if not WDA_AVAILABLE:
            return None
        url = self._find_url_for_serial(serial)
        if not url:
            return None
        self._ensure_wda_ready(serial, url)
        try:
            return wda.Client(url)
        except Exception as e:
            logger.error(f"Failed creating WDA client for {serial[:8]}: {e}")
            return None

    def _session_or_client(self, client):
        try:
            return client.session()
        except Exception:
            return client

    def get_devices(self) -> List[Dict[str, str]]:
        if not WDA_AVAILABLE:
            return []

        devices: List[Dict[str, str]] = []
        seen = set()

        for serial, url in self._env_device_map().items():
            status = self._wda_status(url)
            if not status:
                continue
            value = status.get("value", {}) if isinstance(status.get("value"), dict) else {}
            ios_info = value.get("ios", {}) if isinstance(value.get("ios"), dict) else {}
            self._serial_to_url[serial] = url
            devices.append(
                {
                    "serial": serial,
                    "model": str(ios_info.get("model") or value.get("model") or "iPhone"),
                    "name": str(ios_info.get("name") or value.get("deviceName") or serial),
                    "ios_version": str(ios_info.get("version") or value.get("osVersion") or "Unknown"),
                    "state": "device",
                    "platform": "ios",
                }
            )
            seen.add(serial)

        for url in self._candidate_urls():
            status = self._wda_status(url)
            if not status and self._autostart_enabled:
                self._ensure_wda_ready("", url)
                status = self._wda_status(url)
            if not status:
                continue
            serial = self._derive_serial(url, status)
            if serial in seen:
                continue
            value = status.get("value", {}) if isinstance(status.get("value"), dict) else {}
            ios_info = value.get("ios", {}) if isinstance(value.get("ios"), dict) else {}
            self._serial_to_url[serial] = url
            devices.append(
                {
                    "serial": serial,
                    "model": str(ios_info.get("model") or value.get("model") or "iPhone"),
                    "name": str(ios_info.get("name") or value.get("deviceName") or serial),
                    "ios_version": str(ios_info.get("version") or value.get("osVersion") or "Unknown"),
                    "state": "device",
                    "platform": "ios",
                }
            )
            seen.add(serial)

        logger.info(f"Found {len(devices)} iOS device(s) via WDA")
        return devices

    def get_device_info(self, serial: str) -> Optional[Dict[str, any]]:
        if not WDA_AVAILABLE:
            return None
        client = self._client_for_serial(serial)
        if not client:
            return None

        model = "iPhone"
        name = serial
        ios_version = "Unknown"
        try:
            status = client.status()
            value = status.get("value", {}) if isinstance(status.get("value"), dict) else {}
            ios_info = value.get("ios", {}) if isinstance(value.get("ios"), dict) else {}
            model = str(ios_info.get("model") or value.get("model") or model)
            name = str(ios_info.get("name") or value.get("deviceName") or name)
            ios_version = str(ios_info.get("version") or value.get("osVersion") or ios_version)
        except Exception:
            pass

        width, height = self.get_screen_size(serial)
        return {
            "serial": serial,
            "model": model,
            "name": name,
            "ios_version": ios_version,
            "width": width,
            "height": height,
            "platform": "ios",
        }

    def _get_logical_size(self, client) -> Tuple[int, int]:
        """Return WDA window size in logical points."""
        try:
            size = client.window_size()
            if isinstance(size, dict):
                w = _as_int(size.get("width"), 0)
                h = _as_int(size.get("height"), 0)
            elif isinstance(size, (tuple, list)) and len(size) >= 2:
                w = _as_int(size[0], 0)
                h = _as_int(size[1], 0)
            else:
                w = _as_int(getattr(size, "width", 0), 0)
                h = _as_int(getattr(size, "height", 0), 0)
            if w > 0 and h > 0:
                return (w, h)
        except Exception:
            pass
        return (0, 0)

    def get_screen_size(self, serial: str) -> Tuple[int, int]:
        if not WDA_AVAILABLE:
            return (750, 1334)
        client = self._client_for_serial(serial)
        if not client:
            return (750, 1334)

        try:
            size = client.window_size()
            if isinstance(size, dict):
                w = _as_int(size.get("width"), 0)
                h = _as_int(size.get("height"), 0)
            elif isinstance(size, (tuple, list)) and len(size) >= 2:
                w = _as_int(size[0], 0)
                h = _as_int(size[1], 0)
            else:
                w = _as_int(getattr(size, "width", 0), 0)
                h = _as_int(getattr(size, "height", 0), 0)
            if w > 0 and h > 0:
                return (w, h)
        except Exception:
            pass

        png = self.capture_screenshot(serial)
        if png:
            try:
                with Image.open(io.BytesIO(png)) as img:
                    return (int(img.width), int(img.height))
            except Exception:
                pass
        return (750, 1334)

    def capture_screenshot(self, serial: str) -> Optional[bytes]:
        if not WDA_AVAILABLE:
            return None
        url = self._find_url_for_serial(serial) or f"http://127.0.0.1:{self._wda_port}"

        for attempt in range(self._autostart_retries):
            client = self._client_for_serial(serial)
            if client:
                for try_idx in range(self._screenshot_attempts):
                    try:
                        raw = client.screenshot(format="raw")
                        if isinstance(raw, bytes) and len(raw) > 100:
                            self._screenshot_fail_streak[serial] = 0
                            self._mark_healthy(url)
                            return raw
                        if isinstance(raw, str) and len(raw) > 100:
                            self._screenshot_fail_streak[serial] = 0
                            self._mark_healthy(url)
                            return raw.encode("utf-8")
                    except Exception:
                        pass
                    try:
                        image = client.screenshot()
                        if isinstance(image, bytes) and len(image) > 100:
                            self._screenshot_fail_streak[serial] = 0
                            self._mark_healthy(url)
                            return image
                        if hasattr(image, "save"):
                            buf = io.BytesIO()
                            image.save(buf, format="PNG")
                            data = buf.getvalue()
                            if len(data) > 100:
                                self._screenshot_fail_streak[serial] = 0
                                self._mark_healthy(url)
                                return data
                    except Exception as e:
                        logger.warning(
                            f"[iOS screenshot] WDA attempt {attempt + 1}.{try_idx + 1} failed: {e}"
                        )
                    if try_idx < self._screenshot_attempts - 1:
                        time.sleep(self._screenshot_retry_interval)

            # Track consecutive failures and restart WDA after threshold.
            streak = self._screenshot_fail_streak.get(serial, 0) + 1
            self._screenshot_fail_streak[serial] = streak
            logger.warning(
                f"[iOS screenshot] streak={streak}/{self._screenshot_fail_restart_threshold} for {serial}"
            )
            if streak >= self._screenshot_fail_restart_threshold:
                logger.warning(
                    f"[iOS screenshot] {streak} consecutive failures — restarting WDA proxy"
                )
                self._screenshot_fail_streak[serial] = 0
                self._wda_healthy_ts.pop(url, None)
                self._ensure_wda_ready(serial, url)
            elif attempt < self._autostart_retries - 1:
                self._ensure_wda_ready(serial, url)
                time.sleep(self._autostart_retry_interval)

        return None

    def _get_logical_size_from_xml(self, xml_source: str) -> Tuple[int, int]:
        """Extract the screen's logical size from the WDA XML root/app element.
        The root application element always covers (0, 0, screen_w, screen_h) in WDA
        logical coordinates — the same space as all child element coordinates.
        This is more reliable than window_size() which can return stale/wrong values.
        """
        try:
            root = ET.fromstring(xml_source)
            # Check the root element itself and its immediate children.
            for elem in [root] + list(root):
                x = _as_int(elem.attrib.get("x"), -1)
                y = _as_int(elem.attrib.get("y"), -1)
                w = _as_int(elem.attrib.get("width"), 0)
                h = _as_int(elem.attrib.get("height"), 0)
                # Screen container: starts at (0, 0) and is at least 200x400 pts.
                if x == 0 and y == 0 and w > 200 and h > 400:
                    logger.debug(f"[iOS] Logical screen size from XML: {w}x{h}")
                    return (w, h)
        except Exception as e:
            logger.debug(f"[iOS] Could not extract logical size from XML: {e}")
        return (0, 0)

    def _get_pixel_scale(self, serial: str, xml_source: Optional[str] = None) -> float:
        """Compute pixel-to-point scale factor.
        When xml_source is provided, derives logical dimensions directly from the XML
        (same coordinate system as element bounds), bypassing window_size() inaccuracy.
        Result is cached per serial.
        """
        # If we have xml_source, always re-derive (XML is authoritative for this dump).
        if not xml_source:
            cached = self._pixel_scale_cache.get(serial)
            if cached:
                return cached

        logical_w = 0

        # 1. Try XML-derived logical size (most accurate: same source as element bounds).
        if xml_source:
            logical_w, _ = self._get_logical_size_from_xml(xml_source)

        # 2. Fallback: window_size() via WDA client.
        if logical_w <= 0:
            client = self._client_for_serial(serial)
            if client:
                logical_w, _ = self._get_logical_size(client)

        if logical_w <= 0:
            return self._pixel_scale_cache.get(serial, 1.0)

        # Get pixel width from PNG header (fast, no full decode).
        png = self.capture_screenshot(serial)
        if not png:
            return self._pixel_scale_cache.get(serial, 1.0)

        try:
            import struct
            pixel_w = struct.unpack(">I", png[16:20])[0]
            if pixel_w > 0:
                scale = round(pixel_w / logical_w, 4)
                self._pixel_scale_cache[serial] = scale
                logger.info(
                    f"[iOS scale] serial={serial} logical={logical_w} pixel={pixel_w} "
                    f"scale={scale}"
                    + (" (from XML)" if xml_source else " (from window_size)")
                )
                return scale
        except Exception:
            pass
        return self._pixel_scale_cache.get(serial, 1.0)

    def _bounds_from_wda_attrs(self, attrs: Dict[str, str], px_scale: float = 1.0) -> str:
        x = float(attrs.get("x") or 0)
        y = float(attrs.get("y") or 0)
        w = float(attrs.get("width") or 0)
        h = float(attrs.get("height") or 0)
        if w > 0 or h > 0:
            x1, y1 = round(x * px_scale), round(y * px_scale)
            x2, y2 = round((x + w) * px_scale), round((y + h) * px_scale)
            return f"[{x1},{y1}][{x2},{y2}]"
        for key in ("rect", "frame", "bounds"):
            raw = attrs.get(key)
            if not raw:
                continue
            nums = re.findall(r"-?\d+(?:\.\d+)?", str(raw))
            if len(nums) >= 4:
                rx, ry, rw, rh = [float(n) for n in nums[:4]]
                x1, y1 = round(rx * px_scale), round(ry * px_scale)
                x2, y2 = round((rx + rw) * px_scale), round((ry + rh) * px_scale)
                return f"[{x1},{y1}][{x2},{y2}]"
        return "[0,0][0,0]"

    def _node_clickable(self, tag: str, attrs: Dict[str, str]) -> str:
        if _as_bool_str(attrs.get("enabled", "true"), "true") != "true":
            return "false"
        interactive = ("Button", "Cell", "Link", "TabBar", "Switch", "TextField", "SecureTextField", "SearchField", "Slider")
        if any(k in tag for k in interactive):
            return "true"
        if _as_bool_str(attrs.get("accessible", "false"), "false") == "true":
            return "true"
        return "false"

    def _convert_wda_element(self, element, index: int, px_scale: float = 1.0):
        """Preserve all original WDA attributes (name, label, value, visible, accessible...)
        and add computed helpers needed by the frontend overlay:
          - bounds   "[x1,y1][x2,y2]" in pixel space
          - index    child position
          - clickable  derived from tag + accessible/enabled
          - scrollable derived from tag name
        x / y / width / height are also scaled to pixel space.
        """
        tag = str(element.tag)
        attrs = dict(element.attrib)

        x = float(attrs.get("x") or 0)
        y = float(attrs.get("y") or 0)
        w = float(attrs.get("width") or 0)
        h = float(attrs.get("height") or 0)
        attrs["x"] = str(round(x * px_scale))
        attrs["y"] = str(round(y * px_scale))
        attrs["width"] = str(round(w * px_scale))
        attrs["height"] = str(round(h * px_scale))

        attrs["bounds"] = self._bounds_from_wda_attrs(
            {"x": str(x), "y": str(y), "width": str(w), "height": str(h)}, px_scale
        )

        attrs["index"] = str(index)
        attrs["clickable"] = self._node_clickable(tag, attrs)
        attrs["scrollable"] = "true" if ("ScrollView" in tag or "Table" in tag) else "false"

        xml_node = ET.Element(tag, attrib=attrs)
        for idx, child in enumerate(list(element)):
            xml_node.append(self._convert_wda_element(child, idx, px_scale))
        return xml_node

    def _normalize_wda_xml(self, xml_source: str, px_scale: float = 1.0) -> Optional[str]:
        if not xml_source:
            return None
        try:
            src_root = ET.fromstring(xml_source)
        except ET.ParseError as e:
            logger.error(f"WDA page source parse failed: {e}")
            return None

        out_root = ET.Element("hierarchy", attrib={"rotation": "0", "platform": "ios"})
        if src_root.tag == "hierarchy":
            for idx, child in enumerate(list(src_root)):
                out_root.append(self._convert_wda_element(child, idx, px_scale))
        else:
            out_root.append(self._convert_wda_element(src_root, 0, px_scale))

        buf = io.BytesIO()
        tree = ET.ElementTree(out_root)
        ET.indent(tree, space="  ")
        tree.write(buf, encoding="utf-8", xml_declaration=True)
        return buf.getvalue().decode("utf-8")

    def dump_ui_hierarchy(self, serial: str) -> Optional[str]:
        if not WDA_AVAILABLE:
            return None
        for attempt in range(self._autostart_retries):
            client = self._client_for_serial(serial)
            if client:
                actor = self._session_or_client(client)
                xml_source = None
                try:
                    src = getattr(actor, "source", None)
                    if callable(src):
                        try:
                            xml_source = src(format="xml")
                        except TypeError:
                            xml_source = src()
                    else:
                        xml_source = src
                except Exception as e:
                    logger.warning(f"[iOS dump] WDA source attempt {attempt + 1} failed: {e}")

                if xml_source:
                    # Derive scale from THIS dump's XML (same coordinate origin as elements).
                    px_scale = self._get_pixel_scale(serial, xml_source=str(xml_source))
                    normalized = self._normalize_wda_xml(str(xml_source), px_scale)
                    if normalized:
                        logger.info(
                            f"[iOS dump] Built XML via WDA: {len(normalized)} bytes, "
                            f"px_scale={px_scale}"
                        )
                        return normalized

            if attempt < self._autostart_retries - 1:
                url = self._find_url_for_serial(serial) or f"http://127.0.0.1:{self._wda_port}"
                self._ensure_wda_ready(serial, url)
                time.sleep(self._autostart_retry_interval)

        logger.error("Failed to read WDA page source after retries")
        return None

    def tap(self, serial: str, x: int, y: int) -> bool:
        if not WDA_AVAILABLE:
            return False
        for attempt in range(self._autostart_retries):
            client = self._client_for_serial(serial)
            if client:
                actor = self._session_or_client(client)
                try:
                    lx, ly = x, y
                    logical_w, logical_h = self._get_logical_size(client)
                    scale = self._pixel_scale_cache.get(serial, 1.0)
                    # Frontend now usually sends logical coordinates.
                    # Only downscale if inputs look like pixel coordinates.
                    if (
                        scale > 1.01
                        and logical_w > 0
                        and logical_h > 0
                        and (x > logical_w * 1.2 or y > logical_h * 1.2)
                    ):
                        lx = round(x / scale)
                        ly = round(y / scale)
                    if hasattr(actor, "tap"):
                        actor.tap(lx, ly)
                    elif hasattr(actor, "click"):
                        actor.click(lx, ly)
                    else:
                        client.click(lx, ly)
                    return True
                except Exception as e:
                    logger.warning(f"[iOS tap] WDA attempt {attempt + 1} failed: {e}")
            if attempt < self._autostart_retries - 1:
                url = self._find_url_for_serial(serial) or f"http://127.0.0.1:{self._wda_port}"
                self._ensure_wda_ready(serial, url)
                time.sleep(self._autostart_retry_interval)
        return False

    def swipe(self, serial: str, x1: int, y1: int, x2: int, y2: int, duration: int) -> bool:
        if not WDA_AVAILABLE:
            return False
        dur_sec = max(duration, 0) / 1000.0
        for attempt in range(self._autostart_retries):
            client = self._client_for_serial(serial)
            if client:
                actor = self._session_or_client(client)
                try:
                    lx1, ly1, lx2, ly2 = x1, y1, x2, y2
                    logical_w, logical_h = self._get_logical_size(client)
                    scale = self._pixel_scale_cache.get(serial, 1.0)
                    max_x = max(x1, x2)
                    max_y = max(y1, y2)
                    if (
                        scale > 1.01
                        and logical_w > 0
                        and logical_h > 0
                        and (max_x > logical_w * 1.2 or max_y > logical_h * 1.2)
                    ):
                        lx1 = round(x1 / scale)
                        ly1 = round(y1 / scale)
                        lx2 = round(x2 / scale)
                        ly2 = round(y2 / scale)
                    if hasattr(actor, "swipe"):
                        actor.swipe(lx1, ly1, lx2, ly2, duration=dur_sec)
                    elif hasattr(client, "swipe"):
                        client.swipe(lx1, ly1, lx2, ly2, duration=dur_sec)
                    else:
                        return False
                    return True
                except Exception as e:
                    logger.warning(f"[iOS swipe] WDA attempt {attempt + 1} failed: {e}")
            if attempt < self._autostart_retries - 1:
                url = self._find_url_for_serial(serial) or f"http://127.0.0.1:{self._wda_port}"
                self._ensure_wda_ready(serial, url)
                time.sleep(self._autostart_retry_interval)
        return False
