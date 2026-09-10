# AI-MBSE-Demo

AI 赋能 MBSE 系统设计演示平台，提供本地运行的前后端 MVP。系统覆盖需求结构化、SysML 候选模型生成、追溯关系、变更影响分析、模型预评审、MagicDraw/Cameo Bridge 推送，以及 GMAT/Simulink 真实仿真接入。

## 功能说明

- 需求分析：输入文本或上传 txt/docx/pdf，生成结构化需求。
- 人在回路：支持逐条确认、修改、拒绝，并写入 SQLite。
- 模型生成：从已确认需求生成 Requirement、UseCase、Block、Interface、Activity 和追溯关系。
- SysML 适配：优先调用 `.env` 配置的真实 SysML v2 API，失败后本地保存。
- MagicDraw/Cameo 接入：优先通过 MagicDraw Bridge 推送模型；Bridge 不在线时保留本地交换包，便于排查。
- 影响分析：基于 SQLite 中的模型关系图做 BFS 影响传播。
- 模型预评审：按规则输出评分、问题和建议，支持 JSON 导出。
- 系统仿真：展示 GMAT 与 Simulink 两个真实仿真工具状态，并支持从前端选择运行。
- AI 工作台：展示任务路由、RAG 检索和工具调用过程。

## 启动

后端：

```bat
scripts\run_backend.bat
```

前端：

```bat
scripts\run_frontend.bat
```

访问：

```text
http://localhost:5173
```

健康检查：

```text
http://localhost:8000/api/health
```

## 关键配置

后端配置文件位于 `backend/.env`，模板位于 `backend/.env.example`。

```env
DATABASE_URL=sqlite:///./ai_mbse_demo.db

LLM_API_BASE_URL=
LLM_API_KEY=
LLM_MODEL_NAME=
LLM_ENABLE_REAL_API=false

SYSML_API_BASE_URL=http://sysml2.intercax.com:9000
SYSML_API_TOKEN=
SYSML_ENABLE_REAL_API=true
SYSML_PROJECT_ID=
SYSML_PROJECT_NAME=AI-MBSE-Demo

MAGICDRAW_ENABLE_BRIDGE=true
MAGICDRAW_BRIDGE_URL=http://127.0.0.1:7010/api
MAGICDRAW_PROJECT_PATH=
MAGICDRAW_PACKAGE_NAME=AI_MBSE_Demo
MAGICDRAW_EXPORT_DIR=./exports/magicdraw

GMAT_ENABLE_REAL=true
GMAT_ROOT_DIR=E:\tools\GMAT-R2026a
GMAT_CONSOLE_PATH=E:\tools\GMAT-R2026a\bin\GmatConsole.exe
GMAT_WORK_DIR=./exports/gmat

SIMULINK_ENABLE_REAL=true
SIMULINK_MATLAB_PATH=E:\developtool\MATLAB\R2025a\bin\matlab.exe
SIMULINK_MODEL_PATH=
SIMULINK_WORK_DIR=./exports/simulink
SIMULINK_TIMEOUT_SEC=180
```

## MagicDraw / Cameo Bridge

`/api/magicdraw/status` 会返回 Bridge 是否在线。真实接入依赖一个本地 MagicDraw/Cameo Bridge 服务，默认地址是：

```text
http://127.0.0.1:7010/api
```

Bridge 需要实现：

- `GET /api/health`
- `POST /api/models/import`

`POST /api/models/import` 消费后端生成的 `magicdraw_exchange.json` 负载，通过 MagicDraw/Cameo OpenAPI 创建或复用 Package、Block、Requirement、UseCase、Interface 和 Dependency/Trace/Allocate 等关系。

## GMAT

GMAT 使用 NASA 官方 Windows zip 版本即可，无需安装器。后端会生成 GMAT 脚本，调用 `GmatConsole.exe` 执行 1 天 LEO 轨道传播，并解析最终位置、速度、高度和周期。

## Simulink

Simulink 通过 MATLAB 命令行 `-batch` 模式运行。如果未配置 `SIMULINK_MODEL_PATH`，后端会自动生成一个一阶动态响应演示模型，完成 smoke simulation 并输出稳态值、峰值、超调量和调节时间。

配置正式 `.slx/.mdl` 后，前端“系统仿真”页可在工具下拉框中选择 Simulink 运行。

## 常见问题

- 前端访问后端失败：确认后端在 `http://localhost:8000`。
- MagicDraw 显示 Bridge 未连接：确认 MagicDraw/Cameo Bridge 服务已启动，并监听 `MAGICDRAW_BRIDGE_URL`。
- Simulink 显示不可用：确认 `SIMULINK_ENABLE_REAL=true`，`SIMULINK_MATLAB_PATH` 指向 `matlab.exe`，并且 MATLAB/Simulink 许可可用。
- 数据为空：运行 `scripts/init_demo_data.py`，或在“需求分析”页加载演示数据并完成确认。
