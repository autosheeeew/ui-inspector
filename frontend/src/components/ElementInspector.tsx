/**
 * ElementInspector Component
 * Displays selected element's selectors and attributes (like Appium Inspector)
 */
import React, { useState } from 'react';
import { Card, Table, Typography, Button, Space, message, Tabs, Input, Tag } from 'antd';
import { CopyOutlined, SearchOutlined, InfoCircleOutlined } from '@ant-design/icons';
import { Flex } from 'antd';
import type { ColumnsType } from 'antd/es/table';

const { Title, Text } = Typography;
const { TabPane } = Tabs;

interface ElementAttributes {
  [key: string]: any;
}

interface ElementSelectors {
  // Android
  id?: string | null;
  accessibility_id?: string | null;
  class_name?: string;
  uiautomator?: string[];
  // iOS
  name?: string | null;
  label?: string | null;
  value?: string | null;
  predicate?: string[];
  class_chain?: string[];
  // Common
  xpath_absolute?: string;
  xpath_relative?: string[];
}

interface SelectedElement {
  tag: string;
  attributes: ElementAttributes;
  selectors: ElementSelectors;
  node_path: number[];
}

interface ElementInspectorProps {
  element: SelectedElement | null;
  platform: 'android' | 'ios';
}

interface SelectorRow {
  key: string;
  strategy: string;
  selector: string;
}

interface AttributeRow {
  key: string;
  attribute: string;
  value: string;
}

const ElementInspector: React.FC<ElementInspectorProps> = ({ element, platform }) => {
  const [selectorSearch, setSelectorSearch] = useState('');
  const [attributeSearch, setAttributeSearch] = useState('');

  // Copy to clipboard
  const copyToClipboard = (text: string, label: string) => {
    navigator.clipboard.writeText(text).then(() => {
      message.success(`${label} copied to clipboard`);
    }).catch(() => {
      message.error('Failed to copy');
    });
  };

  if (!element) {
    return (
      <Card style={{ height: '100%' }}>
        <div style={{ 
          display: 'flex', 
          alignItems: 'center', 
          justifyContent: 'center', 
          height: '100%',
          color: '#999'
        }}>
          <Text type="secondary">Select an element to view details</Text>
        </div>
      </Card>
    );
  }

  // Prepare selector data
  const selectorData: SelectorRow[] = [];
  const selectors = element.selectors;

  if (platform === 'ios') {
    // ── iOS selectors ──────────────────────────────────────────────
    // name / label / value (native WDA attributes)
    if (selectors.name) {
      selectorData.push({ key: 'name', strategy: 'name', selector: selectors.name });
    }
    if (selectors.label) {
      selectorData.push({ key: 'label', strategy: 'label', selector: selectors.label });
    }
    if (selectors.value) {
      selectorData.push({ key: 'value', strategy: 'value', selector: selectors.value });
    }

    // XPath Absolute
    if (selectors.xpath_absolute) {
      selectorData.push({ key: 'xpath_absolute', strategy: 'xpath (absolute)', selector: selectors.xpath_absolute });
    }

    // XPath Relative
    selectors.xpath_relative?.forEach((xpath, index) => {
      selectorData.push({ key: `xpath_relative_${index}`, strategy: index === 0 ? 'xpath (relative)' : '', selector: xpath });
    });

    // Predicate String
    selectors.predicate?.forEach((pred, index) => {
      selectorData.push({ key: `predicate_${index}`, strategy: index === 0 ? '-ios predicate string' : '', selector: pred });
    });

    // Class Chain
    selectors.class_chain?.forEach((chain, index) => {
      selectorData.push({ key: `class_chain_${index}`, strategy: index === 0 ? '-ios class chain' : '', selector: chain });
    });

  } else {
    // ── Android selectors ──────────────────────────────────────────
    if (selectors.id) {
      selectorData.push({ key: 'id', strategy: 'id', selector: selectors.id });
    }
    if (selectors.accessibility_id) {
      selectorData.push({ key: 'accessibility_id', strategy: 'accessibility id', selector: selectors.accessibility_id });
    }
    if (selectors.class_name) {
      selectorData.push({ key: 'class_name', strategy: 'class name', selector: selectors.class_name });
    }

    // XPath Absolute
    if (selectors.xpath_absolute) {
      selectorData.push({ key: 'xpath_absolute', strategy: 'xpath (absolute)', selector: selectors.xpath_absolute });
    }

    // XPath Relative
    selectors.xpath_relative?.forEach((xpath, index) => {
      selectorData.push({ key: `xpath_relative_${index}`, strategy: index === 0 ? 'xpath (relative)' : '', selector: xpath });
    });

    // UiAutomator
    selectors.uiautomator?.forEach((sel, index) => {
      selectorData.push({ key: `uiautomator_${index}`, strategy: index === 0 ? '-android uiautomator' : '', selector: sel });
    });
  }

  // Filter selectors
  const filteredSelectors = selectorData.filter(row => 
    row.strategy.toLowerCase().includes(selectorSearch.toLowerCase()) ||
    row.selector.toLowerCase().includes(selectorSearch.toLowerCase())
  );

  // Selector columns
  const selectorColumns: ColumnsType<SelectorRow> = [
    {
      title: 'Find By',
      dataIndex: 'strategy',
      key: 'strategy',
      width: 200,
      render: (text) => text ? <Tag color="blue">{text}</Tag> : null
    },
    {
      title: 'Selector',
      dataIndex: 'selector',
      key: 'selector',
      ellipsis: true,
      render: (text) => (
        <Text 
          code 
          style={{ fontSize: '12px', wordBreak: 'break-all' }}
          copyable={false}
        >
          {text}
        </Text>
      )
    },
    {
      title: 'Action',
      key: 'action',
      width: 80,
      render: (_, record) => (
        <Button
          type="text"
          size="small"
          icon={<CopyOutlined />}
          onClick={() => copyToClipboard(record.selector, record.strategy || 'Selector')}
        />
      )
    }
  ];

  // Prepare attribute data
  const attributeData: AttributeRow[] = Object.entries(element.attributes)
    .filter(([key]) => key !== 'bounds_computed')  // Exclude computed bounds
    .map(([key, value]) => ({
      key,
      attribute: key,
      value: value?.toString() || ''
    }));

  // Filter attributes
  const filteredAttributes = attributeData.filter(row =>
    row.attribute.toLowerCase().includes(attributeSearch.toLowerCase()) ||
    row.value.toLowerCase().includes(attributeSearch.toLowerCase())
  );

  // Attribute columns
  const attributeColumns: ColumnsType<AttributeRow> = [
    {
      title: 'Attribute',
      dataIndex: 'attribute',
      key: 'attribute',
      width: 200,
      render: (text) => <Text strong>{text}</Text>
    },
    {
      title: 'Value',
      dataIndex: 'value',
      key: 'value',
      ellipsis: true,
      render: (text) => (
        <Text 
          style={{ fontSize: '12px', wordBreak: 'break-all' }}
          copyable={false}
        >
          {text || <Text type="secondary">(empty)</Text>}
        </Text>
      )
    },
    {
      title: 'Action',
      key: 'action',
      width: 80,
      render: (_, record) => (
        <Button
          type="text"
          size="small"
          icon={<CopyOutlined />}
          onClick={() => copyToClipboard(record.value, record.attribute)}
        />
      )
    }
  ];

  return (
    <Card 
      title={
        <Space>
          <InfoCircleOutlined />
          <span>Element Details</span>
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
      {/* Key Attributes - Quick View */}
      <Space direction="vertical" size={8} style={{ width: '100%', marginBottom: 12 }}>
        {/* Class/Tag */}
        <Flex justify="space-between" align="center" gap={8}>
          <Text strong style={{ minWidth: 60, fontSize: 12 }}>class:</Text>
          <Text 
            code 
            style={{ 
              flex: 1, 
              fontSize: 11, 
              wordBreak: 'break-all',
              padding: '2px 6px',
            }}
          >
            {element.tag}
          </Text>
          <Button
            type="text"
            size="small"
            icon={<CopyOutlined />}
            onClick={() => copyToClipboard(element.tag, 'Class')}
            style={{ padding: '0 4px' }}
          />
        </Flex>

          {/* ── iOS: name / label / value ── */}
        {platform === 'ios' && element.attributes.name && (
          <Flex justify="space-between" align="center" gap={8}>
            <Text strong style={{ minWidth: 60, fontSize: 12 }}>name:</Text>
            <Text
              code
              style={{ flex: 1, fontSize: 11, wordBreak: 'break-all', padding: '2px 6px' }}
            >
              {element.attributes.name}
            </Text>
            <Button
              type="text" size="small" icon={<CopyOutlined />}
              onClick={() => copyToClipboard(element.attributes.name, 'name')}
              style={{ padding: '0 4px' }}
            />
          </Flex>
        )}
        {platform === 'ios' && element.attributes.label && (
          <Flex justify="space-between" align="center" gap={8}>
            <Text strong style={{ minWidth: 60, fontSize: 12 }}>label:</Text>
            <Text
              code
              style={{ flex: 1, fontSize: 11, wordBreak: 'break-all', padding: '2px 6px' }}
            >
              {element.attributes.label}
            </Text>
            <Button
              type="text" size="small" icon={<CopyOutlined />}
              onClick={() => copyToClipboard(element.attributes.label, 'label')}
              style={{ padding: '0 4px' }}
            />
          </Flex>
        )}
        {platform === 'ios' && element.attributes.value && (
          <Flex justify="space-between" align="center" gap={8}>
            <Text strong style={{ minWidth: 60, fontSize: 12 }}>value:</Text>
            <Text
              code
              style={{ flex: 1, fontSize: 11, wordBreak: 'break-all', padding: '2px 6px' }}
            >
              {element.attributes.value}
            </Text>
            <Button
              type="text" size="small" icon={<CopyOutlined />}
              onClick={() => copyToClipboard(element.attributes.value, 'value')}
              style={{ padding: '0 4px' }}
            />
          </Flex>
        )}

        {/* ── Android: text / resource-id ── */}
        {platform !== 'ios' && element.attributes.text && (
          <Flex justify="space-between" align="center" gap={8}>
            <Text strong style={{ minWidth: 60, fontSize: 12 }}>text:</Text>
            <Text
              code
              style={{ flex: 1, fontSize: 11, wordBreak: 'break-all', padding: '2px 6px' }}
            >
              "{element.attributes.text}"
            </Text>
            <Button
              type="text"
              size="small"
              icon={<CopyOutlined />}
              onClick={() => copyToClipboard(element.attributes.text, 'Text')}
              style={{ padding: '0 4px' }}
            />
          </Flex>
        )}
        {platform !== 'ios' && element.attributes['resource-id'] && (
          <Flex justify="space-between" align="center" gap={8}>
            <Text strong style={{ minWidth: 60, fontSize: 12 }}>id:</Text>
            <Text
              code
              style={{ flex: 1, fontSize: 11, wordBreak: 'break-all', padding: '2px 6px' }}
            >
              {element.attributes['resource-id']}
            </Text>
            <Button
              type="text"
              size="small"
              icon={<CopyOutlined />}
              onClick={() => copyToClipboard(element.attributes['resource-id'], 'ID')}
              style={{ padding: '0 4px' }}
            />
          </Flex>
        )}

        {/* Bounds */}
        {element.attributes.bounds_computed && (
          <Flex justify="space-between" align="center" gap={8}>
            <Text strong style={{ minWidth: 60, fontSize: 12 }}>bounds:</Text>
            <Text 
              code 
              style={{ 
                flex: 1, 
                fontSize: 11,
                padding: '2px 6px',
              }}
            >
              [{element.attributes.bounds_computed.x},{element.attributes.bounds_computed.y}]
              [{element.attributes.bounds_computed.x + element.attributes.bounds_computed.w},{element.attributes.bounds_computed.y + element.attributes.bounds_computed.h}]
            </Text>
            <Button
              type="text"
              size="small"
              icon={<CopyOutlined />}
              onClick={() => {
                const b = element.attributes.bounds_computed;
                copyToClipboard(`[${b.x},${b.y}][${b.x+b.w},${b.y+b.h}]`, 'Bounds');
              }}
              style={{ padding: '0 4px' }}
            />
          </Flex>
        )}

        {/* Status flags */}
        <Flex justify="space-between" align="center" gap={8}>
          <Text strong style={{ minWidth: 60, fontSize: 12 }}>check:</Text>
          <Flex gap={4} style={{ flex: 1 }} wrap="wrap">
            {platform === 'ios' ? (
              <>
                {element.attributes.accessible === 'true' && (
                  <Tag color="green" style={{ fontSize: 10, margin: 0 }}>accessible</Tag>
                )}
                {element.attributes.enabled === 'true' && (
                  <Tag color="cyan" style={{ fontSize: 10, margin: 0 }}>enabled</Tag>
                )}
                {element.attributes.visible === 'true' && (
                  <Tag color="blue" style={{ fontSize: 10, margin: 0 }}>visible</Tag>
                )}
                {element.attributes.clickable === 'true' && (
                  <Tag color="red" style={{ fontSize: 10, margin: 0 }}>clickable</Tag>
                )}
                {!element.attributes.accessible && !element.attributes.enabled && !element.attributes.visible && (
                  <Text type="secondary" style={{ fontSize: 11 }}>-</Text>
                )}
              </>
            ) : (
              <>
                {element.attributes.clickable === 'true' && (
                  <Tag color="green" style={{ fontSize: 10, margin: 0 }}>clickable</Tag>
                )}
                {element.attributes.scrollable === 'true' && (
                  <Tag color="blue" style={{ fontSize: 10, margin: 0 }}>scrollable</Tag>
                )}
                {element.attributes.focusable === 'true' && (
                  <Tag color="orange" style={{ fontSize: 10, margin: 0 }}>focusable</Tag>
                )}
                {element.attributes.enabled === 'true' && (
                  <Tag color="cyan" style={{ fontSize: 10, margin: 0 }}>enabled</Tag>
                )}
                {!element.attributes.clickable && !element.attributes.scrollable && (
                  <Text type="secondary" style={{ fontSize: 11 }}>-</Text>
                )}
              </>
            )}
          </Flex>
          <Button
            type="text"
            size="small"
            icon={<CopyOutlined />}
            onClick={() => {
              const checks = platform === 'ios'
                ? [
                    element.attributes.accessible === 'true' ? 'accessible' : null,
                    element.attributes.enabled === 'true' ? 'enabled' : null,
                    element.attributes.visible === 'true' ? 'visible' : null,
                  ].filter(Boolean).join(', ')
                : [
                    element.attributes.clickable === 'true' ? 'clickable' : null,
                    element.attributes.scrollable === 'true' ? 'scrollable' : null,
                    element.attributes.focusable === 'true' ? 'focusable' : null,
                  ].filter(Boolean).join(', ');
              copyToClipboard(checks || 'none', 'Properties');
            }}
            style={{ padding: '0 4px' }}
          />
        </Flex>
      </Space>

      {/* Tabs for Selectors and Attributes */}
      <Tabs defaultActiveKey="selectors" size="small" style={{ marginTop: 12 }}>
        {/* Find By Tab */}
        <TabPane tab="Selectors" key="selectors">
          <Space direction="vertical" size="middle" style={{ width: '100%' }}>
            {/* Search */}
            <Input
              placeholder="Search selectors..."
              prefix={<SearchOutlined />}
              value={selectorSearch}
              onChange={(e) => setSelectorSearch(e.target.value)}
              allowClear
            />

            {/* Selectors Table */}
            <Table
              columns={selectorColumns}
              dataSource={filteredSelectors}
              pagination={false}
              size="small"
              scroll={{ y: 300 }}
              bordered
            />

            {/* Copy All Button */}
            <Button
              block
              icon={<CopyOutlined />}
              onClick={() => {
                const allSelectors = selectorData
                  .map(row => `${row.strategy}: ${row.selector}`)
                  .join('\n');
                copyToClipboard(allSelectors, 'All selectors');
              }}
            >
              Copy All Selectors
            </Button>
          </Space>
        </TabPane>

        {/* Attributes Tab */}
        <TabPane tab="Attributes" key="attributes">
          <Space direction="vertical" size="middle" style={{ width: '100%' }}>
            {/* Search */}
            <Input
              placeholder="Search attributes..."
              prefix={<SearchOutlined />}
              value={attributeSearch}
              onChange={(e) => setAttributeSearch(e.target.value)}
              allowClear
            />

            {/* Attributes Table */}
            <Table
              columns={attributeColumns}
              dataSource={filteredAttributes}
              pagination={false}
              size="small"
              scroll={{ y: 300 }}
              bordered
            />

            {/* Stats */}
            <Text type="secondary" style={{ fontSize: '12px' }}>
              Total: {attributeData.length} attributes
            </Text>
          </Space>
        </TabPane>

        {/* Info Tab */}
        <TabPane tab="Info" key="info">
          <Space direction="vertical" size="middle" style={{ width: '100%' }}>
            <div>
              <Text strong>Tag:</Text>
              <br />
              <Text code copyable>{element.tag}</Text>
            </div>

            <div>
              <Text strong>Node Path:</Text>
              <br />
              <Text code copyable={{ text: JSON.stringify(element.node_path) }}>
                {JSON.stringify(element.node_path)}
              </Text>
            </div>

            {element.attributes.bounds_computed && (
              <div>
                <Text strong>Bounds:</Text>
                <br />
                <Space direction="vertical" size="small">
                  <Text>x: {element.attributes.bounds_computed.x}</Text>
                  <Text>y: {element.attributes.bounds_computed.y}</Text>
                  <Text>width: {element.attributes.bounds_computed.w}</Text>
                  <Text>height: {element.attributes.bounds_computed.h}</Text>
                </Space>
              </div>
            )}

            <div>
              <Text strong>Platform:</Text>
              <br />
              <Tag color={platform === 'android' ? 'green' : 'blue'}>
                {platform.toUpperCase()}
              </Tag>
            </div>
          </Space>
        </TabPane>
      </Tabs>
    </Card>
  );
};

export default ElementInspector;
