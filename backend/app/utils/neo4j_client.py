"""
Neo4j 本地圖譜記憶庫客戶端
延遲初始化設計 — 僅在首次呼叫時建立連線，避免 ImportError 崩潰
"""

import os
import logging
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


class Neo4jDriver:
    """Neo4j 驅動封裝（延遲初始化）"""

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
                self._driver = GraphDatabase.driver(
                    self.uri, auth=(self.user, self.password)
                )
                logger.info(f"[Neo4j] 已連線至 {self.uri}")
            except ImportError:
                raise ImportError(
                    "[HALT] neo4j 套件未安裝。請執行: pip install neo4j"
                )
            except Exception as e:
                logger.error(f"[Neo4j] 連線失敗: {e}")
                raise
        return self._driver

    def close(self):
        if self._driver:
            self._driver.close()
            self._driver = None

    def execute_query(self, query, parameters=None):
        """執行 Cypher 查詢並返回結果列表"""
        driver = self._get_driver()
        with driver.session() as session:
            result = session.run(query, parameters)
            return [record.data() for record in result]

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
