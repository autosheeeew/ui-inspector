/**
 * Coordinate Display Component
 * Shows real-time cursor coordinates
 */
import React from 'react';
import { Card, Descriptions, Tag, Typography } from 'antd';
import { AimOutlined } from '@ant-design/icons';
import type { Coordinate } from '../types';

const { Text } = Typography;

interface CoordinateDisplayProps {
  coordinate: Coordinate | null;
}

const CoordinateDisplay: React.FC<CoordinateDisplayProps> = ({ coordinate }) => {
  return (
    <Card 
      size="small" 
      title={
        <span>
          <AimOutlined /> Coordinate Picker
        </span>
      }
    >
      {coordinate ? (
        <Descriptions column={1} size="small" bordered>
          <Descriptions.Item label="Device X">
            <Tag color="blue">{coordinate.x} px</Tag>
          </Descriptions.Item>
          <Descriptions.Item label="Device Y">
            <Tag color="blue">{coordinate.y} px</Tag>
          </Descriptions.Item>
          <Descriptions.Item label="Canvas X">
            <Text type="secondary">{coordinate.canvasX.toFixed(0)} px</Text>
          </Descriptions.Item>
          <Descriptions.Item label="Canvas Y">
            <Text type="secondary">{coordinate.canvasY.toFixed(0)} px</Text>
          </Descriptions.Item>
          <Descriptions.Item label="ADB Command">
            <Text code copyable>
              adb shell input tap {coordinate.x} {coordinate.y}
            </Text>
          </Descriptions.Item>
        </Descriptions>
      ) : (
        <div style={{ textAlign: 'center', padding: 20 }}>
          <Text type="secondary">
            Hover over the screen to see coordinates
          </Text>
        </div>
      )}
    </Card>
  );
};

export default CoordinateDisplay;
