import Link from "next/link";

export default function HomePage() {
  return (
    <main className="home-page">
      <section className="home-hero" aria-labelledby="home-title">
        <div className="home-hero-copy">
          <p className="eyebrow">Voice TA</p>
          <h1 id="home-title">课程报告智能助教</h1>
          <p>
            面向课程报告场景的机器人助教，支持报告分析、语音问答和学习总结，让一次提交变成一次可追踪的学习反馈。
          </p>
          <div className="home-hero-actions">
            <Link className="primary-button" href="/register">
              注册账号
            </Link>
            <Link className="secondary-button" href="/login">
              登录系统
            </Link>
          </div>
        </div>
        <div className="home-hero-visual">
          <img src="/home/robot-report-review.png" alt="机器人助教阅读课程报告" />
        </div>
      </section>

      <section className="home-media-section" aria-labelledby="media-title">
        <div className="section-heading">
          <p className="eyebrow">演示播放</p>
          <h2 id="media-title">本地视频展示</h2>
        </div>
        <div className="home-media-frame">
          <video src="/api/home-video" autoPlay muted loop playsInline controls poster="/home/robot-voice-qa.png" />
        </div>
      </section>
    </main>
  );
}
