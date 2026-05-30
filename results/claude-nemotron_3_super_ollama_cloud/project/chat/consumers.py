import json
from channels.generic.websocket import AsyncWebsocketConsumer
from llm_service.ollama_service import OllamaService
from langchain_core.messages import HumanMessage, SystemMessage

class ChatConsumer(AsyncWebsocketConsumer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.ollama_service = OllamaService()
    
    async def connect(self):
        await self.accept()
        # Send a welcome message
        await self.send(text_data=json.dumps({
            'message': 'Hello! How can I assist you today?',
            'type': 'system'
        }))
    
    async def disconnect(self, close_code):
        pass
    
    async def receive(self, text_data):
        text_data_json = json.loads(text_data)
        message = text_data_json.get('message', '')
        
        # Prepare messages for the LLM
        messages = [
            SystemMessage(content="You are a helpful assistant."),
            HumanMessage(content=message)
        ]
        
        # Stream the response back to the client
        async for chunk in self.ollama_service.stream_response(messages):
            await self.send(text_data=json.dumps({
                'message': chunk,
                'type': 'content'
            }))
        
        # Send a message indicating the end of the stream
        await self.send(text_data=json.dumps({
            'message': '',
            'type': 'end'
        }))
