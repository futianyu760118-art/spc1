import React from 'react';
import { Card, List, Tag, Button, Typography } from 'antd';
import { LinkOutlined, ExclamationCircleOutlined } from '@ant-design/icons';

const { Text } = Typography;

interface ExceptionItem {
  type: string;
  title: string;
  subtitle: string;
  url: string;
  tags: string[];
  issue_no?: string;
  order_no?: string;
  risk_level?: string;
  status?: string;
  severity?: string;
  defect_type?: string;
  recorder?: string;
  record_date?: string;
  modifier?: string;
  change_date?: string;
}

interface ExceptionListCardProps {
  title: string;
  items: ExceptionItem[];
  total: number;
}

const ExceptionListCard: React.FC<ExceptionListCardProps> = ({ title, items, total }) => {
  const getStatusColor = (tag: string) => {
    if (!tag) return 'default';
    const lower = tag.toLowerCase();
    if (lower === 'red' || lower === '高风险') return 'red';
    if (lower === 'yellow' || lower === '中风险') return 'orange';
    if (lower === 'blue' || lower === '关注') return 'blue';
    if (lower === 'green' || lower === '正常') return 'green';
    if (lower === 'high' || lower === '严重') return 'red';
    if (lower === 'medium' || lower === '中等') return 'orange';
    if (lower === 'low' || lower === '轻微') return 'blue';
    if (lower === 'open') return 'processing';
    if (lower === 'closed') return 'success';
    if (lower === 'resolved') return 'success';
    return 'default';
  };

  const getSeverityIcon = (severity: string) => {
    const lower = severity?.toLowerCase();
    if (lower === 'high' || lower === '严重') return <ExclamationCircleOutlined style={{ color: '#ff4d4f' }} />;
    if (lower === 'medium' || lower === '中等') return <ExclamationCircleOutlined style={{ color: '#faad14' }} />;
    if (lower === 'low' || lower === '轻微') return <ExclamationCircleOutlined style={{ color: '#1890ff' }} />;
    return null;
  };

  return (
    <Card 
      title={`${title}（共${total}条）`} 
      size="small" 
      style={{ marginBottom: 16 }}
      headStyle={{ fontSize: 14, fontWeight: 500 }}
    >
      <List
        size="small"
        dataSource={items}
        renderItem={(item) => (
          <List.Item
            style={{ padding: '12px 0', borderBottom: '1px solid #f0f0f0' }}
            actions={[
              <Button
                type="link"
                size="small"
                icon={<LinkOutlined />}
                onClick={() => {
                  if (item.url) {
                    window.location.href = item.url;
                  }
                }}
              >
                查看
              </Button>,
            ]}
          >
            <List.Item.Meta
              title={
                <div style={{ display: 'flex', alignItems: 'center', flexWrap: 'wrap', gap: 8 }}>
                  <Text strong style={{ fontSize: 13, color: '#262626' }}>{item.title}</Text>
                  {getSeverityIcon(item.severity || '')}
                  {item.tags.map((tag: string) => (
                    <Tag key={tag} color={getStatusColor(tag)} style={{ fontSize: 11, lineHeight: '16px' }}>
                      {tag}
                    </Tag>
                  ))}
                </div>
              }
              description={
                <div style={{ marginTop: 4 }}>
                  <div style={{ color: '#8c8c8c', fontSize: 12, marginBottom: 4, lineHeight: '1.4' }}>
                    {item.subtitle}
                  </div>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px 16px' }}>
                    {item.order_no && (
                      <Text type="secondary" style={{ fontSize: 12, color: '#595959' }}>
                        订单: {item.order_no}
                      </Text>
                    )}
                    {item.defect_type && (
                      <Text type="secondary" style={{ fontSize: 12, color: '#595959' }}>
                        缺陷类型: {item.defect_type}
                      </Text>
                    )}
                    {item.recorder && (
                      <Text type="secondary" style={{ fontSize: 12, color: '#595959' }}>
                        记录人: {item.recorder}
                      </Text>
                    )}
                    {item.record_date && (
                      <Text type="secondary" style={{ fontSize: 12, color: '#595959' }}>
                        记录日期: {item.record_date}
                      </Text>
                    )}
                    {item.modifier && (
                      <Text type="secondary" style={{ fontSize: 12, color: '#595959' }}>
                        修改人: {item.modifier}
                      </Text>
                    )}
                    {item.change_date && (
                      <Text type="secondary" style={{ fontSize: 12, color: '#595959' }}>
                        修改日期: {item.change_date}
                      </Text>
                    )}
                  </div>
                </div>
              }
            />
          </List.Item>
        )}
      />
    </Card>
  );
};

export default ExceptionListCard;
