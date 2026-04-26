import os
import re
import glob
import sys
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
        
        # Only ingest if there's an actual incident worth reporting, or perhaps all?
        # "無特別報告" means no special report. We might still want to record the race entry, but the user specifies "最重要的 核心事件". 
        # Let's include everything, as it models the horse's history.
        if incident == "無特別報告":
            continue # To save space, let's only ingest actual incidents. Wait, maybe we should just ingest it all. Let's ingest all.
            # No wait, Neo4j is a graph database, empty incidents might clutter it. 
            # I will ingest all because it can also just act as a race history graph. Let's just follow the user's explicit instructions:
            # CREATE (i:Incident {date: $date, race: $race, description: $incident})
            
        records.append({
            'horse_name': horse_name,
            'horse_code': horse_code,
            'date': date,
            'race': race,
            'incident': incident
        })

    return records

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
