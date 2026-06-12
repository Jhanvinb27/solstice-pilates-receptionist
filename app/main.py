import os
import json
import logging
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError

from app.config import settings
from app.models.schemas import ChatRequest
from app.services.llm_service import llm_service
from app.services.calendar_service import calendar_service
from app.services.sheets_service import sheets_service
from app.routers_vapi import vapi_router

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("main")

app = FastAPI(
    title="Solstice Pilates AI Receptionist API",
    description="Backend API for the Solstice Pilates AI receptionist system with streaming and Google integrations.",
    version="1.0.0"
)

app.include_router(vapi_router)

# Base path setup
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")

# Mount static folder for CSS, JS, Images
if os.path.exists(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
else:
    logger.warning(f"Static directory not found at {STATIC_DIR}. Frontend may not load correctly.")

# Serve the main landing page at /
@app.get("/", response_class=HTMLResponse)
async def serve_frontend():
    index_path = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(index_path):
        with open(index_path, "r") as f:
            return HTMLResponse(content=f.read())
    else:
        return HTMLResponse(
            content="<h1>Solstice Pilates AI Receptionist</h1><p>Frontend static files not found. Ensure app/static/index.html is created.</p>",
            status_code=404
        )

# API Endpoint to get system configuration status
@app.get("/api/config")
async def get_config_status():
    return {
        "llm_provider": settings.LLM_PROVIDER,
        "llm_model": settings.LLM_MODEL,
        "use_mock_services": settings.USE_MOCK_SERVICES and calendar_service.use_mock,
        "calendar_connected": not calendar_service.use_mock,
        "sheets_connected": not sheets_service.use_mock,
        "calendar_id": settings.GOOGLE_CALENDAR_ID,
        "spreadsheet_id": settings.GOOGLE_SHEETS_SPREADSHEET_ID or "Using Local Mock DB"
    }

# API Endpoint to fetch current Classes (Calendar database)
@app.get("/api/calendar")
async def get_calendar_state(date: str = "2026-05-28"):
    try:
        classes = calendar_service.get_classes(date)
        return {"classes": classes}
    except Exception as e:
        logger.error(f"Error fetching calendar state: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# API Endpoint to fetch current Sheets database (Contacts & Call Logs)
@app.get("/api/sheets")
async def get_sheets_state():
    try:
        contacts = sheets_service.get_contacts()
        call_logs = sheets_service.get_call_logs()
        return {
            "contacts": contacts,
            "call_logs": call_logs
        }
    except Exception as e:
        logger.error(f"Error fetching sheets state: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# API Endpoint to reset Mock Databases to original state
@app.post("/api/reset")
async def reset_mock_databases():
    try:
        # 1. Reset Calendar Mock
        calendar_path = calendar_service.mock_file_path
        if os.path.exists(calendar_path):
            os.remove(calendar_path)
        calendar_service._ensure_mock_file_exists()
        calendar_service.get_classes("2026-05-28")  # Prepopulate default Thursday
        
        # 2. Reset Sheets Mock
        sheets_path = sheets_service.mock_file_path
        if os.path.exists(sheets_path):
            os.remove(sheets_path)
        sheets_service._ensure_mock_file_exists()
        # Seed sheets default
        default_data = {
            "Contacts": [
                {
                    "Phone": "415-555-0100",
                    "Name": "Jessica Taylor",
                    "Email": "jessica@example.com",
                    "Notes": "Prefers Emma's morning Reformer classes.",
                    "Created At": "2026-05-15T09:30:00Z"
                },
                {
                    "Phone": "415-555-0122",
                    "Name": "David Smith",
                    "Email": "david.smith@example.com",
                    "Notes": "Has lower back concerns, avoid heavy twisting.",
                    "Created At": "2026-05-20T14:15:00Z"
                }
            ],
            "Call Logs": [
                {
                    "Call ID": "call_001",
                    "Phone": "415-555-0100",
                    "Name": "Jessica Taylor",
                    "Summary": "Inquired about class packs and booking policies. Booked mat pilates.",
                    "Handoff Required": False,
                    "Handoff Reason": "",
                    "Created At": "2026-05-25T10:05:00Z"
                },
                {
                    "Call ID": "call_002",
                    "Phone": "415-555-0155",
                    "Name": "Unknown Caller",
                    "Summary": "Complained about being double-charged for the 10-class pack on their credit card.",
                    "Handoff Required": True,
                    "Handoff Reason": "Billing charge dispute / double charge complaint",
                    "Created At": "2026-05-25T11:42:00Z"
                }
            ]
        }
        with open(sheets_path, "w") as f:
            json.dump(default_data, f, indent=2)

        logger.info("Successfully reset all mock databases.")
        return {"status": "success", "message": "Databases reset to initial state successfully."}
    except Exception as e:
        logger.error(f"Error resetting mock databases: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Streaming endpoint for chat conversations using SSE (Server-Sent Events)
@app.post("/api/chat/stream")
async def chat_stream_endpoint(request: ChatRequest):
    """
    Core Chat Endpoint. Receives chat message, phone number, and history.
    Streams back JSON-encoded SSE events including tokens, status indicators, and handoff triggers.
    """
    logger.info(f"Received chat stream request for phone {request.phone}")

    async def event_generator():
        # Convert ChatMessage Pydantic objects to dictionary history
        history_list = []
        for msg in request.history:
            history_list.append({
                "role": msg.role,
                "content": msg.content,
                "name": msg.name,
                "tool_call_id": msg.tool_call_id
            })

        try:
            # Stream the receptionist agent responses
            async for token in llm_service.run_agent_stream(
                user_message=request.message,
                chat_history=history_list,
                phone=request.phone
            ):
                if token.startswith("STATUS: "):
                    # Yield tool run status to update UI
                    yield f"data: {json.dumps({'type': 'status', 'content': token[8:]})}\n\n"
                elif token.startswith("HANDOFF: "):
                    # Yield handoff notification
                    yield f"data: {json.dumps({'type': 'handoff', 'content': token[9:]})}\n\n"
                else:
                    # Yield normal textual token
                    yield f"data: {json.dumps({'type': 'token', 'content': token})}\n\n"
            
            # Send completion signal
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
        except Exception as ex:
            logger.error(f"Error in streaming event generator: {ex}", exc_info=True)
            yield f"data: {json.dumps({'type': 'error', 'content': f'Internal Server Error: {ex}'})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")

if __name__ == "__main__":
    import uvicorn
    # Use port loaded from config
    uvicorn.run("app.main:app", host="0.0.0.0", port=settings.PORT, reload=True)
