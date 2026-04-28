"""
V1100 蜂群推演引擎 (Swarm Prediction Engine)
=============================================
[OPERATION NEURAL BRIDGE - STAGE 2]

核心功能：
  接收首長的自然語言指令 (如 "推演 2026-03-29")，
  從 Neo4j 圖譜記憶中檢索相關馬匹情報，
  調度本地 Ollama (Qwen2.5:7b) 進行蜂群推演，
  輸出 Markdown 格式的戰術報告。

[V1100 核武架構紅線]
  - VRAM Shield: asyncio.Semaphore(3) 嚴格併發控制
  - 絕對錨定: 合法馬匹名單物理攔截
  - 死區防禦: 信心指數 < 80 → [ABORT]
"""

import asyncio
import logging
import time
import re
from pathlib import Path
from typing import Optional, List

from ..utils.neo4j_client import neo4j_db
from ..utils.llm_client import LLMClient

logger = logging.getLogger("v1100.swarm_engine")

# ═══════════════════════════════════════════════
#  [VRAM Shield] 併發鎖 — RTX 3060 Ti (8GB) 防護
#  嚴禁超過 3 個併發 LLM 請求
# ═══════════════════════════════════════════════
VRAM_SEMAPHORE = asyncio.Semaphore(3)


# ═══════════════════════════════════════════════
#  排位表實體解析器 (Race Card Parser)
# ═══════════════════════════════════════════════

def get_runners_for_race(
    target_date: Optional[str],
    target_race: Optional[str],
    uploads_dir: str = "data/uploads"
) -> List[str]:
    """
    從排位表 Markdown 中精準抓取指定場次的所有真實馬名。
    
    Args:
        target_date: 賽事日期 (格式: YYYY-MM-DD)
        target_race: 場次編號 (格式: "1", "2", "3" 等)
        uploads_dir: uploads 目錄路徑
    
    Returns:
        馬名列表 (例如: ["太勝駒", "銳一", "鼓浪高升"])，找不到則回傳空列表
    """
    runners = []
    
    if not target_date or not target_race:
        logger.warning("[Parser] 缺少日期或場次資訊，無法解析排位表")
        return []
    
    try:
        # 嘗試找尋對應日期的 Race Card 檔案
        upload_path = Path(uploads_dir)
        
        # 格式：Race_Card_YYYYMMDD_*.md 或 Race_Card_YYYY-MM-DD_*.md
        date_formatted = target_date.replace("-", "")
        
        race_files = list(upload_path.glob(f"Race_Card_{date_formatted}*.md"))
        if not race_files:
            race_files = list(upload_path.glob(f"*{date_formatted}*.md"))
        
        if not race_files:
            logger.warning(f"[Parser] 找不到日期 {target_date} 的排位表檔案")
            return []
        
        race_file = race_files[0]
        logger.info(f"[Parser] 讀取排位表: {race_file.name}")
        
        with open(race_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 用正則表達式找尋「## 第 N 場」段落
        race_pattern = rf"##\s*第\s*{re.escape(target_race)}\s*場"
        match = re.search(race_pattern, content)
        
        if not match:
            logger.warning(f"[Parser] 找不到第 {target_race} 場的排位表")
            return []
        
        # 提取該場次的內容（從 "## 第 N 場" 到下一個 "##" 或檔案末尾）
        start_pos = match.start()
        next_section = re.search(r"\n##\s*第\s*\d+\s*場", content[start_pos + 1:])
        
        if next_section:
            end_pos = start_pos + next_section.start()
        else:
            end_pos = len(content)
        
        race_section = content[start_pos:end_pos]
        
        # 從表格中提取馬名
        # Markdown 表格格式：| 馬號 | 馬名 | ...
        table_rows = re.findall(r"\|\s*(\d+)\s*\|\s*([^|]+)\s*\|", race_section)
        
        for horse_num, horse_name in table_rows:
            horse_name = horse_name.strip()
            if horse_name and horse_name not in ["馬名", "馬名 "]:  # 跳過表頭
                runners.append(horse_name)
        
        logger.info(f"[Parser] 第 {target_race} 場解析完成，找到 {len(runners)} 匹馬: {', '.join(runners[:5])}...")
        
    except Exception as e:
        logger.error(f"[Parser] 排位表解析失敗: {e}")
        return []
    
    return runners


# ═══════════════════════════════════════════════
#  Neo4j 圖譜記憶檢索
# ═══════════════════════════════════════════════

def _retrieve_graph_intel(prompt: str, target_date: Optional[str] = None, target_race: Optional[str] = None) -> str:
    """
    從 Neo4j 圖譜中檢索與 prompt 相關的馬匹情報。
    回傳格式化的情報文本，供 LLM 作為上下文。
    """
    intel_lines = []

    try:
        # 使用提供的參數或從 prompt 中提取日期關鍵字
        import re
        if target_date:
            date_to_use = target_date
        else:
            date_match = re.search(r'(\d{4}-\d{2}-\d{2})', prompt)
            date_to_use = date_match.group(1) if date_match else None

        if date_to_use:
            # 按日期檢索該日所有事件
            cypher = (
                "MATCH (h:Horse)-[r:HAS_INCIDENT]->(i:Incident) "
                "WHERE i.date = $date "
                "RETURN h.name AS horse, h.code AS code, "
                "       i.description AS incident, i.race AS race "
                "ORDER BY i.race "
                "LIMIT 100"
            )
            records = neo4j_db.execute_query_safe(
                cypher, {"date": date_to_use}, limit=100
            )
        else:
            # 無日期 → 抓取最新的 50 筆事件作為上下文
            cypher = (
                "MATCH (h:Horse)-[r:HAS_INCIDENT]->(i:Incident) "
                "RETURN h.name AS horse, h.code AS code, "
                "       i.description AS incident, i.date AS date, i.race AS race "
                "ORDER BY i.date DESC "
                "LIMIT 50"
            )
            records = neo4j_db.execute_query_safe(cypher, limit=50)

        if records:
            for rec in records:
                horse = rec.get("horse", "?")
                code = rec.get("code", "?")
                incident = rec.get("incident", "無特別報告")
                race = rec.get("race", "?")
                date = rec.get("date", target_date if date_match else "?")
                intel_lines.append(
                    f"- [{date} R{race}] {horse}({code}): {incident}"
                )

        logger.info(
            f"[Swarm] 圖譜檢索完成: {len(records)} 筆情報 "
            f"(prompt: {prompt[:50]}...)"
        )

    except Exception as e:
        logger.warning(f"[Swarm] Neo4j 檢索失敗（將以無情報模式推演）: {e}")
        intel_lines.append("- [WARNING] Neo4j 離線，無法檢索歷史情報")

    return "\n".join(intel_lines) if intel_lines else "（無可用歷史情報）"


# ═══════════════════════════════════════════════
#  蜂群推演核心函數
# ═══════════════════════════════════════════════

async def run_swarm_prediction(
    prompt: str,
    target_date: Optional[str] = None,
    target_race: Optional[str] = None,
    log_callback: Optional[callable] = None,
) -> dict:
    """
    蜂群推演主函數。

    Args:
        prompt: 首長的自然語言指令 (如 "推演 2026-03-29")
        log_callback: 可選的日誌回調函數，接收 (str) 參數

    Returns:
        {
            "tactical_report": "...(Markdown 格式戰術報告)",
            "status_logs": ["log1", "log2", ...],
            "status": "completed" | "aborted" | "error"
        }
    """
    logs = []
    start_time = time.time()

    def _log(msg: str):
        timestamped = f"[{time.strftime('%H:%M:%S')}] {msg}"
        logs.append(timestamped)
        logger.info(f"[Swarm] {msg}")
        if log_callback:
            log_callback(timestamped)

    _log("⚡ 蜂群推演引擎啟動")
    _log(f"📡 首長指令: {prompt}")

    # ─── Phase 1.5: 排位表名單檢索（絕對鐵律） ───
    _log("📋 Phase 1.5: 從排位表中提取真實馬名清單...")
    
    # 從 uploads 目錄提取馬名列表
    from pathlib import Path
    backend_dir = Path(__file__).resolve().parent.parent.parent  # backend/
    uploads_dir = backend_dir.parent / "data" / "uploads"
    
    runners_list = get_runners_for_race(target_date, target_race, str(uploads_dir))
    
    if not runners_list:
        _log("❌ [HALT] 無法獲取排位表名單，推演終止")
        return {
            "tactical_report": "# ❌ 推演中止\n\n無法從排位表獲取馬匹名單。請確認已上傳對應日期的排位表 Markdown 檔案。",
            "status_logs": logs,
            "status": "aborted",
        }
    
    _log(f"✅ 馬名清單已鎖定: {', '.join(runners_list)}")

    # ─── Phase 1: 圖譜情報檢索 ───
    _log("🔍 Phase 1: 從 Neo4j 圖譜記憶中檢索情報...")

    graph_intel = await asyncio.get_event_loop().run_in_executor(
        None, _retrieve_graph_intel, prompt, target_date, target_race
    )

    intel_count = graph_intel.count("\n") + 1 if graph_intel else 0
    _log(f"📊 情報檢索完成: {intel_count} 筆記錄")

    # ─── Phase 2: 構建蜂群推演 Prompt ───
    _log("🧠 Phase 2: 構建推演矩陣，準備調度 Ollama...")

    system_prompt = (
        "你是 V1100 MiroFish 賽馬推演引擎的首席分析官。\n"
        "你的任務是根據歷史情報進行專業的賽馬推演分析。\n\n"
        "## 【絕對鐵律】\n"
        f"本場賽事出賽馬匹名單為：{', '.join(runners_list)}\n"
        "你輸出的報告與分析，絕對、只能、必須使用這份名單內的馬名！\n"
        "嚴禁使用「馬匹A」、「馬匹B」等代號或任何不在名單中的馬名！\n"
        "如果無法使用名單中的馬名進行分析，則必須標註 [INVALID_RUNNER]。\n\n"
        "## 輸出規範\n"
        "1. 使用繁體中文\n"
        "2. 以 Markdown 格式輸出戰術報告\n"
        "3. 報告必須包含：推演摘要、重點馬匹分析、風險評估\n"
        "4. 對每匹重點馬匹標注信心指數 (0-100)\n"
        "5. 信心指數低於 80 的馬匹標注 [CAUTION]\n"
        "6. 嚴禁編造不存在的馬匹名稱\n"
    )

    user_prompt = (
        f"## 本場出賽馬匹名單（共 {len(runners_list)} 匹）\n"
        f"{', '.join(runners_list)}\n\n"
        f"## 首長指令\n{prompt}\n\n"
        f"## 圖譜記憶情報 (來自 Neo4j)\n{graph_intel}\n\n"
        "請根據以上情報與馬匹名單，進行蜂群推演並輸出戰術報告。\n"
        "報告格式：\n"
        "# V1100 戰術報告\n"
        "## 推演摘要\n"
        "## 重點馬匹分析\n"
        "## 風險評估與建議\n"
    )

    # ─── Phase 3: VRAM Shield 保護下調度 LLM ───
    _log("🔒 Phase 3: [VRAM Shield] 取得併發鎖，調度 Ollama/Qwen2.5...")

    tactical_report = ""

    async with VRAM_SEMAPHORE:
        _log(f"🚀 LLM 推論開始 (Semaphore 剩餘: {VRAM_SEMAPHORE._value})")

        try:
            llm = LLMClient()

            # 在執行緒池中呼叫同步的 LLM 客戶端
            tactical_report = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: llm.chat(
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    temperature=0.4,
                    max_tokens=4096,
                ),
            )

            elapsed = time.time() - start_time
            _log(f"✅ LLM 推論完成 (耗時: {elapsed:.1f}s)")

        except Exception as e:
            elapsed = time.time() - start_time
            _log(f"❌ LLM 推論失敗 (耗時: {elapsed:.1f}s): {e}")
            return {
                "tactical_report": f"# ❌ 推演失敗\n\n錯誤: {e}",
                "status_logs": logs,
                "status": "error",
            }

    # ─── Phase 4: 報告後處理 ───
    _log("📝 Phase 4: 報告後處理與完整性驗證...")

    if not tactical_report or len(tactical_report.strip()) < 50:
        _log("⚠️ [ABORT] 報告內容不足，判定推演失敗")
        return {
            "tactical_report": "# ⚠️ 推演中止\n\n報告內容不足，可能因情報不足或模型異常。",
            "status_logs": logs,
            "status": "aborted",
        }

    elapsed = time.time() - start_time
    _log(f"🏁 蜂群推演完成 (總耗時: {elapsed:.1f}s)")

    return {
        "tactical_report": tactical_report,
        "status_logs": logs,
        "status": "completed",
    }
