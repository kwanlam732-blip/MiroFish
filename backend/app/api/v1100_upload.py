"""
V1100 數據灌注 API
處理歷史金庫與今日排位的非同步灌注
"""

import os
import tempfile
import threading
from flask import request, jsonify
from . import graph_bp
from ..utils.logger import get_logger
from ..utils.locale import t

# 導入 V1100 核心灌注組件
import sys
# 將 scripts 目錄加入路徑以便導入 ingestor
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', 'scripts')))
try:
    import v1100_neo4j_ingestor as ingestor
except ImportError:
    # 如果路徑有問題，嘗試相對導入或記錄錯誤
    ingestor = None

logger = get_logger('mirofish.api.v1100')

# 導入預測器
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..')))
try:
    import v1100_predict_2026 as predictor
except ImportError:
    predictor = None

from ..utils.neo4j_client import neo4j_db

@graph_bp.route('/upload/history', methods=['POST'])
def upload_history():
    """
    灌注歷史金庫 (增量更新)
    """
    if not ingestor:
        return jsonify({"success": False, "detail": "V1100 Ingestor 模組未就緒"}), 500

    files = request.files.getlist('files')
    if not files:
        return jsonify({"success": False, "detail": "未檢測到上傳文件"}), 400

    # 啟動非同步背景任務
    thread = threading.Thread(target=_background_ingest, args=(files, False))
    thread.start()

    return jsonify({
        "success": True, 
        "message": f"已接收 {len(files)} 份卷宗，背景灌注協議已啟動。請監控控制台日誌。"
    })

@graph_bp.route('/upload/daily', methods=['POST'])
def upload_daily():
    """
    同步今日排位 (精準清洗 + 注入)
    """
    if not ingestor:
        return jsonify({"success": False, "detail": "V1100 Ingestor 模組未就緒"}), 500

    files = request.files.getlist('files')
    if not files:
        return jsonify({"success": False, "detail": "未檢測到上傳文件"}), 400

    # 啟動非同步背景任務
    thread = threading.Thread(target=_background_ingest, args=(files, True))
    thread.start()

    return jsonify({
        "success": True, 
        "message": f"已接收 {len(files)} 份排位，今日同步協議已啟動。舊有臨時標籤將被清洗。"
    })

@graph_bp.route('/graph_data', methods=['GET'])
def get_v1100_graph_data():
    """
    獲取 V1100 圖譜可視化數據 (ECharts 格式)
    """
    try:
        # 獲取節點
        node_query = """
        MATCH (n)
        WHERE n:Horse OR n:Jockey OR n:Trainer OR n:Race OR n:DailySeed
        RETURN id(n) as id, labels(n) as labels, 
               CASE 
                 WHEN n:Horse THEN n.name 
                 WHEN n:Jockey THEN n.name 
                 WHEN n:Trainer THEN n.name 
                 WHEN n:Race THEN n.date + ' R' + n.race_no
                 ELSE 'Unknown'
               END as name
        LIMIT 200
        """
        nodes_res = neo4j_db.execute_query(node_query)
        
        # 獲取邊
        edge_query = """
        MATCH (n)-[r]->(m)
        WHERE (n:Horse OR n:Jockey OR n:Trainer OR n:Race OR n:DailySeed)
          AND (m:Horse OR m:Jockey OR m:Trainer OR m:Race OR m:DailySeed)
        RETURN id(n) as source, id(m) as target, type(r) as type
        LIMIT 300
        """
        edges_res = neo4j_db.execute_query(edge_query)
        
        nodes = []
        for n in nodes_res:
            category = 'Unknown'
            if 'DailySeed' in n['labels']: category = 'DailySeed'
            elif 'Horse' in n['labels']: category = 'Horse'
            elif 'Jockey' in n['labels']: category = 'Jockey'
            elif 'Trainer' in n['labels']: category = 'Trainer'
            elif 'Race' in n['labels']: category = 'Race'
            
            nodes.append({
                "id": str(n['id']),
                "name": n['name'],
                "category": category
            })
            
        links = []
        for e in edges_res:
            links.append({
                "source": str(e['source']),
                "target": str(e['target']),
                "type": e['type']
            })
            
        return jsonify({"nodes": nodes, "links": links})
    except Exception as e:
        logger.error(f"獲取圖譜數據失敗: {e}")
        return jsonify({"nodes": [], "links": []})

@graph_bp.route('/simulate', methods=['POST'])
def v1100_simulate():
    """
    執行 V1100 蜂群推演
    """
    if not predictor:
        return jsonify({"success": False, "detail": "V1100 Predictor 未就緒"}), 500
        
    data = request.get_json()
    prompt = data.get('prompt', '')
    
    if not prompt:
        return jsonify({"success": False, "detail": "指令不能為空"}), 400
        
    # 解析指令 (簡單示例：推演 2026-03-29 第 2 場)
    import re
    match = re.search(r'(\d{4}-\d{2}-\d{2}).*?第\s*(\d+)\s*場', prompt)
    if not match:
        return jsonify({
            "status": "error",
            "tactical_report": "⚠️ 無法解析戰術指令。請確保包含日期 (YYYY-MM-DD) 與場次。",
            "status_logs": ["[系統] 解析失敗"]
        })
        
    date = match.group(1)
    race_no = match.group(2)
    
    # 執行推演 (背景任務由 Predictor 處理)
    try:
        report = predictor.run_v1100_prediction(date, race_no)
        return jsonify({
            "status": "success",
            "tactical_report": report,
            "status_logs": [
                f"[系統] 獲取日期 {date} 第 {race_no} 場參賽名單...",
                "[圖譜] 檢索歷史表現與競賽事件...",
                "[大腦] 啟動本地 Qwen-7B 進行蜂群推演...",
                "[精準] 應用凱利準則進行注碼優化..."
            ]
        })
    except Exception as e:
        return jsonify({
            "status": "error",
            "tactical_report": f"❌ 推演過程崩潰: {str(e)}",
            "status_logs": ["[系統] 任務中止"]
        })

def _background_ingest(files, is_daily):
    """
    背景灌注處理邏輯
    """
    temp_paths = []
    try:
        # 保存臨時文件
        for file in files:
            ext = os.path.splitext(file.filename)[1]
            fd, path = tempfile.mkstemp(suffix=ext)
            os.close(fd)
            file.save(path)
            temp_paths.append(path)

        all_records = []
        for path in temp_paths:
            records = ingestor.process_file(path)
            all_records.extend(records)

        if not all_records:
            logger.warning("背景任務結束：未從上傳文件提取到任何有效記錄")
            return

        # 執行 Neo4j 注入
        if is_daily:
            logger.info("🚨 [V1100] 執行精準清洗：清除舊有 DailySeed...")
            try:
                from ..utils.neo4j_client import neo4j_db
                neo4j_db.execute_query("MATCH (n:DailySeed) DETACH DELETE n")
            except Exception as e:
                logger.error(f"[V1100] 清洗 DailySeed 失敗: {e}")

        ingestor.ingest_to_neo4j(all_records, is_daily=is_daily)
        logger.info(f"✅ [V1100] {'今日排位' if is_daily else '歷史金庫'} 背景灌注完成，共計 {len(all_records)} 筆記錄")

    except Exception as e:
        logger.error(f"❌ [V1100] 背景灌注任務崩潰: {e}")
    finally:
        # 清理臨時文件
        for path in temp_paths:
            try:
                os.remove(path)
            except:
                pass
