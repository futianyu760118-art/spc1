import React from 'react';
import { Card, List, Tag, Button, Typography } from 'antd';
import { LinkOutlined } from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { scalePx } from '../../utils/fontSize'

const { Text } = Typography;

interface SearchResultItem {
  type: string;
  title: string;
  subtitle: string;
  url: string;
  tags: string[];
  [key: string]: any;
}

interface SearchResultListCardProps {
  title: string;
  items: SearchResultItem[];
  total: number;
}

const SearchResultListCard: React.FC<SearchResultListCardProps> = ({ title, items, total }) => {
  const navigate = useNavigate();

  const getStatusColor = (tag: string) => {
    if (!tag) return 'default';
    const lower = tag.toLowerCase();
    if (lower === 'red' || lower === '高风险') return 'red';
    if (lower === 'yellow' || lower === '中风险') return 'orange';
    if (lower === 'blue' || lower === '关注') return 'blue';
    if (lower === 'green' || lower === '正常') return 'green';
    if (lower === 'open') return 'processing';
    if (lower === 'closed') return 'success';
    return 'default';
  };

  const getTagText = (tag: string) => {
    const tagMap: Record<string, string> = {
      red: '高风险',
      yellow: '中风险',
      blue: '关注',
      green: '正常',
    };
    return tagMap[tag] || tag;
  };

  const handleItemClick = (item: SearchResultItem) => {
    if (item.url) {
      // 提取关键信息作为搜索参数
      const searchParams = new URLSearchParams();
      
      // 根据不同类型的数据，提取不同的关键字段
      if (item.title) {
        // 尝试从标题中提取订单号、物料编码等关键信息
        const orderMatch = item.title.match(/[A-Z]{2}\d{6}-\d{4}-\d{4}/); // 订单号格式
        const materialMatch = item.title.match(/\d{8}/); // 物料编码格式
        
        if (orderMatch) {
          searchParams.set('search', orderMatch[0]);
        } else if (materialMatch) {
          searchParams.set('search', materialMatch[0]);
        } else {
          // 如果没有匹配到特定格式，使用整个标题
          searchParams.set('search', item.title);
        }
      }
      
      // 构建完整的 URL
      const url = searchParams.toString() 
        ? `${item.url}?${searchParams.toString()}`
        : item.url;
      
      navigate(url);
    }
  };

  return (
    <Card 
      title={`${title}（共${total}条）`} 
      size="small" 
      style={{ marginBottom: 16 }}
      headStyle={{ fontSize: scalePx(14), fontWeight: 500 }}
    >
      <List
        size="small"
        dataSource={items}
        renderItem={(item) => (
          <List.Item
            style={{ 
              padding: '16px 12px', 
              borderBottom: '1px solid #f0f0f0',
              display: 'block'
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', width: '100%' }}>
              {/* 左侧内容区 */}
              <div style={{ flex: 1, minWidth: 0, paddingRight: 16 }}>
                {/* 标题行 */}
                <div style={{ marginBottom: 8 }}>
                  <Text strong style={{ fontSize: scalePx(14), color: '#262626', display: 'block', marginBottom: 6 }}>
                    {item.title}
                  </Text>
                  {item.tags && item.tags.length > 0 && (
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                      {item.tags.map((tag: string) => (
                        <Tag key={tag} color={getStatusColor(tag)} style={{ fontSize: scalePx(11), lineHeight: '18px', margin: 0 }}>
                          {getTagText(tag)}
                        </Tag>
                      ))}
                    </div>
                  )}
                </div>

                {/* 副标题 */}
                {item.subtitle && (
                  <div style={{ color: '#8c8c8c', fontSize: scalePx(13), marginBottom: 10, lineHeight: '1.6' }}>
                    {item.subtitle}
                  </div>
                )}

                {/* 详细信息 */}
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(180px, 1fr))', gap: '8px 16px', lineHeight: '1.8' }}>
                  {/* 订单相关字段 */}
                  {item.promised_date && (
                    <Text type="secondary" style={{ fontSize: scalePx(12), color: '#595959' }}>
                      交期: {item.promised_date}
                    </Text>
                  )}
                  {item.status && (
                    <Text type="secondary" style={{ fontSize: scalePx(12), color: '#595959' }}>
                      状态: {item.status}
                    </Text>
                  )}
                  {item.owner && (
                    <Text type="secondary" style={{ fontSize: scalePx(12), color: '#595959' }}>
                      负责人: {item.owner}
                    </Text>
                  )}
                  {/* 跑单管理字段 */}
                  {item.run_date && (
                    <Text type="secondary" style={{ fontSize: scalePx(12), color: '#595959' }}>
                      跑单日期: {item.run_date}
                    </Text>
                  )}
                  {item.run_days && (
                    <Text type="secondary" style={{ fontSize: scalePx(12), color: '#595959' }}>
                      跑单天数: {item.run_days}天
                    </Text>
                  )}
                  {item.procurement_cycle && (
                    <Text type="secondary" style={{ fontSize: scalePx(12), color: '#595959' }}>
                      采购周期: {item.procurement_cycle}天
                    </Text>
                  )}
                  {/* 发票字段 */}
                  {item.invoice_date && (
                    <Text type="secondary" style={{ fontSize: scalePx(12), color: '#595959' }}>
                      开票日期: {item.invoice_date}
                    </Text>
                  )}
                  {item.invoice_amount && (
                    <Text type="secondary" style={{ fontSize: scalePx(12), color: '#595959' }}>
                      开票金额: ¥{item.invoice_amount}
                    </Text>
                  )}
                  {item.remain_payable !== undefined && item.remain_payable !== null && (
                    <Text type="secondary" style={{ fontSize: scalePx(12), color: '#595959' }}>
                      剩余应付: ¥{item.remain_payable}
                    </Text>
                  )}
                  {/* ETA变更字段 */}
                  {item.old_eta && (
                    <Text type="secondary" style={{ fontSize: scalePx(12), color: '#595959' }}>
                      旧交期: {item.old_eta}
                    </Text>
                  )}
                  {item.new_eta && (
                    <Text type="secondary" style={{ fontSize: scalePx(12), color: '#595959' }}>
                      新交期: {item.new_eta}
                    </Text>
                  )}
                  {item.updater && (
                    <Text type="secondary" style={{ fontSize: scalePx(12), color: '#595959' }}>
                      更新人: {item.updater}
                    </Text>
                  )}
                  {/* 用户字段 */}
                  {item.username && (
                    <Text type="secondary" style={{ fontSize: scalePx(12), color: '#595959' }}>
                      用户名: {item.username}
                    </Text>
                  )}
                  {item.emp_code && (
                    <Text type="secondary" style={{ fontSize: scalePx(12), color: '#595959' }}>
                      工号: {item.emp_code}
                    </Text>
                  )}
                  {item.role_name && (
                    <Text type="secondary" style={{ fontSize: scalePx(12), color: '#595959' }}>
                      角色: {item.role_name}
                    </Text>
                  )}
                  {item.last_login_time && (
                    <Text type="secondary" style={{ fontSize: scalePx(12), color: '#595959' }}>
                      最后登录: {item.last_login_time}
                    </Text>
                  )}
                </div>
              </div>

              {/* 右侧操作按钮 */}
              <div style={{ flexShrink: 0 }}>
                <Button
                  type="link"
                  size="small"
                  icon={<LinkOutlined />}
                  onClick={() => handleItemClick(item)}
                >
                  查看
                </Button>
              </div>
            </div>
          </List.Item>
        )}
      />
    </Card>
  );
};

export default SearchResultListCard;
