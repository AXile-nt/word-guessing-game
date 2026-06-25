"""
server.py — 语义猜词后端 (Python 标准库 + sentence-transformers)
功能: 加载 BGE 中文向量模型, 预编码候选词库, 实时计算任意猜词的相似度与排名。
零 web 框架依赖, 用标准库 http.server。一键启动: python server.py

API:
  GET  /                 -> 返回 index.html
  GET  /static/<file>    -> 返回静态资源 (style.css, game.js)
  POST /new              -> 新一局: {target_hidden:true} 返回 {total}
  POST /guess {word}     -> 猜词: 返回 {word, percent, rank, hit}
"""
import json, os, time, sys, urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler

# Windows cmd 下强制 stdout/stderr 用 UTF-8, 避免中文 print 报 UnicodeEncodeError
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

import numpy as np

# 资源根目录: PyInstaller 打包后用 _MEIPASS, 否则用脚本所在目录
def _resource_root():
    if getattr(sys, "frozen", False):    # PyInstaller 打包
        return sys._MEIPASS
    return os.path.dirname(os.path.abspath(__file__))
HERE = _resource_root()
PORT = int(os.environ.get("PORT", "8000"))
MODEL_ID = "BAAI/bge-small-zh-v1.5"   # ModelScope 上的模型 ID

def _is_model_dir(path):
    return path and os.path.isdir(path) and os.path.exists(os.path.join(path, "config.json"))

def resolve_model_dir():
    """定位/下载 BGE 模型。优先环境变量,其次本地 models/ 目录,最后自动下载。"""
    env = os.environ.get("BGE_MODEL_DIR")
    if _is_model_dir(env):
        return env
    # 本地缓存目录(程序同级 models/)。兼容 ModelScope 的默认目录结构。
    candidates = [
        os.path.join(HERE, "models", "BAAI", "bge-small-zh-v1___5"),
        os.path.join(HERE, "models", MODEL_ID.replace("/", "_")),
    ]
    for local in candidates:
        if _is_model_dir(local):
            return local
    # 自动下载(首次启动)
    print(f"[启动] 首次运行, 正在下载 BGE 模型 (~91MB, 仅一次)...", flush=True)
    from modelscope import snapshot_download
    p = snapshot_download(MODEL_ID, cache_dir=os.path.join(HERE, "models"))
    print(f"[启动] 模型下载完成: {p}", flush=True)
    return p
# 候选词来源: 纯词表(腾讯词向量按频次排序), BGE 实时编码
VOCAB_FILE = os.path.join(HERE, "data", "wordlist.txt")
MAX_VOCAB = 120000     # 候选词上限(控制启动内存与排名精度)
TARGET_FLOOR = 0.40    # 目标词取词频前 40% (腾讯词表按频次排序)

# ---- 全局状态 ----
class State:
    model = None
    words = None          # [词]
    mat = None            # (N, dim) 归一化矩阵
    target = None
    target_vec = None
    sims_sorted_idx = None  # 按与 target 相似度降序的词索引
    rank_of = None        # {词: 排名}
    cat_descs = None      # 抽象类别描述句 [str]
    cat_mat = None        # 类别向量矩阵 (用于提示2)
    hint1 = None          # 提示1: 目标词字数
    hint2 = None          # 提示2: 抽象描述
    hint_words = None     # 本局已给过的提示词集合(避免重复)
    hint_last_rank = None # 上次提示词的排名(下次往前递进)
    ready = False
S = State()

# 抽象类别(句子级描述, BGE 擅长匹配) - 用于"提示2: 抽象描述"
CATEGORIES = [
    "一种食物或饮品",
    "一种动物或植物",
    "一种交通工具",
    "一个地点或场所",
    "一种情绪或心理状态",
    "一种天气或自然现象",
    "一种日常用品或工具",
    "一项运动或娱乐活动",
    "一个节日或时间",
    "一种职业或身份",
    "一种颜色",
    "一个动作或行为",
    "一种抽象概念",
    "一个身体部位",
    "一种科技或电子产品",
    "一种服饰或穿着",
    "一种建筑或设施",
    "一种艺术或文化",
]

def load_stopwords():
    return set("我们 你们 他们 这个 那个 什么 怎么 可以 就是 还是 但是 不是 没有 "
               "一个 这样 那样 其实 只是 已经 非常 比较 一直 应该 可能 需要 觉得 "
               "感觉 知道 认为 以为 所以 因为 如果 虽然 不过 而且 然后 现在 以后 以前".split())

def init():
    """加载模型 + 预编码词库(一次性, 启动时)。"""
    t0 = time.time()
    print("[启动] 加载 BGE 中文向量模型…", flush=True)
    from sentence_transformers import SentenceTransformer
    model_dir = resolve_model_dir()
    S.model = SentenceTransformer(model_dir)
    print(f"[启动] 模型就绪 ({time.time()-t0:.1f}s)", flush=True)

    print("[启动] 加载候选词库…", flush=True)
    with open(VOCAB_FILE, encoding="utf-8") as f:
        vocab = [w.strip() for w in f if w.strip()]
    # 截断 + 去单字虚词
    stop = load_stopwords()
    cand = [w for w in vocab[:MAX_VOCAB]
            if len(w) >= 2 and w not in stop]
    S.words = cand
    print(f"[启动] 候选词 {len(cand)} 个, 开始 BGE 编码…", flush=True)

    t1 = time.time()
    S.mat = S.model.encode(cand, batch_size=256, normalize_embeddings=True,
                           show_progress_bar=True).astype(np.float32)
    print(f"[启动] 编码完成 ({time.time()-t1:.1f}s), 矩阵 {S.mat.shape}", flush=True)

    # 预编码抽象类别(用于提示2), 极快(18 句)
    S.cat_descs = CATEGORIES
    S.cat_mat = S.model.encode(CATEGORIES, normalize_embeddings=True,
                               show_progress_bar=False).astype(np.float32)
    print(f"[启动] 类别模板就绪 ({len(CATEGORIES)} 类)", flush=True)

    S.ready = True
    print(f"[启动] 全部就绪, 总耗时 {time.time()-t0:.1f}s, 端口 {PORT}", flush=True)

def make_hint2():
    """提示2: 抽象描述。取目标词最匹配的类别(top1, 相似度过低则取top2混搭)。"""
    cat_sims = S.cat_mat @ S.target_vec
    order = np.argsort(-cat_sims)
    best1 = int(order[0]); best2 = int(order[1])
    s1 = float(cat_sims[best1])
    # 相似度足够高, 直接用 top1 类别
    if s1 >= 0.45:
        return f"它可能是「{S.cat_descs[best1]}」"
    # 边界情况: 用 top1+top2 混搭, 更模糊
    return f"它可能是「{S.cat_descs[best1]}」, 或和「{S.cat_descs[best2]}」有关"

def new_round():
    """随机选目标词 + 预计算排名 + 生成提示。"""
    # 目标从词频前 40% 选(更常见可猜)
    pool_end = int(len(S.words) * TARGET_FLOOR)
    S.target = S.words[np.random.randint(0, pool_end)]
    S.target_vec = S.model.encode([S.target], normalize_embeddings=True,
                                  show_progress_bar=False)[0]
    sims = S.mat @ S.target_vec
    S.sims_sorted_idx = np.argsort(-sims).astype(np.int32)
    S.sims_sorted = sims[S.sims_sorted_idx].astype(np.float32)  # 降序缓存
    S.sims_neg_sorted = (-S.sims_sorted).tolist()               # 排名二分用
    S.rank_of = {}
    for r, i in enumerate(S.sims_sorted_idx):
        S.rank_of[S.words[i]] = r + 1
    # 提示信息(不泄露目标词本身)
    S.hint1 = len(S.target)              # 提示1: 字数
    S.hint2 = make_hint2()               # 提示2: 抽象描述
    S.hint_words = set()                 # 本局已给过的提示词
    S.hint_last_rank = None              # 下次提示从此排名往前找(递进)

def guess(word):
    """实时计算任意词的相似度与排名。word='__HINT__' 时返回提示词。"""
    if not S.ready:
        return {"error": "model loading"}

    # 提示: 每次给一个比上次更接近答案、字数相同、不重复、不是答案的词。
    if word == "__HINT__":
        if S.sims_sorted_idx is None:
            return {"error": "no round"}
        target_len = len(S.target)
        # 起始排名: 第一次从 60 起; 之后从上次提示排名的 55% 起(递进更接近)
        if S.hint_last_rank is None:
            start_rank = 60
        else:
            start_rank = max(3, int(S.hint_last_rank * 0.55))

        def find_hint(target_rank):
            """在 target_rank 附近(先往前, 再往后)找同字数、未给过、非答案的词。"""
            N = len(S.sims_sorted_idx)
            # 交替向两边扩散搜索, 优先更接近(rank 小)
            for delta in range(0, max(target_rank, N - target_rank)):
                for r in (target_rank - delta, target_rank + delta):
                    if r < 2 or r >= N:
                        continue
                    cand = S.words[int(S.sims_sorted_idx[r])]
                    if (len(cand) == target_len and cand != S.target
                            and cand not in S.hint_words):
                        return cand
            return None
        hw = find_hint(start_rank)
        if hw is None:  # 兜底
            hw = S.words[int(S.sims_sorted_idx[1])]
        S.hint_words.add(hw)
        S.hint_last_rank = S.rank_of[hw]
        res = guess(hw)
        res["hit"] = False  # 提示词不算命中
        return res

    w = word.strip()
    if not w:
        return {"error": "empty"}
    vec = S.model.encode([w], normalize_embeddings=True, show_progress_bar=False)[0]
    sim = float(S.target_vec @ vec)
    if w in S.rank_of:
        rank = S.rank_of[w]
    else:
        # 表外词: 用缓存的降序相似度数组二分估算排名
        import bisect
        rank = bisect.bisect_right(S.sims_neg_sorted, -sim) + 1
    # 百分比 = 余弦相似度 × 100 (向量已归一化, 余弦∈[-1,1], 实际≥0)
    # 保留 5 位小数: 精确到 56.23567%, 极高分也能区分(99.99 vs 99.999 vs 100)
    pct = round(max(0.0, sim) * 100, 5)
    return {"word": w, "sim": round(sim, 6), "percent": pct,
            "rank": int(rank), "total": len(S.words),
            "hit": (w == S.target)}

# ---- HTTP ----
class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a): pass  # 静默日志

    def _send(self, code, body, ctype="application/json"):
        b = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype + "; charset=utf-8")
        self.send_header("Content-Length", str(len(b)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(b)

    def _serve_file(self, path):
        if not os.path.isfile(path):
            self._send(404, "not found", "text/plain"); return
        ctype = {".html":"text/html", ".css":"text/css", ".js":"application/javascript",
                 ".json":"application/json", ".png":"image/png", ".ico":"image/x-icon",
                 ".jpg":"image/jpeg", ".svg":"image/svg+xml"}.get(os.path.splitext(path)[1], "application/octet-stream")
        with open(path, "rb") as f: b = f.read()
        self.send_response(200)
        self.send_header("Content-Type", ctype + "; charset=utf-8")
        self.send_header("Content-Length", str(len(b)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        p = urllib.parse.urlparse(self.path).path
        if p == "/" or p == "/index.html":
            self._serve_file(os.path.join(HERE, "index.html"))
        elif p in ("/style.css", "/game.js"):
            fp = os.path.join(HERE, os.path.basename(p))
            self._serve_file(fp)
        elif p == "/status":
            self._send(200, json.dumps({"ready": S.ready}))
        else:
            self._send(404, "not found", "text/plain")

    def do_POST(self):
        p = urllib.parse.urlparse(self.path).path
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode("utf-8") if length else "{}"
        try: data = json.loads(body)
        except: data = {}
        if p == "/new":
            new_round()
            self._send(200, json.dumps({
                "total": len(S.words),
                "ready": True,
                "hint1": S.hint1,        # 目标词字数
                "hint2": S.hint2,        # 抽象描述
            }))
        elif p == "/guess":
            res = guess(data.get("word", ""))
            self._send(200, json.dumps(res))
        else:
            self._send(404, json.dumps({"error": "unknown"}))

def main():
    init()
    # 启动时预开一局
    new_round()
    print(f"[运行] http://localhost:{PORT}/  (Ctrl+C 退出)", flush=True)
    HTTPServer(("127.0.0.1", PORT), Handler).serve_forever()

if __name__ == "__main__":
    main()
