/**
 * Application Entry Point
 * Android UI Inspector Platform
 */
import React from 'react';
import ReactDOM from 'react-dom/client';
import { ConfigProvider, theme } from 'antd';
import App from './App';
import './index.css';

// Ant Design locale (optional, for internationalization)
// import zhCN from 'antd/locale/zh_CN';
// import enUS from 'antd/locale/en_US';

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <ConfigProvider
      theme={{
        token: {
          // Primary color
          colorPrimary: '#1890ff',
          
          // Border radius
          borderRadius: 6,
          
          // Font
          fontSize: 14,
          fontFamily: `-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial,
            'Noto Sans', sans-serif, 'Apple Color Emoji', 'Segoe UI Emoji', 'Segoe UI Symbol',
            'Noto Color Emoji'`,
          
          // Colors
          colorSuccess: '#52c41a',
          colorWarning: '#faad14',
          colorError: '#ff4d4f',
          colorInfo: '#1890ff',
          
          // Layout
          colorBgLayout: '#f0f2f5',
          colorBgContainer: '#ffffff',
          
          // Text
          colorText: 'rgba(0, 0, 0, 0.88)',
          colorTextSecondary: 'rgba(0, 0, 0, 0.65)',
          colorTextTertiary: 'rgba(0, 0, 0, 0.45)',
          
          // Border
          colorBorder: '#d9d9d9',
          colorBorderSecondary: '#f0f0f0',
          
          // Shadow
          boxShadow: '0 1px 2px 0 rgba(0, 0, 0, 0.03), 0 1px 6px -1px rgba(0, 0, 0, 0.02), 0 2px 4px 0 rgba(0, 0, 0, 0.02)',
        },
        algorithm: theme.defaultAlgorithm, // or theme.darkAlgorithm for dark mode
        components: {
          // Button customization
          Button: {
            controlHeight: 32,
            controlHeightLG: 40,
            controlHeightSM: 24,
          },
          // Card customization
          Card: {
            borderRadiusLG: 8,
            boxShadowTertiary: '0 1px 2px 0 rgba(0, 0, 0, 0.03), 0 1px 6px -1px rgba(0, 0, 0, 0.02)',
          },
          // Tree customization
          Tree: {
            titleHeight: 28,
            nodeSelectedBg: '#e6f7ff',
            nodeHoverBg: '#f5f5f5',
          },
          // Input customization
          Input: {
            controlHeight: 32,
            controlHeightLG: 40,
          },
          // Select customization
          Select: {
            controlHeight: 32,
            controlHeightLG: 40,
          },
          // Message customization
          Message: {
            contentBg: '#ffffff',
            contentPadding: '10px 16px',
          },
          // Layout customization
          Layout: {
            headerBg: '#001529',
            headerHeight: 64,
            headerPadding: '0 24px',
            footerBg: '#ffffff',
            footerPadding: '24px 50px',
            bodyBg: '#f0f2f5',
          },
        },
      }}
      // Uncomment for Chinese locale
      // locale={zhCN}
    >
      <App />
    </ConfigProvider>
  </React.StrictMode>
);
