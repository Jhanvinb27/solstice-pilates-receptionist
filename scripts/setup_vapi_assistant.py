import requests
import json
import os

VAPI_API_KEY = os.environ.get("VAPI_API_KEY", "your-vapi-api-key")
SERVER_URL = os.environ.get("SERVER_URL", "https://your-ngrok-url.ngrok.app")

headers = {
    "Authorization": f"Bearer {VAPI_API_KEY}",
    "Content-Type": "application/json"
}

payload = {
    "name": "Solstice Pilates Phase 2 Voice",
    "voice": {
        "provider": "11labs",
        "voiceId": "pqHfZKP75CvOlQylNhV4"  # Bill, nice natural 11labs
    },
    "model": {
        "provider": "custom-llm",
        "url": f"{SERVER_URL}/api/vapi/chat",
        "model": "gpt-4o"
    },
    "transcriber": {
        "provider": "deepgram",
        "model": "nova-2",
        "language": "en"
    },
    "recordingEnabled": True,
    "firstMessage": "Thank you for calling Solstice Pilates! My name is Aura. How can I help you today?",
    "silenceTimeoutSeconds": 40,
    "maxDurationSeconds": 600,
    "clientMessages": ["transcript", "hang", "function-call", "speech-update"],
    "serverMessages": ["end-of-call-report", "status-update", "hang"]
}

print(f"Creating Vapi Assistant targeting URL: {SERVER_URL}/api/vapi/chat...")
response = requests.post("https://api.vapi.ai/assistant", headers=headers, json=payload)
if response.status_code == 201:
    print("Success! Assistant ID:", response.json().get("id"))
else:
    print("Failed!", response.status_code, response.text)
