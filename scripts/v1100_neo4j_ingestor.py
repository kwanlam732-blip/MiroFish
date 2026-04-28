import os
import re
import glob
import sys
import csv
from dotenv import load_dotenv

# Ensure we can import the backend utils
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'backend', 'app', 'utils')))
from neo4j_client import neo4j_db

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

def process_markdown_file(file_path):
    print(f"Processing file: {file_path}")
    
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Split by the header pattern
    blocks = re.split(r'(### \d{4}-\d{2}-\d{2} \| Race \d+ \| 馬名: .*?)\n', content)
    
    records = []
    
    for i in range(1, len(blocks), 2):
        header = blocks[i]
        body = blocks[i+1]
        
        # Parse header
        # Example: ### 2026-01-01 | Race 1 | 馬名: 威威父子 (H419) [🚨 高情報價值]
        header_match = re.search(r'###\s+(\d{4}-\d{2}-\d{2})\s+\|\s+Race\s+(\d+)\s+\|\s+馬名:\s+([^\(]+)\s+\(([^\)]+)\)', header)
        
        if not header_match:
            print(f"Failed to parse header: {header}")
            continue
            
        date = header_match.group(1).strip()
        race = header_match.group(2).strip()
        horse_name = header_match.group(3).strip()
        horse_code = header_match.group(4).strip()
        
        # Extract incident
        incident_match = re.search(r'- \*\*核心事件\*\*:\s+(.*)', body)
        incident = incident_match.group(1).strip() if incident_match else "無特別報告"

        records.append({
            'horse_name': horse_name,
            'horse_code': horse_code,
            'date': date,
            'race': race,
            'incident': incident
        })

    return records


def process_csv_file(file_path):
    print(f"Processing CSV file: {file_path}")
    records = []

    with open(file_path, 'r', encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        for row in reader:
            def get_val(key):
                v = row.get(key, '').strip()
                if not v or str(v).lower() == 'nan':
                    return '無'
                return v

            horse_raw = row.get('馬名', '')
            if not horse_raw or str(horse_raw).lower() == 'nan':
                continue

            # 處理馬名與馬號
            import re
            match = re.search(r'([^\(]+)\s*\(([^\)]+)\)', horse_raw)
            if match:
                horse_name = match.group(1).strip()
                horse_code = match.group(2).strip()
            else:
                horse_name = horse_raw.strip()
                horse_code = row.get('馬號', '').strip()

            date = row.get('賽事日期', '').strip()
            race = row.get('場次', '').strip()
            if not date or not race:
                continue

            incident = row.get('競賽事件', '無特別報告')
            if not incident or incident.strip() == '---' or str(incident).lower() == 'nan':
                incident = '無特別報告'

            records.append({
                'horse_name': horse_name,
                'horse_code': horse_code,
                'jockey': get_val('騎師'),
                'trainer': get_val('練馬師'),
                'actual_weight': get_val('實際 負磅'),
                'horse_weight': get_val('排位 體重'),
                'draw': get_val('檔位'),
                'margin': get_val('頭馬 距離'),
                'running_position': get_val('沿途 走位'),
                'finish_time': get_val('完成 時間'),
                'win_odds': get_val('獨贏 賠率'),
                'sectional_time': get_val('分段時間'),
                'date': date,
                'race': race,
                'track_cond': get_val('場地狀況'),
                'info': get_val('完整賽事資訊'),
                'rank': get_val('名次'),
                'incident': incident.strip()
            })

    return records


def process_file(file_path):
    suffix = os.path.splitext(file_path)[1].lower()
    if suffix in {'.md', '.markdown'}:
        return process_markdown_file(file_path)
    if suffix == '.csv':
        return process_csv_file(file_path)
    print(f"Unsupported file type for ingestion: {suffix}")
    return []


def ingest_to_neo4j(records):
    print(f"Ingesting {len(records)} records to Neo4j...")
    
    # Batch using UNWIND
    query = """
    UNWIND $batch AS record
    MERGE (h:Horse {name: record.horse_name})
    ON CREATE SET h.code = record.horse_code
    
    MERGE (j:Jockey {name: record.jockey})
    MERGE (t:Trainer {name: record.trainer})
    MERGE (r:Race {date: record.date, race_no: record.race})
    ON CREATE SET 
        r.track_cond = record.track_cond,
        r.info = record.info
        
    CREATE (p:Performance {
        rank: record.rank,
        actual_weight: record.actual_weight,
        horse_weight: record.horse_weight,
        draw: record.draw,
        margin: record.margin,
        running_position: record.running_position,
        finish_time: record.finish_time,
        win_odds: record.win_odds,
        sectional_time: record.sectional_time,
        incident: record.incident
    })
    
    CREATE (h)-[:PERFORMED_IN]->(p)
    CREATE (p)-[:AT]->(r)
    CREATE (j)-[:RODE]->(p)
    CREATE (t)-[:TRAINED]->(p)
    """
    
    batch_size = 500
    for i in range(0, len(records), batch_size):
        batch = records[i:i+batch_size]
        try:
            neo4j_db.execute_query(query, {'batch': batch})
            print(f"Successfully ingested batch {i//batch_size + 1} ({len(batch)} records)")
        except Exception as e:
            print(f"Error ingesting batch {i//batch_size + 1}: {e}")

if __name__ == "__main__":
    narratives_dir = r"C:\Users\user\Desktop\HorseRacing\V1100_Narratives"
    md_files = glob.glob(os.path.join(narratives_dir, "V1100_Training_*.md"))
    
    all_records = []
    for md_file in md_files:
        all_records.extend(process_markdown_file(md_file))
        
    print(f"Total records extracted: {len(all_records)}")
    
    if all_records:
        ingest_to_neo4j(all_records)
        
    neo4j_db.close()
    print("Ingestion completed.")
