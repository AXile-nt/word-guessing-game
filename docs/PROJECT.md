# 项目说明 · 语义猜词

## 项目定位

这是一个本地运行的中文语义猜词游戏，玩法类似 Contexto / Semantle：

1. 后端随机选择一个隐藏目标词。
2. 玩家输入任意中文词语。
3. 后端用 BGE 中文向量模型计算猜测词与目标词的余弦相似度。
4. 前端展示相似度百分比、排名和历史猜测。
5. 玩家根据反馈逐步逼近目标词，命中后进入下一局。

项目目标是保持结构简单，方便本地运行、阅读源码和二次修改。

## 当前技术栈

| 层 | 选型 | 说明 |
|---|---|---|
| 前端 | HTML + CSS + 原生 JavaScript | 无构建工具，无 npm 依赖 |
| 后端 | Python 标准库 `http.server` | 提供静态文件和 JSON API |
| 向量模型 | `BAAI/bge-small-zh-v1.5` | 512 维中文语义向量 |
| 模型来源 | ModelScope | 首次启动自动下载到 `models/` |
| 词表 | `data/wordlist.txt` | 一行一个词，可直接替换 |

## 发布版目录

```text
.
├── README.md
├── requirements.txt
├── .gitignore
├── .gitattributes
├── server.py
├── index.html
├── style.css
├── game.js
├── 启动游戏.bat
├── data/
│   └── wordlist.txt
└── docs/
    └── PROJECT.md
```

## 后端流程

```text
启动 server.py
  ↓
定位 BGE 模型：BGE_MODEL_DIR -> models/ 本地缓存 -> ModelScope 下载
  ↓
加载 data/wordlist.txt
  ↓
过滤停用词和单字词，取最多 120000 个候选词
  ↓
用 BGE 预编码候选词矩阵
  ↓
启动 http://127.0.0.1:8000
```

新一局时：

```text
从高频候选词中随机选 target
  ↓
编码 target
  ↓
计算所有候选词与 target 的相似度并排序
  ↓
返回目标词字数和抽象类别提示
```

猜词时：

```text
前端 POST /guess { word }
  ↓
后端编码 word
  ↓
计算 word 与 target 的余弦相似度
  ↓
如果 word 在候选词表中，直接返回预计算排名
  ↓
如果 word 不在词表中，用相似度数组估算排名
```

## 主要接口

- `GET /`
- `GET /status`
- `POST /new`
- `POST /guess`

## 可维护点

- 想换词表：替换 `data/wordlist.txt`，保持一行一个词。
- 想换端口：设置环境变量 `PORT`，例如 `set PORT=8010` 后运行 `python server.py`。
- 想用已有模型：设置环境变量 `BGE_MODEL_DIR` 指向包含 `config.json` 的模型目录。
