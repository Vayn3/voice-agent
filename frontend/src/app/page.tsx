import Link from "next/link";

export default function HomePage() {
  return (
    <section className="workspace">
      <div className="page-head">
        <div>
          <p className="eyebrow">入口</p>
          <h1>课程报告智能助教</h1>
        </div>
        <div className="badge">前后端分离版</div>
      </div>

      <div className="role-grid">
        <Link className="role-card" href="/login">
          <span>用户校验</span>
          <strong>登录后进入对应界面</strong>
          <p>系统会根据管理员、老师、学生角色进入不同工作区，后续可继续接入更严格的权限控制。</p>
        </Link>
        <Link className="role-card" href="/teacher">
          <span>老师端</span>
          <strong>创建课程与查看报告总结</strong>
          <p>填写课程作业要求，查看学生提交状态、报告分析概览、提问计划与教师关注点。</p>
        </Link>
        <Link className="role-card" href="/student">
          <span>学生端</span>
          <strong>加入课程并提交报告</strong>
          <p>选择老师创建的课程，上传课程报告，等待系统生成语音问答所需的问题计划。</p>
        </Link>
        <Link className="role-card" href="/config">
          <span>系统配置</span>
          <strong>配置模型服务</strong>
          <p>填写 DashScope API Key、Base URL 和文本模型。上传前系统会自动检查配置。</p>
        </Link>
      </div>
    </section>
  );
}
