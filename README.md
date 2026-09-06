# 课程报告智能助教

当前版本采用前后端分离结构：

- `backend/`：Python FastAPI，负责系统配置、文件上传、报告解析和问答 Prompt 生成。
- `frontend/`：Next.js，负责报告上传页和系统配置页。
- `MySQL voiceTA`：负责保存用户、课程、报告和问答记录。

系统当前按老师端/学生端组织：

- 老师端：创建课程，填写课程作业要求，查看课程内学生报告的分析总结。
- 学生端：加入课程，提交报告，等待系统生成语音问答问题计划。
- 系统配置：配置 DashScope API Key、Base URL 和文本模型。

当前版本先跑通“登录校验 -> 老师创建课程与要求 -> 学生提交报告 -> 调用 DashScope 文件解析 -> 生成实时语音问答 Prompt -> 老师查看总结”这条主流程。

## 1. 首次准备

```powershell
conda activate voiceTA
pip install -r requirements.txt

cd frontend
npm install
cd ..
```

确认本机 MySQL 8 服务已启动，并且可以使用以下连接信息访问：

```text
数据库：voiceTA
主机：127.0.0.1
端口：3306
用户名：root
密码：root
```

后端启动时会自动创建 `voiceTA` 数据库和以下基础表：

- `users`：用户表，区分 `admin`、`teacher`、`student`。
- `courses`：课程表，保存课程、老师和作业要求。
- `reports`：报告表，保存上传记录、分析状态和模型分析结果。
- `qa_records`：问答记录表，保存后续语音/文本问答内容。

默认应用登录账号：

```text
管理员：admin / admin123
老师：teacher / teacher123
学生：student / student123
```

如果你的 MySQL 连接信息不同，可以通过环境变量覆盖：

```powershell
$env:VOICE_TA_DATABASE_URL="mysql+pymysql://root:root@127.0.0.1:3306/voiceTA?charset=utf8mb4"
$env:VOICE_TA_DB_HOST="127.0.0.1"
$env:VOICE_TA_DB_PORT="3306"
$env:VOICE_TA_DB_USER="root"
$env:VOICE_TA_DB_PASSWORD="root"
```

## 2. 一条命令启动

在项目根目录运行这一条命令即可同时启动前后端：

```powershell
conda activate voiceTA
python scripts/run_dev.py
```

启动后访问：

```text
后端 API：http://127.0.0.1:8000
前端页面：http://localhost:3000
登录页：http://localhost:3000/login
老师端：http://localhost:3000/teacher
学生端：http://localhost:3000/student
系统配置：http://localhost:3000/config
```

停止时，在这个终端里按 `Ctrl+C`。

如果要自定义端口：

```powershell
python scripts/run_dev.py --backend-port 8000 --frontend-port 3000
```

如果你更想用 cmd 脚本，也可以在项目根目录打开 `cmd.exe`，运行：

```bat
scripts\start-dev.cmd
```

这个脚本会自动打开两个新的控制台窗口。

如果想在 PowerShell 中一键启动，也可以运行：

```powershell
.\scripts\start-dev.ps1
```

如果 PowerShell 阻止脚本执行，可以先在当前终端临时允许本次会话执行脚本：

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\scripts\start-dev.ps1
```

## 3. 分别启动

后端：

```powershell
conda activate voiceTA
python -m uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000
```

前端需要另开一个终端：

```powershell
cd frontend
$env:NEXT_PUBLIC_API_BASE_URL="http://127.0.0.1:8000"
npm run dev
```

访问地址：

```text
后端 API：http://127.0.0.1:8000
http://localhost:3000
```

## 4. 停止服务

如果是分别启动，在两个终端里按 `Ctrl+C` 即可。

如果是用一键脚本启动，可以直接关闭脚本打开的两个终端窗口，或者在 `cmd.exe` 中运行：

```bat
scripts\stop-dev.cmd
```

也可以在 PowerShell 中运行：

```powershell
.\scripts\stop-dev.ps1
```

## 5. 系统配置

打开前端后，先进入“系统配置”页面，填写：

- DashScope API Key
- Base URL，默认 `https://dashscope.aliyuncs.com/compatible-mode/v1`
- 文本模型，默认 `qwen-long`

配置会保存到本地 `data/config.json`。该文件已加入 `.gitignore`，不会进入版本库。

上传报告前，前端会调用 `/api/config/check` 检查配置是否完成；后端在创建分析会话时也会再次检查，避免未配置时误提交任务。

## 6. 使用流程

1. 进入“系统配置”，填写 DashScope API Key。
2. 进入“登录”，使用老师账号登录。
3. 进入“老师端”，创建课程，填写作业名称和作业要求。
4. 使用学生账号登录，进入“学生端”，选择课程并上传报告。
5. 系统完成分析后，学生端会显示报告概览、问题计划和语音问答 Prompt。
6. 老师端选择对应课程和学生提交，可以查看报告总结、教师关注点和语音问答 Prompt。

## 7. 主要 API

- `GET /api/config`：读取公开配置状态，不返回明文 API Key。
- `PUT /api/config`：保存系统配置。
- `GET /api/config/check`：检查上传前所需配置是否完成。
- `POST /api/auth/login`：用户登录，返回角色信息。
- `POST /api/courses`：老师创建课程和作业要求。
- `GET /api/courses`：查看课程列表。
- `GET /api/courses/{course_id}`：查看课程详情和学生提交列表。
- `POST /api/courses/{course_id}/sessions`：学生向课程提交报告。
- `POST /api/sessions`：创建报告分析会话并异步生成问答 Prompt。
- `GET /api/sessions/{session_id}`：查询分析状态和结果。
- `GET /api/sessions/{session_id}/qa-records`：查看报告问答记录。
- `POST /api/sessions/{session_id}/qa-records`：新增报告问答记录。

上传文件会保存在 `data/uploads/`，课程、提交记录、用户和问答记录会保存在 MySQL。`data/uploads/` 已加入 `.gitignore`；后续可以继续替换为对象存储和异步队列。
