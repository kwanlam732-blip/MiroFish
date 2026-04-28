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
            horse_name = row.get('horse_name') or row.get('horse') or row.get('馬名') or row.get('馬匹')
            horse_code = row.get('horse_code') or row.get('code') or row.get('馬代號')
            date = row.get('date') or row.get('日期')
            race = row.get('race') or row.get('場次') or row.get('race_no') or row.get('race_number')
            incident = row.get('incident') or row.get('description') or row.get('事件') or '無特別報告'

            if not horse_name or not date or not race:
                continue

            records.append({
                'horse_name': horse_name.strip(),
                'horse_code': (horse_code or '').strip(),
                'date': date.strip(),
                'race': race.strip(),
                'incident': incident.strip(),
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
    CREATE (i:Incident {
        date: record.date, 
        race: record.race, 
        description: record.incident
    })
    CREATE (h)-[:HAS_INCIDENT]->(i)
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
