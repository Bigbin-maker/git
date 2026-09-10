# AI-MBSE-Demo Backend

FastAPI 后端服务，提供需求分析、SysML 模型生成、MagicDraw/Cameo 交换包、变更影响分析、模型预评审和仿真接口。

## 启动

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Swagger:

```text
http://localhost:8000/docs
```

## 配置

复制 `.env.example` 为 `.env` 后按需配置 LLM、SysML API 和 MagicDraw Bridge。SysML 适配器默认按 SysML v2 REST API 参考实现访问 `/projects` 和 `/projects/{projectId}/commits`。MagicDraw Bridge 不可用时会生成本地交换包，外部接口不可用时系统会自动降级保证演示不中断。
