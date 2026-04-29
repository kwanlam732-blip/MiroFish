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

import asyncio
import logging
import os
from pathlib import Path
from contextlib import asynccontextmanager
from typing import List

from fastapi import FastAPI, HTTPException, Query, UploadFile, File, BackgroundTasks, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from app.utils.neo4j_client import neo4j_db
from app.services.v1100_predict_2026 import run_swarm_prediction

# ═══════════════════════════════════════════════
#  路徑錨定 (Absolute Path Anchoring)
# ═══════════════════════════════════════════════

# backend/app/main.py → parent.parent = backend/
BACKEND_DIR = Path(__file__).resolve().parent.parent

# templates/ 目錄（v1100_console.html 所在地）
TEMPLATES_DIR = BACKEND_DIR / "templates"

# 靜態資源目錄（CSS / JS / 圖片）— MF_Local_Engine/static/
STATIC_DIR = BACKEND_DIR.parent / "static"

# 上傳目錄 — MF_Local_Engine/data/uploads/
UPLOAD_DIR = BACKEND_DIR.parent / "data" / "uploads"


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
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    logger.info("═" * 55)
    logger.info("[V1100] ⚡ 全息指揮台 — 後端總線啟動")
    logger.info(f"[V1100] Templates : {TEMPLATES_DIR}")
    logger.info(f"[V1100] Static    : {STATIC_DIR}")
    logger.info(f"[V1100] Uploads   : {UPLOAD_DIR}")
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

# === V1100 暴力路由區 (OPERATION ABSOLUTE COUPLING) ===

@app.post("/api/upload/history")
async def api_upload_history(background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    """暴力路由：歷史金庫背景灌注"""
    try:
        UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        file_path = UPLOAD_DIR / file.filename
        content = await file.read()
        with open(file_path, "wb") as buffer:
            buffer.write(content)
        
        # 呼叫現有的注入邏輯 (歷史模式: is_daily=False)
        background_tasks.add_task(_inject_reality_seeds, [str(file_path)], False)
        
        return JSONResponse(content={"status": "processing", "message": "歷史金庫已開始背景灌注！"})
    except Exception as e:
        logger.error(f"[V1100] 歷史上傳失敗: {e}")
        return JSONResponse(content={"error": str(e)}, status_code=500)

@app.post("/api/upload/daily")
async def api_upload_daily(file: UploadFile = File(...)):
    """暴力路由：今日排位立即同步"""
    try:
        UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        file_path = UPLOAD_DIR / file.filename
        content = await file.read()
        with open(file_path, "wb") as buffer:
            buffer.write(content)
        
        # 呼叫現有的注入邏輯 (每日模式: is_daily=True)
        # 這裡改為同步執行以符合前端「立即同步」的語意，或使用 BackgroundTasks
        _inject_reality_seeds([str(file_path)], True)
        
        return JSONResponse(content={"status": "success", "message": "今日排位已更新！"})
    except Exception as e:
        logger.error(f"[V1100] 今日上傳失敗: {e}")
        return JSONResponse(content={"error": str(e)}, status_code=500)

@app.post("/api/simulate")
async def api_simulate(request: Request):
    """暴力路由：蜂群推演對接"""
    try:
        body = await request.json()
        prompt = body.get("prompt", "推演最新賽事")
        logger.info(f"[V1100] 暴力路由收到推演指令: {prompt}")
        
        # 直接呼叫現有的推演服務
        result = await run_swarm_prediction(prompt=prompt)
        return JSONResponse(content={"status": "success", "report": result.get("tactical_report", "推演完成")})
    except Exception as e:
        logger.error(f"[V1100] 推演失敗: {e}")
        return JSONResponse(content={"error": str(e)}, status_code=500)

# ====================================================

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
    強制對齊：確保從 localhost:8000 直接訪問。
    """
    # 探測優先級 1：backend/templates/ (標準路徑)
    html_path = TEMPLATES_DIR / "v1100_console.html"
    
    # 探測優先級 2：同級目錄 (防錯路徑)
    if not html_path.exists():
        html_path = BACKEND_DIR / "v1100_console.html"
        
    if not html_path.exists():
        logger.error(f"[V1100] 找不到全息介面！路徑探測失敗：{TEMPLATES_DIR}")
        raise HTTPException(
            status_code=404,
            detail=f"[V1100] v1100_console.html 遺失。請確保檔案存在於: {TEMPLATES_DIR}"
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
    
    **[黑盒偵測]** 若 Neo4j 連線失敗，直接回傳 HTTP 500 + 詳細錯誤原因。禁止降級假數據！
    """
    
    # ─── 建立 Neo4j 連線 ───
    try:
        driver = neo4j_db._get_driver()
    except Exception as e:
        error_msg = str(e)
        logger.error(f"[V1100] ❌ 圖譜雷達失效：{error_msg}")
        raise HTTPException(
            status_code=500,
            detail=f"[V1100] Neo4j 連線失敗 (圖譜雷達離線)：{error_msg}。請檢查 .env 配置和 Neo4j 服務狀態。"
        )

    # ─── Cypher 查詢：打破星狀圖，重鑄交織網 (多節點交集) ───
    cypher = (
        "MATCH (n)-[r]->(m) "
        "WITH n, r, m ORDER BY rand() "
        f"LIMIT {limit} "
        "RETURN n, r, m"
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
        
        if node_count == 0:
            logger.warning(f"[V1100] 圖譜為空：0 節點，0 關係。請檢查是否已上傳並處理訓練數據。")
            raise HTTPException(
                status_code=500,
                detail="[V1100] 圖譜為空。請先上傳訓練數據 (Race Card / Training Narratives)。"
            )
        
        logger.info(
            f"[V1100] ✅ 圖譜雷達回傳: {node_count} 節點, {link_count} 關係"
        )

        return JSONResponse(content={
            "nodes": list(nodes_map.values()),
            "links": links,
        })

    except HTTPException:
        raise
    except Exception as e:
        error_msg = str(e)
        logger.error(f"[V1100] ❌ Cypher 查詢異常：{error_msg}")
        raise HTTPException(
            status_code=500,
            detail=f"[V1100] 圖譜查詢失敗：{error_msg}"
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

# 原有 /api/simulate 已由上方暴力路由區接管


# ═══════════════════════════════════════════════
#  路由 5：POST /api/upload — 現實種子上傳 API
# ═══════════════════════════════════════════════

# 原有重複路由已由上方暴力路由區接管



# ═══════════════════════════════════════════════
#  現實種子注入輔助函數
# ═══════════════════════════════════════════════

def _inject_reality_seeds(file_paths: list[str], is_daily: bool = False):
    """注入多個現實種子到 Neo4j 圖譜記憶"""
    import sys
    import os
    
    # ─── [精準打擊協議] 僅在注入每日種子前，清除舊有臨時標籤 ───
    if is_daily:
        logger.info("[V1100] 啟動精準洗地：清除舊有 DailySeed 臨時節點...")
        try:
            # 只刪除帶有 DailySeed 標籤的節點，保留歷史資料 (Horse, Jockey, Trainer 等)
            neo4j_db.execute_query("MATCH (n:DailySeed) DETACH DELETE n")
            logger.info("[V1100] 精準洗地完成，已為今日排位表準備純淨空間")
        except Exception as e:
            logger.error(f"[V1100] 精準洗地失敗: {e}")
    else:
        logger.info("[V1100] 歷史增量模式：跳過洗地，直接進行數據合併")
    
    # 添加 scripts 目錄到路徑
    scripts_dir = BACKEND_DIR.parent / "scripts"
    sys.path.insert(0, str(scripts_dir))
    
    total_records = 0
    try:
        from v1100_neo4j_ingestor import process_file, ingest_to_neo4j
        
        for file_path in file_paths:
            # 處理每個檔案
            records = process_file(file_path)
            
            if records:
                ingest_to_neo4j(records, is_daily=is_daily)
                logger.info(f"[V1100] 成功注入 {len(records)} 筆記錄到 Neo4j (檔案: {Path(file_path).name}, 每日標籤: {is_daily})")
                total_records += len(records)

            else:
                logger.warning(f"[V1100] 檔案中未找到有效記錄: {Path(file_path).name}")
            
    except Exception as e:
        logger.error(f"[V1100] Neo4j 注入異常: {e}")
        raise
    
    logger.info(f"[V1100] 批次注入完成，共處理 {len(file_paths)} 個檔案，總計 {total_records} 筆記錄")


# ═══════════════════════════════════════════════
#  Phantom Bridge (幽靈橋接協議) - 偽裝舊版 Zep 前端
# ═══════════════════════════════════════════════

@app.post("/api/graph/ontology/generate")
async def generate_ontology():
    """本體生成偽裝：直接回傳 V1100 專屬本體，跳過 LLM 呼叫"""
    logger.info("[Phantom Bridge] 攔截 Ontology 請求，回傳 V1100 專屬賽馬本體")
    return JSONResponse(content={
        "status": "success",
        "data": {
            "entity_types": ["Horse (馬匹)", "Race (賽事)", "Incident (賽事事件)", "Jockey (騎師)", "Trainer (練馬師)"],
            "relation_types": ["PARTICIPATES_IN (參賽)", "INVOLVED_IN (捲入事件)", "RIDDEN_BY (策騎)"]
        }
    })

@app.post("/api/graph/build")
async def build_graph():
    """圖譜構建回報：向本地 Neo4j 查詢真實節點數量"""
    logger.info("[Phantom Bridge] 攔截 Build Graph 請求，查詢 Neo4j 狀態")
    nodes_count = 0
    edges_count = 0
    try:
        driver = neo4j_db._get_driver()
        with driver.session() as session:
            n_res = session.run("MATCH (n) RETURN count(n) AS c")
            nodes_count = n_res.single()["c"]
            e_res = session.run("MATCH ()-[r]->() RETURN count(r) AS c")
            edges_count = e_res.single()["c"]
        logger.info(f"[Phantom Bridge] 查詢結果：Nodes={nodes_count}, Edges={edges_count}")
    except Exception as e:
        logger.error(f"[Phantom Bridge] Neo4j 查詢失敗: {e}")
        
    return JSONResponse(content={
        "status": "success",
        "message": "Neo4j 本地圖譜構建完成",
        "stats": {"entities": nodes_count, "relations": edges_count, "schemas": 5}
    })

@app.post("/api/simulation/create")
async def create_simulation():
    """模擬環境初始化偽裝：回傳綠燈"""
    logger.info("[Phantom Bridge] 攔截 Simulation Create 請求，核發通行證")
    return JSONResponse(content={
        "status": "success",
        "message": "V1100 蜂群推演環境已就緒，等待首長下達戰術指令。"
    })

@app.post("/api/simulation/prepare")
async def prepare_simulation():
    """Agent 人設與劇本覆寫：抹除前朝資料，提供賽馬矩陣配置"""
    logger.info("[Phantom Purge] 攔截 Simulation Prepare 請求，注入 V1100 賽馬矩陣配置")
    return JSONResponse(content={
        "status": "success",
        "data": {
            "agents": [
                {"id": "agent_1", "name": "量化分析師", "persona": "專注於檔位、負磅與步速的數據流專家", "role": "Analyst"},
                {"id": "agent_2", "name": "晨操觀察員", "persona": "緊盯馬匹試閘狀態與體能變化的實地觀察者", "role": "Observer"},
                {"id": "agent_3", "name": "圖譜情報官", "persona": "精通 Neo4j 歷史受阻與意外事件的特工", "role": "Intelligence"}
            ],
            "config": {
                "duration": 24, "rounds": 10, "peak_hours": ["19:00", "20:00"]
            },
            "narrative": {
                "direction": "針對即將到來的賽事進行多維度推演，尋找被市場低估的 Alpha 價值馬匹。",
                "initial_posts": [
                    {"agent": "量化分析師", "content": "排位表已鎖定，準備匯入模型進行基礎機率計算。"},
                    {"agent": "圖譜情報官", "content": "Neo4j 記憶庫已連線，正在提取目標馬匹的歷史受阻與傷患紀錄。"}
                ]
            }
        }
    })

@app.post("/api/simulation/start")
async def start_simulation(req: SimulateRequest = None):
    """終極點火與實體對接：觸發本地 Qwen 推演"""
    logger.info("[Phantom Purge] 攔截 Simulation Start 請求，啟動本地 V1100 蜂群引擎")
    
    # 若前端沒有傳入 prompt，提供預設指令
    prompt = req.prompt if req else "推演下一場重點賽事"
    
    # 將推演任務丟到背景執行
    asyncio.create_task(_run_swarm_prediction_task(prompt))
    
    return JSONResponse(content={
        "status": "success",
        "message": "V1100 蜂群引擎已點火！請查看後端終端機獲取戰術報告。",
        "simulation_id": "v1100_strike_001"
    })

async def _run_swarm_prediction_task(prompt: str):
    """背景執行蜂群推演的封裝函數"""
    logger.info(f"[系統] 收到前端點火指令，開始執行 V1100 蜂群推演... 指令: {prompt}")
    try:
        # 正則萃取日期和場次 (強化支援 YYYYMMDD 與 YYYY-MM-DD)
        import re
        date_match = re.search(r'(\d{4}-?\d{2}-?\d{2})', prompt)
        race_match = re.search(r'第\s*(\d+)\s*場', prompt)
        
        target_date = None
        if date_match:
            raw_date = date_match.group(1).replace("-", "")
            target_date = f"{raw_date[:4]}-{raw_date[4:6]}-{raw_date[6:]}"
        target_race = race_match.group(1) if race_match else None
        
        # 呼叫 v1100_predict_2026.py 中的推演邏輯
        result = await run_swarm_prediction(
            prompt=prompt,
            target_date=target_date,
            target_race=target_race
        )
        logger.info(f"[系統] 蜂群推演背景任務完成。狀態: {result.get('status')}")
    except Exception as e:
        logger.error(f"[系統] 蜂群推演背景任務失敗: {e}")
