import json
import logging
from typing import AsyncGenerator, Dict, List, Optional, Any
import openai
from app.config import settings
from app.services.calendar_service import calendar_service
from app.services.sheets_service import sheets_service

# Set up logger
logger = logging.getLogger("llm_service")
logger.setLevel(logging.INFO)
if not logger.handlers:
    ch = logging.StreamHandler()
    ch.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
    logger.addHandler(ch)

# Initialize OpenAI-compatible Async Client
# If base_url is empty, AsyncOpenAI uses its default (https://api.openai.com/v1)
client = openai.AsyncOpenAI(
    api_key=settings.LLM_API_KEY,
    base_url=settings.LLM_BASE_URL if settings.LLM_BASE_URL else None
)

SYSTEM_PROMPT = """You are "Aura", the warm, professional, and efficient AI receptionist for Solstice Pilates—a premium boutique pilates studio in San Francisco.
Your primary role is to help callers book classes, manage reservations, answer studio questions, and handle complaints with exceptional hospitality.

STUDIO INFORMATION:
- Address: 123 Sun Valley Way, San Francisco, CA
- Phone: (415) 555-0190
- Studio Hours:
  * Monday - Friday: 7:00 AM - 8:00 PM
  * Saturday - Sunday: 8:00 AM - 4:00 PM

PRICING & MEMBERSHIPS:
- Single Class Drop-in: $35
- 10-Class Pack: $300 (savings of $50, expires in 6 months)
- Monthly Unlimited Membership: $220/month (best value, includes 2 guest passes per month)

STUDIO POLICIES:
1. Friends & Guest Drop-ins: Yes, friends can drop in for a $35 drop-in rate. If a member has guest passes (from an Unlimited Membership), they can book a spot for their friend by providing their friend's name and email/number.
2. Birthday Parties & Private Events: Yes, we host private wellness events/birthday parties on Saturdays and Sundays after 4:00 PM (outside regular hours). Price starts at $450 for a 2-hour event, including a 50-minute private group reformer session for up to 10 guests. Inquiry details must be logged.
3. Running Late:
   - If arriving under 10 minutes late: Instructors will hold their spot, and the client may join the class (but will miss the warm-up). Reassure the caller.
   - If arriving over 10 minutes late: For safety reasons, clients cannot join. They will be late-canceled. Log this and offer to rebook them to a later class.
4. Billing Complaints: Be highly empathetic and reassuring. Never dispute or argue about charges. Explain that you will immediately escalate this to the studio manager who will review and resolve it within 24 hours. Log the complaint using the inquiry tool and flag for human handoff.

DATE CONTEXT:
- Today is Wednesday, May 27, 2026. So "Thursday" / "tomorrow" refers to 2026-05-28, "Friday" to 2026-05-29, and so on. Always resolve the caller's relative day into a concrete YYYY-MM-DD date before calling tools.

CONVERSATION GUIDELINES:
- Keep answers concise, natural, and helpful. You are speaking to clients over a phone interface (simulated in text). Avoid long-winded paragraphs.
- Tone: Welcoming, calm, reassuring, and premium.
- Active Phone Context: The active caller's phone number is already registered in the system: {phone}. Use this for sheet log queries.
- Handoff Rules: Immediately trigger a human handoff when a caller:
  * Complains about a charge or billing dispute.
  * Expresses deep frustration or insists on speaking to a manager/human.
  * Has a highly complex reservation conflict that you cannot resolve via tools.

TOOL-USAGE WORKFLOW:
- When checking class availability: Use 'list_classes_and_availability'. If the 6 PM Reformer is full, suggest the 7 PM Reformer (or other open slots).
- When booking, rescheduling, or canceling: ALWAYS call 'list_classes_and_availability' first (in the current turn) to obtain the exact `id` of each class, then pass that exact `id` into 'book_class' or 'cancel_or_reschedule_booking'. Never guess or reuse a class id from earlier in the conversation — re-fetch it.
- When booking: You MUST collect the caller's Name. The Phone is automatically mapped. Confirm the booking by calling 'book_class'.
- When rescheduling/canceling: Look up their active classes first or ask them for the class time. Execute via 'cancel_or_reschedule_booking'.
- When logging complaints/parties: Always call 'log_general_inquiry_or_complaint' with the appropriate flags.
- Do NOT make up class schedules, prices, or class ids. Only use data returned by the tools.
"""

# Define available tools
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "list_classes_and_availability",
            "description": "Retrieves the list of pilates classes and remaining open spots for a given date.",
            "parameters": {
                "type": "object",
                "properties": {
                    "date": {
                        "type": "string",
                        "description": "Date formatted as YYYY-MM-DD (e.g. 2026-05-28)."
                    }
                },
                "required": ["date"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "book_class",
            "description": "Reserves a slot in a class for the client. Requires the client's name and class details.",
            "parameters": {
                "type": "object",
                "properties": {
                    "client_name": {
                        "type": "string",
                        "description": "Full name of the client to book."
                    },
                    "class_id": {
                        "type": "string",
                        "description": "Unique identifier of the class (e.g. reformer_thurs_7pm)."
                    },
                    "date": {
                        "type": "string",
                        "description": "Date of the class formatted as YYYY-MM-DD."
                    }
                },
                "required": ["client_name", "class_id", "date"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "cancel_or_reschedule_booking",
            "description": "Cancels or reschedules a client's class booking.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["cancel", "reschedule"],
                        "description": "Whether to cancel the reservation or reschedule it."
                    },
                    "current_class_id": {
                        "type": "string",
                        "description": "The class ID currently booked."
                    },
                    "new_class_id": {
                        "type": "string",
                        "description": "The new class ID to book (required only for reschedule)."
                    },
                    "date": {
                        "type": "string",
                        "description": "Date of the classes formatted as YYYY-MM-DD."
                    }
                },
                "required": ["action", "current_class_id", "date"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "log_general_inquiry_or_complaint",
            "description": "Logs general inquiries, birthday party requests, or billing charge complaints to the sheet.",
            "parameters": {
                "type": "object",
                "properties": {
                    "client_name": {
                        "type": "string",
                        "description": "Full name of the client (use 'Unknown' if not provided)."
                    },
                    "inquiry_type": {
                        "type": "string",
                        "enum": ["charge_complaint", "birthday_party", "friend_dropin", "running_late", "general_inquiry"],
                        "description": "The type of customer inquiry."
                    },
                    "details": {
                        "type": "string",
                        "description": "Descriptive summary or details of the conversation."
                    },
                    "requires_handoff": {
                        "type": "boolean",
                        "description": "Set to True if this requires immediate human manager follow-up (e.g. billing charge complaints)."
                    }
                },
                "required": ["client_name", "inquiry_type", "details", "requires_handoff"]
            }
        }
    }
]

class LLMService:
    def __init__(self):
        pass

    async def run_agent_stream(
        self,
        user_message: str,
        chat_history: List[Dict[str, Any]],
        phone: str
    ) -> AsyncGenerator[str, None]:
        """
        Executes the AI Receptionist agent loop using streaming.
        Handles tool calls, loops back with results, and yields streaming texts to the client.
        Format of yielded messages:
        - Text tokens: yields raw tokens
        - Tool call indicators: yields "STATUS: [description]" (for UI logging)
        - Handoff triggers: yields "HANDOFF: [reason]"
        """
        logger.info(f"Running LLM agent stream for phone: {phone}")

        # Construct messages payload
        system_instructions = SYSTEM_PROMPT.format(phone=phone)
        messages = [{"role": "system", "content": system_instructions}]
        
        # Add history. Only include optional keys (name, tool_call_id) when they
        # actually have values — several OpenAI-compatible providers (e.g. Groq)
        # reject explicit nulls for these fields with a 400 error.
        for msg in chat_history:
            history_msg: Dict[str, Any] = {
                "role": msg["role"],
                "content": msg.get("content"),
            }
            if msg.get("name"):
                history_msg["name"] = msg["name"]
            if msg.get("tool_call_id"):
                history_msg["tool_call_id"] = msg["tool_call_id"]
            if msg.get("tool_calls"):
                history_msg["tool_calls"] = msg["tool_calls"]
            messages.append(history_msg)

        # Add latest user message
        messages.append({"role": "user", "content": user_message})

        loop_count = 0
        max_loops = 5  # Safe cutoff to prevent infinite agent tool loops

        while loop_count < max_loops:
            loop_count += 1
            logger.info(f"Agent Loop iteration {loop_count}")

            # Request LLM stream
            try:
                response_stream = await client.chat.completions.create(
                    model=settings.LLM_MODEL,
                    messages=messages,
                    tools=TOOLS,
                    tool_choice="auto",
                    stream=True
                )
            except Exception as e:
                logger.error(f"Error calling LLM provider: {e}")
                yield f"\n[System Error: Failed to communicate with LLM provider. Error details: {e}]"
                return

            tool_calls_accumulated = {}
            assistant_content_chunks = []
            
            async for chunk in response_stream:
                delta = chunk.choices[0].delta
                
                # Check for standard text output
                if delta.content:
                    assistant_content_chunks.append(delta.content)
                    yield delta.content

                # Check for tool call deltas
                if delta.tool_calls:
                    for tc_delta in delta.tool_calls:
                        idx = tc_delta.index
                        if idx not in tool_calls_accumulated:
                            tool_calls_accumulated[idx] = {
                                "id": tc_delta.id or "",
                                "name": tc_delta.function.name or "",
                                "arguments": ""
                            }
                        if tc_delta.id:
                            tool_calls_accumulated[idx]["id"] = tc_delta.id
                        if tc_delta.function.name:
                            tool_calls_accumulated[idx]["name"] = tc_delta.function.name
                        if tc_delta.function.arguments:
                            tool_calls_accumulated[idx]["arguments"] += tc_delta.function.arguments

            # If there was text, add it to assistant responses
            assistant_text = "".join(assistant_content_chunks)

            # If no tool calls, we are finished!
            if not tool_calls_accumulated:
                # Sync sheets log automatically at the end of the conversation if needed
                # (A simple background task handles call summaries, but we can do it dynamically here)
                return

            # Execute tool calls
            tool_calls_list = list(tool_calls_accumulated.values())
            logger.info(f"Agent executing tool calls: {tool_calls_list}")
            
            # Format and append assistant's message requesting tool calls
            openai_tool_calls = []
            for tc in tool_calls_list:
                openai_tool_calls.append({
                    "id": tc["id"],
                    "type": "function",
                    "function": {
                        "name": tc["name"],
                        "arguments": tc["arguments"]
                    }
                })
            
            messages.append({
                "role": "assistant",
                "content": assistant_text or None,
                "tool_calls": openai_tool_calls
            })

            for tc in tool_calls_list:
                tool_name = tc["name"]
                tool_args_str = tc["arguments"]
                tool_call_id = tc["id"]

                # Parse arguments
                try:
                    args = json.loads(tool_args_str) if tool_args_str else {}
                except json.JSONDecodeError as je:
                    logger.error(f"JSON Decode Error for tool args: {tool_args_str} - {je}")
                    args = {}

                # Execute specific tool
                tool_result = ""
                handoff_triggered = False
                handoff_reason = ""

                yield f"STATUS: ⚙️ Running {tool_name.replace('_', ' ')}..."

                try:
                    if tool_name == "list_classes_and_availability":
                        date = args.get("date")
                        if not date:
                            raise ValueError("Missing 'date' parameter.")
                        
                        classes = calendar_service.get_classes(date)
                        # Format classes list cleanly for the model
                        formatted_classes = []
                        for c in classes:
                            spots_left = c["capacity"] - c["booked_count"]
                            formatted_classes.append(
                                f"- Class: {c['name']} | ID: {c['id']} | Instructor: {c['instructor']} | Time: {c['time']} | Remaining Spots: {spots_left}/{c['capacity']}"
                            )
                        
                        if formatted_classes:
                            tool_result = f"Classes available on {date}:\n" + "\n".join(formatted_classes)
                        else:
                            tool_result = f"No classes scheduled on {date}."

                    elif tool_name == "book_class":
                        client_name = args.get("client_name")
                        class_id = args.get("class_id")
                        date = args.get("date")
                        
                        if not client_name or not class_id or not date:
                            raise ValueError("Missing required parameter: client_name, class_id, or date.")
                        
                        # Add booking on Google Calendar (or Mock)
                        booking_res = calendar_service.create_booking(
                            client_name=client_name,
                            phone=phone,
                            class_id=class_id,
                            date_str=date
                        )
                        
                        # Synchronize Contact into Google Sheets Contacts tab
                        contact_res = sheets_service.upsert_contact(
                            phone=phone,
                            name=client_name,
                            notes=f"Booked class {class_id} on {date}."
                        )

                        # Log call in Call Logs
                        sheets_service.log_call_summary(
                            phone=phone,
                            name=client_name,
                            summary=f"Booked {class_id} on {date}.",
                            handoff=False
                        )
                        
                        if booking_res.get("status") == "already_booked":
                            tool_result = f"Booking failed. Client is already registered in class {class_id}."
                        else:
                            tool_result = f"Success! Booking confirmed for {client_name} in class {class_id} on {date}."

                    elif tool_name == "cancel_or_reschedule_booking":
                        action = args.get("action")
                        current_class_id = args.get("current_class_id")
                        new_class_id = args.get("new_class_id")
                        date = args.get("date")

                        if not action or not current_class_id or not date:
                            raise ValueError("Missing required parameter: action, current_class_id, or date.")

                        # Fetch Contact details for name reference
                        contact = sheets_service.get_contact(phone)
                        client_name = contact.get("Name", "Unknown") if contact else "Caller"

                        if action == "cancel":
                            cancel_res = calendar_service.cancel_booking(
                                phone=phone,
                                class_id=current_class_id,
                                date_str=date
                            )
                            
                            sheets_service.log_call_summary(
                                phone=phone,
                                name=client_name,
                                summary=f"Canceled class {current_class_id} booking for {date}.",
                                handoff=False
                            )
                            tool_result = f"Success! Reservation in class {current_class_id} on {date} has been canceled."

                        elif action == "reschedule":
                            if not new_class_id:
                                raise ValueError("Missing 'new_class_id' for reschedule action.")
                            
                            resched_res = calendar_service.reschedule_booking(
                                phone=phone,
                                current_class_id=current_class_id,
                                new_class_id=new_class_id,
                                date_str=date
                            )
                            
                            sheets_service.log_call_summary(
                                phone=phone,
                                name=client_name,
                                summary=f"Rescheduled class from {current_class_id} to {new_class_id} for {date}.",
                                handoff=False
                            )
                            tool_result = f"Success! Rescheduled from class {current_class_id} to {new_class_id} on {date}."

                    elif tool_name == "log_general_inquiry_or_complaint":
                        client_name = args.get("client_name")
                        inquiry_type = args.get("inquiry_type")
                        details = args.get("details")
                        requires_handoff = args.get("requires_handoff", False)

                        if not client_name or not inquiry_type or not details:
                            raise ValueError("Missing parameter: client_name, inquiry_type, or details.")

                        # Sync sheet contact if it's a known name
                        if client_name != "Unknown":
                            sheets_service.upsert_contact(phone=phone, name=client_name)

                        # Write to call logs sheet
                        sheets_service.log_call_summary(
                            phone=phone,
                            name=client_name,
                            summary=f"Inquiry [{inquiry_type}]: {details}",
                            handoff=requires_handoff,
                            handoff_reason=details if requires_handoff else ""
                        )

                        if requires_handoff:
                            handoff_triggered = True
                            handoff_reason = f"Billing charge complaint or dispute escalation [{inquiry_type}]: {details}"
                            tool_result = f"Logged billing complaint and flagged for IMMEDIATE Human Handoff. Details: {details}."
                        else:
                            tool_result = f"Successfully logged general inquiry: {inquiry_type}. No immediate handoff needed."

                except Exception as ex:
                    logger.error(f"Error executing tool {tool_name}: {ex}", exc_info=True)
                    tool_result = f"Error executing tool {tool_name}: {ex}"

                # Append tool result to messages history
                messages.append({
                    "role": "tool",
                    "name": tool_name,
                    "tool_call_id": tool_call_id,
                    "content": tool_result
                })

                if handoff_triggered:
                    yield f"HANDOFF: {handoff_reason}"

        # If loop limit exceeded
        yield "\n[System Notice: Maximum agent reasoning loop exceeded. Redirecting to human support.]"

llm_service = LLMService()
