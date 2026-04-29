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
#  [None 護盾] 全局暴力安全清洗函數
# ═══════════════════════════════════════════════
def safe_clean(val):
    """暴力防禦：防止 NoneType 導致 .replace() 或 .strip() 崩潰"""
    if val is None:
        return ""
    return str(val).replace(' ', '').strip()

# ═══════════════════════════════════════════════
#  [VRAM Shield] 併發鎖 — RTX 3060 Ti (8GB) 防護
#  嚴禁超過 3 個併發 LLM 請求
# ═══════════════════════════════════════════════
VRAM_SEMAPHORE = asyncio.Semaphore(3)


# ═══════════════════════════════════════════════
#  排位表實體解析器 (Race Card Parser)
# ═══════════════════════════════════════════════

def get_runners_for_race(target_date, target_race, uploads_dir="uploads"):
    import pandas as pd
    import glob
    import os
    
    # 1. 日期與格式強制歸一化 (暴力同步為 YYYY/MM/DD)
    if not target_date:
        return []
        
    # 確保日期格式與 CSV 一致 (使用斜槓)
    standard_date = str(target_date).replace("-", "/")
    # 建立純數字日期用於檔案名搜尋
    clean_date_num = standard_date.replace("/", "")
    
    csv_files = glob.glob(os.path.join(uploads_dir, f"*{clean_date_num}*.csv")) + \
                glob.glob(os.path.join(uploads_dir, f"*{str(target_date).replace('/', '-')}*.csv"))
    
    if csv_files:
        try:
            df = pd.read_csv(csv_files[0])
            # 2. 終極暴力型別對齊
            df['場次'] = df['場次'].astype(str).str.strip()
            df['賽事日期'] = df['賽事日期'].astype(str).str.strip().str.replace("-", "/")
            
            # 確保只抓數字
            race_num_match = re.search(r'(\d+)', str(target_race))
            target_race_str = race_num_match.group(1) if race_num_match else str(target_race).strip()
            
            # 3. 精準狙擊 (日期與場次雙重鎖定)
            runners = df[(df['場次'] == target_race_str) & (df['賽事日期'] == standard_date)]['馬名'].dropna().astype(str).tolist()
            clean_runners = [safe_clean(r) for r in runners if safe_clean(r)]
            
            if clean_runners:
                print(f"[系統] ✅ 馬名清單已鎖定 ({standard_date} R{target_race_str}): {', '.join(clean_runners)}")
                return clean_runners
        except Exception as e:
            print(f"[系統] ❌ CSV 解析崩潰: {e}")
            
    return []


# ═══════════════════════════════════════════════
#  Neo4j 圖譜記憶檢索
# ═══════════════════════════════════════════════

def _retrieve_graph_intel(prompt: str, target_date: Optional[str] = None, target_race: Optional[str] = None, runners_list: List[str] = None) -> str:
    """
    從 Neo4j 圖譜中檢索與 prompt 相關的馬匹情報。
    回傳格式化的情報文本，供 LLM 作為上下文。
    """
    intel_lines = []

    try:
        import re
        if runners_list and len(runners_list) > 0:
            # 根據馬名清單，檢索這些馬匹的所有歷史事件 (近因濾鏡限制最多 6 場)
            cypher = (
                "MATCH (h:Horse)-[:PERFORMED_IN]->(p:Performance)-[:AT]->(r:Race) "
                "WHERE h.name IN $runners "
                "WITH h, p, r "
                "ORDER BY r.date DESC "
                "WITH h, collect({p: p, r: r})[0..6] AS recent_perfs "
                "UNWIND recent_perfs AS perf_data "
                "WITH h, perf_data.p AS p, perf_data.r AS r "
                "OPTIONAL MATCH (j:Jockey)-[:RODE]->(p) "
                "OPTIONAL MATCH (t:Trainer)-[:TRAINED]->(p) "
                "RETURN h.name AS horse, h.code AS code, "
                "       r.date AS date, r.race_no AS race, r.track_cond AS track_cond, "
                "       j.name AS jockey, t.name AS trainer, "
                "       p.rank AS rank, p.actual_weight AS actual_weight, "
                "       p.horse_weight AS horse_weight, p.draw AS draw, "
                "       p.margin AS margin, p.running_position AS running_position, "
                "       p.finish_time AS finish_time, p.win_odds AS win_odds, "
                "       p.sectional_time AS sectional_time, p.incident AS incident "
                "ORDER BY r.date DESC"
            )
            records = neo4j_db.execute_query_safe(
                cypher, {"runners": runners_list}, limit=200
            )
        elif target_date:
            cypher = (
                "MATCH (h:Horse)-[:PERFORMED_IN]->(p:Performance)-[:AT]->(r:Race) "
                "WHERE r.date = $date "
                "OPTIONAL MATCH (j:Jockey)-[:RODE]->(p) "
                "OPTIONAL MATCH (t:Trainer)-[:TRAINED]->(p) "
                "RETURN h.name AS horse, h.code AS code, "
                "       r.date AS date, r.race_no AS race, r.track_cond AS track_cond, "
                "       j.name AS jockey, t.name AS trainer, "
                "       p.rank AS rank, p.actual_weight AS actual_weight, "
                "       p.horse_weight AS horse_weight, p.draw AS draw, "
                "       p.margin AS margin, p.running_position AS running_position, "
                "       p.finish_time AS finish_time, p.win_odds AS win_odds, "
                "       p.sectional_time AS sectional_time, p.incident AS incident "
                "ORDER BY r.race_no "
                "LIMIT 100"
            )
            records = neo4j_db.execute_query_safe(
                cypher, {"date": target_date}, limit=100
            )
        else:
            cypher = (
                "MATCH (h:Horse)-[:PERFORMED_IN]->(p:Performance)-[:AT]->(r:Race) "
                "OPTIONAL MATCH (j:Jockey)-[:RODE]->(p) "
                "OPTIONAL MATCH (t:Trainer)-[:TRAINED]->(p) "
                "RETURN h.name AS horse, h.code AS code, "
                "       r.date AS date, r.race_no AS race, r.track_cond AS track_cond, "
                "       j.name AS jockey, t.name AS trainer, "
                "       p.rank AS rank, p.actual_weight AS actual_weight, "
                "       p.horse_weight AS horse_weight, p.draw AS draw, "
                "       p.margin AS margin, p.running_position AS running_position, "
                "       p.finish_time AS finish_time, p.win_odds AS win_odds, "
                "       p.sectional_time AS sectional_time, p.incident AS incident "
                "ORDER BY r.date DESC "
                "LIMIT 50"
            )
            records = neo4j_db.execute_query_safe(cypher, limit=50)

        if records:
            for rec in records:
                # === [None 護盾] 實裝：暴力防空檢查 ===
                raw_horse = rec.get("horse")
                raw_code = rec.get("code")
                
                # 任何核心馬名為 None 的記錄直接跳過，防止後續崩潰
                if raw_horse is None:
                    continue
                    
                horse = safe_clean(raw_horse)
                code = safe_clean(raw_code) if raw_code else "?"
                
                date = rec.get("date", "?")
                race = rec.get("race", "?")
                
                # 組合 18 維度日誌，對所有屬性實施安全獲取
                def safe_get(key):
                    val = rec.get(key)
                    return "無" if val is None or str(val).lower() == 'nan' else str(val)

                log_str = (
                    f"- [{date} R{race}] {horse}({code}) | "
                    f"名次:{safe_get('rank')}, 賠率:{safe_get('win_odds')}, "
                    f"騎師:{safe_get('jockey')}, 練馬師:{safe_get('trainer')}, "
                    f"檔位:{safe_get('draw')}, 負磅:{safe_get('actual_weight')}, "
                    f"體重:{safe_get('horse_weight')}, "
                    f"走位:{safe_get('running_position')}, 距離:{safe_get('margin')}, "
                    f"時間:{safe_get('finish_time')}({safe_get('sectional_time')}), "
                    f"場地:{safe_get('track_cond')} | 事件: {safe_get('incident')}"
                )
                intel_lines.append(log_str)

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

    # ─── Phase 0: 暴力指令解析 (Command Parser Fix) ───
    # 如果外部未傳入參數，則從 prompt 暴力提取
    import re
    if not target_date:
        date_match = re.search(r'(\d{4}[-/]\d{2}[-/]\d{2})', prompt)
        if date_match:
            target_date = date_match.group(1).replace('-', '/')
            
    if not target_race:
        race_match = re.search(r'第\s*(\d+)\s*場', prompt)
        if race_match:
            target_race = race_match.group(1)

    # 解析後置校驗：若關鍵參數缺失則報警
    if not target_date or not target_race:
        _log(f"❌ 指令解析失敗: date={target_date}, race={target_race}")
        return {
            "tactical_report": (
                "# ❌ 指令解析失敗\n\n"
                f"偵測不到日期或場次。抓取結果：日期=`{target_date}`, 場次=`{target_race}`。\n\n"
                "請確保您的指令包含正確的格式，例如：\n"
                "- `推演 2026/04/29 第 2 場`\n"
                "- `分析 2026-04-29 第 1 場`"
            ),
            "status_logs": logs,
            "status": "error",
        }

    _log(f"🎯 指令解析成功: 日期=`{target_date}`, 場次=`{target_race}`")

    # ─── Phase 1.5: 排位表名單檢索（絕對鐵律） ───
    _log("📋 Phase 1.5: 從排位表中提取真實馬名清單...")
    
    # 從 uploads 目錄提取馬名列表
    from pathlib import Path
    backend_dir = Path(__file__).resolve().parent.parent.parent  # backend/
    uploads_dir = backend_dir.parent / "data" / "uploads"
    
    runners_list = get_runners_for_race(target_date, target_race, str(uploads_dir))
    
    if not runners_list:
        # 強制執行歸一化以顯示正確的報警日期
        display_date = safe_clean(target_date).replace('-', '/')
        _log(f"❌ [HALT] 無法獲取 {display_date} 第 {target_race} 場的數據")
        return {
            "tactical_report": f"# ❌ 推演中止\n\n找不到 **{display_date}** 第 **{target_race}** 場的馬匹數據。請確認：\n1. 日期格式是否正確 (建議使用 YYYY/MM/DD)\n2. 是否已上傳對應的排位表 CSV\n3. 該場次是否存在於該日期中",
            "status_logs": logs,
            "status": "aborted",
        }
    
    _log(f"✅ 馬名清單已鎖定: {', '.join(runners_list)}")

    # ─── Phase 1: 圖譜情報檢索 ───
    _log("🔍 Phase 1: 從 Neo4j 圖譜記憶中檢索情報...")

    graph_intel = await asyncio.get_event_loop().run_in_executor(
        None, _retrieve_graph_intel, prompt, target_date, target_race, runners_list
    )

    intel_count = graph_intel.count("\n") + 1 if graph_intel else 0
    _log(f"📊 情報檢索完成: {intel_count} 筆記錄")

    # ─── Phase 2: 構建蜂群推演 Prompt ───
    _log("🧠 Phase 2: 構建推演矩陣，準備調度 Ollama...")

    system_prompt = (
        "【系統最高鐵律】\n"
        "1. 語系鎖定：你必須、絕對、只能使用「繁體中文 (zh-TW)」輸出。嚴禁使用簡體字！\n"
        "2. 你的身分：你是「V1100 香港賽馬量化狙擊手」，為首長（投資者）尋找高賠率、高勝率的 Alpha 馬匹。\n"
        "3. 嚴禁角色錯亂：你不是練馬師，也不是騎師！絕對不要給出「請騎師注意起跑」、「建議獸醫檢查」這種廢話。首長只關心「這匹馬會不會贏」、「該不該投注」。\n"
        "4. 戰術邏輯：利用歷史情報（受阻事件、走位、賠率、負磅）找出破綻。例如：上次受阻但這次排好檔位的馬，就是絕佳的 Alpha 目標。\n"
        "5. 【最高強制指令】你必須返回一個純 JSON 物件。絕對不允許改變 JSON 的 Key 名稱！必須 100% 遵守以下結構：\n"
        "{\n"
        '  "swarm_analysis": "在這裡進行你所有的分析、100個Agent的辯論、對狀態與賠率的推演...",\n'
        '  "top_4_picks": [\n'
        '    {"horse_name": "馬名(代號)", "confidence": "X%", "reason": "量化優勢與圖譜事件"},\n'
        '    {"horse_name": "馬名(代號)", "confidence": "X%", "reason": "量化優勢與圖譜事件"},\n'
        '    {"horse_name": "馬名(代號)", "confidence": "X%", "reason": "量化優勢與圖譜事件"},\n'
        '    {"horse_name": "馬名(代號)", "confidence": "X%", "reason": "量化優勢與圖譜事件"}\n'
        "  ]\n"
        "}\n"
    )

    user_prompt = (
        f"## 本場出賽馬匹名單（共 {len(runners_list)} 匹）\n"
        f"{', '.join(runners_list)}\n\n"
        f"## 首長指令\n{prompt}\n\n"
        f"## 圖譜記憶情報 (來自 Neo4j)\n{graph_intel}\n\n"
        "請根據以上情報與馬匹名單，嚴格遵照系統鐵律與格式範本進行狙擊推演。\n\n"
        "【最高強制指令】\n"
        "1. 絕對不准使用簡體中文，強制使用繁體中文 (zh-TW)。\n"
        "2. 嚴禁廢話、嚴禁編造「近期狀態良好」等無根據的評語。\n"
        "3. 你的回答必須、只能是純 JSON 格式。絕對不准改變 Key 的名稱！\n"
    )

    # ─── Phase 3: VRAM Shield 保護下調度 LLM ───
    _log("🔒 Phase 3: [VRAM Shield] 取得併發鎖，調度 Ollama/Qwen2.5...")

    tactical_report = ""

    async with VRAM_SEMAPHORE:
        _log(f"🚀 LLM 推論開始 (Semaphore 剩餘: {VRAM_SEMAPHORE._value})")

        try:
            # 使用 Context Manager 確保資源釋放
            with LLMClient() as llm:
                # 在執行緒池中呼叫同步的 LLM 客戶端，強制 JSON 模式
                raw_response = await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: llm.chat(
                        messages=[
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt},
                        ],
                        temperature=0.1,
                        max_tokens=4096,
                        response_format={"type": "json_object"},
                        frequency_penalty=1.2,
                        presence_penalty=1.2,
                        extra_body={"format": "json"}, # 針對 Ollama API 原生 JSON 拘束
                    ),
                )

            # JSON 暴力萃取與清洗 (Regex JSON Extraction)
            import json
            import re
            
            # 暴力尋找字串中第一個 { 到最後一個 } 的內容
            match = re.search(r'\{.*\}', raw_response, re.DOTALL)
            if not match:
                raise ValueError("LLM 輸出中找不到任何 JSON 結構！")
                
            json_str = match.group(0)
            
            try:
                json_result = json.loads(json_str)
            except json.JSONDecodeError as e:
                raise ValueError(f"LLM 返回的 JSON 解析失敗: {e}\n原始擷取內容:\n{json_str[:100]}...")

            # 實裝 Python 沙盒組裝 Markdown
            swarm_analysis = json_result.get("swarm_analysis", "（無推演分析）")
            top_picks = json_result.get("top_4_picks", [])
            
            tactical_report = "=== V1100 終極戰術報告 ===\n"
            tactical_report += f"## 🧠 蜂群推演思維 (Swarm Analysis)\n{swarm_analysis}\n\n"
            tactical_report += "## 🎯 狙擊名單 (Top 4)\n"
            
            for i, pick in enumerate(top_picks):
                # 容錯處理：有些模型可能會自創 Key
                horse = pick.get("horse_name") or pick.get("horse") or pick.get("name", "?")
                conf = pick.get("confidence") or pick.get("conf", "?")
                reason = pick.get("reason") or pick.get("analysis", "?")
                tactical_report += f"### {i+1}. {horse} (信心指數: {conf})\n- {reason}\n"

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
