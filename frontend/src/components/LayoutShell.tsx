import { BranchesOutlined, DashboardOutlined, ExperimentOutlined, LogoutOutlined, RobotOutlined } from '@ant-design/icons';
import { Badge, Button, Layout, Menu, Space, Tag, Tooltip, Typography } from 'antd';
import type { ReactNode } from 'react';
import type { HealthStatus } from '../types';

const { Header, Sider, Content } = Layout;

export type PageKey = 'dashboard' | 'model1' | 'agent' | 'simulation';
export type ShellRole = 'admin' | 'designer';

interface Props {
  activePage: PageKey;
  onPageChange: (page: PageKey) => void;
  health: HealthStatus | null;
  role: ShellRole;
  userName: string;
  workspace: string;
  onLogout: () => void;
  children: ReactNode;
}

const items: Array<{ key: PageKey; icon: JSX.Element; label: string; roles: ShellRole[] }> = [
  { key: 'dashboard', icon: <DashboardOutlined />, label: '首页', roles: ['admin', 'designer'] },
  { key: 'model1', icon: <BranchesOutlined />, label: 'AI工作台', roles: ['admin', 'designer'] },
  { key: 'agent', icon: <RobotOutlined />, label: 'AI智能体', roles: ['admin', 'designer'] },
  { key: 'simulation', icon: <ExperimentOutlined />, label: '系统仿真', roles: ['admin', 'designer'] },
];

export function getAllowedPages(role: ShellRole) {
  return items.filter((item) => item.roles.includes(role)).map((item) => item.key);
}

export default function LayoutShell({ activePage, onPageChange, health, role, userName, workspace, onLogout, children }: Props) {
  const visibleItems = items.filter((item) => item.roles.includes(role));

  return (
    <Layout className="app-shell">
      <Sider className="app-sider" width={232} breakpoint="lg" collapsedWidth={0}>
        <div className="brand-block">
          <div className="brand-mark">AI</div>
          <div>
            <Typography.Text className="brand-title">AI-MBSE-Demo</Typography.Text>
            <Typography.Text className="brand-subtitle">系统设计</Typography.Text>
          </div>
        </div>
        <Menu
          mode="inline"
          selectedKeys={[activePage]}
          items={visibleItems}
          onClick={(item) => onPageChange(item.key as PageKey)}
          className="side-menu"
        />
      </Sider>
      <Layout>
        <Header className="app-header">
          <div>
            <Typography.Text className="header-title">AI 赋能 MBSE 系统设计平台</Typography.Text>
          </div>
          <Space size={10} wrap>
            <Tag color={role === 'admin' ? 'red' : 'blue'}>{userName}</Tag>
            <Tag color="cyan">{workspace}</Tag>
            <StatusTag label="LLM" mode={health?.llm.mode} />
            <StatusTag label="SysML" mode={health?.sysml.mode} />
            <Tag color={health?.magicdraw?.bridge_available ? 'green' : 'gold'}>
              MagicDraw: {health?.magicdraw?.bridge_available ? 'Bridge' : '未连接'}
            </Tag>
            <Tooltip title={health?.simulation.preferred_tool ? `优先工具：${health.simulation.preferred_tool}` : '仿真工具状态'}>
              <Tag color={health?.simulation.mode === 'real' ? 'green' : 'orange'}>
                Simulation: {health?.simulation.mode === 'real' ? 'Real' : 'Mock'}
              </Tag>
            </Tooltip>
            <Badge status={health?.database.available ? 'success' : 'error'} text="SQLite" />
            <Button size="small" icon={<LogoutOutlined />} onClick={onLogout}>
              退出
            </Button>
          </Space>
        </Header>
        <Content className="app-content">{children}</Content>
      </Layout>
    </Layout>
  );
}

function StatusTag({ label, mode }: { label: string; mode?: string }) {
  const normalized = mode === 'real' || mode === 'bridge' ? 'Real' : mode === 'exchange' ? 'Exchange' : 'Mock';
  const color = normalized === 'Real' ? 'green' : normalized === 'Exchange' ? 'gold' : 'blue';
  return <Tag color={color}>{`${label}: ${normalized}`}</Tag>;
}
