import React, { useState, useRef, useEffect } from 'react';
import { Layout, Row, Col, message, Select, Button, Flex, Switch } from 'antd';
import { MobileOutlined, ReloadOutlined, MoonOutlined, SunOutlined } from '@ant-design/icons';
import ScreenCanvas, { ScreenCanvasRef } from './components/ScreenCanvas';
import HierarchyTree, { HierarchyTreeRef } from './components/HierarchyTree';
import ElementInspector from './components/ElementInspector';
import XPathPlayground from './components/XPathPlayground';
import { deviceAPI, elementAPI } from './services/api';
import type { 
  DeviceInfo, 
  HierarchyNode, 
  Overlay, 
  Coordinate, 
  SelectedElement,
  BoundsComputed 
} from './types';
import './App.css';

const { Header, Content } = Layout;
const { Option } = Select;

const App: React.FC = () => {
  const [devices, setDevices] = useState<DeviceInfo[]>([]);
  const [selectedDevice, setSelectedDevice] = useState<string | null>(null);
  const [platform, setPlatform] = useState<string>('android');
  const [hierarchy, setHierarchy] = useState<HierarchyNode | null>(null);
  const [overlays, setOverlays] = useState<Overlay[]>([]);
  const [currentCoordinate, setCurrentCoordinate] = useState<Coordinate | null>(null);
  const [selectedElement, setSelectedElement] = useState<SelectedElement | null>(null);
  const [loadingDevices, setLoadingDevices] = useState(false);
  const [darkMode, setDarkMode] = useState(false);

  const hierarchyTreeRef = useRef<HierarchyTreeRef>(null);
  const screenCanvasRef = useRef<ScreenCanvasRef>(null);

  // Load devices on mount
  useEffect(() => {
    loadDevices();
  }, []);

  const loadDevices = async () => {
    setLoadingDevices(true);
    try {
      const deviceList = await deviceAPI.getDevices();
      console.log('Loaded devices:', deviceList);
      
      setDevices(deviceList);
      
      if (deviceList.length > 0 && !selectedDevice) {
        const firstDevice = deviceList[0];
        setSelectedDevice(firstDevice.serial);
        setPlatform(firstDevice.platform);
        message.success(`Connected to ${firstDevice.model || firstDevice.serial}`);
      } else if (deviceList.length === 0) {
        message.warning('No devices found. Please connect a device.');
      }
    } catch (error) {
      message.error('Failed to load devices');
      console.error(error);
    } finally {
      setLoadingDevices(false);
    }
  };

  // Handle device selection
  const handleDeviceChange = (serial: string) => {
    // Immediately stop the current stream before React re-renders with the new serial.
    // This prevents the old device's WS and backend screenshot loop from running in parallel
    // with the new device's stream.
    if (selectedDevice && selectedDevice !== serial) {
      console.log(`[App] Switching device ${selectedDevice} → ${serial}, force-disconnecting old stream`);
      screenCanvasRef.current?.forceDisconnect();
      // Tell the backend to stop resources for the old device.
      // For iOS this terminates the WDA proxy process.
      deviceAPI.stopStream(selectedDevice);
    }

    setSelectedDevice(serial);
    const device = devices.find(d => d.serial === serial);
    if (device) {
      setPlatform(device.platform);
      setHierarchy(null);
      setOverlays([]);
      setSelectedElement(null);
      message.success(`Switched to ${device.model || device.serial}`);
    }
  };

  // Handle hierarchy loaded from ScreenCanvas
  const handleHierarchyLoaded = (loadedHierarchy: HierarchyNode) => {
    setHierarchy(loadedHierarchy);
  };

  // Handle coordinate update
  const handleCoordinateUpdate = (coord: Coordinate | null) => {
    setCurrentCoordinate(coord);
  };

  // ✅ 修改：点击 Canvas 时查找元素并定位
  const handleTap = async (x: number, y: number) => {
    if (!selectedDevice) return;

    try {
      // 查找元素
      const result = await elementAPI.findByCoordinate(selectedDevice, x, y);
      
      if (result.success && result.element) {
        message.success(`Found: ${result.element.tag}`);
        
        // 设置选中的元素
        setSelectedElement(result.element);
        
        // ✅ 折叠所有并展开到目标节点
        if (hierarchyTreeRef.current && result.element.node_path) {
          hierarchyTreeRef.current.expandAndSelectNode(result.element.node_path);
        }
        
        // 高亮显示
        const bounds = result.element.attributes.bounds_computed;
        if (bounds) {
          setOverlays([{
            bounds,
            color: '#52c41a',
            label: result.element.tag.split('.').pop() || 'Element'
          }]);
        }
      } else {
        message.warning('No element found at this coordinate');
      }
    } catch (error) {
      console.error('Error finding element:', error);
      message.error('Failed to find element');
    }
  };

  // Handle node hover
  const handleNodeHover = (bounds: BoundsComputed | null) => {
    if (bounds) {
      setOverlays([{
        bounds,
        color: '#1890ff',
        label: 'Hover'
      }]);
    } else {
      setOverlays([]);
    }
  };

  // Handle node select
  const handleNodeSelect = (bounds: BoundsComputed | null) => {
    if (bounds) {
      setOverlays([{
        bounds,
        color: '#52c41a',
        label: 'Selected'
      }]);
    }
  };

  // Handle element select — fetch selectors on-demand if they are empty (lazy generation)
  const handleElementSelect = async (element: SelectedElement) => {
    // Optimistically show the element immediately (attributes are always present)
    setSelectedElement(element);

    if (!selectedDevice) return;

    // If selectors are already populated, nothing to do
    if (element.selectors && Object.keys(element.selectors).length > 0) return;

    try {
      const result = await elementAPI.getElementInfo(selectedDevice, element.node_path);
      if (result.success && result.element) {
        setSelectedElement(result.element);
      }
    } catch (e) {
      // Selector fetch failure is non-fatal; element attributes are already shown
      console.warn('[handleElementSelect] Failed to fetch selectors:', e);
    }
  };

  // Handle XPath results
  const handleXPathResults = (bounds: BoundsComputed[]) => {
    const newOverlays = bounds.map((b, index) => ({
      bounds: b,
      color: '#ff4d4f',
      label: `Match ${index + 1}`
    }));
    setOverlays(newOverlays);
  };

  return (
    <Layout style={{ minHeight: '100vh', background: darkMode ? '#141414' : '#f0f2f5' }}>
      <Header style={{ 
        background: '#001529', 
        padding: '0 24px',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        flexWrap: 'wrap',
        height: 'auto',
        minHeight: 64,
      }}>
        {/* Left: Title */}
        <div style={{ 
          color: 'white', 
          fontSize: '20px', 
          fontWeight: 'bold',
          marginRight: 24,
        }}>
          📱 Android UI Inspector
        </div>

        {/* Center: Device Selector */}
        <Flex gap={12} align="center" style={{ flex: 1, minWidth: 300, maxWidth: 600 }}>
          <MobileOutlined style={{ color: 'white', fontSize: 18 }} />
          <Select
            value={selectedDevice}
            onChange={handleDeviceChange}
            style={{ flex: 1, minWidth: 200 }}
            placeholder="Select a device"
            loading={loadingDevices}
            size="large"
          >
            {devices.map((device) => (
              <Option key={device.serial} value={device.serial}>
                {device.model || device.serial} ({device.platform})
              </Option>
            ))}
          </Select>
          <Button
            icon={<ReloadOutlined />}
            onClick={loadDevices}
            loading={loadingDevices}
            type="default"
          >
            Refresh
          </Button>
        </Flex>

        {/* Right: Dark Mode Toggle */}
        <Flex gap={8} align="center" style={{ marginLeft: 24 }}>
          {darkMode ? <MoonOutlined style={{ color: 'white' }} /> : <SunOutlined style={{ color: 'white' }} />}
          <Switch
            checked={darkMode}
            onChange={setDarkMode}
            checkedChildren="🌙"
            unCheckedChildren="☀️"
          />
        </Flex>
      </Header>

      <Content style={{ padding: '16px 16px 0 16px' }}>
        {/* Main Layout — 三列，统一高度 calc(100vh - 80px) */}
        <Row gutter={12} style={{ height: 'calc(100vh - 96px)' }} wrap={false}>
          {/* Left Column: Screen Canvas */}
          <Col flex="0 0 460px" style={{ minWidth: 420, display: 'flex', flexDirection: 'column' }}>
            <ScreenCanvas
              ref={screenCanvasRef}
              deviceSerial={selectedDevice}
              overlays={overlays}
              onCoordinateUpdate={handleCoordinateUpdate}
              onTap={handleTap}
              onHierarchyLoaded={handleHierarchyLoaded}
              coordinate={currentCoordinate}
            />
          </Col>

          {/* Middle Column: Hierarchy Tree */}
          <Col flex="1 1 0" style={{ minWidth: 0, display: 'flex', flexDirection: 'column' }}>
            <HierarchyTree
              ref={hierarchyTreeRef}
              hierarchy={hierarchy}
              deviceSerial={selectedDevice}
              onNodeHover={handleNodeHover}
              onNodeSelect={handleNodeSelect}
              onElementSelect={handleElementSelect}
            />
          </Col>

          {/* Right Column: Element Inspector + XPath Playground */}
          <Col
            flex="1 1 0"
            style={{ display: 'flex', flexDirection: 'column', gap: 12, overflowY: 'auto', minHeight: 0, minWidth: 0 }}
          >
            <ElementInspector
              element={selectedElement}
              platform={platform as 'android' | 'ios'}
            />
            <XPathPlayground
              deviceSerial={selectedDevice}
              platform={platform as 'android' | 'ios'}
              onResultsUpdate={handleXPathResults}
            />
          </Col>
        </Row>
      </Content>
    </Layout>
  );
};

export default App;
