"""
Android UI Inspector - Backend API
Enhanced version with selector generation
"""
from pathlib import Path
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.routing import APIRouter
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import logging
import asyncio
import io
from PIL import Image

from device_manager import device_manager
from xml_parser import XMLParser
import time as _time
import threading as _threading

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# API router with /api prefix (frontend expects /api/devices, etc.)
api_router = APIRouter(prefix="/api", tags=["api"])


# ============================================================================
# Per-device hierarchy cache
# Cache is populated by GET /dump/{serial} and reused by coordinate/info APIs.
# ============================================================================

class _HierarchyCache:
    """Thread-safe per-serial cache for parsed UI hierarchy."""

    def __init__(self):
        self._lock = _threading.Lock()
        # serial → {"xml": str, "parsed": dict, "platform": str, "ts": float}
        self._store: Dict[str, Dict] = {}

    def put(self, serial: str, xml: str, parsed: dict, platform: str) -> None:
        with self._lock:
            self._store[serial] = {
                "xml": xml,
                "parsed": parsed,
                "platform": platform,
                "ts": _time.time(),
            }
        logger.info(f"[cache] Hierarchy cached for {serial} ({parsed.get('total_nodes', 0)} nodes)")

    def get(self, serial: str) -> Optional[Dict]:
        with self._lock:
            return self._store.get(serial)

    def invalidate(self, serial: str) -> None:
        with self._lock:
            self._store.pop(serial, None)

    def has(self, serial: str) -> bool:
        with self._lock:
            return serial in self._store


_hierarchy_cache = _HierarchyCache()


# ============================================================================
# Request/Response Models
# ============================================================================

class XPathQueryRequest(BaseModel):
    serial: str
    xpath: str


class TapRequest(BaseModel):
    serial: str
    x: int
    y: int


class SwipeRequest(BaseModel):
    serial: str
    x1: int
    y1: int
    x2: int
    y2: int
    duration: int = 300


class ElementInfoRequest(BaseModel):
    """Request to get element info by node path"""
    serial: str
    node_path: List[int]


class FindByCoordinateRequest(BaseModel):
    """Request to find element by screen coordinate"""
    serial: str
    x: int
    y: int


# ============================================================================
# Device Management Endpoints
# ============================================================================

@api_router.get("/")
async def root():
    """API root endpoint"""
    return {
        "name": "Android UI Inspector API",
        "version": "2.0.0",
        "status": "running",
        "features": [
            "Multi-platform support (Android + iOS)",
            "Real-time screen streaming",
            "Enhanced selector generation",
            "Coordinate-based element finding"
        ]
    }


@api_router.get("/devices")
async def get_devices():
    """
    Get list of all connected devices (Android + iOS)
    
    Returns:
        List of device information dictionaries
    """
    try:
        devices = device_manager.get_all_devices()
        logger.info(f"Found {len(devices)} device(s)")
        return devices
    except Exception as e:
        logger.error(f"Error getting devices: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.get("/devices/{serial}/info")
async def get_device_info(serial: str):
    """
    Get detailed information about a specific device
    
    Args:
        serial: Device serial number
    
    Returns:
        Device information dictionary
    """
    try:
        info = device_manager.get_device_info(serial)
        if not info:
            raise HTTPException(status_code=404, detail="Device not found")
        return info
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting device info: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Screenshot Endpoints
# ============================================================================

@api_router.get("/screenshot/{serial}")
async def capture_screenshot(serial: str):
    """
    Capture a single screenshot from device
    
    Args:
        serial: Device serial number
    
    Returns:
        PNG image
    """
    try:
        logger.info(f"Capturing screenshot for device: {serial}")
        
        screenshot_bytes = device_manager.capture_screenshot(serial)
        
        if not screenshot_bytes:
            raise HTTPException(status_code=500, detail="Failed to capture screenshot")
        
        return Response(content=screenshot_bytes, media_type="image/png")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error capturing screenshot: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# UI Hierarchy Endpoints (Enhanced)
# ============================================================================

@api_router.get("/dump/{serial}")
async def dump_ui_hierarchy(serial: str):
    """
    Dump UI hierarchy with enhanced selector generation.
    Result is cached; subsequent calls to find-by-coordinate / element/info
    use the cache and do NOT re-dump the device.
    """
    try:
        logger.info(f"Dumping UI hierarchy for device: {serial}")

        # Get fresh XML from device
        xml_content = device_manager.dump_ui_hierarchy(serial)

        if not xml_content:
            raise HTTPException(status_code=500, detail="Failed to dump UI hierarchy")

        # Detect platform
        manager = device_manager.get_manager_for_device(serial)
        platform = 'ios' if manager and manager.platform.value == 'ios' else 'android'

        # Parse with enhanced parser
        result = XMLParser.parse_xml_to_json(xml_content, platform=platform)

        if not result['success']:
            raise HTTPException(status_code=500, detail=result.get('error', 'Parse failed'))

        # ── Store in cache so other APIs can reuse without re-dumping ──
        _hierarchy_cache.put(serial, xml_content, result, platform)

        # Get device info for screen dimensions
        device_info = device_manager.get_device_info(serial)

        return {
            "success": True,
            "platform": platform,
            "device_info": device_info,
            "total_nodes": result['total_nodes'],
            "hierarchy": result['hierarchy'],
            "cached": False,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error dumping UI hierarchy: {e}")
        import traceback
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))


@api_router.get("/dump/{serial}/xml")
async def get_cached_xml(serial: str):
    """Return the cached raw XML for a device (populated by GET /dump/{serial})."""
    from fastapi.responses import Response as FastAPIResponse
    cached = _hierarchy_cache.get(serial)
    if not cached or not cached.get("xml"):
        raise HTTPException(status_code=404, detail="No cached XML. Refresh hierarchy first.")
    return FastAPIResponse(
        content=cached["xml"],
        media_type="application/xml",
        headers={"Content-Disposition": f'attachment; filename="hierarchy-{serial}.xml"'},
    )


@api_router.post("/element/info")
async def get_element_info(request: ElementInfoRequest):
    """
    Get detailed information about an element by its node path.
    Uses cached hierarchy when available (populated by GET /dump/{serial}).
    """
    try:
        logger.info(f"Getting element info for path: {request.node_path}")

        cached = _hierarchy_cache.get(request.serial)
        if cached:
            result = cached["parsed"]
            platform = cached["platform"]
            logger.info(f"[cache] Using cached hierarchy for element/info ({request.serial})")
        else:
            # Fallback: fresh dump
            xml_content = device_manager.dump_ui_hierarchy(request.serial)
            if not xml_content:
                raise HTTPException(status_code=500, detail="Failed to dump UI hierarchy")
            manager = device_manager.get_manager_for_device(request.serial)
            platform = 'ios' if manager and manager.platform.value == 'ios' else 'android'
            result = XMLParser.parse_xml_to_json(xml_content, platform=platform)
            if result['success']:
                _hierarchy_cache.put(request.serial, xml_content, result, platform)

        if not result['success']:
            raise HTTPException(status_code=500, detail="Failed to parse hierarchy")
        
        # Find node by path
        node = XMLParser.find_node_by_path(result['hierarchy'], request.node_path)
        
        if not node:
            raise HTTPException(status_code=404, detail="Element not found")
        
        return {
            "success": True,
            "element": {
                "tag": node['tag'],
                "attributes": node['attributes'],
                "selectors": node['selectors'],
                "node_path": node['node_path']
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting element info: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.post("/element/find-by-coordinate")
async def find_element_by_coordinate(request: FindByCoordinateRequest):
    """
    Find element at specific screen coordinate.
    Uses cached hierarchy when available — avoids re-dumping the device on every click.
    Refresh the cache by calling GET /dump/{serial} first.
    """
    try:
        logger.info(f"Finding element at ({request.x}, {request.y})")

        cached = _hierarchy_cache.get(request.serial)
        if cached:
            result = cached["parsed"]
            platform = cached["platform"]
            logger.info(f"[cache] Using cached hierarchy for find-by-coordinate ({request.serial})")
        else:
            # No cache yet — do a fresh dump and store it
            logger.info(f"[cache] No cache for {request.serial}, dumping fresh hierarchy")
            xml_content = device_manager.dump_ui_hierarchy(request.serial)
            if not xml_content:
                raise HTTPException(status_code=500, detail="Failed to dump UI hierarchy")
            manager = device_manager.get_manager_for_device(request.serial)
            platform = 'ios' if manager and manager.platform.value == 'ios' else 'android'
            result = XMLParser.parse_xml_to_json(xml_content, platform=platform)
            if result['success']:
                _hierarchy_cache.put(request.serial, xml_content, result, platform)

        if not result['success']:
            raise HTTPException(status_code=500, detail="Failed to parse hierarchy")
        
        def find_all_by_coordinate(node, x, y, depth=0):
            """递归查找所有包含该坐标的节点"""
            matches = []
            
            bounds = node.get('attributes', {}).get('bounds_computed')
            if not bounds:
                for child in node.get('children', []):
                    matches.extend(find_all_by_coordinate(child, x, y, depth + 1))
                return matches
            
            x_in_bounds = bounds['x'] <= x <= bounds['x'] + bounds['w']
            y_in_bounds = bounds['y'] <= y <= bounds['y'] + bounds['h']
            
            if x_in_bounds and y_in_bounds:
                area = bounds['w'] * bounds['h']
                is_clickable = node.get('attributes', {}).get('clickable') == 'true'
                
                matches.append((node, depth, area, is_clickable))
                
                for child in node.get('children', []):
                    matches.extend(find_all_by_coordinate(child, x, y, depth + 1))
            
            return matches
        
        all_matches = find_all_by_coordinate(result['hierarchy'], request.x, request.y)
        
        if not all_matches:
            return {
                "success": False,
                "error": f"No element found at coordinate ({request.x}, {request.y})"
            }
        
        # 如果存在可见元素，过滤掉不可见的；全可见或全不可见则不过滤
        visible_matches   = [m for m in all_matches if m[0].get('attributes', {}).get('visible') != 'false']
        invisible_matches = [m for m in all_matches if m[0].get('attributes', {}).get('visible') == 'false']
        if visible_matches and invisible_matches:  # 混合情况才过滤
            all_matches = visible_matches

        # ✅ 优先选择可点击的元素
        clickable_matches = [m for m in all_matches if m[3]]  # is_clickable

        if clickable_matches:
            # 可点击元素：按深度降序，面积升序
            clickable_matches.sort(key=lambda x: (-x[1], x[2]))
            found_node = clickable_matches[0][0]
            logger.info(f"Found clickable element at depth {clickable_matches[0][1]}")
        else:
            # 非可点击元素：按深度降序，面积升序
            all_matches.sort(key=lambda x: (-x[1], x[2]))
            found_node = all_matches[0][0]
            logger.info(f"Found non-clickable element at depth {all_matches[0][1]}")
        
        logger.info(f"Element: {found_node['tag']}, Total matches: {len(all_matches)}")
        
        return {
            "success": True,
            "element": {
                "tag": found_node['tag'],
                "attributes": found_node['attributes'],
                "selectors": found_node['selectors'],
                "node_path": found_node['node_path']
            },
            "total_matches": len(all_matches),
            "clickable_matches": len([m for m in all_matches if m[3]])
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error finding element by coordinate: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return {
            "success": False,
            "error": str(e)
        }




# ============================================================================
# XPath Query Endpoint
# ============================================================================

@api_router.post("/xpath/query")
async def query_xpath(request: XPathQueryRequest):
    """
    Query elements using XPath
    
    Args:
        request: XPathQueryRequest with serial and xpath
    
    Returns:
        XPath query results
    """
    try:
        logger.info(f"XPath query for device {request.serial}: {request.xpath}")

        # Use cached XML when available
        cached = _hierarchy_cache.get(request.serial)
        if cached:
            xml_content = cached["xml"]
            logger.info(f"[cache] Using cached XML for XPath query ({request.serial})")
        else:
            xml_content = device_manager.dump_ui_hierarchy(request.serial)
            if not xml_content:
                raise HTTPException(status_code=500, detail="Failed to dump UI hierarchy")
            manager = device_manager.get_manager_for_device(request.serial)
            platform = 'ios' if manager and manager.platform.value == 'ios' else 'android'
            parsed = XMLParser.parse_xml_to_json(xml_content, platform=platform)
            if parsed['success']:
                _hierarchy_cache.put(request.serial, xml_content, parsed, platform)

        result = XMLParser.query_xpath(xml_content, request.xpath)
        
        if not result['success']:
            raise HTTPException(status_code=400, detail=result.get('error', 'XPath query failed'))
        
        logger.info(f"XPath query found {result['count']} match(es)")
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in XPath query: {e}")
        raise HTTPException(status_code=500, detail=str(e))



# ============================================================================
# Device Control Endpoints
# ============================================================================

@api_router.post("/tap")
async def tap_coordinate(request: TapRequest):
    """
    Simulate tap at coordinate
    
    Args:
        request: Contains serial, x, y
    
    Returns:
        Success status
    """
    try:
        logger.info(f"Tap at ({request.x}, {request.y}) on {request.serial}")
        
        success = device_manager.tap(request.serial, request.x, request.y)
        
        if not success:
            raise HTTPException(status_code=500, detail="Tap failed")
        
        return {"success": True}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error tapping: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.post("/swipe")
async def swipe_gesture(request: SwipeRequest):
    """
    Simulate swipe gesture
    
    Args:
        request: Contains serial, coordinates, duration
    
    Returns:
        Success status
    """
    try:
        logger.info(f"Swipe from ({request.x1}, {request.y1}) to ({request.x2}, {request.y2})")
        
        success = device_manager.swipe(
            request.serial,
            request.x1, request.y1,
            request.x2, request.y2,
            request.duration
        )
        
        if not success:
            raise HTTPException(status_code=500, detail="Swipe failed")
        
        return {"success": True}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error swiping: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.post("/stream/stop/{serial}")
async def stop_device_stream(serial: str):
    """
    Stop all background streaming resources for a device.
    For iOS (ios-wda-*): terminates the WDA proxy process so it doesn't
    keep running after the frontend switches to another device.
    """
    try:
        if serial.startswith("ios-wda-"):
            ios_mgr = getattr(device_manager, "ios_manager", None)
            if ios_mgr and hasattr(ios_mgr, "stop_wda_proxy"):
                ios_mgr.stop_wda_proxy(serial)
                logger.info(f"[stream/stop] Stopped WDA proxy for {serial}")
        return {"success": True, "serial": serial}
    except Exception as e:
        logger.error(f"[stream/stop] Error stopping stream for {serial}: {e}")
        return {"success": False, "error": str(e)}


# ============================================================================
# App Factory & Server Startup
# ============================================================================

def create_app(static_dir: Optional[Path] = None) -> FastAPI:
    """Create FastAPI app, optionally serving static frontend."""
    app = FastAPI(title="Android UI Inspector API", version="2.0.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://localhost:3000", "http://127.0.0.1:8000"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Mount API router
    app.include_router(api_router)

    # WebSocket at /ws (no /api prefix)
    @app.websocket("/ws/screen/{serial}")
    async def websocket_screen_stream(websocket: WebSocket, serial: str):
        await _websocket_screen_stream_impl(websocket, serial)

    # Mount static files when serving bundled frontend
    if static_dir and static_dir.exists() and (static_dir / "index.html").exists():
        static_path = Path(static_dir)
        assets_dir = static_path / "assets"
        if assets_dir.is_dir():
            app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

        async def serve_spa(path: str = ""):
            """SPA fallback: serve index.html for non-file routes."""
            if path and (path.startswith(("api/", "ws/")) or path in ("api", "ws")):
                raise HTTPException(status_code=404, detail="Not found")
            file_path = static_path / path
            if path and file_path.is_file():
                return FileResponse(file_path)
            return FileResponse(static_path / "index.html")

        app.add_api_route("/{path:path}", serve_spa, methods=["GET"], include_in_schema=False)

    return app


# Copy WebSocket handler for reuse (registered in create_app)
async def _websocket_screen_stream_impl(websocket: WebSocket, serial: str):
    from starlette.websockets import WebSocketState

    connection_id = id(websocket)
    try:
        await websocket.accept()
        logger.info(f"[{connection_id}] WebSocket connected for device: {serial}")
    except Exception as e:
        logger.error(f"[{connection_id}] Failed to accept WebSocket: {e}")
        return

    frame_count = 0
    error_count = 0
    max_errors = 3
    screenshot_fail_streak = 0
    max_screenshot_fail_streak = 120  # ~60s tolerance before closing stream

    try:
        manager = device_manager.get_manager_for_device(serial)
        if not manager:
            logger.error(f"[{connection_id}] Device {serial} not found")
            try:
                await websocket.send_json({"error": "Device not found"})
            except Exception:
                pass
            return

        logger.info(f"[{connection_id}] Starting screen stream for {serial}")

        TARGET_FPS = 10
        TARGET_INTERVAL = 1.0 / TARGET_FPS
        LOG_TIMING_EVERY = 10

        t_capture_total = 0.0
        t_encode_total = 0.0
        t_send_total = 0.0

        while True:
            if websocket.client_state != WebSocketState.CONNECTED:
                break
            loop_start = asyncio.get_event_loop().time()
            try:
                # ── Stage 1: capture (run in thread so event loop stays free) ──
                t0 = asyncio.get_event_loop().time()
                screenshot_bytes = await asyncio.to_thread(
                    device_manager.capture_screenshot, serial
                )
                t_capture = asyncio.get_event_loop().time() - t0

                if not screenshot_bytes or not isinstance(screenshot_bytes, bytes):
                    screenshot_fail_streak += 1
                    if screenshot_fail_streak % 10 == 0:
                        logger.warning(
                            f"[{connection_id}] Screenshot unavailable "
                            f"({screenshot_fail_streak}/{max_screenshot_fail_streak}), keep waiting..."
                        )
                    if screenshot_fail_streak >= max_screenshot_fail_streak:
                        logger.error(f"[{connection_id}] Screenshot unavailable too long, closing stream.")
                        break
                    await asyncio.sleep(0.5)
                    continue
                screenshot_fail_streak = 0

                # ── Stage 2: encode ────────────────────────────────────────────
                t0 = asyncio.get_event_loop().time()
                try:
                    img = Image.open(io.BytesIO(screenshot_bytes))
                    max_width = 1242
                    if img.width > max_width:
                        ratio = max_width / img.width
                        new_height = int(img.height * ratio)
                        img = img.resize((max_width, new_height), Image.Resampling.LANCZOS)
                    buffer = io.BytesIO()
                    # Skip optimize=True (two-pass Huffman) — saves 50-100ms per frame.
                    img.save(buffer, format="JPEG", quality=80)
                    jpeg_bytes = buffer.getvalue()
                    buffer.close()
                    if not jpeg_bytes or len(jpeg_bytes) < 100:
                        error_count += 1
                        continue
                except Exception as e:
                    logger.error(f"[{connection_id}] Error processing image: {e}")
                    error_count += 1
                    if error_count >= max_errors:
                        break
                    await asyncio.sleep(0.5)
                    continue
                t_encode = asyncio.get_event_loop().time() - t0

                if websocket.client_state != WebSocketState.CONNECTED:
                    break

                # ── Stage 3: send ──────────────────────────────────────────────
                t0 = asyncio.get_event_loop().time()
                try:
                    await asyncio.wait_for(websocket.send_bytes(jpeg_bytes), timeout=2.0)
                    frame_count += 1
                    error_count = 0
                    screenshot_fail_streak = 0
                except asyncio.TimeoutError:
                    error_count += 1
                    if error_count >= max_errors:
                        break
                    continue
                except Exception as e:
                    error_name = type(e).__name__
                    msg = str(e)
                    if error_name in ['ClientDisconnected', 'ConnectionClosed', 'ConnectionClosedOK', 'WebSocketDisconnect']:
                        break
                    # Server-initiated close — treat as clean exit.
                    if isinstance(e, RuntimeError) and "close message has been sent" in msg:
                        break
                    logger.error(f"[{connection_id}] Error sending: {error_name}: {e}")
                    error_count += 1
                    if error_count >= max_errors:
                        break
                    continue
                t_send = asyncio.get_event_loop().time() - t0

                # ── Timing log ─────────────────────────────────────────────────
                t_capture_total += t_capture
                t_encode_total  += t_encode
                t_send_total    += t_send
                if frame_count % LOG_TIMING_EVERY == 0:
                    avg_cap  = t_capture_total / LOG_TIMING_EVERY * 1000
                    avg_enc  = t_encode_total  / LOG_TIMING_EVERY * 1000
                    avg_send = t_send_total    / LOG_TIMING_EVERY * 1000
                    logger.info(
                        f"[{connection_id}] [{serial}] frame={frame_count} avg over {LOG_TIMING_EVERY}: "
                        f"capture={avg_cap:.0f}ms  encode={avg_enc:.0f}ms  "
                        f"send={avg_send:.0f}ms  total={avg_cap+avg_enc+avg_send:.0f}ms "
                        f"size={len(jpeg_bytes)//1024}KB"
                    )
                    t_capture_total = t_encode_total = t_send_total = 0.0

                # ── Adaptive sleep ─────────────────────────────────────────────
                elapsed = asyncio.get_event_loop().time() - loop_start
                sleep_time = max(0.0, TARGET_INTERVAL - elapsed)
                if sleep_time > 0:
                    await asyncio.sleep(sleep_time)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[{connection_id}] Unexpected error: {type(e).__name__}: {e}")
                error_count += 1
                if error_count >= max_errors:
                    break
                await asyncio.sleep(0.5)
    except Exception as e:
        logger.error(f"[{connection_id}] Fatal error: {type(e).__name__}: {e}")
    finally:
        try:
            if websocket.client_state == WebSocketState.CONNECTED:
                await websocket.close()
        except Exception:
            pass
        logger.info(f"[{connection_id}] Stream ended for {serial}, total frames: {frame_count}")


# Legacy app instance for direct run (python -m backend.main)
app = create_app()


if __name__ == "__main__":
    import uvicorn

    logger.info("Starting Android UI Inspector API Server...")
    logger.info("API Documentation: http://localhost:8000/docs")
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
