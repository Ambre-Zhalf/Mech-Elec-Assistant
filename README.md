# 机电学习助手(本地 Agent 版)

把讯飞星火低代码平台上的「机电学习助手」工作流,迁移为本地运行的代码 Agent:

- **后端**:Python + FastAPI,复刻原工作流全部节点(意图决策、问答、公司推荐、岗位检索、学习计划、知识图谱、档案与长期记忆)。
- **大模型**:全部使用 DeepSeek `deepseek-v4-flash`(模型名、API 地址可在 `.env` 修改)。
- **工具**:对外暴露 5 个工具:`verified_search`(真实链搜索)、`find_recruitment_links`(招聘入口发现)、`fetch_page`(读静态页)、`render_page`(渲染动态页)、`bilibili_search`(B站视频)。底层 `web_search`(百度优先,失败回退 Anspire → Bing)已收敛为**内部函数**,不再单独开放给大模型,由 `verified_search` 等内部调用。`parse_pdf`(PDF 识别)工具随识别功能一同**暂时下架**。
- **招聘入口发现**:列出岗位前先用“招聘入口发现”工具抓取公司官网主页导航中的真实“人才招聘 / 加入我们 / Careers”链接(如 mokahr、hotjob 等招聘平台),避免在官网下乱猜 `/zhaopin/`、`/talent/` 子路径;再用无头浏览器渲染抓取真实岗位。工具会先尝试**探测公司域名根**(`www.域名`/`域名`,要求页面与公司相关,避免误抓深交所/财经门户/品牌目录),再到官网主页导航里挖真实招聘入口;招聘平台(mokahr/hotjob/51job)、品牌目录站、行业门户等也可作为候选输出;内部默认“先快速 `web_search`,命中不了再自动升级 `verified_search`”;可在 `.env` 用 `FIND_RECRUIT_USE_VERIFIED=1` 强制全程真实性校验,或 `=off` 只保留快速搜索。
- **增强搜索**:默认内置联网搜索优先(百度 → Anspire → Bing);当大模型输出公司官网/招聘信息/B站视频等检索类内容后,回复下方出现浅蓝色 **“对搜索结果不满意?使用增强搜索”**,点击即可用 [Anspire AI Search](https://open.anspire.cn/document/docs/searchApi/) 再次检索,结果以可点击链接展示。
- **真实性检索(verified_search)**:凡涉及公司官网、招聘岗位、证书学习资源等对链接真实性要求高的检索,统一走 `verified_search` 工具,按 **“主搜 → 真实性审查 → free-search-mcp 多引擎回退 → 再审查 → 必要时 DeepSeek 联网 → 子项单独重搜”** 的链式顺序取数。真实性审查会先用**非流式 GET + 状态码 + 有限正文**判断“能否打开 + 是否相关 + 是否聚合/百科站”(避免流式读正文触发的连接重置);**黑名单按域名(host)匹配**,不再用 `news` 等宽泛子串误杀官网路径;若 `requests` 打不开(超时/WAF/JS),还会**用 Playwright 真浏览器**(`render_page`)二次确认。不通过就自动改用 [free-search-mcp](https://github.com/sweetcornna/free-search-mcp) 的多引擎 RRF 合并结果并再次初筛;仍失败再尝试 DeepSeek 联网(已在 `.env` 开启 `DEEPSEEK_WEB_SEARCH=1`,若你的 DeepSeek 端点不支持 `web_search` 工具该级会被自动跳过并记录)。`verified_search` 返回的 `verified=false` 或某子项存疑时,大模型会把该子项单独作为关键词重新搜索,绝不采用未核实链接。
- **竞赛推荐**:证书学习资料输出后,进入“竞赛环节”,智能体按“**根据你的专业和目标岗位**”推荐适合的竞赛,数据来自项目内 `data/gb/大学生工科竞赛榜单.xlsx`(路径固定,无需配置),按计算机类/电子信息类/其他工学类/机器人类/职业技能类分组展示;用户可继续询问某个竞赛的报名/内容/备赛建议。
- **前端**:蓝白简约风网页聊天界面,零构建,浏览器直接打开。
- **知识图谱**:学习计划生成后自动转换为与《计算机发展.json》一致的 nodes/edges JSON,回复中出现 **“一键导入知识图谱”** 按钮,点击即可导入本机知识图谱并自动跳转展示(内置 D3 力导向图,支持缩放、多布局、图谱管理与导入历史)。
- **图书**:左侧底部“图书”入口,支持图书搜索与 PDF 下载保存到“我的书籍”;“我的书籍”页面支持把电脑里的 PDF 直接拖拽上传并命名保存。下载时若某个共享账号到达每日 10 本额度,会自动切换下一个共享账号重试(readzn 共享账号池);若 readzn 一时不可用(超时/无法访问),会回退到直连下载,尽量保证仍能下载。
- **PDF 识别**:**⚠️ 暂时下架**。利用本机 MinerU 扫描 PDF 书籍(即“我的书籍”每本书的“识别”与“我的书籍(Markdown)”)已暂时下架,代码已注释保留;图书搜索、下载、上传到“我的书籍”、打开与删除等其余图书功能不受影响。

## 快速开始

```bash
# 1. 安装依赖(已安装可跳过)
pip install -r requirements.txt

# 2. 配置 API Key(已提供 .env;换 Key 时编辑它即可)
#    DEEPSEEK_API_KEY=sk-xxx

# 3. 启动
python app.py

# Linux/macOS 也可用一键脚本(Windows 用 start.bat):
#   ./run.sh
# 默认监听 127.0.0.1:8000;要对外访问再设:
#   export HOST=0.0.0.0   # (可选) export PORT=8000

# 4. 浏览器打开
http://localhost:8000
```

### 真实性检索回退(free-search-mcp,可选但推荐)

`verified_search` 的第二级回退依赖 [free-search-mcp](https://github.com/sweetcornna/free-search-mcp)。
它被安装到一个**隔离虚拟环境** `.venv-search`,不会污染机电助手的现有依赖:

```bash
python -m venv .venv-search
.venv-search\Scripts\python -m pip install free-search-mcp mcp
```

国内网络建议加镜像:

```bash
.venv-search\Scripts\python -m pip install --index-url https://mirrors.aliyun.com/pypi/simple/ free-search-mcp mcp
```

- 若这一步没装、或 `free_search` 被禁,`verified_search` 会自动跳过 free-search-mcp 回退,直接进入“必要时 DeepSeek 联网 / 如实标注未验证”,不影响主搜。
- 回退用引擎在 `.env` 的 `FREE_SEARCH_ENGINES` 配置(默认 `baidu,bing,duckduckgo`)。

### PDF 识别(本机完整版 MinerU)

> ⚠️ **暂时下架**：本功能(利用本机 MinerU 扫描 PDF 书籍 / “我的书籍”识别 / “我的书籍(Markdown)”)当前已下架,以下说明仅供恢复时参考。

纯文本型 PDF 直接用本地 PyMuPDF 读取,无需联网;扫描件/复杂排版调用本机 `mineru` CLI。

首次运行前需要下载模型权重(较大,取决于 `pipeline` 或 `vlm` 模型):

```bash
# 推荐:只下载 pipeline 模型(较省资源,够扫描件 OCR 用)
mineru-models-download -m pipeline
# 若要用 VLM/hybrid 高精度,则下载全部模型
mineru-models-download -m all
```

- 模型默认下载到 `~/.cache/mineru`(可用环境变量/配置修改)。
- 对 204 页这类大扫描书,CPU 解析较慢,可调大 `.env` 的 `MINERU_TIMEOUT`(默认 1200 秒)。
- 整个过程完全本地、离线、不上传文件,无需任何 token。

注意两点:

- **模型源**:国内 HuggingFace 不通,统一在 `.env` 里用 `MINERU_MODEL_SOURCE=local`
  (直接从 `mineru.json` 的 `models-dir.pipeline` 读本地模型,不联网、不加锁),
  下载模型时用国内源:`mineru-models-download -m pipeline -s modelscope`。
- **GPU 加速**:若显卡是 RTX 50 系(Blackwell,如 RTX 5060),需要把 torch 换成 CUDA 12.8 版:
  `pip install torch==2.8.0+cu128 --index-url https://download.pytorch.org/whl/cu128`
  (国内可用镜像 `https://mirror.sjtu.edu.cn/pytorch-wheels/cu128/`)。
- `mineru` CLI 在 Windows 上出结果后其托管 mineru-api 偶发不退出,代码已改为
  “等到 .md 输出后即结束进程树”,不会卡住。
- 若跑 OCR 报 `CUDA error: CUBLAS_STATUS_EXECUTION_FAILED`(显存不足),
  在 `.env` 设 `MINERU_VIRTUAL_VRAM_SIZE=4`,让 MinerU 以 batch_ratio=1 处理,避免 8GB 显存 OOM。

## 工作流说明

与原始 YAML 流程一一对应:

1. **开始**:接收用户输入,写入长期记忆。
2. **档案读取 + 记忆检索**:读取已保存的专业/城市/学校/意向公司/岗位;按关键词检索历史对话。
3. **意图决策**:判断进入「规划」分支(出现专业、学校、城市、公司、岗位等)还是「导师追问」分支(问课程难度、名词解释、调整计划等)。
4. **规划分支**(核心):
   - 问答节点:依次询问城市、学校、意向公司、意向岗位(有档案时提示确认)。
   - Agent「列出公司」:联网搜索,按「校招企业 / 城市知名机电企业 / 行业标杆」三类各推荐 ≥10 家,附推荐理由与来源链接。
   - Agent「列出岗位」:抓目标公司官网招聘页,结构化输出岗位名称、工作内容、学历与能力要求、地点/批次/截止日期;招聘子页面为 JS 动态渲染时,自动改用无头浏览器渲染抓取。
   - Agent「学习计划」:按大一到大四 8 个学期拆分,目标可衡量、禁止"熟练掌握"等空泛词;每个学习项调用 B站搜索,附播放量前三的视频链接。
   - 档案提取与保存:把专业/城市/学校/意向公司/岗位写入变量存储(本地 SQLite),后续对话直接复用。
   - 知识图谱:把计划内容提炼为 nodes/edges 的 JSON,随回复输出。
   - 一键导入:点击回复中的“一键导入知识图谱”,后端把 JSON 写入本地图谱库(data/graph.db),前端切换到内置知识图谱视图并自动加载展示。
5. **默认分支**:导师式答疑(DeepSeek),结合档案与历史记忆回复,不编造视频链接,只给搜索关键词。
6. **长期记忆**:每轮用户输入与 AI 回复均写入记忆库,下次对话可检索。

## 配置项(.env)

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `DEEPSEEK_API_KEY` | DeepSeek API Key(必填) | 无 |
| `DEEPSEEK_BASE_URL` | API 地址 | `https://api.deepseek.com/v1` |
| `DEEPSEEK_MODEL` | 模型名 | `deepseek-v4-flash` |
| `ANSPIRE_API_KEY` | Anspire AI Search 增强搜索 API Key(可选;配置后启用“增强搜索”) | 无 |
| `ANSPIRE_API_URL` | Anspire AI Search 接口地址 | `https://plugin.anspire.cn/api/ntsearch/search` |
| `ANSPIRE_TIMEOUT` | Anspire 请求超时(秒) | `30` |
| `SEARCH_ENGINE` | 联网搜索主引擎(`baidu`/`bing`/`duckduckgo`/`anspire`,失败自动依次回退) | `baidu` |
| `AGENT_MAX_TOOL_CALLS` | Agent 单次任务工具调用总量上限 | `30` |
| `TOOL_CAP_VERIFIED_SEARCH` | 真实链搜索(verified_search)次数上限 | `10` |
| `TOOL_CAP_FETCH_PAGE` | 网页读取次数上限 | `8` |
| `TOOL_CAP_BILIBILI` | B站搜索次数上限 | `14` |
| `TOOL_CAP_RENDER_PAGE` | 动态网页渲染次数上限 | `6` |
| `TOOL_CAP_FIND_RECRUIT` | 招聘入口发现次数上限 | `3` |
| `AGENT_BROWSER_PATH` | 无头浏览器路径(搜索用;想全程 Edge 可指向 Edge 的 msedge.exe) | 自动检测 |
| `AGENT_BROWSER_CHANNEL` | Agent 动态渲染(Playwright)所用浏览器通道(自动按平台:Windows=msedge,Linux=chromium) | 自动(msedge/chromium) |
| `ZBOOK_BASE_URL` | z-library 镜像站地址 | `https://zh.101k.by` |
| `ZBOOK_INDEX_URL` | 镜像入口索引页 | `https://znew.pages.dev/` |
| `ZBOOK_SHARED_ACCOUNT_URL` | 共享账号服务页(readzn) | `https://readzn.com/zlibrary-shared-account` |
| `BOOK_SEARCH_MODEL` | 图书功能使用的模型名(预留) | `deepseek-v4-flash-vision-exp` |
| `BOOK_TIMEOUT` | 图书抓取超时(秒) | `25` |
| `BOOK_BROWSER_CHANNEL` | 图书下载用的浏览器通道(Playwright;`msedge` 或 `chrome`;自动按平台) | 自动(msedge/chromium) |

## 数据存储

- 用户档案、长期记忆、会话状态保存在本地 SQLite:`data/agent.db`(首次运行自动创建)。
- 知识图谱数据保存在本地 SQLite:`data/graph.db`(图谱、节点、关系、导入历史)。
- 下载的书籍 PDF 保存在 `data/books/` 目录。
- 删除 `data/` 目录即可清空全部记忆与档案,恢复全新状态。

## 项目结构

```text
Agent/
├── app.py                 # FastAPI 服务入口
├── agent/
│   ├── config.py          # .env 加载
│   ├── llm.py             # DeepSeek 客户端 + Agent 工具循环
│   ├── tools.py           # 联网搜索 / 网页读取 / B站搜索
│   ├── anspire.py         # Anspire AI Search 增强搜索
│   ├── store.py           # SQLite 档案、记忆、会话
│   ├── graph_store.py     # SQLite 知识图谱存储(图谱 / 节点 / 关系 / 导入历史)
│   ├── books.py           # 图书搜索 / 下载 / 本地书籍管理
│   └── workflow.py        # 意图决策、问答状态机、各 Agent 提示词
├── static/                # 前端(index.html / style.css / app.js / graph.js / vendor/d3.min.js)
├── start.bat              # 一键启动脚本
├── .env                   # 敏感配置(已被 .gitignore 忽略)
└── requirements.txt
```

## 安全提示

- `.env` 内含 API Key,已被 `.gitignore` 忽略,请勿提交到版本库或公开分享。
- 如 Key 曾在不安全渠道(如聊天记录、公开仓库)中出现过,建议到 DeepSeek / Anspire 控制台更换。
