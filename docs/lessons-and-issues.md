# 问题与解决记录（含未完成项）

> 面向评审与答辩：记录本项目实现过程中真实遇到的问题、定位方式与最终处理，以及明确没做的事和原因。
> 最后更新：2026-11-27

## 1. 关键问题与解决

| # | 问题 | 现象 | 根因 | 解决 | 证据 |
| --- | --- | --- | --- | --- | --- |
| 1 | 前端无法启动 / 构建 | 页面白屏，Vite 报 `Failed to resolve import "../lib/categories"` | 仓库根 `.gitignore` 的 Python 模板规则 `lib/` 会忽略任意层级的 `lib/`，`frontend/src/lib/` 从未被提交 | 加例外 `!frontend/src/lib/` 与 `!frontend/src/lib/**`；按调用点补回 `categories.ts` / `format.ts`；新增 **Frontend CI**（`npm ci` + `tsc -b` + `vite build`）防复发 | PR #7、`.github/workflows/frontend.yml` |
| 2 | 视觉模型偶发返回空内容 | 某张小票连续两次空响应，识别失败 | 上游模型抖动/限流 | 对“空响应”单独重试一次并追加“请直接输出 JSON”，仍空才转可读提示；评测从 9/10 恢复到 10/10 | `ocr_service.py` 的重试分支、`docs/ocr-eval.md` |
| 3 | 模型输出不是合法 JSON | 直接解析报错 | 模型可能输出解释文字或 ```` ```json ```` 代码块 | 先提取代码块与首个 `{...}` 再 `json.loads`；失败重试一次；仍失败抛 `OcrError` 由 Orchestrator 转提示 | `test_ocr_service.py` 的脏输出用例 |
| 4 | 评审环境没有 API Key | 无法演示真实模型 | Key 属于个人凭据，不能进仓库 | 双层降级：未配 `VISION_API_KEY` 用 OCR 桩；未配 `LLM_API_KEY` 用规则模型；两条链路都能完整演示 | `README` 启动说明、`/api/health` 的 `llm_configured` |
| 5 | 模型会“编数字” | 查账回答可能凭空给金额 | 直接让模型自由回答 | 查账/统计必须走工具与 SQL，回答中的金额来自查询结果；工具参数非法返回 `ok=false` 交模型自纠 | `agent/orchestrator.py`、`tools.py`、`docs/agent-design.md` |
| 6 | 本机没有 Docker 环境 | 无法本地构建镜像 | 开发机未安装 Docker/WSL | 用 GitHub Actions 的 `Docker` workflow 做构建 + 健康检查 + 上传冒烟；`Dockerfile` 按标准布局可复现 | `.github/workflows/docker.yml`、`Dockerfile` |
| 7 | 小票图片隐私 | 上传图片可能含个人信息 | 图片会落盘到 `data/uploads/` | 只存本地、不入 Git（`.gitignore` 覆盖 `data/`）；演示只用合成小票；接口限制 10MB 与 MIME | `.gitignore`、`api/ocr/upload` 校验 |
| 8 | 上传文件伪装 | 改后缀的非图片文件也能通过 | 只看扩展名 | 增加文件头校验（PNG/JPEG/WEBP magic），并用分块读取限制大小 | `backend/app/api/ocr.py`、`test_ocr_upload.py` |

## 2. 设计取舍

| 决策 | 取舍 | 影响 |
| --- | --- | --- |
| 视觉大模型做主 OCR | 版式鲁棒、开发快；依赖外网与额度 | 保留 `OcrService` 协议，可替换为 PaddleOCR |
| 合成小票做评测 | 可复现、无隐私；与真实拍照有差距 | 评测数字（10/10）只能代表合成样本，文档已注明 |
| SQLite 而非 Postgres | 零运维、单文件易复现 | 并发写有限，演示场景足够；已开 WAL 与 `busy_timeout` |
| 不引入向量库/RAG | 记账场景数据量小，SQL 聚合足够 | 少了“RAG”亮点，但换来可解释与可验证 |
| 前端产物由 FastAPI 托管（生产） | 部署简单、无跨域 | 需要先 `npm run build` 再挂 `dist`（README 已写） |

## 3. 未完成项与原因

| 项 | 状态 | 原因 / 后续 |
| --- | --- | --- |
| 前端自动化测试（Vitest/Playwright） | 未做 | 时间优先给了联调与 CI 构建；目前用 `frontend/README.md` 手工清单 + 后端契约测试兜底 |
| 真实小票评测规模 | 仅 10 张合成样本 | 真实票据涉及隐私；后续可扩展到 50 张脱敏样本，并统计真实拍照准确率 |
| 本机 Docker 换机复现 | 仅 CI 验证 | 开发机无 Docker；答辩前建议在有 Docker 的机器跑一次 `docker compose up --build` |
| 月度消费建议（功能文档 F5，扩展项） | 未实现 | 非 MVP 必做项；Agent 已有工具化基础，后续加 `get_monthly_advice` 工具与 `/api/advice` 即可 |
| 语音录入 | 未做 | 题目只要求文本/图片；语音需要额外 ASR 依赖 |
| 多用户与鉴权 | 未做 | 单机演示场景，README「已知问题」中已注明 |

## 4. 答辩可讲的三条经验

1. **降级设计比模型效果更重要**：没有 Key、模型超时、输出异常、图片缺失，四条路径都有可读提示且不 500；
2. **数字必须可追溯**：查账与统计走 SQL，OCR 只负责“理解”，不负责“事实”；
3. **CI 是防回归的底线**：后端测试、前端构建、Docker 冒烟三条流水线都挂在 PR 上，`lib/` 被 `.gitignore` 吞掉这类问题会在 CI 直接暴露。
