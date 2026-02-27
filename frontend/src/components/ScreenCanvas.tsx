/**
 * Screen Canvas Component
 * Handles screen streaming, overlays, and coordinate picking
 */
import React, { useRef, useEffect, useState, useCallback, forwardRef, useImperativeHandle } from 'react';
import { Stage, Layer, Rect, Arrow } from 'react-konva';
import { Card, Typography, Spin, Button, message, Tooltip, Flex, Popover } from 'antd';
import { SyncOutlined, BgColorsOutlined, ReloadOutlined, ApiOutlined, InfoCircleOutlined, AimOutlined, CameraOutlined } from '@ant-design/icons';
import { deviceAPI, hierarchyAPI, interactionAPI } from '../services/api';
import type { DeviceInfo, Overlay, Coordinate, HierarchyNode, BoundsComputed } from '../types';

const { Text } = Typography;

interface ScreenCanvasProps {
  deviceSerial: string | null;
  overlays: Overlay[];
  onCoordinateUpdate: (coord: Coordinate | null) => void;
  onTap?: (x: number, y: number) => void;
  onHierarchyLoaded?: (hierarchy: HierarchyNode) => void;
  coordinate?: Coordinate | null;
}

export interface ScreenCanvasRef {
  /** Immediately close the current WebSocket without waiting for the close handshake. */
  forceDisconnect: () => void;
}

const ScreenCanvas = forwardRef<ScreenCanvasRef, ScreenCanvasProps>(({
  deviceSerial,
  overlays,
  onCoordinateUpdate,
  onTap,
  onHierarchyLoaded,
  coordinate,
}, ref) => {
  const [deviceInfo, setDeviceInfo] = useState<DeviceInfo | null>(null);
  const [imageUrl, setImageUrl] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [canvasSize, setCanvasSize] = useState({ width: 360, height: 640 });
  const [scale, setScale] = useState(1);
  const [isConnected, setIsConnected] = useState(false);
  const [hierarchy, setHierarchy] = useState<HierarchyNode | null>(null);
  const [showElementBounds, setShowElementBounds] = useState(true);
  const [elementBounds, setElementBounds] = useState<Array<{ bounds: BoundsComputed; label: string; color: string }>>([]);
  const [frameSize, setFrameSize] = useState({ width: 0, height: 0 });
  const [hierarchyFit, setHierarchyFit] = useState({ x: 1, y: 1 });
  
  const wsRef = useRef<WebSocket | null>(null);
  const imageRef = useRef<HTMLImageElement | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const currentSerialRef = useRef<string | null>(null);
  const imageUrlRef = useRef<string | null>(null);
  // Timing: timestamp when the latest WS frame bytes were received.
  const frameRecvTsRef = useRef<number>(0);
  const frameTimingRef = useRef({ count: 0, sumWsDecode: 0, sumWsPaint: 0 });

  // Download current screenshot frame
  const downloadScreenshot = useCallback(() => {
    const url = imageUrlRef.current;
    if (!url) {
      message.warning('No screenshot available');
      return;
    }
    const serial = currentSerialRef.current || deviceSerial || 'device';
    const a = document.createElement('a');
    a.href = url;
    a.download = `screenshot-${serial}-${Date.now()}.png`;
    a.click();
  }, [deviceSerial]);

  // Hierarchy refresh loading overlay
  const [hierarchyLoading, setHierarchyLoading] = useState(false);

  // Tap mode state
  const [tapMode, setTapMode] = useState(false);
  const tapStartRef = useRef<{ x: number; y: number; canvasX: number; canvasY: number } | null>(null);
  const [swipeArrow, setSwipeArrow] = useState<{ x1: number; y1: number; x2: number; y2: number } | null>(null);
  const SWIPE_THRESHOLD = 20; // canvas pixels

  // Expose forceDisconnect so parent can stop the stream instantly on device switch.
  useImperativeHandle(ref, () => ({
    forceDisconnect: () => {
      const ws = wsRef.current;
      if (ws) {
        console.log(`[WS] forceDisconnect: closing ${currentSerialRef.current}`);
        currentSerialRef.current = null; // prevent auto-reconnect
        wsRef.current = null;
        try { ws.close(1000, 'Device switched'); } catch (_) { /* ignore */ }
      }
      setIsConnected(false);
      cleanupImageUrl();
    },
  }), []); // eslint-disable-line react-hooks/exhaustive-deps

  const estimateHierarchyBounds = useCallback((node: HierarchyNode): { maxRight: number; maxBottom: number } => {
    let maxRight = 0;
    let maxBottom = 0;
    const walk = (n: HierarchyNode) => {
      const b = n.attributes?.bounds_computed;
      if (b && b.w > 0 && b.h > 0) {
        maxRight = Math.max(maxRight, b.x + b.w);
        maxBottom = Math.max(maxBottom, b.y + b.h);
      }
      n.children?.forEach(walk);
    };
    walk(node);
    return { maxRight, maxBottom };
  }, []);

  const recalcHierarchyFit = useCallback((tree: HierarchyNode | null, dInfo: DeviceInfo | null, frame: { width: number; height: number }) => {
    if (!tree || !dInfo) {
      setHierarchyFit({ x: 1, y: 1 });
      return;
    }

    const { maxRight, maxBottom } = estimateHierarchyBounds(tree);
    if (maxRight <= 0 || maxBottom <= 0) {
      setHierarchyFit({ x: 1, y: 1 });
      return;
    }

    // If hierarchy coordinates are much larger than logical device size,
    // they are likely in frame-pixel space (e.g. 1170) while device is logical points (e.g. 390).
    const oversizedX = maxRight > dInfo.width * 1.2;
    const oversizedY = maxBottom > dInfo.height * 1.2;
    let fitX = 1;
    let fitY = 1;

    if (oversizedX || oversizedY) {
      if (frame.width > 0 && frame.height > 0) {
        fitX = dInfo.width / frame.width;
        fitY = dInfo.height / frame.height;
      } else {
        fitX = dInfo.width / maxRight;
        fitY = dInfo.height / maxBottom;
      }
    }

    // Clamp to avoid extreme noise from malformed bounds.
    fitX = Math.max(0.1, Math.min(2, fitX));
    fitY = Math.max(0.1, Math.min(2, fitY));
    setHierarchyFit({ x: fitX, y: fitY });
  }, [estimateHierarchyBounds]);

  // Calculate scale factor — canvas 填满容器
  const calculateScale = useCallback((deviceWidth: number, deviceHeight: number) => {
    // Header + card padding + top toolbar height
    const overhead = 55 + 16 + 38;
    const containerEl = containerRef.current;
    const availableWidth = containerEl
      ? Math.max(containerEl.clientWidth, 160)
      : window.innerWidth / 3 - 24;
    // 列高 = calc(100vh - 96px)
    const availableHeight = window.innerHeight - 96 - overhead;

    const scaleX = availableWidth / deviceWidth;
    const scaleY = availableHeight / deviceHeight;
    const newScale = Math.min(scaleX, scaleY, 1.2);  // Allow up to 120% for sharper display

    setScale(newScale);
    setCanvasSize({
      width: deviceWidth * newScale,
      height: deviceHeight * newScale,
    });
  }, []);

  // Fetch device info
  useEffect(() => {
    if (!deviceSerial) return;

    const fetchDeviceInfo = async () => {
      try {
        const info = await deviceAPI.getDeviceInfo(deviceSerial);
        setDeviceInfo(info);
        calculateScale(info.width, info.height);
      } catch (error) {
        message.error('Failed to get device info');
        console.error(error);
      }
    };

    fetchDeviceInfo();
  }, [deviceSerial, calculateScale]);

  // Responsive canvas - recalculate on window resize
  useEffect(() => {
    if (!deviceInfo) return;

    const handleResize = () => {
      calculateScale(deviceInfo.width, deviceInfo.height);
    };

    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, [deviceInfo, calculateScale]);

  useEffect(() => {
    recalcHierarchyFit(hierarchy, deviceInfo, frameSize);
  }, [hierarchy, deviceInfo, frameSize, recalcHierarchyFit]);

  // Extract bounds from hierarchy for all interactive elements
  const extractElementBounds = useCallback((node: HierarchyNode): Array<{ bounds: BoundsComputed; label: string; color: string }> => {
    const results: Array<{ bounds: BoundsComputed; label: string; color: string }> = [];
    
    const traverse = (n: HierarchyNode, depth: number = 0) => {
      const attrs = n.attributes;

      // Skip invisible elements entirely (don't draw, but still traverse children)
      if (attrs.visible === 'false') {
        n.children?.forEach(child => traverse(child, depth + 1));
        return;
      }

      const boundsComputed = attrs.bounds_computed;
      
      // Only add elements that:
      // 1. Have valid bounds
      // 2. Are interactive (clickable, scrollable, focusable, long-clickable) or have text
      // 3. Have reasonable size (not too small or too large)
      if (boundsComputed && 
          (attrs.clickable === 'true' || 
           attrs.scrollable === 'true' || 
           attrs.focusable === 'true' || 
           attrs['long-clickable'] === 'true' ||
           (attrs.text && attrs.text.length > 0)) &&
          boundsComputed.w > 10 && 
          boundsComputed.h > 10 &&
          boundsComputed.w < 2000 &&
          boundsComputed.h < 3000) {
        
        // Determine color based on element type
        let color = '#1890ff'; // default blue
        
        if (attrs.clickable === 'true') {
          color = '#52c41a'; // green for clickable
        } else if (attrs.scrollable === 'true') {
          color = '#faad14'; // orange for scrollable
        } else if (attrs['long-clickable'] === 'true') {
          color = '#13c2c2'; // cyan for long-clickable
        }
        
        // Create label
        let label = '';
        if (attrs.text) {
          label = attrs.text;
        } else if (attrs['resource-id']) {
          label = attrs['resource-id'].split('/').pop() || '';
        } else if (attrs['content-desc']) {
          label = attrs['content-desc'];
        }
        
        // Truncate long labels
        if (label && label.length > 20) {
          label = label.substring(0, 17) + '...';
        }
        
        results.push({
          bounds: boundsComputed,
          label: label || n.tag.split('.').pop() || '',
          color,
        });
      }
      
      // Recursively process children
      if (n.children) {
        n.children.forEach(child => traverse(child, depth + 1));
      }
    };
    
    traverse(node);
    return results;
  }, []);

  // Auto-load hierarchy once when device is first connected
  useEffect(() => {
    if (!deviceSerial) return;

    const loadHierarchy = async () => {
      try {
        console.log(`Auto-loading UI hierarchy for device: ${deviceSerial} (first time only)`);
        const response = await hierarchyAPI.dumpHierarchy(deviceSerial);
        
        if (response.success && response.hierarchy) {
          setHierarchy(response.hierarchy);
          
          // Extract all interactive elements
          const bounds = extractElementBounds(response.hierarchy);
          setElementBounds(bounds);
          
          // Notify parent component
          if (onHierarchyLoaded) {
            onHierarchyLoaded(response.hierarchy);
          }
          
          console.log(`✅ Loaded hierarchy with ${response.total_nodes} nodes, found ${bounds.length} interactive elements`);
        } else {
          console.error('❌ Failed to load hierarchy:', response.error);
          message.error('Failed to load UI hierarchy');
        }
      } catch (error) {
        console.error('❌ Error loading hierarchy:', error);
        message.error('Error loading UI hierarchy');
      }
    };

    loadHierarchy();
  }, [deviceSerial]); // Only load when device serial changes (device switch)

  // Cleanup function for WebSocket
  const closeWebSocket = useCallback(() => {
    if (wsRef.current) {
      console.log('Closing WebSocket connection...');
      try {
        wsRef.current.close();
      } catch (error) {
        console.error('Error closing WebSocket:', error);
      }
      wsRef.current = null;
    }
    setIsConnected(false);
  }, []);

  // Cleanup image URL - use ref to avoid closure issues
  const cleanupImageUrl = useCallback(() => {
    if (imageUrlRef.current) {
      URL.revokeObjectURL(imageUrlRef.current);
      imageUrlRef.current = null;
      setImageUrl(null);
    }
  }, []); // No dependencies - stable reference

  // WebSocket screen streaming
  useEffect(() => {
    if (!deviceSerial) {
      if (wsRef.current) {
        wsRef.current.close(1000, 'No device');
        wsRef.current = null;
      }
      setIsConnected(false);
      cleanupImageUrl();
      return;
    }

    const prevWs = wsRef.current;
    const prevSerial = currentSerialRef.current;
    currentSerialRef.current = deviceSerial;
    wsRef.current = null;
    setIsConnected(false);

    const openNewWs = () => {
      if (currentSerialRef.current !== deviceSerial) return;

      setLoading(true);
      const wsUrl = deviceAPI.getWebSocketUrl(deviceSerial);
      console.log(`[WS] Connecting to ${wsUrl}`);

      const ws = new WebSocket(wsUrl);
      ws.binaryType = 'arraybuffer';
      wsRef.current = ws;

      ws.onopen = () => {
        if (currentSerialRef.current !== deviceSerial) { ws.close(1000, 'Stale'); return; }
        console.log(`[WS] Connected: ${deviceSerial}`);
        setLoading(false);
        setIsConnected(true);
      };

      ws.onmessage = (event) => {
        if (currentSerialRef.current !== deviceSerial) return;
        frameRecvTsRef.current = performance.now();
        const blob = new Blob([event.data], { type: 'image/jpeg' });
        const url = URL.createObjectURL(blob);
        if (imageUrlRef.current) URL.revokeObjectURL(imageUrlRef.current);
        imageUrlRef.current = url;
        setImageUrl(url);
      };

      ws.onerror = () => { setIsConnected(false); };

      ws.onclose = (event) => {
        console.log(`[WS] Closed: ${deviceSerial}`, event.code, event.reason);
        if (wsRef.current === ws) wsRef.current = null;
        setIsConnected(false);
        if (currentSerialRef.current === deviceSerial && !event.wasClean) {
          console.log('[WS] Reconnecting in 2s...');
          setTimeout(() => {
            if (currentSerialRef.current === deviceSerial) openNewWs();
          }, 2000);
        }
      };
    };

    if (prevWs && prevWs.readyState !== WebSocket.CLOSED) {
      // Wait for old WS to fully close before opening new one.
      console.log(`[WS] Waiting for old stream (${prevSerial}) to close before opening ${deviceSerial}`);
      cleanupImageUrl();
      const onPrevClose = () => {
        prevWs.removeEventListener('close', onPrevClose);
        openNewWs();
      };
      prevWs.addEventListener('close', onPrevClose);
      prevWs.close(1000, 'Device switched');
    } else {
      openNewWs();
    }

    return () => {
      console.log(`[WS] Cleanup for ${deviceSerial}`);
      currentSerialRef.current = null;
      const ws = wsRef.current;
      if (ws) {
        ws.close(1000, 'Cleanup');
        wsRef.current = null;
      }
      cleanupImageUrl();
    };
  }, [deviceSerial, cleanupImageUrl]); // eslint-disable-line react-hooks/exhaustive-deps

  // Load image for canvas
  useEffect(() => {
    if (!imageUrl) return;

    const recvTs = frameRecvTsRef.current;
    const img = new Image();
    img.src = imageUrl;
    img.onload = () => {
      const decodeTs = performance.now();
      imageRef.current = img;
      setFrameSize({ width: img.width, height: img.height });

      requestAnimationFrame(() => {
        const paintTs = performance.now();
        const wsDecode = decodeTs - recvTs;
        const wsPaint  = paintTs  - recvTs;
        const stats = frameTimingRef.current;
        stats.count++;
        stats.sumWsDecode += wsDecode;
        stats.sumWsPaint  += wsPaint;
        if (stats.count % 10 === 0) {
          const avgDecode = (stats.sumWsDecode / 10).toFixed(0);
          const avgPaint  = (stats.sumWsPaint  / 10).toFixed(0);
          console.log(
            `[ScreenCanvas timing] avg over 10 frames — ` +
            `ws→decode: ${avgDecode}ms  ws→painted: ${avgPaint}ms`
          );
          stats.sumWsDecode = stats.sumWsPaint = 0;
        }
      });
    };

    return () => {
      img.onload = null;
    };
  }, [imageUrl]);

  // Convert canvas coordinates to device coordinates
  const canvasToDevice = useCallback(
    (canvasX: number, canvasY: number): { x: number; y: number } => {
      if (!deviceInfo) return { x: 0, y: 0 };
      
      return {
        x: Math.round(canvasX / scale),
        y: Math.round(canvasY / scale),
      };
    },
    [deviceInfo, scale]
  );

  // Convert device coordinates to canvas coordinates
  const deviceToCanvas = useCallback(
    (deviceX: number, deviceY: number): { x: number; y: number } => {
      return {
        x: deviceX * hierarchyFit.x * scale,
        y: deviceY * hierarchyFit.y * scale,
      };
    },
    [scale, hierarchyFit]
  );

  // Handle mouse move
  const handleMouseMove = (e: any) => {
    const stage = e.target.getStage();
    const pointerPos = stage.getPointerPosition();
    if (!pointerPos) return;

    const deviceCoord = canvasToDevice(pointerPos.x, pointerPos.y);
    onCoordinateUpdate({
      x: deviceCoord.x,
      y: deviceCoord.y,
      canvasX: pointerPos.x,
      canvasY: pointerPos.y,
    });

    if (tapMode && tapStartRef.current) {
      const dx = pointerPos.x - tapStartRef.current.canvasX;
      const dy = pointerPos.y - tapStartRef.current.canvasY;
      if (Math.sqrt(dx * dx + dy * dy) > SWIPE_THRESHOLD) {
        setSwipeArrow({
          x1: tapStartRef.current.canvasX,
          y1: tapStartRef.current.canvasY,
          x2: pointerPos.x,
          y2: pointerPos.y,
        });
      }
    }
  };

  const handleMouseLeave = () => {
    onCoordinateUpdate(null);
    setSwipeArrow(null);
  };

  const handleMouseDown = (e: any) => {
    if (!tapMode) return;
    const stage = e.target.getStage();
    const pos = stage.getPointerPosition();
    if (pos) {
      const dc = canvasToDevice(pos.x, pos.y);
      tapStartRef.current = { x: dc.x, y: dc.y, canvasX: pos.x, canvasY: pos.y };
      setSwipeArrow(null);
    }
  };

  const handleMouseUp = (e: any) => {
    if (!tapMode || !tapStartRef.current) return;
    const stage = e.target.getStage();
    const pos = stage.getPointerPosition();
    if (!pos) return;
    const dx = pos.x - tapStartRef.current.canvasX;
    const dy = pos.y - tapStartRef.current.canvasY;
    const dist = Math.sqrt(dx * dx + dy * dy);
    const start = tapStartRef.current;
    tapStartRef.current = null;
    setSwipeArrow(null);
    if (deviceSerial) {
      if (dist > SWIPE_THRESHOLD) {
        const endDc = canvasToDevice(pos.x, pos.y);
        interactionAPI.swipe(deviceSerial, start.x, start.y, endDc.x, endDc.y, 300)
          .then(() => message.success(`Swipe sent: (${start.x}, ${start.y}) -> (${endDc.x}, ${endDc.y})`))
          .catch(() => message.error(`Swipe failed: (${start.x}, ${start.y}) -> (${endDc.x}, ${endDc.y})`));
      } else {
        interactionAPI.tap(deviceSerial, start.x, start.y)
          .then(() => message.success(`Tap sent: (${start.x}, ${start.y})`))
          .catch(() => message.error(`Tap failed: (${start.x}, ${start.y})`));
      }
    }
  };

  // Handle click/tap (select mode only)
  const handleClick = (e: any) => {
    if (tapMode) return;
    const stage = e.target.getStage();
    const pointerPos = stage.getPointerPosition();

    if (pointerPos && onTap && deviceInfo) {
      let hx: number;
      let hy: number;

      if (frameSize.width > 0 && canvasSize.width > 0) {
        // Direct mapping: canvas px → screenshot pixel space (= bounds_computed space).
        // Works for both iOS (frame 1170x2532, device 375x812) and Android (frame == device px).
        hx = Math.round(pointerPos.x * frameSize.width / canvasSize.width);
        hy = Math.round(pointerPos.y * frameSize.height / canvasSize.height);
      } else {
        // Fallback before first frame arrives: use logical device space.
        const deviceCoord = canvasToDevice(pointerPos.x, pointerPos.y);
        hx = deviceCoord.x;
        hy = deviceCoord.y;
      }

      onTap(hx, hy);
    }
  };

  // Refresh screenshot
  const refreshScreen = () => {
    if (imageUrlRef.current) {
      URL.revokeObjectURL(imageUrlRef.current);
    }
    const url = deviceAPI.getScreenshotUrl(deviceSerial!);
    imageUrlRef.current = url;
    setImageUrl(url);
  };

  // Refresh hierarchy
  const refreshHierarchy = async () => {
    if (!deviceSerial) return;
    
    setHierarchyLoading(true);
    try {
      console.log('Refreshing UI hierarchy...');
      const response = await hierarchyAPI.dumpHierarchy(deviceSerial);
      
      if (response.success && response.hierarchy) {
        setHierarchy(response.hierarchy);
        const bounds = extractElementBounds(response.hierarchy);
        setElementBounds(bounds);
        
        // Notify parent component
        if (onHierarchyLoaded) {
          onHierarchyLoaded(response.hierarchy);
        }
        
        message.success(`Refreshed: ${bounds.length} interactive elements`);
      } else {
        message.error('Failed to refresh hierarchy');
      }
    } catch (error) {
      message.error('Error refreshing hierarchy');
      console.error(error);
    } finally {
      setHierarchyLoading(false);
    }
  };

  // Manual reconnect
  const handleReconnect = () => {
    closeWebSocket();
    cleanupImageUrl();
    setLoading(true);
    
    // Trigger reconnection by updating a dummy state
    setTimeout(() => {
      if (deviceSerial && deviceInfo) {
        const wsUrl = deviceAPI.getWebSocketUrl(deviceSerial);
        const ws = new WebSocket(wsUrl);
        ws.binaryType = 'arraybuffer';
        
        ws.onopen = () => {
          console.log('Reconnected');
          setLoading(false);
          setIsConnected(true);
        };
        
        ws.onmessage = (event) => {
          if (currentSerialRef.current !== deviceSerial) return;
          
          const blob = new Blob([event.data], { type: 'image/jpeg' });
          const url = URL.createObjectURL(blob);
          
          if (imageUrlRef.current) {
            URL.revokeObjectURL(imageUrlRef.current);
          }
          
          imageUrlRef.current = url;
          setImageUrl(url);
        };
        
        ws.onerror = () => {
          message.error('Reconnection failed');
          setIsConnected(false);
        };
        
        ws.onclose = () => {
          setIsConnected(false);
        };
        
        wsRef.current = ws;
      }
    }, 100);
  };

  if (!deviceSerial) {
    return (
      <Card>
        <div style={{ textAlign: 'center', padding: 40 }}>
          <Text type="secondary">Please select a device first</Text>
        </div>
      </Card>
    );
  }

  return (
    <Card
      title={
        <Flex align="center" justify="space-between" style={{ width: '100%' }}>
          <Flex gap={8} align="center">
            <span style={{ fontWeight: 500, fontSize: 14 }}>Device Screen</span>
            {isConnected && (
              <span style={{ color: '#52c41a', fontSize: 12 }}>● Connected</span>
            )}
            {!isConnected && !loading && (
              <span style={{ color: '#ff4d4f', fontSize: 12 }}>● Disconnected</span>
            )}
          </Flex>
          <Text type="secondary" style={{ fontSize: 12, fontFamily: 'monospace' }}>
            {coordinate ? `(${coordinate.x}, ${coordinate.y})` : '(--, --)'}
          </Text>
        </Flex>
      }
      style={{ 
        height: '100%',
        display: 'flex',
        flexDirection: 'column',
      }}
      bodyStyle={{
        flex: 1,
        minHeight: 0,
        padding: '8px',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
      }}
      headStyle={{
        minHeight: 'auto',
        padding: '8px 12px',
      }}
    >
      {/* Canvas area — fills remaining height */}
      <div 
        ref={containerRef} 
        style={{ 
          position: 'relative', 
          width: '100%',
          flex: 1,
          minHeight: 0,
          display: 'flex',
          justifyContent: 'center',
          alignItems: 'center',
        }}
      >
        {loading && (
          <div style={{ textAlign: 'center', padding: 40 }}>
            <Spin size="large" tip="Connecting to device..." />
          </div>
        )}
        
        {!loading && (
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 6 }}>
            {/* Horizontal toolbar on top of canvas */}
            <Flex
              gap={6}
              align="center"
              justify="flex-end"
              style={{
                width: '100%',
                maxWidth: canvasSize.width,
              }}
            >
              <Tooltip title={tapMode ? 'Tap Mode ON — click to disable' : 'Enable Tap Mode (click/swipe device)'}>
                <Button
                  icon={<AimOutlined style={{ color: tapMode ? '#ff4d4f' : undefined }} />}
                  onClick={() => setTapMode((prev) => !prev)}
                  size="small"
                  type="default"
                  style={tapMode ? { background: '#fff1f0', borderColor: '#ffa39e' } : undefined}
                />
              </Tooltip>
              <Tooltip title={`Show element bounds (${elementBounds.length} elements)`}>
                <Button
                  icon={<BgColorsOutlined style={{ color: showElementBounds && !tapMode ? '#1890ff' : undefined }} />}
                  onClick={() => setShowElementBounds((prev) => !prev)}
                  size="small"
                  type="default"
                  style={showElementBounds && !tapMode ? { background: '#e6f4ff', borderColor: '#91caff' } : undefined}
                  disabled={tapMode}
                />
              </Tooltip>
              <Tooltip title="Refresh UI Hierarchy">
                <Button
                  icon={<ApiOutlined />}
                  onClick={refreshHierarchy}
                  size="small"
                  type="default"
                />
              </Tooltip>
              <Tooltip title="Reconnect WebSocket">
                <Button
                  icon={<ReloadOutlined />}
                  onClick={handleReconnect}
                  size="small"
                  type="default"
                  disabled={loading}
                />
              </Tooltip>
              <Tooltip title="Refresh Screenshot">
                <Button
                  icon={<SyncOutlined />}
                  onClick={refreshScreen}
                  size="small"
                  type="default"
                />
              </Tooltip>
              <Tooltip title="Save Screenshot">
                <Button
                  icon={<CameraOutlined />}
                  onClick={downloadScreenshot}
                  size="small"
                  type="default"
                  disabled={!imageUrl}
                />
              </Tooltip>
              <Popover
                trigger="click"
                placement="bottomRight"
                content={
                  <Flex vertical gap={4} style={{ minWidth: 170 }}>
                    <Text type="secondary" style={{ fontSize: 12, fontFamily: 'monospace' }}>
                      Device: {deviceInfo ? `${deviceInfo.width}x${deviceInfo.height}` : '--'}
                    </Text>
                    <Text type="secondary" style={{ fontSize: 12, fontFamily: 'monospace' }}>
                      Frame: {frameSize.width > 0 ? `${frameSize.width}x${frameSize.height}` : '--'}
                    </Text>
                    <Text type="secondary" style={{ fontSize: 12, fontFamily: 'monospace' }}>
                      Scale: {(scale * 100).toFixed(0)}%
                    </Text>
                    <Text type="secondary" style={{ fontSize: 12, fontFamily: 'monospace' }}>
                      Fit: {hierarchyFit.x.toFixed(3)}x, {hierarchyFit.y.toFixed(3)}y
                    </Text>
                    <Text type="secondary" style={{ fontSize: 12, fontFamily: 'monospace' }}>
                      Elements: {elementBounds.length}
                    </Text>
                    <Text type="secondary" style={{ fontSize: 12, fontFamily: 'monospace' }}>
                      Cursor: {coordinate ? `(${coordinate.x}, ${coordinate.y})` : '(--, --)'}
                    </Text>
                  </Flex>
                }
              >
                <Button
                  icon={<InfoCircleOutlined />}
                  size="small"
                  type="default"
                />
              </Popover>
            </Flex>

            <div
              style={{
                display: 'flex',
                alignItems: 'flex-start',
                gap: 0,
                position: 'relative',
              }}
            >
              <div 
              style={{ 
                border: '2px solid #d9d9d9', 
                borderRadius: 4, 
                overflow: 'hidden',
                boxShadow: '0 2px 8px rgba(0,0,0,0.15)',
                position: 'relative',
              }}
            >
              {hierarchyLoading && (
                <div style={{
                  position: 'absolute',
                  inset: 0,
                  background: 'rgba(0,0,0,0.45)',
                  display: 'flex',
                  flexDirection: 'column',
                  alignItems: 'center',
                  justifyContent: 'center',
                  gap: 10,
                  zIndex: 10,
                  borderRadius: 4,
                  pointerEvents: 'none',
                }}>
                  <Spin size="large" />
                  <span style={{ color: '#fff', fontSize: 13 }}>Refreshing hierarchy…</span>
                </div>
              )}
              <Stage
                width={canvasSize.width}
                height={canvasSize.height}
                onMouseMove={handleMouseMove}
                onMouseLeave={handleMouseLeave}
                onMouseDown={handleMouseDown}
                onMouseUp={handleMouseUp}
                onClick={handleClick}
                style={{ cursor: tapMode ? 'crosshair' : 'default', background: '#000', display: 'block' }}
                pixelRatio={3}
              >
                <Layer>
                {/* Background image */}
                {imageUrl && imageRef.current && (
                  <KonvaImage
                    image={imageRef.current}
                    width={canvasSize.width}
                    height={canvasSize.height}
                  />
                )}
                
                {/* Element bounds from hierarchy — hidden in tap mode */}
                {showElementBounds && !tapMode && elementBounds.map((element, index) => {
                  const canvasPos = deviceToCanvas(element.bounds.x, element.bounds.y);
                  return (
                    <Rect
                      key={`element-${index}`}
                      x={canvasPos.x}
                      y={canvasPos.y}
                      width={element.bounds.w * hierarchyFit.x * scale}
                      height={element.bounds.h * hierarchyFit.y * scale}
                      stroke={element.color}
                      strokeWidth={1.5}
                      opacity={0.9}
                      dash={[5, 3]}
                    />
                  );
                })}
                
                {/* Manual overlays (from element selection) */}
                {overlays.map((overlay, index) => {
                  const canvasPos = deviceToCanvas(overlay.bounds.x, overlay.bounds.y);
                  return (
                    <Rect
                      key={`overlay-${index}`}
                      x={canvasPos.x}
                      y={canvasPos.y}
                      width={overlay.bounds.w * hierarchyFit.x * scale}
                      height={overlay.bounds.h * hierarchyFit.y * scale}
                      stroke={overlay.color}
                      strokeWidth={3}
                      fill={overlay.color}
                      opacity={0.25}
                    />
                  );
                })}

                {/* Swipe arrow feedback in tap mode */}
                {tapMode && swipeArrow && (
                  <Arrow
                    points={[swipeArrow.x1, swipeArrow.y1, swipeArrow.x2, swipeArrow.y2]}
                    stroke="red"
                    fill="red"
                    strokeWidth={2}
                    pointerLength={10}
                    pointerWidth={8}
                    opacity={0.85}
                  />
                )}
                </Layer>
              </Stage>
              </div>

            </div>
          </div>
        )}
      </div>
    </Card>
  );
});

ScreenCanvas.displayName = 'ScreenCanvas';

// Custom Konva Image component
const KonvaImage: React.FC<any> = ({ image, width, height }) => {
  const imageRef = useRef<any>(null);
  
  useEffect(() => {
    if (imageRef.current) {
      imageRef.current.getLayer()?.batchDraw();
    }
  }, [image]);
  
  return (
    <Rect
      ref={imageRef}
      fillPatternImage={image}
      fillPatternScaleX={width / image.width}
      fillPatternScaleY={height / image.height}
      width={width}
      height={height}
    />
  );
};

export default ScreenCanvas;
