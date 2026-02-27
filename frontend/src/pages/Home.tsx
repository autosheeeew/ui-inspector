/**
 * Home Page - Main Inspector Interface
 * Placeholder for now, will be updated in Step 4
 */
import React from 'react';
import { Typography, Card } from 'antd';

const { Title, Paragraph } = Typography;

const Home: React.FC = () => {
  return (
    <div style={{ padding: 24 }}>
      <Card>
        <Title level={2}>Android/iOS UI Inspector</Title>
        <Paragraph>
          Main inspector interface will be here.
        </Paragraph>
        <Paragraph>
          For now, please visit <a href="/test-inspector">/test-inspector</a> to test the ElementInspector component.
        </Paragraph>
      </Card>
    </div>
  );
};

export default Home;
