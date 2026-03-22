# Agent 升级改造方案（Prompt/上下文工程 + 记忆与知识层）

## 1. 目标与范围

本方案聚焦两块能力建设：

1. Prompt 与上下文工程  
2. 记忆与知识层

目标是把当前项目从 Demo 级别提升为可面试讲解、可线上运行的 Agent 后端系统。

---

## 2. 改动点与优化点

### 2.1 Prompt 与上下文工程

#### A. 上下文压缩（Context Compression）
- 改动点：
  - 增加对话摘要器，将历史长对话压缩为结构化摘要（用户目标、约束、已确认偏好、待确认事项）。
  - 保留最近 N 轮原始对话 + 历史摘要的混合上下文策略。
- 优化点：
  - 降低 token 成本与响应时延。
  - 降低长对话中的信息漂移与幻觉概率。

#### B. RAG 注入策略（Retrieval Augmented Generation）
- 改动点：
  - 引入知识检索层（优先本地知识库，后续可接 CMS/数据库）。
  - 设计注入模板：检索结果按“高可信度 + 高相关度”排序后注入 prompt。
  - 给注入内容加来源标记（source/version/timestamp）。
- 优化点：
  - 回答可追溯，减少“编造知识”。
  - 提升针对业务规则和本地知识的回答准确率。

#### C. 冲突指令消解（Instruction Conflict Resolution）
- 改动点：
  - 显式实现指令优先级：System > Developer > User > Retrieved Context。
  - 对冲突内容落日志（冲突类型、被丢弃指令、最终裁决）。
- 优化点：
  - 避免高风险越权调用与“忽略系统规则”类 prompt injection。
  - 稳定输出行为，提高安全与一致性。

---

### 2.2 记忆与知识层

#### A. 短期会话记忆（Session Memory）
- 改动点：
  - 新增会话级存储：记录当前会话关键槽位（城市、预算、交通偏好、酒店档位、行程天数）。
  - 每轮对话后自动更新槽位。
- 优化点：
  - 减少用户重复输入。
  - 支持多轮澄清后稳定生成方案。

#### B. 长期用户画像（Long-term Profile）
- 改动点：
  - 增加用户画像表（跨会话）：稳定偏好、历史行为统计、偏好置信度。
  - 区分“会话临时偏好”与“长期偏好”并做融合。
- 优化点：
  - 支持个性化推荐。
  - 让下一次会话能继承历史偏好，提高命中率。

#### C. 向量检索（Vector Retrieval）
- 改动点：
  - 将知识文档与历史记忆向量化并建立索引。
  - 检索时使用混合召回（关键词 + 语义向量）提升覆盖率。
- 优化点：
  - 对口语化问题、改写问题更稳健。
  - 为 RAG 与记忆召回提供统一检索能力。

#### D. 知识版本化与过期策略（Versioning + Expiration）
- 改动点：
  - 文档与记忆条目增加 version、valid_from、valid_to、updated_at 字段。
  - 增加 TTL 与失效扫描任务（例如天气类、活动类知识短 TTL）。
- 优化点：
  - 防止使用陈旧信息。
  - 发生知识错误时可按版本回滚和审计。

---

## 3. 实施难度与工作量评估

### Phase 1：上下文工程（中等，约 1-2 周）
- 内容：上下文压缩 + 冲突消解 + 基础 RAG 注入
- 产出：Prompt Builder、Context Manager、检索注入器
- 风险：主要是策略调优，工程风险较低

### Phase 2：记忆与检索（中高，约 2-4 周）
- 内容：会话记忆、长期画像、向量检索、TTL
- 产出：Memory Service、Profile Store、Vector Store 集成
- 风险：需要数据模型、迁移和线上存储策略

### Phase 3：版本化与治理（高，约 1-2 周）
- 内容：版本发布/回滚、审计日志、知识生命周期管理
- 产出：Knowledge Registry + Version Policy
- 风险：涉及运维流程与数据治理，不仅是代码改造

---

## 4. 按当前仓库结构的实施清单

当前主要后端目录：
- `backend/app/agents`
- `backend/app/services`
- `backend/app/api`
- `backend/app/models`
- `backend/app/config.py`

建议新增目录：
- `backend/app/memory/`
- `backend/app/retrieval/`
- `backend/app/prompting/`
- `backend/app/knowledge/`
- `backend/app/evals/`（可选，建议加）

---

## 5. 具体文件级改造建议

### 5.1 Prompt 与上下文工程

1. 新增 `backend/app/prompting/prompt_builder.py`
- 职责：
  - 统一构造 system/developer/user/retrieved context 的最终 prompt。
  - 实现冲突指令优先级裁决。

2. 新增 `backend/app/prompting/context_compressor.py`
- 职责：
  - 历史对话压缩成结构化摘要。
  - 控制上下文 token 上限。

3. 新增 `backend/app/retrieval/rag_injector.py`
- 职责：
  - 调用检索服务拿候选知识。
  - 过滤、排序、截断后注入 prompt。

4. 修改 `backend/app/agents/trip_planner_agent.py`
- 职责：
  - 从“手写长 prompt”升级为“调用 Prompt Builder”。
  - 把景点、天气、酒店结果与检索知识统一拼装。

---

### 5.2 记忆与知识层

1. 新增 `backend/app/memory/session_memory.py`
- 职责：
  - 管理短期会话记忆（slot-based）。
  - 提供读写接口：`load_session_memory / update_session_memory`。

2. 新增 `backend/app/memory/user_profile.py`
- 职责：
  - 管理长期用户画像（偏好与置信度）。
  - 会话结束时同步更新画像。

3. 新增 `backend/app/retrieval/vector_store.py`
- 职责：
  - 封装向量库操作（upsert/search/delete）。
  - 屏蔽底层向量引擎差异（FAISS/pgvector/其他）。

4. 新增 `backend/app/knowledge/knowledge_registry.py`
- 职责：
  - 管理知识元数据（版本、有效期、来源、更新时间）。
  - 提供版本查询、最新版本选择、失效过滤。

5. 新增 `backend/app/knowledge/expiration_policy.py`
- 职责：
  - 定义 TTL 策略（按知识类型差异化）。
  - 提供过期检查与清理逻辑。

6. 修改 `backend/app/models/schemas.py`
- 职责：
  - 增加记忆与知识相关 schema（SessionState、UserProfile、KnowledgeItem）。

7. 修改 `backend/app/config.py`
- 职责：
  - 增加向量库、TTL、RAG 开关、记忆开关等配置项。

---

### 5.3 API 与可观测性（建议同步做）

1. 修改 `backend/app/api/routes/trip.py`
- 职责：
  - 入参增加 `session_id`、`user_id`（用于记忆层）。
  - 返回结果中附带 `knowledge_sources`（可选）。

2. 新增 `backend/app/services/telemetry_service.py`（可选）
- 职责：
  - 记录关键指标：检索命中率、工具调用成功率、上下文压缩比、响应耗时。

3. 修改 `backend/app/api/main.py`
- 职责：
  - 启动时初始化记忆存储/向量索引/知识策略。

---

## 6. 推荐实施顺序（先后顺序）

1. 先做 Prompt Builder + Context Compressor（最小改动、见效快）。  
2. 接入 RAG Injector（先本地静态知识，验证注入流程）。  
3. 引入 Session Memory（按 `session_id` 管理短期记忆）。  
4. 增加 User Profile（按 `user_id` 维护长期偏好）。  
5. 接入 Vector Store（把知识和记忆统一检索）。  
6. 落地 Knowledge Registry + Expiration（版本和过期治理）。  
7. 补全 Telemetry 与评测脚本（输出可量化简历指标）。

---

## 7. 里程碑与简历可量化指标建议

1. 质量指标
- 行程生成成功率（JSON 可解析 + 字段完整）  
- 工具调用成功率（MCP 调用成功/总调用）  
- 检索命中率（被采纳知识片段数/注入片段数）

2. 性能指标
- 平均响应时延、P95 时延  
- 上下文压缩率（压缩后 token / 压缩前 token）  
- 单次请求平均 token 成本

3. 体验指标
- 用户二次澄清率（越低越好）  
- 个性化命中率（推荐与画像一致比例）  
- 过期知识触发率（验证过期策略有效性）

---

## 8. 最小可上线版本（MVP）建议

如果要快速形成“线上运行”叙事，先完成以下 MVP：

1. Prompt Builder + 冲突消解  
2. Context Compressor（最近 N 轮 + 摘要）  
3. Session Memory（Redis/内存皆可）  
4. 基础 RAG（静态知识 + 向量检索）  
5. `trip` API 打通 `session_id/user_id`  
6. 基础指标埋点（耗时、调用成功率、解析成功率）

完成以上即可形成较强面试叙事，再迭代长期画像与知识版本化。

---

## 9. 第二阶段冲刺计划（2周：评测 + 性能 + 可观测）

目标：把“功能可用”升级为“效果可证、性能可控、线上可运营”。

### 9.1 Week 1：RAG效果验证（质量闭环）

Day 1
- 新增 `backend/app/evals/datasets/rag_eval_cases.jsonl`
- 收集 50 条评测样本（城市、预算、天气、多轮、冲突指令）
- 定义标签字段：`expected_facts`, `must_include`, `must_not_include`

Day 2
- 新增 `backend/app/evals/rag_eval_runner.py`
- 实现离线评测运行器（批量调用检索与生成）
- 输出基础指标：`recall@k`, `context_precision`, `json_parse_rate`

Day 3
- 新增 `backend/app/evals/faithfulness_judge.py`
- 增加“答案忠实度”检查（答案是否被检索证据支持）
- 产出日报表（csv/json）

Day 4
- 参数网格搜索：`top_k / retrieval_mode / keyword_weight / vector_weight`
- 记录每组参数在评测集上的指标与耗时
- 选出默认参数基线

Day 5
- 固化回归门槛（例如：`json_parse_rate >= 95%`, `recall@3 >= 70%`）
- 在本地脚本形成 `make eval` 或等价命令

Week 1 验收标准
- 有可复现实验集和评测脚本
- 可稳定输出 3-5 个质量指标
- 有一套经过评测选出的默认检索参数

### 9.2 Week 2：查询速度与可观测（工程闭环）

Day 6
- 新增 `backend/app/services/cache_service.py`
- 引入检索缓存（query + session 维度，TTL可配置）
- 指标：缓存命中率、平均检索耗时

Day 7
- 在 `trip_planner_agent.py` 中并发化非依赖步骤（天气/酒店/景点）
- 控制并发超时与失败降级
- 指标：`P50`, `P95`, 超时率

Day 8
- 新增 `backend/app/services/telemetry_service.py`
- 结构化打点：`request_id/session_id/user_id/stage/latency/token_estimate`
- 每个阶段落 trace：compress/retrieve/tool_call/generate/parse

Day 9
- 新增 `backend/app/api/routes/debug.py`
- 提供 `rag-debug` 接口返回：命中知识、过滤原因、版本选择结果
- 提供 `metrics-debug` 接口返回当前进程窗口指标

Day 10
- 压测与回归（`50/100/200` 并发等级）
- 产出性能报告：吞吐、错误率、P95、缓存收益
- 调整默认超时、重试、缓存TTL

Week 2 验收标准
- 有可查看的链路级日志与指标
- P95 与错误率有优化结果（对比改造前基线）
- 可通过 debug 接口解释“为什么命中这条知识”

### 9.3 建议新增文件清单（第二阶段）

- `backend/app/evals/datasets/rag_eval_cases.jsonl`
- `backend/app/evals/rag_eval_runner.py`
- `backend/app/evals/faithfulness_judge.py`
- `backend/app/services/cache_service.py`
- `backend/app/services/telemetry_service.py`
- `backend/app/api/routes/debug.py`
- `backend/app/evals/reports/`（评测输出目录）

### 9.4 面试可讲的交付成果

1. 质量侧
- “从主观效果”变成“可量化评测”：recall、faithfulness、json parse rate。

2. 性能侧
- “从可用”变成“可扩展”：P95、缓存命中率、并发吞吐。

3. 工程侧
- “从黑盒”变成“可解释”：debug接口、版本过滤原因、冲突裁决日志。

### 9.5 风险与规避

1. 评测集偏差
- 规避：按场景分桶采样，保持线上请求分布一致性。

2. 参数过拟合
- 规避：保留独立验证集，不在同一批数据上反复调参后报告结果。

3. 过度优化时延导致质量下降
- 规避：以“质量门槛优先，性能在门槛内优化”为原则。
