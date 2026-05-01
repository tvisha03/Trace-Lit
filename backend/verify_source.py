import json
import urllib.request

BASE_URL = "http://localhost:8000/api/v1"

def test_citation():
    # Get active session
    req = urllib.request.Request(f"{BASE_URL}/sessions/")
    try:
        with urllib.request.urlopen(req) as response:
            sessions = json.loads(response.read().decode())
    except Exception as e:
        print("Failed to get sessions:", e)
        return
        
    if not sessions:
        print("No sessions found.")
        return
        
    session_id = sessions[0]["id"]
    print(f"Using session: {session_id}")

    # Send a query
    print("Sending query...")
    query_data = json.dumps({"query": "What are the main points?"}).encode('utf-8')
    req = urllib.request.Request(f"{BASE_URL}/sessions/{session_id}/chat", data=query_data, headers={'Content-Type': 'application/json'})
    
    try:
        with urllib.request.urlopen(req) as response:
            chat_resp = json.loads(response.read().decode())
    except Exception as e:
        print("Chat failed:", e)
        return
        
    havf = chat_resp.get("havf_results", [])
    if not havf:
        print("No citations found in response.")
        return
    
    print(f"Found {len(havf)} citations.")
    for item in havf:
        print(f"\nCitation Ref: {item.get('citation_ref')}")
        print(f"Paper ID: {item.get('paper_id')}")
        print(f"Page Number (from API): {item.get('page_number')}")
        print(f"Source Sentence: {item.get('source_sentence')}")
        
test_citation()
