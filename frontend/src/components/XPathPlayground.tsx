/**
 * XPath Playground Component
 * Test XPath queries and visualize results
 */
import React, { useState } from 'react';
import {
  Card,
  Input,
  Button,
  Space,
  Typography,
  Alert,
  List,
  Tag,
  Divider,
  message,
  Collapse,
  Flex,
} from 'antd';
import {
  SearchOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  CodeOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons';
import { hierarchyAPI } from '../services/api';
import type { XPathQueryResponse, XPathMatch, BoundsComputed } from '../types';

const { Text, Paragraph } = Typography;
const { TextArea } = Input;

interface XPathPlaygroundProps {
  deviceSerial: string | null;
  onResultsUpdate: (bounds: BoundsComputed[]) => void;
}

const XPathPlayground: React.FC<XPathPlaygroundProps> = ({
  deviceSerial,
  onResultsUpdate,
}) => {
  const [xpathQuery, setXpathQuery] = useState<string>('');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<XPathQueryResponse | null>(null);

  // Predefined XPath examples
  const examples = [
    {
      label: 'All clickable elements',
      xpath: '//*[@clickable="true"]',
    },
    {
      label: 'Elements with text',
      xpath: '//*[@text!=""]',
    },
    {
      label: 'Buttons',
      xpath: '//android.widget.Button',
    },
    {
      label: 'TextViews',
      xpath: '//android.widget.TextView',
    },
    {
      label: 'Elements by resource-id',
      xpath: '//*[@resource-id="com.example:id/button"]',
    },
    {
      label: 'Elements by content-desc',
      xpath: '//*[@content-desc="Search"]',
    },
    {
      label: 'Scrollable containers',
      xpath: '//*[@scrollable="true"]',
    },
  ];

  // Execute XPath query
  const executeQuery = async () => {
    if (!deviceSerial) {
      message.warning('Please select a device first');
      return;
    }

    if (!xpathQuery.trim()) {
      message.warning('Please enter an XPath query');
      return;
    }

    setLoading(true);
    try {
      const response = await hierarchyAPI.queryXPath(deviceSerial, xpathQuery);
      setResult(response);

      if (response.success) {
        // Extract bounds for visualization
        const bounds = response.matches
          .map((match) => match.bounds_computed)
          .filter(Boolean); // ✅ 过滤掉 undefined
        onResultsUpdate(bounds);
        message.success(`Found ${response.count} matching element(s)`);
      } else {
        message.error(response.error || 'Query failed');
        onResultsUpdate([]);
      }
    } catch (error: any) {
      message.error('Failed to execute XPath query');
      console.error(error);
      setResult(null);
      onResultsUpdate([]);
    } finally {
      setLoading(false);
    }
  };

  // Clear results
  const clearResults = () => {
    setResult(null);
    onResultsUpdate([]);
  };

  // Use example
  const useExample = (xpath: string) => {
    setXpathQuery(xpath);
  };

  return (
    <Card
      title={
        <Space>
          <CodeOutlined /> XPath Playground
        </Space>
      }
      style={{ 
        display: 'flex', 
        flexDirection: 'column',
      }}
      bodyStyle={{ 
        padding: '10px',
      }}
    >
      <Space direction="vertical" style={{ width: '100%' }} size={12}>
        {/* XPath Input */}
        <div>
          <TextArea
            value={xpathQuery}
            onChange={(e) => setXpathQuery(e.target.value)}
            placeholder="Enter XPath query (e.g., //*[@text='Login'])"
            rows={2}
            style={{ fontFamily: 'monospace', fontSize: 12 }}
            onPressEnter={(e) => {
              if (e.ctrlKey || e.metaKey) {
                executeQuery();
              }
            }}
          />
          <Text type="secondary" style={{ fontSize: 11, marginTop: 4, display: 'block' }}>
            ⌘+Enter to execute
          </Text>
        </div>

        {/* Action Buttons */}
        <Flex gap={8} wrap="wrap">
          <Button
            type="primary"
            icon={<SearchOutlined />}
            onClick={executeQuery}
            loading={loading}
            disabled={!deviceSerial}
            size="small"
          >
            🔍 Test Locator
          </Button>
          <Button onClick={clearResults} size="small">Clear</Button>
        </Flex>

        {/* Quick Examples - Collapsible */}
        <Collapse
          size="small"
          items={[
            {
              key: '1',
              label: (
                <Space size={4}>
                  <ThunderboltOutlined style={{ color: '#faad14' }} />
                  <Text strong style={{ fontSize: 12 }}>Quick Examples</Text>
                </Space>
              ),
              children: (
                <Flex wrap="wrap" gap={6}>
                  {examples.map((example, index) => (
                    <Tag
                      key={index}
                      color="blue"
                      style={{ cursor: 'pointer', fontSize: 11, margin: 0 }}
                      onClick={() => useExample(example.xpath)}
                    >
                      {example.label}
                    </Tag>
                  ))}
                </Flex>
              ),
            },
          ]}
        />

        <Divider style={{ margin: '8px 0' }} />

        {/* Results */}
        {result && (
          <div>
            {result.success ? (
              <>
                <Alert
                  message={
                    <Space>
                      <CheckCircleOutlined />
                      <Text strong>
                        Found {result.count} matching element(s)
                      </Text>
                    </Space>
                  }
                  type="success"
                  showIcon={false}
                  style={{ marginBottom: 12 }}
                />

                {result.matches.length > 0 && (
                  <List
                    size="small"
                    bordered
                    dataSource={result.matches}
                    style={{ maxHeight: 300, overflow: 'auto' }}
                    renderItem={(match: XPathMatch, index: number) => (
                      <List.Item>
                        <Space direction="vertical" style={{ width: '100%' }}>
                          <Space>
                            <Tag color="purple">#{index + 1}</Tag>
                            {/* ✅ 修复：使用 match.tag */}
                            <Text strong>
                              {match.tag ? match.tag.split('.').pop() : 'Unknown'}
                            </Text>
                          </Space>
                          
                          {/* ✅ 修复：从 attributes 中获取 */}
                          {match.attributes?.text && (
                            <Text>
                              <Text type="secondary">Text:</Text> "{match.attributes.text}"
                            </Text>
                          )}
                          
                          {match.attributes?.['resource-id'] && (
                            <Text>
                              <Text type="secondary">ID:</Text>{' '}
                              {match.attributes['resource-id']}
                            </Text>
                          )}
                          
                          {match.attributes?.['content-desc'] && (
                            <Text>
                              <Text type="secondary">Desc:</Text>{' '}
                              {match.attributes['content-desc']}
                            </Text>
                          )}
                          
                          {/* ✅ 添加安全检查 */}
                          {match.bounds_computed && (
                            <Text code style={{ fontSize: 11 }}>
                              Bounds: ({match.bounds_computed.x}, {match.bounds_computed.y}) 
                              [{match.bounds_computed.w} × {match.bounds_computed.h}]
                            </Text>
                          )}
                        </Space>
                      </List.Item>
                    )}
                  />
                )}
              </>
            ) : (
              <Alert
                message={
                  <Space>
                    <CloseCircleOutlined />
                    <Text strong>Query Failed</Text>
                  </Space>
                }
                description={result.error}
                type="error"
                showIcon={false}
              />
            )}
          </div>
        )}

        {/* XPath Syntax Help */}
        <div>
          <Text strong>XPath Syntax Tips:</Text>
          <Paragraph style={{ fontSize: 12, marginTop: 8, marginBottom: 0 }}>
            • <Text code>//*[@attribute="value"]</Text> - Match by attribute
            <br />
            • <Text code>//ClassName</Text> - Match by class name
            <br />
            • <Text code>//*[contains(@text, "keyword")]</Text> - Partial text match
            <br />
            • <Text code>//*[@clickable="true" and @enabled="true"]</Text> - Multiple conditions
            <br />
            • <Text code>//node/child::*</Text> - Select children
          </Paragraph>
        </div>
      </Space>
    </Card>
  );
};

export default XPathPlayground;
