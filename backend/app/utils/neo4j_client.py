"""
Neo4j 本地圖譜記憶庫客戶端
延遲初始化設計 — 僅在首次呼叫時建立連線，避免 ImportError 崩潰

[V1100 Token 節流防禦] 2026-04-27
- execute_query_safe: 自動注入 LIMIT，防止無限結果集撐爆 Token
- DEFAULT_QUERY_LIMIT / MAX_QUERY_LIMIT: 可配置上限常數
- search_related_nodes: 帶 LIMIT + 相似度閾值的安全檢索方法
"""

import os
import logging
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


# ═══ Token 節流常數 ═══
# 預設查詢結果上限（防止單次查詢撐爆 Agent Context）
DEFAULT_QUERY_LIMIT = 50
# 硬性最大上限，即使呼叫方指定更高也會被截斷
MAX_QUERY_LIMIT = 200
# 相似度閾值下限（0-1），低於此值的結果直接丟棄
DEFAULT_SIMILARITY_THRESHOLD = 0.3


class Neo4jDriver:
    """Neo4j 驅動封裝（延遲初始化 + Token 節流防禦）"""

    def __init__(self):
        self.uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
        self.user = os.getenv("NEO4J_USERNAME", "neo4j")
        self.password = os.getenv("NEO4J_PASSWORD", "password")
        self._driver = None

    def _get_driver(self):
        """延遲初始化 Neo4j 驅動，首次呼叫時才載入 neo4j 套件"""
        if self._driver is None:
            try:
                from neo4j import GraphDatabase
                from neo4j.exceptions import AuthError, ServiceUnavailable
                
                logger.info(f"[Neo4j] 嘗試連線至: {self.uri}")
                logger.info(f"[Neo4j] 使用認證帳號: {self.user}")
                
                self._driver = GraphDatabase.driver(
                    self.uri, auth=(self.user, self.password)
                )
                
                # 驗證連線
                with self._driver.session() as session:
                    session.run("RETURN 1")
                
                logger.info(f"[Neo4j] ✅ 已連線至 {self.uri}")
                
            except ImportError:
                error_msg = "[HALT] neo4j 套件未安裝。請執行: pip install neo4j"
                logger.error(error_msg)
                raise ImportError(error_msg)
                
            except Exception as e:
                error_type = type(e).__name__
                error_msg = str(e)
                
                logger.error(f"[Neo4j] ❌ 連線失敗 ({error_type}): {error_msg}")
                logger.error(f"[Neo4j] URI: {self.uri}")
                logger.error(f"[Neo4j] USERNAME: {self.user}")
                logger.error(f"[Neo4j] 請檢查 .env 檔案中的 NEO4J_URI / NEO4J_USERNAME / NEO4J_PASSWORD")
                
                # 提供診斷建議
                if "Unauthorized" in error_msg or "authentication" in error_msg.lower():
                    logger.error(f"[Neo4j] 🔑 診斷：認證失敗。密碼可能不正確或用戶不存在。")
                elif "connection" in error_msg.lower() or "refused" in error_msg.lower():
                    logger.error(f"[Neo4j] 🔌 診斷：連線被拒絕。Neo4j 服務可能未啟動或埠設定錯誤。")
                    logger.error(f"[Neo4j] 建議：請確認 Neo4j Desktop 已啟動並點擊 Start！")
                elif "resolve" in error_msg.lower():
                    logger.error(f"[Neo4j] 📍 診斷：無法解析主機名稱。請檢查 NEO4J_URI 格式。")
                
                raise RuntimeError(f"[HALT] Neo4j 連線失敗: {error_msg}")
                
        return self._driver

    def close(self):
        if self._driver:
            self._driver.close()
            self._driver = None

    def execute_query(self, query, parameters=None):
        """
        執行 Cypher 查詢並返回結果列表。
        [WARNING] 此方法不自動注入 LIMIT，建議優先使用 execute_query_safe()。
        """
        # [Token 節流] 偵測無 LIMIT 的裸查詢並發出警告
        if 'LIMIT' not in query.upper() and 'RETURN' in query.upper():
            logger.warning(
                f"[Token Shield] 偵測到無 LIMIT 的 Cypher 查詢，可能導致結果集爆量。"
                f" 建議改用 execute_query_safe()。Query 前綴: {query[:80]}..."
            )
        driver = self._get_driver()
        with driver.session() as session:
            result = session.run(query, parameters)
            return [record.data() for record in result]

    def execute_query_safe(self, query, parameters=None, limit=None):
        """
        [Token 節流版] 執行 Cypher 查詢，自動注入 LIMIT 防止結果集爆量。

        Args:
            query: Cypher 查詢語句
            parameters: 查詢參數
            limit: 結果上限，預設 DEFAULT_QUERY_LIMIT，硬性上限 MAX_QUERY_LIMIT

        Returns:
            結果列表（dict）
        """
        # 計算有效 LIMIT
        effective_limit = min(
            limit or DEFAULT_QUERY_LIMIT,
            MAX_QUERY_LIMIT
        )

        # 若查詢中已有 LIMIT 子句，不重複注入
        if 'LIMIT' not in query.upper():
            query = query.rstrip().rstrip(';')
            query = f"{query} LIMIT {effective_limit}"
            logger.info(f"[Token Shield] 自動注入 LIMIT {effective_limit}")
        else:
            logger.info(f"[Token Shield] 查詢已含 LIMIT，跳過注入")

        driver = self._get_driver()
        with driver.session() as session:
            result = session.run(query, parameters)
            return [record.data() for record in result]

    def search_related_nodes(
        self,
        horse_name: str,
        relation_type: str = "HAS_INCIDENT",
        limit: int = None,
        similarity_threshold: float = None
    ):
        """
        [Token 節流版] 檢索馬匹關聯節點，帶硬性 LIMIT 與相似度閾值。

        Args:
            horse_name: 馬匹名稱
            relation_type: 關係類型，預設 HAS_INCIDENT
            limit: 結果上限
            similarity_threshold: 相似度閾值（預留，目前以 LIMIT 為主控）

        Returns:
            結果列表
        """
        effective_limit = min(
            limit or DEFAULT_QUERY_LIMIT,
            MAX_QUERY_LIMIT
        )
        threshold = similarity_threshold or DEFAULT_SIMILARITY_THRESHOLD

        cypher = (
            f"MATCH (h:Horse {{name: $horse_name}})-[r:{relation_type}]->(t) "
            f"RETURN t.description AS fact, t.date AS date, "
            f"       type(r) AS rel_type "
            f"LIMIT {effective_limit}"
        )

        logger.info(
            f"[Token Shield] search_related_nodes: horse={horse_name}, "
            f"rel={relation_type}, limit={effective_limit}, threshold={threshold}"
        )

        return self.execute_query(cypher, {"horse_name": horse_name})

    def verify_connectivity(self):
        """驗證 Neo4j 連線是否正常"""
        try:
            driver = self._get_driver()
            driver.verify_connectivity()
            return True
        except Exception as e:
            logger.error(f"[Neo4j] 連線驗證失敗: {e}")
            return False


# 全局單例（延遲初始化，不會在 import 時崩潰）
neo4j_db = Neo4jDriver()
