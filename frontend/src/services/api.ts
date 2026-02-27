/**
 * API Service
 * Handles all API calls to backend
 */

// 使用相对路径，通过 Vite 代理转发到后端
const API_BASE_URL = '/api';

// WebSocket 需要直接连接后端（代理不支持 WebSocket）
const WS_BASE_URL = import.meta.env.DEV 
  ? 'ws://localhost:8000'  // 开发环境直接连接
  : `ws://${window.location.host}`;  // 生产环境使用当前 host

// ============================================================================
// Device API
// ============================================================================

export const deviceAPI = {
  /**
   * Get all connected devices
   */
  getDevices: async () => {
    const response = await fetch(`${API_BASE_URL}/devices`);
    
    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }
    
    return response.json();
  },

  /**
   * Get device info
   */
  getDeviceInfo: async (serial: string) => {
    const response = await fetch(`${API_BASE_URL}/devices/${serial}/info`);
    
    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }
    
    return response.json();
  },

  /**
   * Get WebSocket URL for screen streaming
   * WebSocket 不能通过 HTTP 代理，需要直接连接
   */
  getWebSocketUrl: (serial: string): string => {
    return `${WS_BASE_URL}/ws/screen/${serial}`;
  },

  /**
   * Get screenshot URL (single frame)
   */
  getScreenshotUrl: (serial: string): string => {
    return `${API_BASE_URL}/screenshot/${serial}?t=${Date.now()}`;
  },

  /**
   * Tell the backend to stop all streaming resources for a device.
   * For iOS this terminates the WDA proxy process.
   * Fire-and-forget: errors are logged but not re-thrown.
   */
  stopStream: async (serial: string): Promise<void> => {
    try {
      await fetch(`${API_BASE_URL}/stream/stop/${serial}`, { method: 'POST' });
    } catch (e) {
      console.warn(`[deviceAPI] stopStream(${serial}) failed:`, e);
    }
  },
};

// ============================================================================
// Hierarchy API
// ============================================================================

export const hierarchyAPI = {
  /**
   * Dump UI hierarchy
   */
  dumpHierarchy: async (serial: string) => {
    const response = await fetch(`${API_BASE_URL}/dump/${serial}`);
    
    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }
    
    return response.json();
  },

  /**
   * Query XPath
   */
  queryXPath: async (serial: string, xpath: string) => {
    const response = await fetch(`${API_BASE_URL}/xpath/query`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        serial,
        xpath,
      }),
    });
    
    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }
    
    return response.json();
  },
};

// ============================================================================
// Element API
// ============================================================================

export const elementAPI = {
  /**
   * Get element info by node path
   */
  getElementInfo: async (serial: string, nodePath: number[]) => {
    const response = await fetch(`${API_BASE_URL}/element/info`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        serial,
        node_path: nodePath,
      }),
    });
    
    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }
    
    return response.json();
  },

  /**
   * Find element by coordinate
   */
  findByCoordinate: async (serial: string, x: number, y: number) => {
    const response = await fetch(`${API_BASE_URL}/element/find-by-coordinate`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        serial,
        x,
        y,
      }),
    });
    
    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }
    
    return response.json();
  },
};

// ============================================================================
// Interaction API
// ============================================================================

export const interactionAPI = {
  /**
   * Tap at coordinate
   */
  tap: async (serial: string, x: number, y: number) => {
    const response = await fetch(`${API_BASE_URL}/tap`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        serial,
        x,
        y,
      }),
    });
    
    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }
    
    return response.json();
  },

  /**
   * Swipe gesture
   */
  swipe: async (serial: string, x1: number, y1: number, x2: number, y2: number, duration: number = 300) => {
    const response = await fetch(`${API_BASE_URL}/swipe`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        serial,
        x1,
        y1,
        x2,
        y2,
        duration,
      }),
    });
    
    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }
    
    return response.json();
  },
};
