import React from 'react';
import { Card, List, Tag, Button, Typography } from 'antd';
import { LinkOutlined } from '@ant-design/icons';

const { Text } = Typography;

interface BasicDataItem {
  type: string;
  title: string;
  subtitle: string;
  url: string;
  tags: string[];
  customer_code?: string;
  customer_name?: string;
  customer_level?: string;
  supplier_code?: string;
  supplier_name?: string;
  supplier_type?: string;
  contact_person?: string;
  material_code?: string;
  material_name?: string;
}

interface BasicDataCardProps {
  title: string;
  items: BasicDataItem[];
  total: number;
}

const BasicDataCard: React.FC<BasicDataCardProps> = ({ title, items, total }) => {
  const getStatusColor = (tag: string) => {
    if (!tag) return 'default';
    const lower = tag.toLowerCase();
    if (lower === 'a' || lower === 'a类') return 'red';
    if (lower === 'b' || lower === 'b类') return 'orange';
    if (lower === 'c' || lower === 'c类') return 'blue';
    if (lower === 'direct' || lower === '直接') return 'green';
    if (lower === 'indirect' || lower === '间接') return 'blue';
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
                  {item.customer_code && (
                    <Text type="secondary" style={{ marginLeft: 16 }}>
                      客户编码: {item.customer_code}
                    </Text>
                  )}
                  {item.customer_level && (
                    <Text type="secondary" style={{ marginLeft: 16 }}>
                      客户等级: {item.customer_level}
                    </Text>
                  )}
                  {item.supplier_code && (
                    <Text type="secondary" style={{ marginLeft: 16 }}>
                      供应商编码: {item.supplier_code}
                    </Text>
                  )}
                  {item.supplier_type && (
                    <Text type="secondary" style={{ marginLeft: 16 }}>
                      供应商类型: {item.supplier_type}
                    </Text>
                  )}
                  {item.contact_person && (
                    <Text type="secondary" style={{ marginLeft: 16 }}>
                      联系人: {item.contact_person}
                    </Text>
                  )}
                  {item.material_code && (
                    <Text type="secondary" style={{ marginLeft: 16 }}>
                      物料编码: {item.material_code}
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

export default BasicDataCard;
