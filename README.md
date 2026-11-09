# 机电学习助手 - 本地 Agent 版

基于 Python + FastAPI 的机电专业学业规划工作流智能体,支持多用户登录、四年学习计划、公司/岗位检索、知识图谱、图书检索下载与竞赛推荐。

## 功能特性

- **多用户登录与用户记录**:首次进入填写昵称与密码(默认密码 `123`),昵称全局唯一,密码在服务端真实校验;`admin` 为管理员账号,可在“用户记录”中展开查看所有用户的提问与 AI 回复
- **在线人数**:页面右上角以胶囊标签显示当前在线人数,约 10 秒轮询刷新一次
- **历史对话标题**:按学校、专业、公司和岗位逐步自动命名;普通答疑使用首条有效提问。侧栏铅笔按钮可手动改名并锁定标题,“整理旧标题”支持预览后回填默认标题。整理不会改变对话时间或消息内容;旧版无归属记录由管理员整理。
- **规划模式**:依次询问城市、学校、意向公司、意向岗位,产出大一至大四共 8 个学期的学习计划,目标可衡量,末尾附“一键导入知识图谱”入口
- **课程视频按需查询**:生成计划时不再实时搜视频,计划表每门课右侧是蓝色“查询”按钮,点击后才针对该课程检索 B站视频,取播放量前 3 的视频/合集;查询过程在弹窗中用灰色小框展示工具调用与思考记录,弹窗可点 `_` 最小化(后台继续搜索,再点“查询/查看”可重新打开),完成后按钮变绿色“查看”
- **公司推荐**:按「校招企业 / 城市知名机电企业 / 行业标杆」分类推荐,每家公司以灰色胶囊卡片展示企业名称、推荐理由与官方网址
- **公司官网搜索**:公司先整体输出,官网列是“点击搜索”按钮;点击后只针对该目标公司检索官网(中英文名、招聘域名多轮尝试),命中以绿色可点击链接展示,未找到或超过 120 秒显示“未找到目标公司官网”
- **岗位检索**:先用「招聘入口发现」抓取公司官网真实的“人才招聘 / 加入我们 / Careers”入口(不在官网上乱猜 `/zhaopin/` 之类子路径),再用无头浏览器渲染抓取真实岗位;每个岗位以灰色胶囊卡片展示,链接为蓝色可点击
- **真实性检索**:涉及公司官网、招聘岗位、证书学习资源等对链接真实性要求高的检索统一走 `verified_search`,按「主搜 → 真实性审查 → free-search-mcp 多引擎回退 → 再审查 → 必要时 DeepSeek 联网 → 子项单独重搜」链式取数,不采用未核实链接
- **增强搜索**:检索类回复下方提供「对搜索结果不满意?使用增强搜索」,点击即用 [Anspire AI Search](https://open.anspire.cn/document/docs/searchApi/) 再次检索,结果以可点击链接展示
- **知识图谱**:学习计划自动转换为与《计算机发展.json》一致的 nodes/edges JSON,回复中出现“一键导入知识图谱”按钮,导入后在内置 D3 力导向图中查看,支持缩放、多布局、图谱管理与导入历史撤销
- **竞赛推荐**:证书学习资料输出后按专业与目标岗位推荐竞赛,数据来自 `data/gb/大学生工科竞赛榜单.xlsx`,按计算机类 / 电子信息类 / 其他工学类 / 机器人类 / 职业技能类分组;可继续追问某个竞赛的报名方式、赛事内容与备赛建议
- **图书**:左下角“图书”入口支持按书名搜索并返回书籍页与下载链接;点击结果右侧「下载」会在新标签页打开该书的下载页,由浏览器直接下载(服务端不再中转保存),「书籍页」可另开详情页。“我的书籍”支持拖拽上传本机 PDF 并命名保存。国内镜像从 [z-library 镜像大全](https://zz.sodanav.com/) 的「Z-Library镜像入口」卡片动态读取(该页会不定期更新),并自动解析出入口真正落地的站点;解析失败时回退到固定地址
- **课程**:输入框上方“课程”入口展示课程列表,点“打开”在新标签页打开课程平台
- **竞赛学习模式**:右下角切换到“竞赛学习模式”后,在新标签页打开竞赛导师站点
- **PDF 识别(⚠️ 暂时下架)**:利用本机 MinerU 扫描 PDF 书籍(即“我的书籍”每本书的“识别”与“我的书籍(Markdown)”)已暂时下架,相关代码注释保留;图书搜索、下载、上传到“我的书籍”、打开与删除等其余图书功能不受影响

## 工作流

与原始 YAML 流程一一对应:

1. **开始**:接收用户输入,写入长期记忆
2. **档案读取 + 记忆检索**:读取已保存的专业/城市/学校/意向公司/岗位,并按关键词检索历史对话
3. **意图决策**:判断进入「规划」分支(出现专业、学校、城市、公司、岗位等)还是「导师追问」分支(问课程难度、名词解释、调整计划等)
4. **规划分支**:问答收集意向 → 列出公司 → 列出岗位 → 生成四年学习计划 → 提炼知识图谱 JSON(可一键导入)
5. **默认分支**:导师式答疑,结合档案与历史记忆回复,不编造视频链接,只给搜索关键词
6. **长期记忆**:每轮用户输入与 AI 回复均写入记忆库,下次对话可检索

## 技术栈

| 层级 | 技术 |
|------|------|
| 后端框架 | Python + FastAPI(uvicorn) |
| 大模型 | DeepSeek `deepseek-flash`(当前版本为 DeepSeek-V4.1-Flash-1017,全部环节统一使用) |
| 联网搜索 | 百度 / Bing / DuckDuckGo / Anspire AI Search,多引擎 RRF 合并 |
| 浏览器自动化 | Playwright(Windows 走 `msedge`,Linux 走 `chromium`) |
| 前端 | 原生 HTML + CSS + JavaScript(零构建) |
| 图谱渲染 | D3.js(`static/vendor/d3.min.js`) |
| 数据存储 | SQLite(用户、档案、记忆、会话、知识图谱) |
| 图书下载 | 镜像大全(zz.sodanav.com)发现 + Playwright 会话下载 |
| 竞赛数据 | pandas + openpyxl 读取竞赛榜单 Excel |

## 项目结构

```text
Agent/
├── app.py                       # FastAPI 服务入口(对话、图谱、图书、课程、登录等接口)
├── agent/                       # 后端逻辑
│   ├── config.py                # .env 加载
│   ├── llm.py                   # DeepSeek 客户端 + Agent 工具循环
│   ├── tools.py                 # 联网搜索 / 网页读取 / 动态渲染 / B站搜索
│   ├── free_search.py           # free-search-mcp 多引擎回退(隔离环境调用)
│   ├── anspire.py               # Anspire AI Search 增强搜索
│   ├── workflow.py              # 意图决策、问答状态机、各智能体提示词
│   ├── store.py                 # 用户、档案、记忆、会话、在线状态(SQLite)
│   ├── graph_store.py           # 知识图谱存储(图谱 / 节点 / 关系 / 导入历史)
│   ├── books.py                 # 图书搜索与 PDF 下载
│   ├── books_md.py              # 书籍 Markdown(随 PDF 识别功能暂时下架)
│   ├── pdf_extract.py           # PDF 识别(暂时下架,代码注释保留)
│   ├── competitions.py          # 竞赛榜单读取
│   ├── competition_links.py     # 竞赛资料链接检索
│   └── tasks.py                 # 后台任务(搜索 / 下载 / 视频查询进度)
├── static/                      # 前端(零构建)
│   ├── index.html
│   ├── style.css
│   ├── app.js
│   ├── graph.js                 # 知识图谱视图
│   └── vendor/d3.min.js
├── data/                        # 运行时数据(数据库、书籍、竞赛榜单)
├── requirements.txt
├── .env                         # 敏感配置(已被 .gitignore 忽略)
├── run.sh / start.sh / stop.sh  # Linux/macOS 启动与停止
└── start.bat                    # Windows 一键启动
```

## 快速启动

### 环境要求

- [Python](https://www.python.org/) >= 3.10
- [Playwright](https://playwright.dev/) 浏览器(动态网页渲染、图书下载、B站搜索需要)

### 安装依赖

```bash
pip install -r requirements.txt

playwright install chromium
```

### 配置

从 `.env.example` 复制出 `.env`,至少填写 DeepSeek API Key:

```bash
DEEPSEEK_API_KEY=sk-xxx
```

### 启动服务

```bash
python app.py
```

浏览器打开 [http://localhost:8000](http://localhost:8000) 即可使用。

Windows 也可双击 `start.bat`;Linux/macOS 用一键脚本后台启动与停止:

```bash
./start.sh    # 后台启动,日志写入 app.log
./stop.sh     # 停止服务
```

克隆后仍需先安装依赖并配置 `.env`。`data/` 不纳入 Git,因此新克隆不包含竞赛榜单 `data/gb/大学生工科竞赛榜单.xlsx`、证书数据 `data/certs_data.json` 和竞赛链接 `data/competitions_links.json`;需要相应功能时请自行准备这些文件。缺少竞赛榜单时无法生成竞赛推荐,缺少证书数据时会使用内置规则回退。

### 部署到服务器

- 需要对外访问时,在 `.env` 设置 `HOST=0.0.0.0`(端口由 `PORT` 控制,默认 `8000`)
- `.env` 的 `AGENT_BROWSER_PATH` 指向容器内 Chromium(如 `/root/.cache/ms-playwright/chromium-1234/chrome-linux64/chrome`);本地开发时该路径不存在会自动回退到本机 Chrome/Edge
- 上传项目后执行 `./start.sh` 启动、`./stop.sh` 停止;改动后端代码或 `.env` 后需重启生效

### 可选组件:多引擎搜索回退(free-search-mcp)

`verified_search` 的第二级回退依赖 [free-search-mcp](https://github.com/sweetcornna/free-search-mcp),安装在隔离虚拟环境 `.venv-search`,不影响主环境依赖:

```bash
python -m venv .venv-search
.venv-search/bin/python -m pip install --index-url https://mirrors.aliyun.com/pypi/simple/ free-search-mcp mcp
# Windows 用 .venv-search\Scripts\python
```

- 未安装或该级被禁用时,`verified_search` 会自动跳过,直接进入“必要时 DeepSeek 联网 / 如实标注未验证”,不影响主搜
- 回退引擎在 `.env` 的 `FREE_SEARCH_ENGINES` 配置(默认 `baidu,bing,duckduckgo`)

### 恢复 PDF 识别(暂时下架)

> ⚠️ 该功能当前已下架,以下内容仅供恢复时参考。

纯文本型 PDF 直接用本地 PyMuPDF 读取,无需联网;扫描件/复杂排版调用本机 `mineru` CLI,全程本地离线、不上传文件。

```bash
# 首次运行需下载模型权重(推荐只装 pipeline,够扫描件 OCR 用)
mineru-models-download -m pipeline -s modelscope
```

- 国内网络在 `.env` 设 `MINERU_MODEL_SOURCE=local`,直接从本地模型目录读取
- 204 页这类大扫描件 CPU 解析较慢,可调大 `.env` 的 `MINERU_TIMEOUT`(默认 1200 秒)
- 显存不足报 `CUDA error: CUBLAS_STATUS_EXECUTION_FAILED` 时,在 `.env` 设 `MINERU_VIRTUAL_VRAM_SIZE=4`
- 恢复时还需取消 `requirements.txt` 中 `pymupdf` 的注释

## API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/` | 前端页面 |
| POST | `/api/chat` | 对话(非流式) |
| POST | `/api/chat/stream` | 对话(SSE 流式输出) |
| POST | `/api/chat/retry` | 重试上一条提问 |
| GET | `/api/profile` | 读取用户档案 |
| POST | `/api/reset` | 重置会话状态 |
| POST | `/api/auth/login` | 登录(昵称 + 密码校验) |
| POST | `/api/auth/logout` | 退出登录 |
| GET | `/api/auth/me` | 校验登录态 |
| GET | `/api/admin/records` | 管理员查看用户提问记录 |
| POST | `/api/presence/ping` | 在线状态上报 |
| GET | `/api/presence/online` | 查询在线人数 |
| GET | `/api/sessions` | 会话列表 |
| PATCH | `/api/sessions/{session_id}` | 手动重命名并锁定标题,需登录并校验客户端归属 |
| GET/POST | `/api/sessions/title-backfill` | 预览 / 应用旧默认标题回填,需登录并校验客户端归属 |
| GET | `/api/sessions/{session_id}/messages` | 会话消息 |
| DELETE | `/api/sessions/{session_id}` | 删除会话 |
| GET | `/api/graphs` | 图谱列表 |
| GET/PUT/PATCH/DELETE | `/api/graphs/{graph_id}` | 图谱读取 / 保存 / 重命名 / 删除 |
| DELETE | `/api/graphs/{graph_id}/imports/{import_id}` | 撤销某次图谱导入 |
| POST | `/api/graph/import` | 一键导入知识图谱 |
| POST | `/api/books/search` | 图书搜索(异步任务) |
| GET | `/api/books/search/status/{task_id}` | 图书搜索进度 |
| POST | `/api/books/download` | 图书下载(异步任务) |
| GET | `/api/books/download/status/{task_id}` | 图书下载进度 |
| POST | `/api/books/upload` | 上传本地 PDF 到“我的书籍” |
| GET | `/api/books` | 本地书籍列表 |
| GET | `/api/books/file/{filename}` | 读取 / 打开书籍文件 |
| DELETE | `/api/books/{filename}` | 删除书籍 |
| POST | `/api/course/video` | 课程视频查询(异步任务) |
| GET | `/api/course/video/status/{task_id}` | 视频查询进度 |
| POST | `/api/company/website` | 单个公司官网搜索(超时上限 120 秒) |
| POST | `/api/search/anspire` | Anspire 增强搜索 |

## 配置说明

配置集中在项目根目录 `.env`(可从 `.env.example` 复制):

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `DEEPSEEK_API_KEY` | DeepSeek API Key(必填) | 无 |
| `DEEPSEEK_BASE_URL` | API 地址 | `https://api.deepseek.com/v1` |
| `DEEPSEEK_MODEL` | 模型名(全部环节统一使用) | `deepseek-flash` |
| `DEEPSEEK_MODEL_PRO` | 检索型任务(搜公司官网/搜B站视频)所用模型;留空自动跟随 `DEEPSEEK_MODEL` | `deepseek-flash` |
| `HOST` / `PORT` | 监听地址与端口(对外访问设 `0.0.0.0`) | `127.0.0.1` / `8000` |
| `ADMIN_PASSWORD` | 管理员账号密码 | 无 |
| `USER_DEFAULT_PASSWORD` | 普通用户默认密码 | `123` |
| `ANSPIRE_API_KEY` | Anspire AI Search Key(可选,配置后启用增强搜索) | 无 |
| `ANSPIRE_API_URL` | Anspire 接口地址 | `https://plugin.anspire.cn/api/ntsearch/search` |
| `ANSPIRE_TIMEOUT` | Anspire 请求超时(秒) | `30` |
| `SEARCH_ENGINE` | 联网搜索主引擎(`baidu`/`bing`/`duckduckgo`/`anspire`,失败自动回退) | `baidu` |
| `AGENT_MAX_TOOL_CALLS` | Agent 单次任务工具调用总量上限 | `30` |
| `TOOL_CAP_VERIFIED_SEARCH` | 真实链搜索(verified_search)次数上限 | `10` |
| `TOOL_CAP_FETCH_PAGE` | 网页读取次数上限 | `8` |
| `TOOL_CAP_BILIBILI` | B站搜索次数上限 | `14` |
| `TOOL_CAP_RENDER_PAGE` | 动态网页渲染次数上限 | `8` |
| `TOOL_CAP_FIND_RECRUIT` | 招聘入口发现次数上限 | `3` |
| `AGENT_BROWSER_PATH` | 无头浏览器路径(搜索用) | 自动检测 |
| `AGENT_BROWSER_CHANNEL` | Playwright 浏览器通道(Windows `msedge` / Linux `chromium`) | 自动 |
| `ZBOOK_INDEX_URL` | 镜像大全页面,读取「Z-Library镜像入口」卡片 | `https://zz.sodanav.com/` |
| `ZBOOK_BASE_URL` | 兜底镜像地址(镜像大全不可达或解析失败时使用) | `https://zh.834101.ru` |
| `ZBOOK_STORAGE_STATE` | Playwright 登录状态文件路径(可选,相对项目目录或绝对路径) | 空 |
| `BOOK_TIMEOUT` | 图书抓取超时(秒) | `25` |
| `BOOK_BROWSER_CHANNEL` | 图书搜索与下载使用的浏览器通道 | 自动 |

图书搜索与下载先访问镜像大全,读取「Z-Library镜像入口」卡片里的按钮(镜像一、镜像二…),并跟随跳转解析出入口真正落地的站点,再在该站点检索书名。镜像大全里的入口域名通常只是跳转门面:任意路径都会被 302 到首页,搜索词随之丢失,因此不能直接拿入口域名当检索地址。镜像列表缓存 30 分钟,上次没取到列表时 1 分钟后重试;解析失败或该页改版时自动回退到 `ZBOOK_BASE_URL`。镜像仍会受网络、反爬验证和账号规则影响,程序以实际解析到的书目为准。

镜像需要登录时可配置个人登录状态。在项目目录运行下列命令,将 `<镜像地址>` 替换为 `https://zh.834101.ru`,在浏览器中完成验证与登录后关闭窗口。

```powershell
python -m playwright codegen --channel msedge --save-storage data/zlibrary-session.json "<镜像地址>"
```

随后在 `.env` 中设置 `ZBOOK_STORAGE_STATE=data/zlibrary-session.json` 并重启服务。状态文件包含登录凭据,应保存在本机已被 Git 忽略的 `data/` 目录,供搜索时复用浏览器登录态。点击「下载」会在新标签页打开该书的下载页,登录、验证码与下载额度全部由你本机的浏览器处理;游客额度用尽或需要登录时,页面会直接给出提示。

浏览器通道留空时,Windows 会依次尝试 Edge、Chrome 和 Playwright Chromium,Linux 默认使用 Playwright Chromium;显式指定通道时仅使用指定项。网页渲染会校验 HTTPS 证书,并通过 `render_duration_ms` 返回耗时及通过 `error_type` 区分失败原因。服务日志还记录模型、工具和搜索引擎的耗时,便于排查慢请求。

数据存储与安全:

- 用户、档案、记忆、会话、在线状态存于 `data/agent.db`;知识图谱存于 `data/graph.db`;下载的书籍存于 `data/books/`(首次运行自动创建)
- 删除 `data/` 目录即可清空全部记忆与档案,恢复全新状态
- `.env` 与 `data/` 已被 `.gitignore` 忽略,请勿把 API Key 提交到版本库或公开分享;若 Key 曾出现在不安全渠道,建议到 DeepSeek / Anspire 控制台更换
