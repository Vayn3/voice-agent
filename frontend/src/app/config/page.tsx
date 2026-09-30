"use client";

import { FormEvent, useEffect, useState } from "react";
import { RequireRole } from "@/app/RequireRole";
import { getConfig, listUsers, saveConfig, updateUserRole } from "@/lib/api";
import type { SystemConfig, User, UserRole } from "@/types/api";

const DEFAULT_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1";
const DEFAULT_MODEL = "qwen-long";
const DEFAULT_REALTIME_MODEL_VERSION = "1.2.1.1";

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
  const [codeModel, setCodeModel] = useState("qwen3-coder-plus");
  const [realtimeApiKey, setRealtimeApiKey] = useState("");
  const [realtimeModelVersion, setRealtimeModelVersion] = useState(DEFAULT_REALTIME_MODEL_VERSION);
  const [message, setMessage] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    getConfig()
      .then((payload) => {
        setConfig(payload);
        setBaseUrl(payload.dashscope_base_url || DEFAULT_BASE_URL);
        setModel(payload.dashscope_text_model || DEFAULT_MODEL);
        setCodeModel(payload.dashscope_code_model || "qwen3-coder-plus");
        setRealtimeModelVersion(payload.volc_realtime_model_version || DEFAULT_REALTIME_MODEL_VERSION);
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
        dashscope_code_model: codeModel,
        volc_realtime_api_key: realtimeApiKey,
        volc_realtime_model_version: realtimeModelVersion
      });
      setConfig(payload);
      setApiKey("");
      setRealtimeApiKey("");
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
          当前豆包实时语音配置：API Key {config.volc_realtime_api_key_masked}，模型版本{" "}
          {config.volc_realtime_model_version}
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
            <p className="hint">文档模型读取PDF/Word；代码审查模型分析全部源码、联合审查、生成答辩问题和评分。</p>
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
            文档模型（支持fileid的qwen-long）
            <input value={model} onChange={(event) => setModel(event.currentTarget.value)} required />
          </label>
          <label>
            代码审查与评分模型
            <input value={codeModel} onChange={(event) => setCodeModel(event.currentTarget.value)} required />
            <small>默认qwen3-coder-plus，也可填写账号支持的通用模型；源码按完整文本传入。</small>
          </label>
        </div>

        <div className="config-section">
          <div>
            <h2>豆包端到端实时语音</h2>
            <p className="hint">
              使用火山控制台的 API Key 鉴权；O2.0 的规范版本号为 1.2.1.1。
            </p>
          </div>

          <label>
            豆包语音 API Key
            <input
              type="password"
              value={realtimeApiKey}
              onChange={(event) => setRealtimeApiKey(event.currentTarget.value)}
              placeholder={config?.volc_realtime_api_key_masked ? `当前：${config.volc_realtime_api_key_masked}` : "请输入 API Key"}
              required={!config?.volc_realtime_api_key_masked}
            />
          </label>

          <label>
            实时模型版本
            <select value={realtimeModelVersion} onChange={(event) => setRealtimeModelVersion(event.currentTarget.value)}>
              <option value="1.2.1.1">O2.0（1.2.1.1）</option>
              <option value="2.2.0.0">SC2.0（2.2.0.0）</option>
            </select>
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
