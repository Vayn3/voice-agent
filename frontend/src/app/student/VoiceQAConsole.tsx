"use client";

import { useEffect, useRef, useState } from "react";
import { createVoiceQASummary, voiceQAWebSocketUrl } from "@/lib/api";

export function VoiceQAConsole({
  sessionId,
  summary,
  onSummary
}: {
  sessionId: string;
  summary: string;
  onSummary: () => Promise<void>;
}) {
  const [running, setRunning] = useState(false);
  const [summarizing, setSummarizing] = useState(false);
  const [status, setStatus] = useState("等待开始");
  const [messages, setMessages] = useState<{ role: "teacher" | "student" | "system"; text: string }[]>([]);
  const wsRef = useRef<WebSocket | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const inputContextRef = useRef<AudioContext | null>(null);
  const outputContextRef = useRef<AudioContext | null>(null);
  const processorRef = useRef<ScriptProcessorNode | null>(null);
  const playbackTimeRef = useRef(0);
  const endingRef = useRef(false);

  useEffect(() => () => cleanupVoiceQA(), []);

  async function startVoiceQA() {
    setMessages([]);
    setStatus("正在连接实时语音服务");
    setRunning(true);
    endingRef.current = false;
    playbackTimeRef.current = 0;

    try {
      await prepareOutputAudio();
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Audio output initialization failed");
      setRunning(false);
      return;
    }

    const websocket = new WebSocket(voiceQAWebSocketUrl(sessionId));
    websocket.binaryType = "arraybuffer";
    wsRef.current = websocket;

    websocket.onopen = async () => {
      try {
        await startMicrophone(websocket);
      } catch (error) {
        setStatus(error instanceof Error ? error.message : "无法打开麦克风");
        cleanupVoiceQA();
      }
    };

    websocket.onmessage = async (event) => {
      if (typeof event.data === "string") {
        const payload = JSON.parse(event.data);
        if (payload.type === "ready") {
          setStatus("问答进行中，请按语音助教提示回答");
        } else if (payload.type === "model_text") {
          setMessages((current) => [...current, { role: "teacher", text: payload.text }]);
          if (payload.ended) {
            endingRef.current = true;
            stopMicrophone();
            setStatus("检测到问答结束，已停止麦克风，正在生成总结");
          }
        } else if (payload.type === "user_text") {
          if (endingRef.current) return;
          setMessages((current) => [...current, { role: "student", text: payload.text }]);
        } else if (payload.type === "done") {
          cleanupVoiceQA();
          await generateSummary();
        } else if (payload.type === "error") {
          setStatus(payload.message || "实时问答出错");
          cleanupVoiceQA();
        }
      } else {
        await playPcmS16Le(event.data);
      }
    };

    websocket.onerror = () => {
      setStatus("实时问答连接失败");
      cleanupVoiceQA();
    };
    websocket.onclose = () => setRunning(false);
  }

  async function startMicrophone(websocket: WebSocket) {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    streamRef.current = stream;
    const AudioContextClass = getAudioContextClass();
    const context = new AudioContextClass();
    inputContextRef.current = context;
    const source = context.createMediaStreamSource(stream);
    const processor = context.createScriptProcessor(4096, 1, 1);
    processorRef.current = processor;
    processor.onaudioprocess = (event) => {
      if (endingRef.current) return;
      if (websocket.readyState !== WebSocket.OPEN) return;
      websocket.send(floatTo16kPcm(event.inputBuffer.getChannelData(0), context.sampleRate));
    };
    source.connect(processor);
    processor.connect(context.destination);
  }

  async function generateSummary() {
    setSummarizing(true);
    try {
      const payload = await createVoiceQASummary(sessionId);
      setMessages((current) => [
        ...current,
        { role: "system", text: `总结已生成，共整理 ${payload.qa_records.length} 条问答记录。` }
      ]);
      setStatus("问答总结已生成");
      await onSummary();
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "总结生成失败");
    } finally {
      setSummarizing(false);
    }
  }

  function stopVoiceQA() {
    setStatus("正在结束问答并整理记录");
    endingRef.current = true;
    stopMicrophone();
    wsRef.current?.send(JSON.stringify({ type: "finish" }));
  }

  function stopMicrophone() {
    processorRef.current?.disconnect();
    processorRef.current = null;
    inputContextRef.current?.close();
    inputContextRef.current = null;
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
  }

  function cleanupVoiceQA() {
    stopMicrophone();
    if (wsRef.current?.readyState === WebSocket.OPEN) wsRef.current.close();
    wsRef.current = null;
    setRunning(false);
  }

  async function prepareOutputAudio() {
    const AudioContextClass = getAudioContextClass();
    const context = outputContextRef.current || new AudioContextClass({ sampleRate: 24000 });
    outputContextRef.current = context;
    if (context.state === "suspended") {
      await context.resume();
    }
  }

  async function playPcmS16Le(data: ArrayBuffer) {
    await prepareOutputAudio();
    const context = outputContextRef.current;
    if (!context) return;
    const sourcePcm = new DataView(data);
    const sampleCount = Math.floor(sourcePcm.byteLength / 2);
    const samples = new Float32Array(sampleCount);
    for (let index = 0; index < sampleCount; index += 1) {
      samples[index] = sourcePcm.getInt16(index * 2, true) / 0x8000;
    }
    const buffer = context.createBuffer(1, samples.length, 24000);
    buffer.copyToChannel(samples, 0);
    const source = context.createBufferSource();
    source.buffer = buffer;
    source.connect(context.destination);
    const startAt = Math.max(context.currentTime, playbackTimeRef.current);
    source.start(startAt);
    playbackTimeRef.current = startAt + buffer.duration;
  }

  return (
    <div className="voice-console">
      <div className="voice-actions">
        <button className="primary-button" type="button" disabled={running || summarizing} onClick={startVoiceQA}>
          {running ? "问答进行中" : "开始实时问答"}
        </button>
        <button className="secondary-button" type="button" disabled={!running} onClick={stopVoiceQA}>
          结束问答并生成总结
        </button>
      </div>
      <p className="hint">{status}</p>
      <div className="voice-log">
        {messages.length ? (
          messages.map((message, index) => (
            <div className={`voice-line ${message.role}`} key={`${message.role}-${index}`}>
              <strong>{message.role === "teacher" ? "语音助教" : message.role === "student" ? "学生" : "系统"}</strong>
              <p>{message.text}</p>
            </div>
          ))
        ) : (
          <div className="empty">开始后，实时识别到的问答记录会显示在这里。</div>
        )}
      </div>
      {summary && (
        <div className="brief-item">
          <strong>问答总结报告</strong>
          <p className="qa-summary">{summary}</p>
        </div>
      )}
    </div>
  );
}

function floatTo16kPcm(input: Float32Array, sourceSampleRate: number): ArrayBuffer {
  const targetSampleRate = 16000;
  const ratio = sourceSampleRate / targetSampleRate;
  const outputLength = Math.floor(input.length / ratio);
  const buffer = new ArrayBuffer(outputLength * 2);
  const view = new DataView(buffer);
  for (let index = 0; index < outputLength; index += 1) {
    const sample = Math.max(-1, Math.min(1, input[Math.floor(index * ratio)]));
    view.setInt16(index * 2, sample < 0 ? sample * 0x8000 : sample * 0x7fff, true);
  }
  return buffer;
}

function getAudioContextClass(): typeof AudioContext {
  return window.AudioContext || (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
}
