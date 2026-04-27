"""
V1100 全息指揮台 — FastAPI 後端總線
=============================================
[OPERATION NEURAL BRIDGE - STAGE 1]

靜態掛載：http://localhost:8000  → v1100_console.html
圖譜 API：GET /api/graph_data   → ECharts / D3.js 友好 JSON
健康檢查：GET /health           → 系統狀態

啟動方式（從 backend/ 目錄）：
  uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

[V1100 核武架構紅線]
  - VRAM Shield: asyncio.Semaphore 防護已預留
  - Token Shield: Neo4j 查詢硬性 LIMIT 200，預設 100
  - 絕對錨定: 馬匹名單物理攔截預留接口
"""

import logging
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .utils.neo4j_client import neo4j_db
from .services.v1100_predict_2026 import run_swarm_prediction

# ═══════════════════════════════════════════════
#  路徑錨定 (Absolute Path Anchoring)
# ═══════════════════════════════════════════════

# backend/app/main.py → parent.parent = backend/
BACKEND_DIR = Path(__file__).resolve().parent.parent

# templates/ 目錄（v1100_console.html 所在地）
TEMPLATES_DIR = BACKEND_DIR / "templates"

# 靜態資源目錄（CSS / JS / 圖片）— MF_Local_Engine/static/
STATIC_DIR = BACKEND_DIR.parent / "static"


# ═══════════════════════════════════════════════
#  日誌配置
# ═══════════════════════════════════════════════

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s │ %(message)s",
)
logger = logging.getLogger("v1100.command_center")


# ═══════════════════════════════════════════════
#  Neo4j Node → ECharts JSON 轉換輔助函式
# ═══════════════════════════════════════════════

def _node_to_id(node) -> str:
    """
    從 Neo4j Node 物件提取人類可讀 ID。
    優先順序：name → title → description（截斷） → element_id
    """
    for key in ("name", "title"):
        if key in node:
            return str(node[key])
    if "description" in node:
        desc = str(node["description"])
        return desc[:40] + "…" if len(desc) > 40 else desc
    return str(node.element_id)


def _node_to_category(node) -> str:
    """從 Neo4j Node 提取第一個 Label 作為類別"""
    labels = list(node.labels)
    return labels[0] if labels else "Unknown"


def _node_to_props(node) -> dict:
    """
    提取節點附加屬性，排除已作為 id 使用的欄位。
    所有值強制 JSON 安全序列化。
    """
    skip_keys = {"name", "title"}
    result = {}
    for k, v in dict(node).items():
        if k in skip_keys:
            continue
        if isinstance(v, (str, int, float, bool)) or v is None:
            result[k] = v
        else:
            result[k] = str(v)
    return result


# ═══════════════════════════════════════════════
#  FastAPI 生命週期管理 (Lifespan)
# ═══════════════════════════════════════════════

@asynccontextmanager
async def lifespan(app: FastAPI):
    """啟動 / 關閉時的資源管理"""
    # ─── 啟動 ───
    TEMPLATES_DIR.mkdir(exist_ok=True)
    logger.info("═" * 55)
    logger.info("[V1100] ⚡ 全息指揮台 — 後端總線啟動")
    logger.info(f"[V1100] Templates : {TEMPLATES_DIR}")
    logger.info(f"[V1100] Static    : {STATIC_DIR}")
    logger.info("═" * 55)

    yield

    # ─── 關閉 ───
    neo4j_db.close()
    logger.info("[V1100] 全息指揮台已關閉，Neo4j 連線已釋放")


# ═══════════════════════════════════════════════
#  FastAPI 應用實例
# ═══════════════════════════════════════════════

app = FastAPI(
    title="V1100 全息指揮台",
    description="MiroFish Local Engine — 賽馬圖譜記憶 & 蜂群推演指揮中心",
    version="1.1.0",
    lifespan=lifespan,
)

# CORS 全開放（本地開發環境）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 靜態資源掛載（/static → MF_Local_Engine/static/）
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


# ═══════════════════════════════════════════════
#  路由 1：根路由 → v1100_console.html
# ═══════════════════════════════════════════════

@app.get("/", include_in_schema=False)
async def serve_console():
    """
    根路由：載入 V1100 全息指揮台前端頁面。
    檔案位置：backend/templates/v1100_console.html
    """
    html_path = TEMPLATES_DIR / "v1100_console.html"
    if not html_path.exists():
        raise HTTPException(
            status_code=404,
            detail=(
                "[V1100] v1100_console.html 尚未部署。"
                f" 請將檔案置於: {html_path}"
            ),
        )
    return FileResponse(str(html_path), media_type="text/html")


# ═══════════════════════════════════════════════
#  路由 2：健康檢查
# ═══════════════════════════════════════════════

@app.get("/health")
async def health_check():
    """系統健康檢查 — 驗證 Neo4j 連線狀態"""
    neo4j_ok = neo4j_db.verify_connectivity()
    return {
        "status": "operational" if neo4j_ok else "degraded",
        "service": "V1100 全息指揮台",
        "version": "1.1.0",
        "neo4j": "connected" if neo4j_ok else "disconnected",
    }


# ═══════════════════════════════════════════════
#  路由 3：GET /api/graph_data — 圖譜檢索 API
# ═══════════════════════════════════════════════

@app.get("/api/graph_data")
async def get_graph_data(
    limit: int = Query(
        default=100,
        ge=1,
        le=200,
        description="最大回傳關係數（硬性上限 200，防止前端卡死）",
    ),
):
    """
    圖譜檢索 API — 從 Neo4j 抓取節點與關係。

    將 Neo4j 原始資料轉換為 ECharts / D3.js 友好的標準 JSON：

    ```json
    {
      "nodes": [
        {"id": "馬匹A", "category": "Horse", ...},
        {"id": "事件B", "category": "Incident", ...}
      ],
      "links": [
        {"source": "馬匹A", "target": "事件B", "type": "HAS_INCIDENT"}
      ]
    }
    ```

    **[Token Shield]** 硬性 LIMIT 200，預設 100。
    """
    # ─── 建立 Neo4j 連線 ───
    try:
        driver = neo4j_db._get_driver()
    except ImportError as e:
        logger.error(f"[V1100] Neo4j 套件未安裝: {e}")
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        logger.error(f"[V1100] Neo4j 連線失敗: {e}")
        raise HTTPException(
            status_code=503,
            detail=f"[V1100] Neo4j 連線失敗，請確認 Neo4j 服務已啟動: {e}",
        )

    # ─── Cypher 查詢：抓取有關係的節點對 ───
    cypher = (
        "MATCH (n)-[r]->(m) "
        "RETURN n, r, m "
        f"LIMIT {limit}"
    )

    nodes_map: dict[str, dict] = {}   # 去重用 map: id → node dict
    links: list[dict] = []

    try:
        with driver.session() as session:
            result = session.run(cypher)

            for record in result:
                src = record["n"]
                rel = record["r"]
                tgt = record["m"]

                # ── 來源節點 ──
                src_id = _node_to_id(src)
                if src_id not in nodes_map:
                    nodes_map[src_id] = {
                        "id": src_id,
                        "category": _node_to_category(src),
                        **_node_to_props(src),
                    }

                # ── 目標節點 ──
                tgt_id = _node_to_id(tgt)
                if tgt_id not in nodes_map:
                    nodes_map[tgt_id] = {
                        "id": tgt_id,
                        "category": _node_to_category(tgt),
                        **_node_to_props(tgt),
                    }

                # ── 關係（邊） ──
                links.append({
                    "source": src_id,
                    "target": tgt_id,
                    "type": rel.type,
                })

        node_count = len(nodes_map)
        link_count = len(links)
        logger.info(
            f"[V1100] graph_data 回傳: {node_count} 節點, {link_count} 關係"
        )

        return JSONResponse(content={
            "nodes": list(nodes_map.values()),
            "links": links,
        })

    except Exception as e:
        logger.error(f"[V1100] Cypher 查詢失敗: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"[V1100] 圖譜查詢失敗: {e}",
        )


# ═══════════════════════════════════════════════
#  Pydantic 請求 / 回應模型
# ═══════════════════════════════════════════════

class SimulateRequest(BaseModel):
    """推演請求模型"""
    prompt: str = Field(
        ...,
        min_length=2,
        max_length=500,
        description="首長的推演指令 (如 '推演 2026-03-29')",
        examples=["推演 2026-03-29", "分析下一場沙田賽事"],
    )


class SimulateResponse(BaseModel):
    """推演回應模型"""
    tactical_report: str = Field(description="Markdown 格式戰術報告")
    status_logs: list[str] = Field(description="推演過程日誌")
    status: str = Field(description="completed | aborted | error")


# ═══════════════════════════════════════════════
#  路由 4：POST /api/simulate — 蜂群推演 API
# ═══════════════════════════════════════════════

@app.post("/api/simulate", response_model=SimulateResponse)
async def simulate(req: SimulateRequest):
    """
    蜂群推演 API — 接收首長指令，調度本地 Ollama 進行推演。

    **流程：**
    1. 從 Neo4j 圖譜記憶檢索相關情報
    2. [VRAM Shield] 取得併發鎖 (Semaphore=3)
    3. 調度 Ollama/Qwen2.5:7b 進行蜂群推演
    4. 回傳 Markdown 格式戰術報告

    **請求 JSON：**
    ```json
    {"prompt": "推演 2026-03-29"}
    ```

    **回應 JSON：**
    ```json
    {
      "tactical_report": "# V1100 戰術報告\\n...",
      "status_logs": ["[HH:MM:SS] ⚡ 蜂群推演引擎啟動", ...],
      "status": "completed"
    }
    ```
    """
    logger.info(f"[V1100] 收到推演指令: {req.prompt}")

    try:
        result = await run_swarm_prediction(prompt=req.prompt)

        logger.info(
            f"[V1100] 推演完成: status={result['status']}, "
            f"report_len={len(result['tactical_report'])}"
        )

        return JSONResponse(content=result)

    except Exception as e:
        logger.error(f"[V1100] 推演異常: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"[V1100] 蜂群推演失敗: {e}",
        )
