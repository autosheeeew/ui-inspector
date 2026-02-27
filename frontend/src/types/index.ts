/**
 * Type Definitions for Android UI Inspector
 */

// ============================================================================
// Device Types
// ============================================================================

export interface DeviceInfo {
  serial: string;
  model: string;
  name: string;
  android_version?: string;
  ios_version?: string;
  width: number;
  height: number;
  state: string;
  platform: string;
}

// ============================================================================
// UI Hierarchy Types
// ============================================================================

export interface BoundsComputed {
  x: number;
  y: number;
  w: number;
  h: number;
}

export interface NodeAttributes {
  [key: string]: any;
  index?: string;
  text?: string;
  'resource-id'?: string;
  class?: string;
  package?: string;
  'content-desc'?: string;
  checkable?: string;
  checked?: string;
  clickable?: string;
  enabled?: string;
  focusable?: string;
  focused?: string;
  scrollable?: string;
  'long-clickable'?: string;
  password?: string;
  selected?: string;
  bounds?: string;
  bounds_computed?: BoundsComputed;
  name?: string;  // iOS
  label?: string;  // iOS
  value?: string;  // iOS
}

export interface ElementSelectors {
  id?: string | null;
  accessibility_id?: string | null;
  class_name?: string;
  xpath_absolute?: string;
  xpath_relative?: string[];
  uiautomator?: string[];
  predicate?: string[];
  class_chain?: string[];
}

export interface HierarchyNode {
  tag: string;
  attributes: NodeAttributes;
  children: HierarchyNode[];
  selectors?: ElementSelectors;
  node_path?: number[];
}

export interface SelectedElement {
  tag: string;
  attributes: NodeAttributes;
  selectors: ElementSelectors;
  node_path: number[];
}

// ============================================================================
// Screen & Interaction Types
// ============================================================================

export interface Coordinate {
  x: number;
  y: number;
  canvasX?: number;
  canvasY?: number;
}

export interface Overlay {
  bounds: BoundsComputed;
  color: string;
  label?: string;
}

// ============================================================================
// XPath Types
// ============================================================================

export interface XPathMatch {
  tag: string;
  attributes: NodeAttributes;
  bounds_computed?: BoundsComputed;
}

export interface XPathQueryResult {
  success: boolean;
  count: number;
  matches: XPathMatch[];
  error?: string;
}

// ============================================================================
// API Response Types
// ============================================================================

export interface DumpHierarchyResponse {
  success: boolean;
  platform: string;
  device_info: DeviceInfo;
  total_nodes: number;
  hierarchy: HierarchyNode;
  error?: string;
}

export interface ElementInfoResponse {
  success: boolean;
  element: SelectedElement;
  error?: string;
}

export interface FindByCoordinateResponse {
  success: boolean;
  element?: SelectedElement;
  error?: string;
}

export interface TapResponse {
  success: boolean;
  error?: string;
}

export interface SwipeResponse {
  success: boolean;
  error?: string;
}

/**
 * XPath query match result
 */
export interface XPathMatch {
  tag: string;  // ✅ 完整的类名，如 "android.widget.Button"
  attributes: {
    [key: string]: string;
  };
  bounds_computed: BoundsComputed;
}

/**
 * XPath query response
 */
export interface XPathQueryResponse {
  success: boolean;
  count: number;
  matches: XPathMatch[];
  error?: string;
}
