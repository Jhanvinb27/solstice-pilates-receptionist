# Solstice Pilates Receptionist - API Docs & Postman Guide

This document contains a comprehensive review of all API endpoints exposed by the Solstice Pilates FastAPI backend, including raw HTTP requests, request body schemas, and example response payloads. You can copy these details directly into **Postman** to execute manual endpoint tests.

---

## 1. System Configuration
Retrieves active configurations, including the LLM provider, current model, and active Google API connection status (Connected vs Mock).

* **Endpoint**: `GET http://localhost:8000/api/config`
* **Headers**: `Accept: application/json`

### Example Response:
```json
{
  "llm_provider": "openai",
  "llm_model": "gpt-4o",
  "use_mock_services": true,
  "calendar_connected": false,
  "sheets_connected": false,
  "calendar_id": "primary",
  "spreadsheet_id": "Using Local Mock DB"
}
```

---

## 2. Calendar Classes & Availability
Retrieves the list of scheduled Pilates classes and booking counts for a given date.

* **Endpoint**: `GET http://localhost:8000/api/calendar`
* **Query Parameters**:
  * `date`: (String YYYY-MM-DD, defaults to `2026-05-28` Thursday)
* **Headers**: `Accept: application/json`

### Example Request (Postman):
`GET http://localhost:8000/api/calendar?date=2026-05-28`

### Example Response:
```json
{
  "classes": [
    {
      "id": "reformer_thurs_6pm",
      "name": "Reformer Pilates",
      "instructor": "Emma",
      "date": "2026-05-28",
      "time": "6:00 PM",
      "capacity": 10,
      "booked_count": 10,
      "attendees": [
        {"name": "Michael Chen", "phone": "415-555-1001"},
        {"name": "Sophia Rodriguez", "phone": "415-555-1002"}
      ]
    },
    {
      "id": "reformer_thurs_7pm",
      "name": "Reformer Pilates",
      "instructor": "Emma",
      "date": "2026-05-28",
      "time": "7:00 PM",
      "capacity": 10,
      "booked_count": 8,
      "attendees": [
        {"name": "John Doe", "phone": "415-555-2001"}
      ]
    }
  ]
}
```

---

## 3. Sheet Data (Contacts & Call Logs)
Queries the current state of Google Sheets data including recorded client profiles (Contacts) and caller chat summaries (Call Logs).

* **Endpoint**: `GET http://localhost:8000/api/sheets`
* **Headers**: `Accept: application/json`

### Example Response:
```json
{
  "contacts": [
    {
      "Phone": "415-555-0100",
      "Name": "Jessica Taylor",
      "Email": "jessica@example.com",
      "Notes": "Prefers Emma's morning Reformer classes.",
      "Created At": "2026-05-15T09:30:00Z"
    }
  ],
  "call_logs": [
    {
      "Call ID": "call_002",
      "Phone": "415-555-0155",
      "Name": "Unknown Caller",
      "Summary": "Complained about being double-charged for the 10-class pack on their credit card.",
      "Handoff Required": true,
      "Handoff Reason": "Billing charge dispute / double charge complaint",
      "Created At": "2026-05-25T11:42:00Z"
    }
  ]
}
```

---

## 4. Reset Mock Databases
Clears all current session mutations and restores the Mock local JSON files (`mock_calendar.json` and `mock_sheets.json`) to their default prepopulated testing state.

* **Endpoint**: `POST http://localhost:8000/api/reset`
* **Headers**: `Content-Type: application/json`

### Example Response:
```json
{
  "status": "success",
  "message": "Databases reset to initial state successfully."
}
```

---

## 5. SSE Streaming Chat Interface
This is the core streaming chat endpoint which accepts user prompts, runs the receptionist reasoning loops, executes calendar/sheet tools, and streams structured Server-Sent Events (SSE) back in real-time.

* **Endpoint**: `POST http://localhost:8000/api/chat/stream`
* **Headers**: 
  * `Content-Type: application/json`
  * `Accept: text/event-stream`

### Example Request Body (Postman):
```json
{
  "message": "Is the 6pm Reformer class on Thursday open?",
  "phone": "415-555-0190",
  "history": []
}
```

### Example Event-Stream Output (Postman console):
```text
data: {"type": "status", "content": "⚙️ Running list classes and availability..."}

data: {"type": "token", "content": "Hi there! "}

data: {"type": "token", "content": "I just checked, and that 6pm class on Thursday is full. "}

data: {"type": "token", "content": "However, we have 2 spots open in the 7pm Reformer class right after it! Would you like me to book that instead?"}

data: {"type": "done"}
```

### Booking Example Request Body:
```json
{
  "message": "Yes, please book the 7pm Reformer instead. My name is Sara.",
  "phone": "415-555-0190",
  "history": [
    {"role": "user", "content": "Is the 6pm Reformer class on Thursday open?"},
    {"role": "assistant", "content": "I just checked, and that 6pm class on Thursday is full. However, we have 2 spots open in the 7pm Reformer class right after it! Would you like me to book that instead?"}
  ]
}
```

### Event-Stream Booking Output:
```text
data: {"type": "status", "content": "⚙️ Running book class..."}

data: {"type": "status", "content": "⚙️ Running upsert contact..."}

data: {"type": "status", "content": "⚙️ Running log call summary..."}

data: {"type": "token", "content": "Great, Sara! I've booked you into the 7:00 PM Reformer class this Thursday. "}

data: {"type": "token", "content": "Looking forward to seeing you then! Is there anything else I can help you with?"}

data: {"type": "done"}
```

### Charge Complaint (Handoff Trigger) Request Body:
```json
{
  "message": "I noticed an incorrect double charge of $300 on my credit card statement today and I want it refunded immediately.",
  "phone": "415-555-0190",
  "history": []
}
```

### Event-Stream Handoff Output:
```text
data: {"type": "status", "content": "⚙️ Running log general inquiry or complaint..."}

data: {"type": "handoff", "content": "Billing charge dispute / double charge complaint details: Double charge of $300 on card."}

data: {"type": "token", "content": "I am so sorry to hear that you were charged twice for your package, Sara. I completely understand how frustrating that must be. "}

data: {"type": "token", "content": "I have logged this billing issue right away and escalated it to our studio manager. They will review this transaction and reach out to you within the next 24 hours to issue a refund and make this right. "}

data: {"type": "token", "content": "I appreciate your patience!"}

data: {"type": "done"}
```
