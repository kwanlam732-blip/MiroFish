import os
import sys
from dotenv import load_dotenv

# Add the project root to sys.path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, project_root)

from backend.app.services.zep_tools import ZepToolsService

def test_neo4j_retrieval():
    print("Testing ZepToolsService.search_graph (now backed by Neo4j)...")
    service = ZepToolsService("horse_memory")
    
    # Query for a known horse from V1100_Training_2026.md
    # Let's search for "鐵甲驌龍" (J459) or just something general
    query = "鐵甲驌龍"
    print(f"Executing search_graph for query: {query}")
    
    try:
        results = service.search_graph(graph_id="horse_memory", query=query)
        print(f"Results type: {type(results)}")
        print(f"Results count: {len(results) if isinstance(results, list) else 'Unknown'}")
        print("Results:")
        
        # Parse the JSON string results if needed, or if it returns strings
        if isinstance(results, str):
            print(results)
        else:
            for i, result in enumerate(results):
                print(f"[{i+1}] {result}")
                
    except Exception as e:
        print(f"Error during retrieval: {e}")

if __name__ == "__main__":
    load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))
    test_neo4j_retrieval()
