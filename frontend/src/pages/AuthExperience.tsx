import {
  CheckCircleOutlined,
  IdcardOutlined,
  LockOutlined,
  LoginOutlined,
  SettingOutlined,
  UserOutlined,
} from '@ant-design/icons';
import { Button, Modal, Segmented, Tag, Typography } from 'antd';
import { useMemo, useState } from 'react';

export type DemoRole = 'admin' | 'designer';

export interface DemoUserSession {
  role: DemoRole;
  name: string;
  account: string;
  workspace: string;
  branch: string;
}

interface AuthExperienceProps {
  onLogin: (role: DemoRole) => void;
}

const permissions = [
  { key: 'project', label: '项目与工作空间', admin: true, designer: true },
  { key: 'rbac', label: '用户角色与权限管理', admin: true, designer: false },
  { key: 'model', label: 'AI 需求理解与 SysML 生成', admin: true, designer: true },
  { key: 'magicdraw', label: 'MagicDraw 推送与同步', admin: true, designer: true },
  { key: 'audit', label: '审计日志与变更影响分析', admin: true, designer: false },
  { key: 'simulation', label: '系统仿真与验证任务', admin: true, designer: true },
];

export function getDemoUserSession(role: DemoRole): DemoUserSession {
  return role === 'admin'
    ? {
        role,
        name: '系统管理员',
        account: 'admin@customer.local',
        workspace: '全局管理工作台',
        branch: 'main / 权限基线',
      }
    : {
        role,
        name: '设计师',
        account: 'designer01@customer.local',
        workspace: '卫星任务分析系统',
        branch: 'dev/designer-01',
      };
}

export default function AuthExperience({ onLogin }: AuthExperienceProps) {
  const [role, setRole] = useState<DemoRole>('admin');
  const [permissionOpen, setPermissionOpen] = useState(false);

  const activeUser = useMemo(() => getDemoUserSession(role), [role]);
  const visiblePermissions = permissions.filter((item) => (role === 'admin' ? item.admin : item.designer));

  return (
    <main className="enterprise-login-screen">
      <section className="enterprise-login-card">
        <div className="enterprise-login-brand">
          <div>
            <Typography.Text className="auth-kicker">统一认证入口</Typography.Text>
            <Typography.Title level={2}>AI 赋能 MBSE 系统</Typography.Title>
          </div>
          <div className="auth-lock-mark">
            <LockOutlined />
          </div>
        </div>

        <div className="enterprise-login-body">
          <div className="enterprise-login-section">
            <Segmented
              block
              value={role}
              onChange={(value) => setRole(value as DemoRole)}
              options={[
                { label: '系统管理员', value: 'admin', icon: <SettingOutlined /> },
                { label: '设计师', value: 'designer', icon: <UserOutlined /> },
              ]}
            />

            <div className="auth-account-preview enterprise-account-preview">
              <div className="auth-avatar">
                <IdcardOutlined />
              </div>
              <div>
                <strong>{activeUser.name}</strong>
                <span>{activeUser.account}</span>
                <em>{activeUser.workspace}</em>
              </div>
            </div>

            <div className="enterprise-login-actions">
              <Button type="primary" size="large" icon={<LoginOutlined />} block onClick={() => onLogin(role)}>
                以{activeUser.name}身份进入系统
              </Button>
              <Button size="large" block onClick={() => setPermissionOpen(true)}>
                查看当前角色权限说明
              </Button>
            </div>
          </div>
        </div>
      </section>

      <Modal
        title={`${activeUser.name}权限说明`}
        open={permissionOpen}
        onCancel={() => setPermissionOpen(false)}
        footer={[
          <Button key="close" type="primary" onClick={() => setPermissionOpen(false)}>
            知道了
          </Button>,
        ]}
      >
        <div className="enterprise-permission-summary">
          <div>
            <span>账号</span>
            <strong>{activeUser.account}</strong>
          </div>
          <div>
            <span>工作空间</span>
            <strong>{activeUser.workspace}</strong>
          </div>
          <div>
            <span>分支</span>
            <strong>{activeUser.branch}</strong>
          </div>
        </div>
        <div className="auth-permission-list enterprise-permission-list">
          {permissions.map((item) => {
            const enabled = visiblePermissions.some((permission) => permission.key === item.key);
            return (
              <div className="auth-permission-row" key={item.key}>
                <div>
                  <CheckCircleOutlined className={enabled ? 'is-on' : 'is-off'} />
                  <span>{item.label}</span>
                </div>
                <Tag color={enabled ? 'green' : 'default'}>{enabled ? '允许' : '不可见'}</Tag>
              </div>
            );
          })}
        </div>
      </Modal>
    </main>
  );
}
