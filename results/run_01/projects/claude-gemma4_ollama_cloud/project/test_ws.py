import asyncio
import websockets
import json

async def test_ws():
    uri = "ws://localhost:8003/ws/chat/"
    async with websockets.connect(uri) as websocket:
        print("Connected")
        await websocket.send(json.dumps({"message": "Hi"}))
        
        for i in range(5):
            try:
                msg = await asyncio.wait_for(websocket.recv(), timeout=2.0)
                print(f"Received {i}: {msg}")
            except asyncio.TimeoutError:
                print("Timeout")
                break

asyncio.run(test_ws())
