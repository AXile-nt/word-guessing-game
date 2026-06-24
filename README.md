# 语义猜词

中文版 Contexto / Semantle 风格的本地猜词小游戏。玩家输入任意中文词语，系统用 BGE 中文向量模型计算它和隐藏目标词的语义相似度，并返回相似度百分比与排名；越接近目标词，分数越高、排名越靠前。

![语义猜词 logo](logo.png)

## 特性

- 支持任意输入词：生造词、网络词、专有名词也可以实时计算相似度。
- 本地运行：不需要账号、API Key 或远程服务。
- 轻量前端：HTML、CSS、原生 JavaScript。
- 简单后端：Python 标准库 `http.server` + `sentence-transformers`。
- 内置中文候选词表：`data/wordlist.txt`，一行一个词，可自行替换。

## 运行环境

- Python 3.10+
- Windows、macOS 或 Linux
- 首次运行需要联网下载 BGE-small-zh-v1.5 模型；之后会优先使用本地缓存。

## 快速开始

```bash
pip install -r requirements.txt
python server.py
```

浏览器访问：

```text
http://localhost:8000/
```

Windows 用户也可以双击：

```text
启动游戏.bat
```

## 首次启动说明

首次启动会从 ModelScope 下载 `BAAI/bge-small-zh-v1.5` 模型到项目内的 `models/` 目录。该目录已被 `.gitignore` 排除，不建议提交到普通 GitHub 仓库，因为模型权重接近 100 MB。

启动时后端还会把候选词表编码成向量矩阵，机器较慢时可能需要等待几十秒。

## 目录结构

```text
.
├── README.md
├── requirements.txt
├── server.py              # Python 后端，加载模型并提供 API
├── index.html             # 游戏页面
├── style.css              # 页面样式
├── game.js                # 前端交互逻辑
├── logo.png               # 图标
├── 启动游戏.bat            # Windows 一键启动脚本
├── data/
│   └── wordlist.txt       # 目标词候选池
└── docs/
    └── PROJECT.md         # 项目结构和实现说明
```

## API

- `GET /`：返回游戏页面
- `GET /status`：返回模型是否加载完成
- `POST /new`：开始新一局，返回候选词总数和提示
- `POST /guess`：提交猜测词，返回相似度、排名和是否命中

## GitHub 发布注意

这个仓库只适合提交源码、词表和文档。请不要提交：

- `models/` 模型缓存
- `__pycache__/` Python 缓存
- `.zip`、`.exe` 等打包产物
- 本地虚拟环境目录

如果要发布安装包，可以把 exe/zip 放到 GitHub Release 附件里，而不是提交到仓库代码区。

## License

MIT
