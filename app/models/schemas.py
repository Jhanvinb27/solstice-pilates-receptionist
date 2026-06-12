from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any

class ChatMessage(BaseModel):
    role: str = Field(..., description="Role of the message author: 'user', 'assistant', 'system', or 'tool'")
    content: Optional[str] = Field(None, description="Text content of the message")
    name: Optional[str] = Field(None, description="Optional name of the sender (e.g., tool name)")
    tool_call_id: Optional[str] = Field(None, description="Required if role is 'tool'")

class ChatRequest(BaseModel):
    message: str = Field(..., description="The user's input message")
    history: List[ChatMessage] = Field(default=[], description="The conversation history")
    phone: str = Field(..., description="The caller's phone number to maintain sheet/contact context")

class ChatResponse(BaseModel):
    response: str = Field(..., description="Assistant's message text")
    handoff_required: bool = Field(default=False, description="Flag indicating if a human needs to intervene")
    handoff_reason: Optional[str] = Field(default=None, description="Reason for handing off to human")
