#!/usr/bin/env python3
"""
V1100 全息指揮台啟動腳本
"""

import os
import sys
from pathlib import Path

# 添加 backend 目錄到 Python 路徑
backend_dir = Path(__file__).parent
sys.path.insert(0, str(backend_dir))

# 設置 PYTHONPATH 環境變數
os.environ['PYTHONPATH'] = str(backend_dir)

# 啟動 uvicorn
if __name__ == '__main__':
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        reload_dirs=[str(backend_dir.parent)]  # 監視整個項目目錄
    )