## 参考文献候选清单：主表 75 条 + 备选 12 条

我用 search_web 逐条检索过。主表和备选表里每一条的标题、作者、发表处和年份，都在 arXiv、ACL Anthology、出版社或会议官网上查到了。少数条目的页码、首字母缩写和"等"之前的作者顺序是凭记忆补的，这些都列在最后的说明里。

**格式约定（全文统一）：**
- 期刊用 [J]，会议用 [C]//会议名，技术报告用 [R]。
- 预印本统一写成"[J]. arXiv preprint arXiv:xxxx.xxxxx, 年."。
- 作者超过 3 人时，列前 3 人再加"et al."；中文文献用"等"。

---

### A. 企业知识管理 / 企业搜索 / IM 协作中的知识沉淀（6）
[A1] Nonaka I. A dynamic theory of organizational knowledge creation[J]. Organization Science, 1994, 5(1): 14-37.｜SECI 知识转化模型（隐性→显性），说明 IM 群聊中的隐性知识需要被"外化"，用在绪论/研究背景｜https://doi.org/10.1287/orsc.5.1.14
[A2] Alavi M, Leidner D E. Review: Knowledge management and knowledge management systems: Conceptual foundations and research issues[J]. MIS Quarterly, 2001, 25(1): 107-136.｜KMS 的创造、存储/检索、转移、应用四过程框架，用在第 2 章相关工作｜https://doi.org/10.2307/3250961
[A3] Hawking D. Challenges in enterprise search[C]//Proceedings of the 15th Australasian Database Conference (ADC 2004). CRPIT 27. Australian Computer Society, 2004: 15-24.｜企业搜索的经典挑战，包括异构数据源、安全裁剪（ACL）和评测困难，用在绪论/相关工作｜https://dl.acm.org/doi/10.5555/1012294.1012297
[A4] Leonardi P M, Huysman M, Steinfield C. Enterprise social media: Definition, history, and prospects for the study of social technologies in organizations[J]. Journal of Computer-Mediated Communication, 2013, 19(1): 1-19.｜企业社交媒体/IM 的定义，以及"可见性、持久性"使聊天记录成为知识资产，用在研究背景｜https://doi.org/10.1111/jcc4.12029
[A5] Chatterjee P, Damevski K, Kraft N A, et al. Software-related Slack chats with disentangled conversations[C]//Proceedings of the 17th International Conference on Mining Software Repositories (MSR 2020, Data Showcase). ACM, 2020.｜Slack 群聊解缠数据集（3.9 万会话），说明可以从 IM 中挖掘知识，用在相关工作和会话切分一节｜https://doi.org/10.1145/3379597.3387493
[A6] Akkiraju R, Xu A, Bora D, et al. FACTS about building retrieval augmented generation-based chatbots[J]. arXiv preprint arXiv:2407.07858, 2024.｜NVIDIA 企业 RAG 聊天机器人的实践经验，涉及新鲜度、架构、成本、测试和安全（文档级 ACL），用在需求分析/系统设计｜https://arxiv.org/abs/2407.07858

### B. 大语言模型基础（7）
[B1] Vaswani A, Shazeer N, Parmar N, et al. Attention is all you need[C]//Advances in Neural Information Processing Systems 30 (NeurIPS 2017). 2017: 5998-6008.｜Transformer 架构，用在第 2 章基础理论｜https://arxiv.org/abs/1706.03762
[B2] Brown T, Mann B, Ryder N, et al. Language models are few-shot learners[C]//Advances in Neural Information Processing Systems 33 (NeurIPS 2020). 2020: 1877-1901.｜GPT-3 与上下文学习，用在第 2 章 LLM 概述｜https://arxiv.org/abs/2005.14165
[B3] Ouyang L, Wu J, Jiang X, et al. Training language models to follow instructions with human feedback[C]//Advances in Neural Information Processing Systems 35 (NeurIPS 2022). 2022: 27730-27744.｜InstructGPT/RLHF 指令对齐，用在第 2 章｜https://arxiv.org/abs/2203.02155
[B4] Touvron H, Lavril T, Izacard G, et al. LLaMA: Open and efficient foundation language models[J]. arXiv preprint arXiv:2302.13971, 2023.｜开源基座模型，私有化部署的前提，用在第 2 章和部署章节｜https://arxiv.org/abs/2302.13971
[B5] Yang A, Yang B, Zhang B, et al. Qwen2.5 technical report[J]. arXiv preprint arXiv:2412.15115, 2024.｜Qwen2.5 系列（18T tokens，0.5B–72B），系统生成模型的选型依据，用在系统实现/部署｜https://arxiv.org/abs/2412.15115
[B6] Yang A, Li A, Yang B, et al. Qwen3 technical report[J]. arXiv preprint arXiv:2505.09388, 2025.｜思考/非思考统一模式与思考预算，支撑 Agent 推理规划的模型选型，用在系统实现｜https://arxiv.org/abs/2505.09388
[B7] Guo D, Yang D, Zhang H, et al. DeepSeek-R1: Incentivizing reasoning capability in LLMs via reinforcement learning[J]. arXiv preprint arXiv:2501.12948, 2025.（期刊版：Nature, 2025, 645: 633-638）｜纯 RL 激发长链推理，用在第 2 章推理模型和 Agent 背景｜https://arxiv.org/abs/2501.12948

### C. 检索增强生成 RAG（13）
[C1] Lewis P, Perez E, Piktus A, et al. Retrieval-augmented generation for knowledge-intensive NLP tasks[C]//Advances in Neural Information Processing Systems 33 (NeurIPS 2020). 2020: 9459-9474.｜RAG 范式的开山之作（DPR+BART），用在第 2 章 RAG 基础｜https://arxiv.org/abs/2005.11401
[C2] Guu K, Lee K, Tung Z, et al. REALM: Retrieval-augmented language model pre-training[C]//Proceedings of the 37th International Conference on Machine Learning (ICML 2020). PMLR 119, 2020: 3929-3938.｜预训练阶段引入隐式检索器，用在第 2 章｜https://arxiv.org/abs/2002.08909
[C3] Karpukhin V, Oguz B, Min S, et al. Dense passage retrieval for open-domain question answering[C]//Proceedings of EMNLP 2020. ACL, 2020: 6769-6781.｜双塔稠密检索 DPR，"稠密路"的理论基础，用在第 2 章/第 4 章｜https://aclanthology.org/2020.emnlp-main.550/
[C4] Gao Y, Xiong Y, Gao X, et al. Retrieval-augmented generation for large language models: A survey[J]. arXiv preprint arXiv:2312.10997, 2023.｜Naive/Advanced/Modular RAG 三阶段综述，用在绪论国内外现状｜https://arxiv.org/abs/2312.10997
[C5] 刘雪颖, 云静, 李博, 等. 基于大型语言模型的检索增强生成综述[J]. 计算机工程与应用, 2025, 61(13): 1-25.｜中文 RAG 综述，用在绪论国内研究现状｜http://cea.ceaj.org/（期刊官网，按篇名检索）
[C6] Asai A, Wu Z, Wang Y, et al. Self-RAG: Learning to retrieve, generate, and critique through self-reflection[C]//The Twelfth International Conference on Learning Representations (ICLR 2024). 2024.｜用反思 token 判断是否检索、相关性和支撑度，是"检索充分性自反思"的直接依据，用在第 4/5 章｜https://arxiv.org/abs/2310.11511
[C7] Yan S Q, Gu J C, Zhu Y, et al. Corrective retrieval augmented generation[J]. arXiv preprint arXiv:2401.15884, 2024.｜轻量检索评估器加纠错动作（正确/模糊/错误），用在自反思和重检索设计｜https://arxiv.org/abs/2401.15884
[C8] Gao L, Ma X, Lin J, et al. Precise zero-shot dense retrieval without relevance labels[C]//Proceedings of ACL 2023. ACL, 2023: 1762-1777.｜HyDE 假设文档嵌入，用在查询扩展/改写一节｜https://aclanthology.org/2023.acl-long.99/
[C9] Sarthi P, Abdullah S, Tuli A, et al. RAPTOR: Recursive abstractive processing for tree-organized retrieval[C]//ICLR 2024. 2024.｜递归聚类摘要树形索引，可参考用于长会话/长文档的多粒度索引｜https://arxiv.org/abs/2401.18059
[C10] Edge D, Trinh H, Cheng N, et al. From local to global: A graph RAG approach to query-focused summarization[J]. arXiv preprint arXiv:2404.16130, 2024.｜GraphRAG 社区摘要，用在相关工作中的结构化 RAG 对比｜https://arxiv.org/abs/2404.16130
[C11] Jeong S, Baek J, Cho S, et al. Adaptive-RAG: Learning to adapt retrieval-augmented large language models through question complexity[C]//Proceedings of NAACL 2024. ACL, 2024: 7036-7050.｜按问题复杂度路由（不检索/单步/多步），用在 Agent 检索规划｜https://aclanthology.org/2024.naacl-long.389/
[C12] Singh A, Ehtesham A, Kumar S, et al. Agentic retrieval-augmented generation: A survey on agentic RAG[J]. arXiv preprint arXiv:2501.09136, 2025.｜Agentic RAG 分类（路由、多智能体、纠错、自适应），用在绪论和第 2 章｜https://arxiv.org/abs/2501.09136
[C13] Liu N F, Lin K, Hewitt J, et al. Lost in the middle: How language models use long contexts[J]. Transactions of the Association for Computational Linguistics, 2024, 12: 157-173.｜长上下文的 U 型位置效应，支撑重排后截断与上下文排序策略，用在生成模块设计｜https://aclanthology.org/2024.tacl-1.9/

### D. 检索技术（10）
[D1] Robertson S, Zaragoza H. The probabilistic relevance framework: BM25 and beyond[J]. Foundations and Trends in Information Retrieval, 2009, 3(4): 333-389.｜BM25 理论，"稀疏路"的基线，用在第 2 章｜https://doi.org/10.1561/1500000019
[D2] Khattab O, Zaharia M. ColBERT: Efficient and effective passage search via contextualized late interaction over BERT[C]//Proceedings of SIGIR 2020. ACM, 2020: 39-48.｜后期交互多向量检索，也是 ColPali 的基础，用在第 2 章｜https://arxiv.org/abs/2004.12832
[D3] Chen J, Xiao S, Zhang P, et al. M3-Embedding: Multi-linguality, multi-functionality, multi-granularity text embeddings through self-knowledge distillation[C]//Findings of ACL 2024. ACL, 2024: 2318-2335.｜BGE-M3 同时输出稠密、稀疏和多向量，是系统稠密+稀疏两路的核心模型，用在第 4 章｜https://aclanthology.org/2024.findings-acl.137/
[D4] Xiao S, Liu Z, Zhang P, et al. C-Pack: Packed resources for general Chinese embeddings[C]//Proceedings of SIGIR 2024. ACM, 2024: 641-649.｜C-MTEB 中文评测基准和 BGE 模型，用在中文向量模型选型和评测｜https://arxiv.org/abs/2309.07597
[D5] Cormack G V, Clarke C L A, Buettcher S. Reciprocal rank fusion outperforms Condorcet and individual rank learning methods[C]//Proceedings of SIGIR 2009. ACM, 2009: 758-759.｜RRF 融合公式（k=60），三路融合的直接依据，用在第 4 章｜https://doi.org/10.1145/1571941.1572114
[D6] Nogueira R, Cho K. Passage re-ranking with BERT[J]. arXiv preprint arXiv:1901.04085, 2019.｜monoBERT 交叉编码器重排，用在重排模块｜https://arxiv.org/abs/1901.04085
[D7] Malkov Y A, Yashunin D A. Efficient and robust approximate nearest neighbor search using hierarchical navigable small world graphs[J]. IEEE Transactions on Pattern Analysis and Machine Intelligence, 2020, 42(4): 824-836.｜HNSW 近似最近邻索引，用在向量索引选型｜https://arxiv.org/abs/1603.09320
[D8] Wang J, Yi X, Guo R, et al. Milvus: A purpose-built vector data management system[C]//Proceedings of SIGMOD 2021. ACM, 2021: 2614-2627.｜Milvus 架构，支持标量过滤混合查询，权限过滤可以借此下推，用在系统实现｜https://doi.org/10.1145/3448016.3457550
[D9] Izacard G, Caron M, Hosseini L, et al. Unsupervised dense information retrieval with contrastive learning[J]. Transactions on Machine Learning Research, 2022.｜Contriever 无监督对比学习检索器，用在第 2 章｜https://arxiv.org/abs/2112.09118
[D10] Wang L, Yang N, Huang X, et al. Text embeddings by weakly-supervised contrastive pre-training[J]. arXiv preprint arXiv:2212.03533, 2022.｜E5 嵌入模型，可作为对比基线｜https://arxiv.org/abs/2212.03533

### E. 多模态（17）
[E1] Radford A, Kim J W, Hallacy C, et al. Learning transferable visual models from natural language supervision[C]//Proceedings of ICML 2021. PMLR 139, 2021: 8748-8763.｜CLIP 图文对比学习，"视觉路"基础，用在第 2 章｜https://arxiv.org/abs/2103.00020
[E2] Yang A, Pan J, Lin J, et al. Chinese CLIP: Contrastive vision-language pretraining in Chinese[J]. arXiv preprint arXiv:2211.01335, 2022.｜中文图文检索模型，适合中文截图检索｜https://arxiv.org/abs/2211.01335
[E3] Li J, Li D, Savarese S, et al. BLIP-2: Bootstrapping language-image pre-training with frozen image encoders and large language models[C]//Proceedings of ICML 2023. PMLR 202, 2023: 19730-19742.｜Q-Former 连接视觉编码器与 LLM，用在第 2 章 VLM 发展｜https://arxiv.org/abs/2301.12597
[E4] Liu H, Li C, Wu Q, et al. Visual instruction tuning[C]//Advances in Neural Information Processing Systems 36 (NeurIPS 2023). 2023.｜LLaVA 视觉指令微调，用在第 2 章｜https://arxiv.org/abs/2304.08485
[E5] Wang P, Bai S, Tan S, et al. Qwen2-VL: Enhancing vision-language model's perception of the world at any resolution[J]. arXiv preprint arXiv:2409.12191, 2024.｜动态分辨率与 M-RoPE，用在截图转写模型选型｜https://arxiv.org/abs/2409.12191
[E6] Bai S, Chen K, Liu X, et al. Qwen2.5-VL technical report[J]. arXiv preprint arXiv:2502.13923, 2025.｜文档解析、OCR 与定位能力，系统 VLM 转写模块用的模型，用在第 4 章｜https://arxiv.org/abs/2502.13923
[E7] Faysse M, Sibille H, Wu T, et al. ColPali: Efficient document retrieval with vision language models[C]//The Thirteenth International Conference on Learning Representations (ICLR 2025). 2025.｜免 OCR 的页面图像多向量检索，同时提出 ViDoRe 基准，"视觉路"检索与评测都用得上｜https://arxiv.org/abs/2407.01449
[E8] Yu S, Tang C, Xu B, et al. VisRAG: Vision-based retrieval-augmented generation on multi-modality documents[C]//ICLR 2025. 2025.｜基于 VLM 的检索与生成，避免解析损失，用在多模态 RAG 相关工作｜https://arxiv.org/abs/2410.10594
[E9] Cho J, Mahata D, Irsoy O, et al. M3DocRAG: Multi-modal retrieval is what you need for multi-page multi-document understanding[J]. arXiv preprint arXiv:2411.04952, 2024.｜ColPali+Qwen2-VL 的多页多文档 RAG，用在相关工作和方案对比｜https://arxiv.org/abs/2411.04952
[E10] Abootorabi M M, Zobeiri A, Dehghani M, et al. Ask in any modality: A comprehensive survey on multimodal retrieval-augmented generation[C]//Findings of ACL 2025. ACL, 2025.｜多模态 RAG 综述，用在绪论国内外现状｜https://aclanthology.org/2025.findings-acl.861/
[E11] Mathew M, Karatzas D, Jawahar C V. DocVQA: A dataset for VQA on document images[C]//Proceedings of WACV 2021. IEEE, 2021: 2200-2209.｜文档图像问答基准，用在评测和相关工作｜https://arxiv.org/abs/2007.00398
[E12] Huang Y, Lv T, Cui L, et al. LayoutLMv3: Pre-training for document AI with unified text and image masking[C]//Proceedings of the 30th ACM International Conference on Multimedia (MM 2022). ACM, 2022: 4083-4091.｜版面理解预训练，用在版面解析一节｜https://arxiv.org/abs/2204.08387
[E13] Du Y, Li C, Guo R, et al. PP-OCR: A practical ultra lightweight OCR system[J]. arXiv preprint arXiv:2009.09941, 2020.｜PaddleOCR 核心（检测、方向分类、识别），用在 OCR 转写模块｜https://arxiv.org/abs/2009.09941
[E14] Wang B, Xu C, Zhao X, et al. MinerU: An open-source solution for precise document content extraction[J]. arXiv preprint arXiv:2409.18839, 2024.｜PDF 版面、公式、表格解析成 Markdown，用在文档附件解析模块｜https://arxiv.org/abs/2409.18839
[E15] Radford A, Kim J W, Xu T, et al. Robust speech recognition via large-scale weak supervision[C]//Proceedings of ICML 2023. PMLR 202, 2023: 28492-28518.｜Whisper 多语种 ASR，用在语音转写对比方案｜https://arxiv.org/abs/2212.04356
[E16] Gao Z, Zhang S, McLoughlin I, et al. Paraformer: Fast and accurate parallel transformer for non-autoregressive end-to-end speech recognition[C]//Proceedings of Interspeech 2022. ISCA, 2022: 2063-2067.｜非自回归中文 ASR，系统语音转写主模型，用在第 4 章｜https://arxiv.org/abs/2206.08317
[E17] Gao Z, Li Z, Wang J, et al. FunASR: A fundamental end-to-end speech recognition toolkit[C]//Proceedings of Interspeech 2023. ISCA, 2023: 1593-1597.｜VAD、ASR、标点、时间戳全链路工具包，用在系统实现｜https://arxiv.org/abs/2305.11013

### F. Agent（8）
[F1] Yao S, Zhao J, Yu D, et al. ReAct: Synergizing reasoning and acting in language models[C]//The Eleventh International Conference on Learning Representations (ICLR 2023). 2023.｜Thought-Action-Observation 循环，Agent 检索规划的核心范式，用在第 2/5 章｜https://arxiv.org/abs/2210.03629
[F2] Schick T, Dwivedi-Yu J, Dessì R, et al. Toolformer: Language models can teach themselves to use tools[C]//NeurIPS 36. 2023.｜LLM 自主学习调用 API，是工具调用的理论来源｜https://arxiv.org/abs/2302.04761
[F3] Shinn N, Cassano F, Gopinath A, et al. Reflexion: Language agents with verbal reinforcement learning[C]//NeurIPS 36. 2023.｜语言化自我反思，用在检索充分性反思机制｜https://arxiv.org/abs/2303.11366
[F4] Wei J, Wang X, Schuurmans D, et al. Chain-of-thought prompting elicits reasoning in large language models[C]//NeurIPS 35. 2022: 24824-24837.｜思维链，用在第 2 章推理基础｜https://arxiv.org/abs/2201.11903
[F5] Wang L, Ma C, Feng X, et al. A survey on large language model based autonomous agents[J]. Frontiers of Computer Science, 2024, 18(6): 186345.｜Agent 四模块框架（画像、记忆、规划、行动），用在第 2 章｜https://arxiv.org/abs/2308.11432
[F6] Qin Y, Liang S, Ye Y, et al. ToolLLM: Facilitating large language models to master 16000+ real-world APIs[C]//ICLR 2024. 2024.｜工具学习与 API 检索，可参考用于函数调用/工具注册设计｜https://arxiv.org/abs/2307.16789
[F7] Li X, Dong G, Jin J, et al. Search-o1: Agentic search-enhanced large reasoning models[J]. arXiv preprint arXiv:2501.05366, 2025.｜推理过程中按需检索，加 Reason-in-Documents 去噪，用在检索型 Agent 相关工作｜https://arxiv.org/abs/2501.05366
[F8] Jin B, Zeng H, Yue Z, et al. Search-R1: Training LLMs to reason and leverage search engines with reinforcement learning[J]. arXiv preprint arXiv:2503.09516, 2025.｜RL 训练多轮检索推理，用在相关工作和未来工作｜https://arxiv.org/abs/2503.09516

### G. 会话解缠 / 话题切分 / 查询改写（5）
[G1] Elsner M, Charniak E. You talking to me? A corpus and algorithm for conversation disentanglement[C]//Proceedings of ACL-08: HLT. ACL, 2008: 834-842.｜IRC 会话解缠的首个语料与图聚类算法，用在会话切分一节｜https://aclanthology.org/P08-1095/
[G2] Kummerfeld J K, Gouravajhala S R, Peper J J, et al. A large-scale corpus for conversation disentanglement[C]//Proceedings of ACL 2019. ACL, 2019: 3846-3856.｜Ubuntu IRC 7.7 万条回复图标注，解缠的主流基准，用在会话切分方法与评测｜https://aclanthology.org/P19-1374/
[G3] Xing L, Carenini G. Improving unsupervised dialogue topic segmentation with utterance-pair coherence scoring[C]//Proceedings of SIGDIAL 2021. ACL, 2021: 167-177.｜BERT 语句对连贯性打分加 TextTiling 式切分，含中文数据集，可直接借鉴做话题切分｜https://aclanthology.org/2021.sigdial-1.18/
[G4] Elgohary A, Peskov D, Boyd-Graber J. Can you unpack that? Learning to rewrite questions-in-context[C]//Proceedings of EMNLP-IJCNLP 2019. ACL, 2019: 5918-5924.｜CANARD 对话式问题改写，用在多轮查询改写｜https://aclanthology.org/D19-1605/
[G5] Ma X, Gong Y, He P, et al. Query rewriting for retrieval-augmented large language models[C]//Proceedings of EMNLP 2023. ACL, 2023: 5303-5315.｜Rewrite-Retrieve-Read 框架，用在查询改写模块｜https://aclanthology.org/2023.emnlp-main.322/

### H. 评测（5）
[H1] Es S, James J, Espinosa-Anke L, et al. RAGAS: Automated evaluation of retrieval augmented generation[C]//Proceedings of EACL 2024: System Demonstrations. ACL, 2024: 150-158.｜忠实度、答案相关性、上下文精确率/召回率，用在实验评测指标｜https://aclanthology.org/2024.eacl-demo.16/
[H2] Saad-Falcon J, Khattab O, Potts C, et al. ARES: An automated evaluation framework for retrieval-augmented generation systems[C]//Proceedings of NAACL 2024. ACL, 2024: 338-354.｜合成数据训练评审模型加 PPI 置信区间，用在评测方法｜https://aclanthology.org/2024.naacl-long.20/
[H3] Zheng L, Chiang W L, Sheng Y, et al. Judging LLM-as-a-judge with MT-Bench and Chatbot Arena[C]//NeurIPS 36 Datasets and Benchmarks Track. 2023.｜LLM 评审的一致性及位置/冗长偏差，用在实验设计｜https://arxiv.org/abs/2306.05685
[H4] Huang L, Yu W, Ma W, et al. A survey on hallucination in large language models: Principles, taxonomy, challenges, and open questions[J]. ACM Transactions on Information Systems, 2025.｜幻觉分类（事实性/忠实性），用在绪论问题提出｜https://doi.org/10.1145/3703155
[H5] Gao T, Yen H, Yu J, et al. Enabling large language models to generate text with citations[C]//Proceedings of EMNLP 2023. ACL, 2023: 6465-6488.｜ALCE 引用召回率/精确率，用在可溯源生成与引用评测｜https://aclanthology.org/2023.emnlp-main.398/

### I. 访问控制 / 隐私 / 私有化部署（4）
[I1] Sandhu R S, Coyne E J, Feinstein H L, et al. Role-based access control models[J]. Computer, 1996, 29(2): 38-47.｜RBAC0–RBAC3 模型，群组/角色映射到 ACL 的理论依据，用在权限过滤设计｜https://doi.org/10.1109/2.485845
[I2] Zeng S, Zhang J, He P, et al. The good and the bad: Exploring privacy issues in retrieval-augmented generation (RAG)[C]//Findings of ACL 2024. ACL, 2024.｜RAG 检索库的泄露风险，说明需要检索前权限过滤，用在需求分析和安全设计｜https://arxiv.org/abs/2402.16893
[I3] Bhatt S S, Rajore T, Aggarwal K, et al. Enterprise AI must enforce participant-aware access control[J]. arXiv preprint arXiv:2509.14608, 2025.｜企业多用户 AI 应在检索和生成环节确定性地执行参与者感知的访问控制，与本文 ACL 过滤直接相关｜https://arxiv.org/abs/2509.14608
[I4] Kwon W, Li Z, Zhuang S, et al. Efficient memory management for large language model serving with PagedAttention[C]//Proceedings of SOSP 2023. ACM, 2023: 611-626.｜vLLM 推理服务，用在私有化部署实现｜https://arxiv.org/abs/2309.06180

---

### 备选（已核实，因为数量上限移出主表，可按需替换）（12）
- Treem J W, Leonardi P M. Social media use in organizations: Exploring the affordances of visibility, editability, persistence, and association[J]. Annals of the International Communication Association (Communication Yearbook 36), 2013.｜企业社交媒体的四种可供性（属 A 类）
- Zhao W X, Zhou K, Li J, et al. A survey of large language models[J]. arXiv preprint arXiv:2303.18223, 2023.｜https://arxiv.org/abs/2303.18223（属 B 类）
- DeepSeek-AI. DeepSeek-V3 technical report[R]. arXiv preprint arXiv:2412.19437, 2024.｜https://arxiv.org/abs/2412.19437（属 B 类）
- Jiang Z, Xu F F, Gao L, et al. Active retrieval augmented generation[C]//EMNLP 2023.｜FLARE，https://arxiv.org/abs/2305.06983（属 C 类）
- Trivedi H, Balasubramanian N, Khot T, et al. Interleaving retrieval with chain-of-thought reasoning for knowledge-intensive multi-step questions[C]//ACL 2023.｜IRCoT，https://aclanthology.org/2023.acl-long.557/（属 C 类）
- Xi Z, Chen W, Guo X, et al. The rise and potential of large language model based agents: A survey[J]. arXiv preprint arXiv:2309.07864, 2023.（属 F 类）
- Hearst M A. TextTiling: Segmenting text into multi-paragraph subtopic passages[J]. Computational Linguistics, 1997, 23(1): 33-64.｜https://aclanthology.org/J97-1003/（属 G 类）
- Elsner M, Charniak E. Disentangling chat[J]. Computational Linguistics, 2010, 36(3): 389-409.｜https://doi.org/10.1162/coli_a_00003（属 G 类）
- Chen J, Lin H, Han X, et al. Benchmarking large language models in retrieval-augmented generation[C]//AAAI 2024.｜RGB 中英双语基准，含拒答能力，https://arxiv.org/abs/2309.01431（属 H 类）
- Hu V C, Ferraiolo D, Kuhn R, et al. Guide to attribute based access control (ABAC) definition and considerations: NIST SP 800-162[R]. Gaithersburg: NIST, 2014.｜https://doi.org/10.6028/NIST.SP.800-162（属 I 类）
- Zou W, Geng R, Wang B, et al. PoisonedRAG: Knowledge corruption attacks to retrieval-augmented generation of large language models[C]//USENIX Security 2025.｜https://arxiv.org/abs/2402.07867（属 I 类）
- Bu H, Du J, Na X, et al. AISHELL-1: An open-source Mandarin speech corpus and a speech recognition baseline[C]//O-COCOSDA 2017. IEEE, 2017: 1-5.｜https://arxiv.org/abs/1709.05522（属 E 类，中文 ASR 评测时可换回主表）

---

### 核实说明（把握较低之处）
1. **页码基本凭记忆，未逐条检索：**
   - 会议论文的页码基本来自我的记忆，没有逐条通过检索确认。期刊卷期页码（Nonaka、Alavi、Hawking、HNSW、BM25、Sandhu、Elsner 2010）是检索确认过的。
   - 定稿前建议到 DBLP 或 ACL Anthology 核对一遍页码。可疑度较高的有：A4 JCMC 19(1):1-19、C11、D3、D4、D8、G3、H1、H2、I4 等。
   - [C5] 的 2025, 61(13): 1-25 来自检索结果摘要，建议在知网复核。
2. **作者顺序有凭记忆补全的部分：**
   - 一作和标题都已检索确认。
   - 第 2、3 作者凭记忆填写的有：A6（Xu A, Bora D）、B6（Li A）、D3、E5、E6、E7、E8、E13、E14、E17、F7、F8、I2（He P）、H4（Yu W, Ma W）。
   - 只拿到一作或团队名的：B5/B6（Qwen Team），B7 检索结果给出的是 Liang Wenfeng、Guo Daya 等。
3. **[B7] 期刊版标题与 arXiv 不同：** Nature 正式版的标题是 "DeepSeek-R1 incentivizes reasoning in LLMs through reinforcement learning"，与 arXiv 版不同。我写的是 arXiv 标题，并在括注里给了 Nature 卷页，引用时二选一并保持一致。
4. **[A5] DOI 和 [A3] 的 ACM DL 链接是凭记忆写的**，标题、作者、会议都已确认，链接需要点开验证。[C5] 只给了期刊官网，没有直链。
5. **[I3] Bhatt et al. 2025 是较新的预印本**，作者列表来自 arXiv 检索结果。
6. **用户要的一项没有列出：** "LangGraph/函数调用"没有对应的同行评审论文，所以没列。如需要，可按 [EB/OL] 引用 LangGraph 官方文档或 OpenAI Function Calling 文档，注明访问日期即可。
7. **"已检索、未入表"的条目：**
   - 检索中出现但未独立核实、所以没有收录的：Permission-Aware RAG (Jeong & Lee, IEEE Access)、RAGent (arXiv:2409.07489)，以及检索结果里两篇 2026 年的 secure-RAG 综述。
   - 另外，《软件学报》2026 年《检索增强生成在软件工程中的应用综述》（张犬俊等）检索到了，但偏离本题，没有收录。