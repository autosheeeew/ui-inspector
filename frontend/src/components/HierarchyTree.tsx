/**
 * Hierarchy Tree Component
 */
import React, { useState, useImperativeHandle, forwardRef, useMemo, useRef } from 'react';
import { Card, Tree, Typography, Space, Tag, Empty, Tooltip, Button, message } from 'antd';
import { AppstoreOutlined, InfoCircleOutlined, DownloadOutlined } from '@ant-design/icons';
import type { DataNode } from 'antd/es/tree';
import type { HierarchyNode, BoundsComputed, SelectedElement } from '../types';

const { Text } = Typography;

interface HierarchyTreeProps {
  hierarchy: HierarchyNode | null;
  deviceSerial?: string | null;
  onNodeHover?: (bounds: BoundsComputed | null) => void;
  onNodeSelect?: (bounds: BoundsComputed | null) => void;
  onElementSelect?: (element: SelectedElement) => void;
}

interface ExtendedDataNode extends DataNode {
  data?: BoundsComputed;
  nodeData?: HierarchyNode;
}

export interface HierarchyTreeRef {
  expandAndSelectNode: (nodePath: number[]) => void;
  collapseAll: () => void;
}

const HierarchyTree = forwardRef<HierarchyTreeRef, HierarchyTreeProps>(({
  hierarchy,
  deviceSerial,
  onNodeHover,
  onNodeSelect,
  onElementSelect,
}, ref) => {
  const [expandedKeys, setExpandedKeys] = useState<React.Key[]>([]);
  const [selectedKeys, setSelectedKeys] = useState<React.Key[]>([]);
  const treeScrollRef = useRef<HTMLDivElement>(null);

  useImperativeHandle(ref, () => ({
    expandAndSelectNode: (nodePath: number[]) => {
      if (!hierarchy) return;

      const keysToExpand: React.Key[] = ['0'];
      let currentKey = '0';
      for (let i = 1; i < nodePath.length; i++) {
        currentKey = `${currentKey}-${nodePath[i]}`;
        keysToExpand.push(currentKey);
      }

      const targetKey = nodePath.length === 1 ? '0' : `0-${nodePath.slice(1).join('-')}`;

      setExpandedKeys(keysToExpand);
      setSelectedKeys([targetKey]);

      setTimeout(() => {
        const treeData = hierarchy ? [convertToTreeData(hierarchy, '', 0)] : [];
        if (treeData.length > 0) {
          const targetNode = findNodeByKey(treeData[0], targetKey);
          if (targetNode) {
            const bounds = targetNode.data as BoundsComputed;
            const nodeData = targetNode.nodeData as HierarchyNode;

            if (onNodeSelect && bounds) onNodeSelect(bounds);

            if (onElementSelect && nodeData) {
              onElementSelect({
                tag: nodeData.tag || 'Unknown',
                attributes: nodeData.attributes || {},
                selectors: nodeData.selectors || {},
                node_path: nodeData.node_path || [],
              });
            }

            setTimeout(() => {
              const container = treeScrollRef.current;
              const selectedNode = container?.querySelector('.ant-tree-node-selected');
              if (container && selectedNode) {
                const containerRect = container.getBoundingClientRect();
                const nodeRect = selectedNode.getBoundingClientRect();
                const nodeOffsetTop = nodeRect.top - containerRect.top + container.scrollTop;
                container.scrollTo({
                  top: nodeOffsetTop - containerRect.height / 2 + nodeRect.height / 2,
                  behavior: 'smooth',
                });
              }
            }, 200);
          }
        }
      }, 100);
    },
    collapseAll: () => {
      setExpandedKeys([]);
      setSelectedKeys([]);
    },
  }));

  const findNodeByKey = (node: ExtendedDataNode, key: string): ExtendedDataNode | null => {
    if (node.key === key) return node;
    if (node.children) {
      for (const child of node.children as ExtendedDataNode[]) {
        const found = findNodeByKey(child, key);
        if (found) return found;
      }
    }
    return null;
  };

  const convertToTreeData = (
    node: HierarchyNode,
    parentKey: string = '',
    childIndex: number = 0
  ): ExtendedDataNode => {
    const key = parentKey === '' ? '0' : `${parentKey}-${childIndex}`;
    const attrs = node.attributes || {};

    const className = node.tag || attrs.class || 'Unknown';
    const isIOS = className.startsWith('XCUIElementType');

    let displayName = className;
    if (!isIOS && (className === 'node' || className === 'Unknown')) {
      if (attrs['resource-id']) {
        displayName = attrs['resource-id'].split('/').pop() || className;
      } else if (attrs['content-desc']) {
        displayName = attrs['content-desc'];
      } else if (attrs.text) {
        displayName = attrs.text.length > 20 ? attrs.text.substring(0, 20) + '...' : attrs.text;
      } else if (attrs.clickable === 'true') {
        displayName = 'Clickable';
      } else if (attrs.scrollable === 'true') {
        displayName = 'Scrollable';
      }
    }

    const trunc = (s: string, max = 30) => s.length > max ? s.substring(0, max) + '…' : s;

    const iosName  = isIOS ? (attrs.name  || '') : '';
    const iosLabel = isIOS ? (attrs.label || '') : '';
    const iosValue = isIOS ? (attrs.value || '') : '';

    const monoBase: React.CSSProperties = { fontFamily: 'monospace', fontSize: '12px' };
    const tagColor   = className === 'node' ? '#ff4d4f' : isIOS ? '#722ed1' : '#1890ff';
    const punctColor = '#8c8c8c';
    const keyColor   = '#d46b08';
    const valColor   = '#389e0d';

    const xmlAttr = (attrKey: string, val: string) => (
      <span key={attrKey}>
        <span style={{ ...monoBase, color: keyColor, fontStyle: 'italic' }}>{' '}{attrKey}</span>
        <span style={{ ...monoBase, color: punctColor }}>{'='}</span>
        <span style={{ ...monoBase, color: valColor }}>"{trunc(val)}"</span>
      </span>
    );

    const androidText        = !isIOS && attrs.text ? attrs.text : '';
    const androidResourceId  = !isIOS && attrs['resource-id'] ? attrs['resource-id'].split('/').pop() || '' : '';
    const androidContentDesc = !isIOS && attrs['content-desc'] ? attrs['content-desc'] : '';

    const title = (
      <span style={{ whiteSpace: 'nowrap', ...monoBase }}>
        <span style={{ color: punctColor }}>&lt;</span>
        <span style={{ color: tagColor, fontWeight: 600 }}>{displayName}</span>

        {isIOS && iosValue && xmlAttr('value', iosValue)}
        {isIOS && iosName  && xmlAttr('name',  iosName)}
        {isIOS && iosLabel && iosLabel !== iosName && xmlAttr('label', iosLabel)}

        {!isIOS && androidText && displayName !== attrs.text && xmlAttr('text', androidText)}
        {!isIOS && androidResourceId && !displayName.includes(androidResourceId) && xmlAttr('resource-id', androidResourceId)}
        {!isIOS && androidContentDesc && displayName !== attrs['content-desc'] && xmlAttr('content-desc', androidContentDesc)}

        <span style={{ color: punctColor }}>&gt;</span>

        {attrs.clickable === 'true' && (
          <Tag color="red" style={{ fontSize: '10px', margin: '0 0 0 4px' }}>clickable</Tag>
        )}
        {attrs.scrollable === 'true' && (
          <Tag color="blue" style={{ fontSize: '10px', margin: '0 0 0 4px' }}>scrollable</Tag>
        )}
      </span>
    );

    const children = (node.children || []).map((child, index) =>
      convertToTreeData(child, key, index)
    );

    return {
      key,
      title,
      children: children.length > 0 ? children : undefined,
      data: attrs.bounds_computed,
      nodeData: node,
    };
  };

  const treeData = useMemo(
    () => (hierarchy ? [convertToTreeData(hierarchy, '', 0)] : []),
    [hierarchy] // eslint-disable-line react-hooks/exhaustive-deps
  );

  const handleMouseEnter = (info: any) => {
    const bounds = info.node.data as BoundsComputed;
    if (bounds && onNodeHover) onNodeHover(bounds);
  };

  const handleMouseLeave = () => {
    if (onNodeHover) onNodeHover(null);
  };

  const handleSelect = (selectedKeys: React.Key[], info: any) => {
    setSelectedKeys(selectedKeys);

    if (selectedKeys.length > 0) {
      const node = info.node as ExtendedDataNode;
      if (onNodeSelect) onNodeSelect(node.data as BoundsComputed);
      if (onElementSelect && node.nodeData) {
        onElementSelect({
          tag: node.nodeData.tag || 'Unknown',
          attributes: node.nodeData.attributes || {},
          selectors: node.nodeData.selectors || {},
          node_path: node.nodeData.node_path || [],
        });
      }
    } else {
      if (onNodeSelect) onNodeSelect(null);
    }
  };

  const handleExpand = (expandedKeys: React.Key[]) => {
    setExpandedKeys(expandedKeys);
  };

  const downloadXml = async () => {
    if (!deviceSerial) {
      message.warning('No device selected');
      return;
    }
    try {
      const resp = await fetch(`/api/dump/${encodeURIComponent(deviceSerial)}/xml`);
      if (!resp.ok) {
        const err = await resp.json().catch(() => ({ detail: resp.statusText }));
        message.error(`Download failed: ${err.detail || resp.statusText}`);
        return;
      }
      const blob = await resp.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `hierarchy-${deviceSerial}.xml`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      message.error(`Download failed: ${String(e)}`);
    }
  };

  const expandAll = () => {
    const getAllKeys = (nodes: ExtendedDataNode[]): React.Key[] => {
      let keys: React.Key[] = [];
      nodes.forEach((node) => {
        keys.push(node.key);
        if (node.children) keys = keys.concat(getAllKeys(node.children as ExtendedDataNode[]));
      });
      return keys;
    };
    setExpandedKeys(getAllKeys(treeData));
  };

  const collapseAll = () => setExpandedKeys([]);

  return (
    <Card
      title={<Space><AppstoreOutlined /> UI Hierarchy</Space>}
      extra={
        <Space size={4}>
          <Tooltip title="Expand All">
            <Button type="text" size="small" onClick={expandAll}>Expand</Button>
          </Tooltip>
          <Tooltip title="Collapse All">
            <Button type="text" size="small" onClick={collapseAll}>Collapse</Button>
          </Tooltip>
          <Tooltip title="Download XML">
            <Button
              type="text"
              size="small"
              icon={<DownloadOutlined />}
              onClick={downloadXml}
              disabled={!hierarchy || !deviceSerial}
            />
          </Tooltip>
          <Tooltip title="Click nodes to view details, hover to highlight">
            <InfoCircleOutlined style={{ color: '#1890ff' }} />
          </Tooltip>
        </Space>
      }
      style={{ height: '100%', display: 'flex', flexDirection: 'column' }}
      bodyStyle={{
        flex: 1,
        minHeight: 0,
        padding: '10px',
        display: 'flex',
        flexDirection: 'column',
        overflow: 'hidden',
      }}
    >
      {!hierarchy ? (
        <Empty
          description="No hierarchy data. Select a device to auto-load."
          image={Empty.PRESENTED_IMAGE_SIMPLE}
          style={{ marginTop: 40 }}
        />
      ) : (
        <div
          ref={treeScrollRef}
          style={{ flex: 1, minHeight: 0, overflowY: 'auto', overflowX: 'auto' }}
        >
          <Tree
            showLine
            style={{ minWidth: 'max-content' }}
            treeData={treeData}
            expandedKeys={expandedKeys}
            selectedKeys={selectedKeys}
            onExpand={handleExpand}
            onSelect={handleSelect}
            titleRender={(node: any) => (
              <div
                onMouseEnter={() => handleMouseEnter({ node })}
                onMouseLeave={handleMouseLeave}
                style={{ padding: '2px 0', cursor: 'pointer', whiteSpace: 'nowrap' }}
              >
                {node.title}
              </div>
            )}
          />
        </div>
      )}
    </Card>
  );
});

HierarchyTree.displayName = 'HierarchyTree';

export default HierarchyTree;
