import React from 'react';
import { Card, List, Tag, Button, Typography } from 'antd';
import { LinkOutlined } from '@ant-design/icons';

const { Text } = Typography;

interface MaterialItem {
  type: string;
  title: string;
  subtitle: string;
  url: string;
  tags: string[];
  material_code?: string;
  material_name?: string;
  order_no?: string;
  shortage_qty?: number;
  shortage_flag?: boolean;
  req_qty?: number;
  status?: string;
  supplier_name?: string;
}

interface MaterialListCardProps {
  title: string;
  items: MaterialItem[];
  total: number;
}

const MaterialListCard: React.FC<MaterialListCardProps> = ({ title, items, total }) => {
  const getStatusColor = (tag: string) => {
    if (!tag) return 'default';
    const lower = tag.toLowerCase();
    if (lower === 'active') return 'processing';
    if (lower === 'inactive') return 'default';
    if (lower === '欠料') return 'red';
    if (lower === 'open') return 'processing';
    if (lower === 'closed') return 'success';
    return 'default';
  };

  return (
    <Card title={`${title}（共${total}条）`} size="small" style={{ marginBottom: 16 }}>
      <List
        size="small"
        dataSource={items}
        renderItem={(item) => (
          <List.Item
            actions={[
              <Button
                type="link"
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
                <div>
                  <Text strong>{item.title}</Text>
                  {item.tags.map((tag: string) => (
                    <Tag key={tag} color={getStatusColor(tag)} style={{ marginLeft: 8 }}>
                      {tag}
                    </Tag>
                  ))}
                </div>
              }
              description={
                <div>
                  <Text type="secondary">{item.subtitle}</Text>
                  {item.order_no && (
                    <Text type="secondary" style={{ marginLeft: 16 }}>
                      订单: {item.order_no}
                    </Text>
                  )}
                  {item.shortage_flag && item.shortage_qty && (
                    <Text type="danger" style={{ marginLeft: 16 }}>
                      欠料: {item.shortage_qty}
                    </Text>
                  )}
                  {item.req_qty && !item.shortage_flag && (
                    <Text type="secondary" style={{ marginLeft: 16 }}>
                      需求: {item.req_qty}
                    </Text>
                  )}
                  {item.status && (
                    <Text type="secondary" style={{ marginLeft: 16 }}>
                      状态: {item.status}
                    </Text>
                  )}
                </div>
              }
            />
          </List.Item>
        )}
      />
    </Card>
  );
};

export default MaterialListCard;
