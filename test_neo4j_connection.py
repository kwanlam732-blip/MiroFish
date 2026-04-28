import os
import sys
from dotenv import load_dotenv

# 加載 .env 檔案
load_dotenv()

# 添加項目路徑
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

try:
    from backend.app.utils.neo4j_client import neo4j_db
    
    def main():
        print("═" * 50)
        print("V1100 Neo4j 本地連線測試 (真身認證版)")
        print("═" * 50)
        
        # 讀取環境變數（驗證是否正確載入）
        uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
        user = os.getenv("NEO4J_USERNAME", "neo4j")
        # 隱藏密碼
        pwd = os.getenv("NEO4J_PASSWORD", "未設定")
        pwd_display = pwd[:2] + "*" * (len(pwd)-2) if len(pwd) > 2 else "***"
        
        print(f"[*] URI      : {uri}")
        print(f"[*] USERNAME : {user}")
        print(f"[*] PASSWORD : {pwd_display}")
        print("-" * 50)
        
        print("[*] 正在嘗試連線至 Neo4j...")
        if neo4j_db.verify_connectivity():
            print("\n✅ [SUCCESS] 已成功連線至本地 Neo4j 數據庫！")
            print("   奪回控制權成功。")
            
            # 測試簡單查詢
            try:
                result = neo4j_db.execute_query("RETURN 'Connection Verified' AS status")
                print(f"[*] 測試查詢結果: {result[0]['status']}")
            except Exception as e:
                print(f"[*] 查詢測試失敗: {e}")
        else:
            print("\n❌ [FAILURE] 無法連線至 Neo4j。")
            print("   請確認 Neo4j Desktop 已啟動，且數據庫狀態為 'Active'。")
            print("   請確認 .env 中的密碼與 STEP 1 設定的一致。")
            sys.exit(1)
        print("═" * 50)

    if __name__ == "__main__":
        main()

except ImportError as e:
    print(f"❌ [ERROR] 缺少必要套件或路徑配置錯誤: {e}")
    sys.exit(1)
except Exception as e:
    print(f"❌ [HALT] 發生未知錯誤: {e}")
    sys.exit(1)
