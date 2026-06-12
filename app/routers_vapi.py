import json
import logging
from typing import Dict, Any, List
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import StreamingResponse

from app.services.llm_service import llm_service
from app.models.schemas import ChatMessage

logger = logging.getLogger("vapi_router")
vapi_router = APIRouter()

@vapi_router.post("/api/vapi/chat")
async def vapi_custom_llm(request: Request):
    """
    Acts as a Custom LLM endpoint for Vapi.
    Vapi posts the chat history and the call context.
    We return an SSE stream matching OpenAI's chat completion format.
    """
    body = await request.json()
    logger.info(f"Received Vapi chat loop request")

    messages = body.get("messages", [])
    call = body.get("call", {})
    customer = call.get("customer", {})
    phone = customer.get("number", "Unknown Caller")

    # Extract the last user message and the history
    if not messages:
        raise HTTPException(status_code=400, detail="No messages provided.")

    # Format history and extract the latest user message
    chat_history = []
    user_message = ""
    
    for msg in messages:
        role = msg.get("role")
        content = msg.get("content", "")
        # Vapi might send a system prompt which we can skip since run_agent_stream handles our system prompt
        if role == "system":
            continue
        
        # We find the last user message
        if msg == messages[-1] and role == "user":
            user_message = content
        else:
            chat_history.append({
                "role": role,
                "content": content
            })

    async def vapi_event_generator():
        # First chunk expected by Vapi (OpenAI format)
        yield f"data: {json.dumps({'id': 'vapi-1', 'object': 'chat.completion.chunk', 'choices': [{'index': 0, 'delta': {'role': 'assistant'}, 'finish_reason': None}]})}\n\n"

        try:
            # We call the existing phase 1 agent logic!
            async for token in llm_service.run_agent_stream(
                user_message=user_message,
                chat_history=chat_history,
                phone=phone
            ):
                # The run_agent_stream yields raw content, STATUS triggers, and HANDOFF triggers.
                # We filter out UI triggers for voice since Vapi only cares about spoken text
                if token.startswith("STATUS: ") or token.startswith("HANDOFF: "):
                    continue
                else:
                    # Send standard token delta
                    yield f"data: {json.dumps({'id': 'vapi-1', 'object': 'chat.completion.chunk', 'choices': [{'index': 0, 'delta': {'content': token}, 'finish_reason': None}]})}\n\n"

            # Finish reason
            yield f"data: {json.dumps({'id': 'vapi-1', 'object': 'chat.completion.chunk', 'choices': [{'index': 0, 'delta': {}, 'finish_reason': 'stop'}]})}\n\n"
            yield "data: [DONE]\n\n"
        except Exception as ex:
            logger.error(f"Error in Vapi generator: {ex}", exc_info=True)
            yield f"data: {json.dumps({'id': 'vapi-1', 'object': 'chat.completion.chunk', 'choices': [{'index': 0, 'delta': {'content': ' Sorry, I encountered an internal error.'}, 'finish_reason': 'stop'}]})}\n\n"
            yield "data: [DONE]\n\n"

    return StreamingResponse(vapi_event_generator(), media_type="text/event-stream")
