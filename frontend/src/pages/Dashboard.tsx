import {
  BranchesOutlined,
  ExperimentOutlined,
} from '@ant-design/icons';
import { Badge, Card, Descriptions, Tag, Typography } from 'antd';
import { useEffect, useState } from 'react';
import { client } from '../api/client';
import type { HealthStatus } from '../types';

const steps = [
  {
    title: 'AI工作台到MagicDraw',
    description: '通过AI对话生成完整SysML工程，推送MagicDraw，并在前端回显Bridge结果、工程包、元素和关系。',
    icon: <BranchesOutlined />,
  },
  {
    title: '系统仿真',
    description: '调用GMAT或Simulink输出真实仿真证据，用于后续工程分析。',
    icon: <ExperimentOutlined />,
  },
];

export default function Dashboard() {
  const [health, setHealth] = useState<HealthStatus | null>(null);

  useEffect(() => {
    client.health().then(setHealth).catch(() => setHealth(null));
  }, []);

  return (
    <div className="page-stack">
      <div className="page-heading">
        <div>
          <h1>AI 赋能 MBSE 系统设计平台</h1>
          <p>当前系统聚焦“AI工作台”主流程：AI对话生成SysML工程、推送MagicDraw Bridge、前端实时回显模型图和返回结果，并保留系统仿真能力。</p>
        </div>
        <Tag color="blue">AI-MBSE-Demo</Tag>
      </div>

      <div className="step-grid">
        {steps.map((step, index) => (
          <Card className="dashboard-step" key={step.title}>
            <Typography.Title level={5}>
              {step.icon} {index + 1}. {step.title}
            </Typography.Title>
            <Typography.Paragraph type="secondary">{step.description}</Typography.Paragraph>
          </Card>
        ))}
      </div>

      <div className="content-band">
        <Descriptions title="系统状态" bordered column={{ xs: 1, sm: 1, md: 2, lg: 2 }}>
          <Descriptions.Item label="LLM状态">
            <Badge status={health?.llm.mode === 'real' ? 'success' : 'processing'} text={modeText(health?.llm.mode)} />
          </Descriptions.Item>
          <Descriptions.Item label="SysML API状态">
            <Badge status={health?.sysml.mode === 'real' ? 'success' : 'processing'} text={modeText(health?.sysml.mode)} />
          </Descriptions.Item>
          <Descriptions.Item label="MagicDraw状态">
            <Badge
              status={health?.magicdraw?.bridge_available ? 'success' : 'warning'}
              text={health?.magicdraw?.bridge_available ? 'Bridge已连接' : 'Bridge未连接'}
            />
          </Descriptions.Item>
          <Descriptions.Item label="仿真工具状态">
            <Badge
              status={health?.simulation.mode === 'real' ? 'success' : 'warning'}
              text={health?.simulation.mode === 'real' ? `真实工具可用：${health?.simulation.preferred_tool}` : '未安装，当前为Mock模式'}
            />
          </Descriptions.Item>
          <Descriptions.Item label="数据库状态">
            <Badge status={health?.database.available ? 'success' : 'error'} text={health?.database.message || '正常'} />
          </Descriptions.Item>
        </Descriptions>
      </div>
    </div>
  );
}

function modeText(mode?: string) {
  return mode === 'real' ? '真实接口可用' : 'Mock模式';
}
