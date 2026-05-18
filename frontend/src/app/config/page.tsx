"use client";

import { FormEvent, useEffect, useState } from "react";
import { getConfig, saveConfig } from "@/lib/api";
import type { SystemConfig } from "@/types/api";

const DEFAULT_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1";
const DEFAULT_MODEL = "qwen-long";

export default function ConfigPage() {
  const [config, setConfig] = useState<SystemConfig | null>(null);
  const [apiKey, setApiKey] = useState("");
  const [baseUrl, setBaseUrl] = useState(DEFAULT_BASE_URL);
  const [model, setModel] = useState(DEFAULT_MODEL);
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
        dashscope_text_model: model
      });
      setConfig(payload);
      setApiKey("");
      setMessage("配置已保存。");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "保存失败");
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="workspace config-card">
      <div className="page-head">
        <div>
          <p className="eyebrow">系统配置</p>
          <h1>DashScope 模型配置</h1>
        </div>
        <div className={config?.configured ? "badge" : "badge warn"}>
          {config?.configured ? "已配置" : "未配置"}
        </div>
      </div>

      {config?.dashscope_api_key_masked && (
        <p className="hint">当前 API Key：{config.dashscope_api_key_masked}</p>
      )}
      {message && (
        <p className={message.includes("保存") ? "message success" : "message error"}>
          {message}
        </p>
      )}

      <form className="form" onSubmit={handleSubmit}>
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
          <input
            value={baseUrl}
            onChange={(event) => setBaseUrl(event.currentTarget.value)}
            required
          />
        </label>

        <label>
          文本模型
          <input value={model} onChange={(event) => setModel(event.currentTarget.value)} required />
        </label>

        <button className="primary-button" type="submit" disabled={saving}>
          {saving ? "保存中..." : "保存配置"}
        </button>
      </form>
    </section>
  );
}
