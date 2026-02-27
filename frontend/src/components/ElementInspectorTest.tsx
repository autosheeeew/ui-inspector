/**
 * Test page for ElementInspector component
 */
import React, { useState } from 'react';
import { Space, Button, Card } from 'antd';
import ElementInspector from './ElementInspector';

const ElementInspectorTest: React.FC = () => {
  const [selectedElement, setSelectedElement] = useState<any>(null);

  // Sample Android element
  const androidElement = {
    tag: 'android.widget.TextView',
    attributes: {
      text: 'Hello World',
      'resource-id': 'com.example.app:id/title',
      'content-desc': 'Title text',
      clickable: 'true',
      enabled: 'true',
      bounds: '[20,50][500,150]',
      bounds_computed: {
        x: 20,
        y: 50,
        w: 480,
        h: 100
      }
    },
    selectors: {
      id: 'com.example.app:id/title',
      accessibility_id: 'Title text',
      class_name: 'android.widget.TextView',
      xpath_absolute: '//android.widget.FrameLayout[1]/android.widget.LinearLayout[1]/android.widget.TextView[1]',
      xpath_relative: [
        "//*[@resource-id='com.example.app:id/title']",
        "//*[@content-desc='Title text']",
        "//*[@text='Hello World']"
      ],
      uiautomator: [
        'new UiSelector().resourceId("com.example.app:id/title")',
        'new UiSelector().text("Hello World")',
        'new UiSelector().description("Title text")'
      ]
    },
    node_path: [0, 0, 0, 0]
  };

  // Sample iOS element
  const iosElement = {
    tag: 'XCUIElementTypeButton',
    attributes: {
      name: 'Login',
      label: 'Login Button',
      value: '1',
      enabled: 'true',
      visible: 'true',
      bounds_computed: {
        x: 100,
        y: 200,
        w: 200,
        h: 44
      }
    },
    selectors: {
      id: 'Login',
      accessibility_id: 'Login Button',
      class_name: 'XCUIElementTypeButton',
      xpath_absolute: '//XCUIElementTypeWindow[1]/XCUIElementTypeButton[1]',
      xpath_relative: [
        "//*[@name='Login']",
        "//*[@label='Login Button']"
      ],
      predicate: [
        "name == 'Login'",
        "label == 'Login Button'",
        "type == 'XCUIElementTypeButton'"
      ],
      class_chain: [
        "**/XCUIElementTypeButton[`name == 'Login'`]",
        "**/XCUIElementTypeButton[`label == 'Login Button'`]"
      ]
    },
    node_path: [0, 0, 0]
  };

  return (
    <div style={{ padding: 24 }}>
      <Space direction="vertical" size="large" style={{ width: '100%' }}>
        <Card title="ElementInspector Test">
          <Space>
            <Button onClick={() => setSelectedElement(androidElement)}>
              Load Android Element
            </Button>
            <Button onClick={() => setSelectedElement(iosElement)}>
              Load iOS Element
            </Button>
            <Button onClick={() => setSelectedElement(null)}>
              Clear Selection
            </Button>
          </Space>
        </Card>

        <div style={{ height: '600px' }}>
          <ElementInspector
            element={selectedElement}
            platform={selectedElement?.selectors?.uiautomator ? 'android' : 'ios'}
          />
        </div>
      </Space>
    </div>
  );
};

export default ElementInspectorTest;
