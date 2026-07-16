"use client";

import { FormEvent, useEffect, useState } from "react";
import { RequireRole } from "@/app/RequireRole";
import { getConfig, listUsers, saveConfig, updateUserRole } from "@/lib/api";
import type { SystemConfig, User, UserRole } from "@/types/api";

const DEFAULT_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1";
const DEFAULT_MODEL = "qwen-long";

type AdminView = "config" | "users";

export default function ConfigPage() {
  return (
    <RequireRole roles={["admin"]}>
      {() => <AdminWorkspace />}
    </RequireRole>
  );
}

function AdminWorkspace() {
  const [view, setView] = useState<AdminView>("config");

  return (
    <section className="workspace config-card">
      <div className="page-head">
        <div>
          <p className="eyebrow">管理员</p>
          <h1>{view === "config" ? "系统配置" : "用户管理"}</h1>
        </div>
        <div className="segmented">
          <button className={view === "config" ? "active" : ""} type="button" onClick={() => setView("config")}>
            系统配置
          </button>
          <button className={view === "users" ? "active" : ""} type="button" onClick={() => setView("users")}>
            用户管理
          </button>
        </div>
      </div>

      {view === "config" ? <ConfigForm /> : <UserManagement />}
    </section>
  );
}

function ConfigForm() {
  const [config, setConfig] = useState<SystemConfig | null>(null);
  const [apiKey, setApiKey] = useState("");
  const [baseUrl, setBaseUrl] = useState(DEFAULT_BASE_URL);
  const [model, setModel] = useState(DEFAULT_MODEL);
  const [realtimeAppId, setRealtimeAppId] = useState("");
  const [realtimeAccessKey, setRealtimeAccessKey] = useState("");
  const [realtimeAppKey, setRealtimeAppKey] = useState("");
  const [message, setMessage] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    getConfig()
      .then((payload) => {
        setConfig(payload);
        setBaseUrl(payload.dashscope_base_url || DEFAULT_BASE_URL);
        setModel(payload.dashscope_text_model || DEFAULT_MODEL);
      })
      .catch(() => setMessage("后端服务未连接，请确认 FastAPI 已启动。"));
  }, []);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaving(true);
    setMessage("");
    try {
      const payload = await saveConfig({
        dashscope_api_key: apiKey,
        dashscope_base_url: baseUrl,
        dashscope_text_model: model,
        volc_realtime_app_id: realtimeAppId,
        volc_realtime_access_key: realtimeAccessKey,
        volc_realtime_app_key: realtimeAppKey
      });
      setConfig(payload);
      setApiKey("");
      setRealtimeAppId("");
      setRealtimeAccessKey("");
      setRealtimeAppKey("");
      setMessage("配置已保存。");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "保存失败");
    } finally {
      setSaving(false);
    }
  }

  const allConfigured = Boolean(config?.configured && config?.realtime_configured);

  return (
    <>
      <div className={allConfigured ? "badge" : "badge warn"}>
        {allConfigured ? "已配置" : "未完整配置"}
      </div>
      {config?.dashscope_api_key_masked && (
        <p className="hint">当前 DashScope API Key：{config.dashscope_api_key_masked}</p>
      )}
      {config?.realtime_configured && (
        <p className="hint">
          当前实时语音配置：App ID {config.volc_realtime_app_id_masked}，Access Token{" "}
          {config.volc_realtime_access_key_masked}，Secret Key {config.volc_realtime_app_key_masked}
        </p>
      )}
      {message && (
        <p className={message.includes("保存") ? "message success" : "message error"}>
          {message}
        </p>
      )}

      <form className="form" onSubmit={handleSubmit}>
        <div className="config-section">
          <div>
            <h2>DashScope 文本模型</h2>
            <p className="hint">用于解析报告、生成提问计划和问答总结。</p>
          </div>

          <label>
            DashScope API Key
            <input
              type="password"
              value={apiKey}
              onChange={(event) => setApiKey(event.currentTarget.value)}
              placeholder={config?.configured ? "输入新 Key 可覆盖当前配置" : "请输入 DashScope API Key"}
              required={!config?.configured}
            />
          </label>

          <label>
            Base URL
            <input value={baseUrl} onChange={(event) => setBaseUrl(event.currentTarget.value)} required />
          </label>

          <label>
            文本模型
            <input value={model} onChange={(event) => setModel(event.currentTarget.value)} required />
          </label>
        </div>

        <div className="config-section">
          <div>
            <h2>实时语音对话 API</h2>
            <p className="hint">
              这三个值分别对应豆包控制台中的 APP ID、Access Token 和 Secret Key。
            </p>
          </div>

          <label>
            App ID
            <input
              type="password"
              value={realtimeAppId}
              onChange={(event) => setRealtimeAppId(event.currentTarget.value)}
              placeholder={config?.volc_realtime_app_id_masked ? `当前：${config.volc_realtime_app_id_masked}` : "请输入 API_APP_ID"}
              required={!config?.volc_realtime_app_id_masked}
            />
          </label>

          <label>
            Access Token
            <input
              type="password"
              value={realtimeAccessKey}
              onChange={(event) => setRealtimeAccessKey(event.currentTarget.value)}
              placeholder={
                config?.volc_realtime_access_key_masked
                  ? `当前：${config.volc_realtime_access_key_masked}`
                  : "请输入 Access Token"
              }
              required={!config?.volc_realtime_access_key_masked}
            />
          </label>

          <label>
            Secret Key
            <input
              type="password"
              value={realtimeAppKey}
              onChange={(event) => setRealtimeAppKey(event.currentTarget.value)}
              placeholder={config?.volc_realtime_app_key_masked ? `当前：${config.volc_realtime_app_key_masked}` : "请输入 Secret Key"}
              required={!config?.volc_realtime_app_key_masked}
            />
          </label>
        </div>

        <button className="primary-button" type="submit" disabled={saving}>
          {saving ? "保存中..." : "保存配置"}
        </button>
      </form>
    </>
  );
}

function UserManagement() {
  const [users, setUsers] = useState<User[]>([]);
  const [message, setMessage] = useState("");
  const [savingUserId, setSavingUserId] = useState("");

  useEffect(() => {
    refreshUsers();
  }, []);

  async function refreshUsers() {
    try {
      setUsers(await listUsers());
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "无法加载用户列表");
    }
  }

  async function handleRoleChange(userId: string, role: UserRole) {
    setSavingUserId(userId);
    setMessage("");
    try {
      const updated = await updateUserRole(userId, role);
      setUsers((current) => current.map((user) => (user.id === userId ? updated : user)));
      setMessage("权限已更新。");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "更新权限失败");
    } finally {
      setSavingUserId("");
    }
  }

  return (
    <div className="config-section">
      {message && (
        <p className={message.includes("更新") ? "message success" : "message error"}>
          {message}
        </p>
      )}
      <div className="list-stack">
        {users.map((user) => (
          <div className="user-row" key={user.id}>
            <div>
              <strong>{user.display_name || user.username}</strong>
              <p className="hint">{user.username}</p>
            </div>
            <select
              value={user.role}
              disabled={savingUserId === user.id}
              onChange={(event) => handleRoleChange(user.id, event.currentTarget.value as UserRole)}
            >
              <option value="student">学生</option>
              <option value="teacher">老师</option>
              <option value="admin">管理员</option>
            </select>
          </div>
        ))}
      </div>
    </div>
  );
}
