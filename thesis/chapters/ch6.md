# 第6章 系统详细实现

本章在第5章总体设计的基础上，介绍系统的开发环境与各模块的具体实现，给出关键代码与运行界面。系统后端约 2700 行 Python 代码，前端为基于 Vue3 与 Element Plus 的单页应用。

## 6.1 开发与运行环境

系统的开发与运行环境如表 6.1 所示。值得说明的是，全部模型均在一台无独立 GPU 的笔记本电脑上本地运行，验证了系统在资源受限条件下私有化部署的可行性。

表 6.1 开发与运行环境

| 类别 | 配置 |
|---|---|
| 硬件 | Apple M5 处理器，16 GB 统一内存，无独立 GPU |
| 操作系统 | macOS 27 |
| 编程语言 | Python 3.12、JavaScript（ES2020） |
| 后端框架 | FastAPI、Uvicorn、LangGraph、Pydantic |
| 模型推理 | Ollama（Qwen3-8B Q4、Qwen2.5-VL-3B Q4）、PyTorch 2.15 + Transformers（MPS 加速） |
| 嵌入与重排 | BAAI/bge-m3、BAAI/bge-reranker-v2-m3、OFA-Sys/chinese-clip-vit-base-patch16 |
| OCR 与 ASR | RapidOCR（ONNX Runtime）、FunASR（paraformer-zh + fsmn-vad + ct-punc） |
| 存储 | Milvus Lite、SQLite、本地文件系统 |
| 文档处理 | PyMuPDF、python-docx、python-pptx、pandas/openpyxl |
| 前端 | Vue 3、Element Plus、marked |

系统代码按照第5章的分层架构组织，主要目录结构如下：

```text
backend/eim/
  config.py          全局配置（模型、路径、检索与切分参数，可由环境变量覆盖）
  models.py          核心数据结构：Message / Attachment / ParsedContent / Topic / MKU / Answer
  llm.py             OpenAI 兼容大模型客户端（Ollama / vLLM 通用）
  adapters/          IM 适配器：抽象接口、IM 模拟器、数据集加载
  parsing/           多模态解析：调度器、图片、语音、文档、表格、分块
  knowledge/         知识构建：向量化、话题切分、MKU 构建、入库流水线
  retrieval/         检索：BM25、融合与重排、混合检索器
  agent/             智能体：提示词、状态图、机器人服务
  storage/           存储：SQLite 元数据库、Milvus 向量库
  api/               FastAPI 服务
frontend/dist/       IM 模拟器与管理后台
datasets/simeim/     SimEIM 数据集构建脚本
experiments/         评测脚本
```

## 6.2 IM 适配器与消息接入模块实现

### 6.2.1 统一数据模型

系统使用 Pydantic 定义统一的数据模型，各 IM 平台的原始事件均由适配器归一化为 `Message` 对象，其核心字段包括消息 ID、会话 ID、发送人、时间戳、消息类型、文本、附件、被回复消息 ID 和被 @ 用户列表。知识单元 `MKU` 的定义与式（4.5）一一对应：

```python
class MKU(BaseModel):
    mku_id: str
    conv_id: str
    topic_id: str
    kind: str = "dialog"            # dialog: 会话单元; attachment: 附件单元
    modalities: list[Modality] = []
    title: str = ""
    content: str                    # 用于检索与生成的规范化文本
    evidence: list[str] = []        # 证据消息 ID，用于溯源跳转
    ts_start: float = 0.0
    ts_end: float = 0.0
    acl: list[str] = []             # 可见主体集合，检索时前置过滤
    image_path: str | None = None
    meta: dict[str, Any] = {}
```

### 6.2.2 适配器抽象与 IM 模拟器

适配器抽象类 `IMAdapter` 定义了表 5.6 中的全部方法。由于企业真实 IM 数据与接口保密，本文实现了一个独立的 IM 模拟器及其适配器 `SimulatorAdapter`，用于系统演示与评测。模拟器使用独立的数据库文件存储用户、会话与消息，与知识库元数据库隔离，模拟“外部 IM 平台”；它支持群聊与单聊，支持文本、图片、文件和语音消息，以及回复与 @ 提及。实时事件通过异步队列实现发布订阅：每当有新消息写入，消息对象会被推送到所有订阅者的队列中，机器人服务与前端 WebSocket 推送均以订阅者身份接收事件。

权限主体按式（4.8）计算，代码如下：

```python
def get_user_principals(self, user_id: str) -> set[str]:
    p = {f"user:{user_id}"}
    p |= {f"conv:{c.conv_id}" for c in self.conversations_of(user_id)}
    dept = self.user_dept(user_id)
    if dept:
        p.add(f"dept:{dept}")
    return p
```

接入企业 IM 时，只需按同一接口实现一个新的适配器，例如通过平台开放接口拉取会话与历史消息，通过事件回调或长连接接收实时消息，并把平台消息结构映射为 `Message`，上层模块无需任何修改。

### 6.2.3 机器人服务

机器人服务 `BotService` 包含两个并发协程：事件监听协程订阅 IM 事件流，在消息 @ 了知识助手或来自与知识助手的单聊时，异步调用智能体作答，并把回答与来源卡片发送回原会话；增量入库协程在新消息到达后等待 20 秒（防抖），然后批量执行增量同步，避免每条消息都触发一次入库。智能体的推理在线程池中执行，不阻塞事件循环。

## 6.3 多模态解析模块实现

解析调度器 `ParserDispatcher` 根据消息类型与附件扩展名选择解析器，单条消息解析失败时记录错误并返回占位文本，保证整体流程不中断：

```python
def parse(self, msg: Message) -> list[ParsedContent]:
    if msg.type == MsgType.TEXT or msg.attachment is None:
        return [ParsedContent(msg_id=msg.msg_id, modality=Modality.TEXT, text=msg.text)] if msg.text else []
    path, ext = Path(msg.attachment.path), Path(msg.attachment.path).suffix.lower()
    try:
        if msg.type == MsgType.IMAGE or ext in IMAGE_EXT:
            return self._image(msg, path)
        if msg.type == MsgType.AUDIO or ext in AUDIO_EXT:
            return self._audio(msg, path)
        if ext in SHEET_EXT:
            return self._sheet(msg, path)
        return self._document(msg, path, ext)
    except Exception as e:
        return [ParsedContent(msg_id=msg.msg_id, modality=Modality.TEXT,
                              text=f"【附件】{msg.attachment.name}（解析失败）", meta={"error": str(e)})]
```

**（1）图片解析。** OCR 使用 RapidOCR，识别结果包含文本框坐标、文字和置信度。实现中过滤置信度低于 0.5 的结果，按文本框左上角纵坐标以 12 像素为粒度聚合成行，再按横坐标排序，恢复阅读顺序。图片描述通过 OpenAI 兼容接口调用本地 Qwen2.5-VL 模型，图像以 Base64 编码嵌入请求中。VLM 调用失败时自动降级为仅使用 OCR 文本。

**（2）文档解析。** PDF 使用 PyMuPDF 逐页抽取文本层，同时以 110 DPI 渲染页面图像，用于视觉检索；若某页文本少于 50 个字符，判定为扫描页，对渲染图像执行 OCR。Word 文档按 XML 元素顺序遍历段落与表格：遇到标题样式的段落时更新章节路径并输出前一节的内容，遇到表格时转为数据框并按表格方式序列化。PPT 以页为单位抽取标题、文本框、表格与备注。

**（3）表格解析。** 使用 pandas 读取 Excel 的全部工作表或 CSV 文件，去除空行空列，把无名列重命名为“列 $i$”，每 15 行组成一个分块，按 4.1.2 节的方式序列化。整数值的浮点数（如 5.0）格式化为整数，避免出现“5.0 人日”这类不自然的表达。

**（4）语音解析。** 使用 FunASR 加载 `paraformer-zh` 中文识别模型、`fsmn-vad` 语音端点检测模型和 `ct-punc` 标点恢复模型，在 CPU 上推理。为避免语音模型依赖库与向量库 gRPC 客户端及 MPS 计算上下文在同一进程中相互干扰，系统默认通过独立子进程执行语音转写（并解析绝对文件路径），子进程内通过缓存单例复用模型实例（也对应生产环境中可水平扩展的独立 ASR 推理服务）。

## 6.4 知识构建模块实现

### 6.4.1 BGE-M3 向量化

为避免依赖与新版 Transformers 不兼容的第三方封装库，本文基于 Transformers 直接实现了 BGE-M3 的稠密与稀疏编码，计算方式与官方实现一致：稠密向量取最后一层 [CLS] 位置的隐状态并做 L2 归一化；稀疏向量由各词元隐状态经官方发布的线性层与 ReLU 得到权重，同一词元 ID 取最大值，并去除特殊符号。在 Apple Silicon（MPS）和 CUDA 设备上，编码器主干以 `float16` 半精度加载以减少显存占用并提升吞吐，线性稀疏映射层保持 `float32` 数值精度；批量编码时先按文本长度排序，减少填充带来的计算浪费。关键代码如下：

```python
with torch.no_grad():
    h = model(**enc).last_hidden_state
    dense = torch.nn.functional.normalize(h[:, 0], dim=-1)          # 稠密向量
    w = torch.relu(self._sparse(h)).squeeze(-1)                      # 词元权重
for tid, wt, m in zip(ids[r], w[r], mask[r]):
    if m and tid not in self._special and wt > 0:
        sparse[int(tid)] = max(sparse.get(int(tid), 0.0), float(wt))  # 同一词元取最大
```

### 6.4.2 话题切分与 MKU 构建

话题切分器 `TopicSegmenter` 按算法 4.1 实现。活跃话题以数据类保存消息 ID 列表、发言人列表、质心向量和起止时间，质心按式（4.3）更新。低信息量消息通过正则表达式识别，涵盖“好的、收到、明白、+1、谢谢、辛苦了”等常见应答。为便于对比实验，同一模块中还实现了固定窗口切分器 `FixedWindowSegmenter` 作为基线。

知识单元构建器 `MKUBuilder` 对每个话题生成会话单元与附件单元。话题摘要通过大模型的 JSON 输出模式获得，提示词要求输出标题、摘要和关键词。知识单元 ID 由话题 ID、单元类型与窗口序号的哈希值生成，保证重复构建时 ID 稳定，从而支持幂等的增量更新。

### 6.4.3 入库流水线与增量更新

入库流水线 `Ingestor` 的 `sync_from_adapter` 方法遍历适配器返回的会话，读取同步水位，拉取新消息并下载附件，然后调用 `ingest_conversation` 完成解析、切分、构建与索引。增量更新的核心逻辑如下：

```python
start = 0.0 if since_ts <= 0 else since_ts - self.segmenter.window      # 回溯活跃窗口
msgs = self.db.get_messages(conv.conv_id, since_ts=start)
topics = self.segmenter.segment(conv.conv_id, msgs, texts, vecs)
old_topic_ids = self._topics_containing({m.msg_id for m in msgs})       # 受影响的旧话题
self.vs.delete(self.db.delete_mkus_of_topics(old_topic_ids))            # 删除旧 MKU 与向量
mkus = [u for tp in topics for u in self.builder.build(conv, tp, mdict, parsed)]
self.index_mkus(mkus)                                                   # 写入新 MKU 与索引
```

## 6.5 混合检索模块实现

### 6.5.1 向量库与权限过滤

向量库封装类 `VectorStore` 在初始化时按表 5.5 创建 `mku_text` 与 `mku_visual` 两个集合，并显式加载集合（`load_collection`）。工程实现中针对 macOS 环境下 Milvus Lite 内核与 PyTorch MPS 的并发兼容性，在 `VectorStore` 初始化建立 Milvus 连接之前预先执行一次轻量 MPS 张量上下文初始化，以防止 gRPC/进程派生后的 Metal 上下文段错误。权限过滤表达式的生成代码如下，其中 `None` 表示管理员或离线评测模式，不做过滤；空集合表示用户没有任何权限，此时生成一个永远不成立的条件：

```python
def acl_expr(principals):
    if principals is None:
        return ""
    if not principals:
        return 'mku_id == "__none__"'
    plist = ", ".join(f'"{p}"' for p in sorted(principals))
    return f"array_contains_any(acl, [{plist}])"
```

该表达式与时间范围、会话范围等过滤条件以 `and` 连接后，作为 `filter` 参数传入 Milvus 的 `search` 接口，在近似最近邻搜索过程中生效。

### 6.5.2 BM25 索引

BM25 索引基于 rank_bm25 实现，文本经 jieba 搜索引擎模式分词并去除停用词；为每个文档记录 ACL 集合，同时构建“词项→文档”的倒排表。检索时只对至少命中一个查询词的文档按 BM25 分数排序，并过滤无权访问的文档。这样处理也避免了小规模语料中逆文档频率为负导致的排序异常。

### 6.5.3 混合检索器

混合检索器 `HybridRetriever` 通过配置对象 `RetrievalConfig` 控制各通路、重排、时效衰减与权限过滤的开关以及各通路的召回数量和融合权重，`retrieve` 方法返回 Top-$N$ 结果和各阶段耗时。融合与重排的核心代码如下：

```python
fused = rrf(lists, weights=cfg.weights)[: cfg.rerank_pool]            # 加权 RRF，式（4.6）
mkus = self.db.get_mkus([d for d, _, _ in fused])
hits = [Hit(mku=mkus[d], score=s, sources=src) for d, s, src in fused if d in mkus]
if p is not None:                                                     # 二次 ACL 校验
    hits = [h for h in hits if set(h.mku.acl) & p]
scores = get_reranker().score(query, [h.mku.content for h in hits])  # 交叉编码器重排
for h, s in zip(hits, scores):
    h.score = (1 - lam) * s + lam * time_decay(h.mku.ts_end, now)     # 时效衰减，式（4.7）
```

重排模型同样基于 Transformers 直接实现：在 MPS/CUDA 设备上以 `float16` 半精度加载 `BGE-Reranker-v2-M3`，把（查询，文档）对拼接编码，取分类头输出的 logit 并经 Sigmoid 映射为 $[0,1]$ 的相关性分数；并提供面向成对文本的批量打分接口 `score_pairs`。在苹果 M 芯片 MPS 后端实测表明，半精度推理将重排耗时从单精度（FP32）的约 6.75 s 缩短至 2.17 s（加速约 3.1 倍），相关性得分输出保持一致。为控制计算量，文档内容截断为前 1500 个字符，最大序列长度为 512。

## 6.6 Agent 编排与问答模块实现

### 6.6.1 状态图构建

智能体基于 LangGraph 的 `StateGraph` 实现，状态类型 `AgentState` 为 `TypedDict`，各节点函数接收当前状态并返回需要更新的字段。图的构建代码如下：

```python
g = StateGraph(AgentState)
for name in ("understand", "retrieve", "reflect", "generate", "verify", "chitchat", "clarify"):
    g.add_node(name, getattr(self, name))
g.set_entry_point("understand")
g.add_conditional_edges("understand", self._route_understand)        # 闲聊 / 澄清 / 检索
g.add_edge("retrieve", "reflect")
g.add_conditional_edges("reflect", lambda s: "retrieve"
    if s["reflection"].get("next_action") == "search" and s["iters"] < self.cfg.max_iters
    else "generate")                                                  # 重检或生成
g.add_edge("generate", "verify")
g.add_edge("verify", END)
```

### 6.6.2 大模型调用与思考模式控制

大模型客户端 `LLMClient` 通过 OpenAI 兼容的 `/chat/completions` 接口调用本地模型，支持 JSON 输出模式和图像输入。Qwen3 默认开启思考模式，会显著增加查询理解、反思等结构化任务的延迟。实现中对这类任务在请求中设置 `reasoning_effort: "none"` 关闭思考，实测一个简单的结构化输出请求的耗时由约 8 秒降至 0.5 秒左右。JSON 解析采用容错策略：从返回文本中提取第一个完整的 JSON 对象，解析失败时返回空字典，由各节点使用默认值兜底。

### 6.6.3 引用校验与来源卡片

引用校验节点按句末标点切分回答，提取每句中的引用编号，将全部待检“句子—证据”对汇总后单次调用重排模型的批量接口 `score_pairs` 计算支撑度，删除支撑度过低的引用并剔除越界编号，从而避免逐句串行重排带来的重复推理延迟。最终保留的编号被映射为 `Citation` 对象，包含知识单元 ID、会话 ID、证据消息 ID 和内容摘要。机器人服务在发送回复时把引用组装为来源卡片，附带来源会话名称、发送人、发送时间以及附件信息，前端据此渲染可点击的来源列表。

## 6.7 前端界面实现

前端采用 Vue 3 与 Element Plus 开发，依赖库以静态文件形式随系统发布，不依赖外部内容分发网络，满足内网部署要求。界面包括 IM 模拟器和管理后台两部分。

### 6.7.1 IM 模拟器与问答界面

IM 模拟器界面如图 6.1 所示：左侧为会话列表，顶部可以切换当前身份以模拟不同员工；中间为消息区，支持图片预览、文件下载、语音播放和引用回复；底部为输入区，支持发送文本与附件。员工在群聊中输入“@小知”加问题即可提问，或在“小知”单聊中直接提问。

![](figs/fig6_1_im_chat.png)

图 6.1 IM 模拟器群聊界面

知识助手的回答以 Markdown 渲染，引用编号以上标形式高亮显示；回答下方为来源卡片列表，展示每条来源的会话、发送人、时间、附件名和内容摘要，点击后自动切换到来源会话并高亮定位原始消息，如图 6.2 所示。若当前用户不在来源会话中，系统提示无法跳转。

![](figs/fig6_2_qa_card.png)

图 6.2 知识助手回答与来源卡片

### 6.7.2 管理后台

管理后台如图 6.3 所示，顶部为统计卡片，包括会话数、消息数、话题数、知识单元数、文本与视觉向量数、问答次数、用户反馈和平均响应时间；中部提供“增量同步入库”和“全量重建”操作；下方为知识单元浏览和问答日志两个标签页。知识单元浏览支持按会话、类型和关键词筛选，展示单元的模态、标题、内容、证据数量和 ACL；问答日志展示每次问答的提问者、问题、回答、耗时和反馈，展开后可查看完整的智能体推理轨迹，包括查询理解结果、每轮检索的查询与 Top 结果、反思判断以及引用校验情况，便于管理员分析问题和调优系统。

![](figs/fig6_3_admin.png)

图 6.3 管理后台

## 6.8 本章小结

本章介绍了系统的开发与运行环境以及各模块的实现：IM 接入模块通过统一数据模型和适配器抽象实现平台解耦，并实现了 IM 模拟器与机器人服务；多模态解析模块实现了图片、文档、表格与语音的解析；知识构建模块基于 Transformers 实现了 BGE-M3 编码，并实现了话题切分、知识单元构建与增量入库；混合检索模块实现了权限过滤下推、BM25 倒排检索以及融合、重排与时效衰减；智能体模块基于 LangGraph 实现了检索规划状态图、思考模式控制与引用校验；前端实现了 IM 模拟器与管理后台。
