import React from 'react';
import { Card, List, Tag, Button, Typography, Progress } from 'antd';
import { LinkOutlined } from '@ant-design/icons';

const { Text } = Typography;

interface ProductionItem {
  type: string;
  title: string;
  subtitle: string;
  url: string;
  tags: string[];
  order_no?: string;
  process_type?: string;
  status?: string;
  plan_date?: string;
  qty?: number;
  completion_rate?: number;
}

interface ProductionListCardProps {
  title: string;
  items: ProductionItem[];
  total: number;
}

const ProductionListCard: React.FC<ProductionListCardProps> = ({ title, items, total }) => {
  const getStatusColor = (tag: string) => {
    if (!tag) return 'default';
    const lower = tag.toLowerCase();
    if (lower === '前道') return 'blue';
    if (lower === '贴片' || lower === 'smt') return 'purple';
    if (lower === '精益') return 'cyan';
    if (lower === '组装') return 'orange';
    if (lower === '包装') return 'green';
    if (lower === 'open') return 'processing';
    if (lower === 'in_progress') return 'processing';
    if (lower === 'completed') return 'success';
    if (lower === 'delayed') return 'error';
    return 'default';
  };

  const getProcessTypeLabel = (processType: string) => {
    const processMap: Record<string, string> = {
      front_process: '前道',
      smt: '贴片',
      lean: '精益',
      assembly: '组装',
      packaging: '包装',
    };
    return processMap[processType] || processType;
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
                  {item.plan_date && (
                    <Text type="secondary" style={{ marginLeft: 16 }}>
                      计划日期: {item.plan_date}
                    </Text>
                  )}
                  {item.qty && (
                    <Text type="secondary" style={{ marginLeft: 16 }}>
                      数量: {item.qty}
                    </Text>
                  )}
                  {item.completion_rate && (
                    <div style={{ marginTop: 4 }}>
                      <Text type="secondary">完成率: </Text>
                      <Progress
                        percent={item.completion_rate}
                        size="small"
                        style={{ width: 100, display: 'inline-block', marginLeft: 8 }}
                      />
                    </div>
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

export default ProductionListCard;
