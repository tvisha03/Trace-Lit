import asyncio
import sys
import os
import httpx

async def main():
    # first, get a session id
    async with httpx.AsyncClient() as client:
        res = await client.get("http://localhost:8000/api/v1/sessions")
        sessions = res.json()
        if not sessions:
            print("No sessions found")
            return
        
        # take the most recent session
        session_id = sessions[0]["id"]
        
        # query messages
        res = await client.get(f"http://localhost:8000/api/v1/sessions/{session_id}/chat/messages")
        data = res.json()
        messages = data.get("messages", [])
        if not messages:
            print("No messages in session")
            return
            
        last_msg = messages[-1]
        print(f"Message ID: {last_msg['id']}")
        havf = last_msg.get("havf_results", [])
        if havf:
            print("First havf result keys:", havf[0].keys())
            print("Transformation type:", havf[0].get("transformation_type"))
        else:
            print("No havf results")

if __name__ == "__main__":
    asyncio.run(main())
