/**
 * Device Selector Component
 */
import React, { useState, useEffect } from 'react';
import { Card, Select, Button, Space, Typography, message } from 'antd';
import { MobileOutlined, ReloadOutlined } from '@ant-design/icons';
import { deviceAPI } from '../services/api';
import type { DeviceInfo } from '../types';

const { Text } = Typography;
const { Option } = Select;

interface DeviceSelectorProps {
  onDeviceSelect: (device: DeviceInfo) => void;
}

const DeviceSelector: React.FC<DeviceSelectorProps> = ({
  onDeviceSelect,
}) => {
  const [devices, setDevices] = useState<DeviceInfo[]>([]);
  const [selectedSerial, setSelectedSerial] = useState<string | null>(null);
  const [loadingDevices, setLoadingDevices] = useState(false);

  useEffect(() => {
    loadDevices();
  }, []);

  const loadDevices = async () => {
    setLoadingDevices(true);
    try {
      const deviceList = await deviceAPI.getDevices();
      console.log('Loaded devices:', deviceList);
      
      setDevices(deviceList);
      
      if (deviceList.length > 0) {
        const firstDevice = deviceList[0];
        setSelectedSerial(firstDevice.serial);
        // ✅ 传递完整对象
        onDeviceSelect(firstDevice);
      } else {
        message.warning('No devices found. Please connect a device.');
      }
    } catch (error) {
      message.error('Failed to load devices');
      console.error(error);
    } finally {
      setLoadingDevices(false);
    }
  };

  // ✅ 修改：传递完整的 device 对象
  const handleDeviceChange = (serial: string) => {
    setSelectedSerial(serial);
    const device = devices.find(d => d.serial === serial);
    if (device) {
      console.log('Selected device:', device);
      onDeviceSelect(device);  // ✅ 传递完整对象
    }
  };

  return (
    <Card>
      <Space size="middle" style={{ width: '100%' }}>
        <MobileOutlined style={{ fontSize: 24 }} />
        
        <div style={{ flex: 1 }}>
          <Text strong>Device:</Text>
          <Select
            value={selectedSerial}
            onChange={handleDeviceChange}
            style={{ width: '100%', marginTop: 8 }}
            placeholder="Select a device"
            loading={loadingDevices}
          >
            {devices.map((device) => (
              <Option key={device.serial} value={device.serial}>
                {device.model || device.serial} ({device.platform})
              </Option>
            ))}
          </Select>
        </div>

        <Button
          icon={<ReloadOutlined />}
          onClick={loadDevices}
          loading={loadingDevices}
        >
          Refresh Devices
        </Button>
      </Space>
    </Card>
  );
};

export default DeviceSelector;
