# Aura — Solstice Pilates AI Receptionist (Phase 1)

Welcome to **Aura**, a production-grade, highly pluggable, and OpenAI-compatible AI Receptionist built for **Solstice Pilates**, a boutique reformer pilates studio in San Francisco.

Aura answers client inquiries, checks class schedules, books classes, cancels or reschedules reservations, and processes late arrivals or billing disputes.

---

## 🌟 Key Features

1. **OpenAI-Compatible Orchestration**: Connects to any standard OpenAI-compatible API endpoint (Groq, OpenRouter, Nvidia NIM, Ollama, OpenAI) via environment variables.
2. **Defensive API Design with Fail-Safe Mocking**: Includes an out-of-the-box local JSON-based mock database for both Google Calendar and Google Sheets. The application runs immediately without configuration, and transitions seamlessly to live Google APIs once credentials are set in the `.env` file.
3. **SSE Streaming & Native Tool Calling**: Streams text responses chunk-by-chunk in real-time, executing background database queries concurrently.
4. **Premium Glassmorphic Web Interface**: A premium, harmonized dark/light theme UI featuring:
   - **Simulated Caller Setup**: Toggle phone context (e.g., Sara vs. Jessica Taylor) to test customized context lookups.
   - **Live System badging**: Displays connection health and configuration details.
   - **Live Visual DB Dashboard**: Watch the calendar capacity drop, caller contacts sync, and billing dispute logs get marked for human handoff in real-time as the agent speaks!
   - **Escalation Notification**: Displays a warning alert immediately when the agent escalates a call.

---

## 📂 File Architecture

The codebase has a clean division of files:

- **`app/main.py`**: FastAPI server initialization, static routes, configuration state endpoints, and SSE stream endpoints.
- **`app/config.py`**: Environment variables manager using Pydantic Settings.
- **`app/models/schemas.py`**: Pydantic request/response model definitions.
- **`app/services/llm_service.py`**: Receptionist system guidelines, tools payload specs, streaming loops, and call-inquiry executors.
- **`app/services/calendar_service.py`**: Google Calendar API client & local JSON capacity manager.
- **`app/services/sheets_service.py`**: Google Sheets API client & local JSON Contacts/Logs manager.
- **`app/static/`**: Clean static files containing premium glass-morphic styles, structured HTML, and SSE-Fetch client scripts.
- **`app/data/`**: JSON databases containing pre-seeded initial states for testing classes (e.g. Thursday classes).
- **`tests/test_services.py`**: Comprehensive test suite checking bookings, sheet logging, and capacity conflicts.

---

## 🚀 Quick Start (Local Mock Mode)

Aura comes pre-configured to run locally using mock services so you can test all features immediately without configuring keys.

### 1. Set Up Environment

Ensure you have Python 3 installed. Navigate to the project directory and create a virtual environment:

```bash
# Navigate to the folder
cd solstice_pilates_receptionist

# Create a virtual environment
python3 -m venv venv

# Activate the virtual environment
source venv/bin/activate  # On Windows use: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Configure Environment variables

A default `.env` file is already created for you with `USE_MOCK_SERVICES=True`. It reads `app/data/mock_calendar.json` and `app/data/mock_sheets.json`.

### 3. Run the Server

Start the FastAPI server:

```bash
python3 -m uvicorn app.main:app --reload
```

Open your browser and navigate to: **`http://localhost:8000`**

---

## ⚙️ Running Automated Tests

To ensure the integrity of the booking and sheets services, run the test suite:

```bash
python3 -m unittest tests/test_services.py
```

---

## 🔑 NEXT STEPS: Configure Real LLMs & Google APIs

To activate real Google integrations and transition from Mock Mode, complete the following steps:

### Phase A: Setup Your LLM Provider

1. Open the `.env` file in the project root.
2. Edit **`LLM_PROVIDER`** (e.g., `openai`, `groq`, `openrouter`, `nvidia`, `ollama`).
3. Fill in your **`LLM_API_KEY`**.
4. Set **`LLM_BASE_URL`** if using non-OpenAI endpoints:
   - **Groq**: `https://api.groq.com/openai/v1`
   - **OpenRouter**: `https://openrouter.ai/api/v1`
   - **Nvidia NIM**: `https://integrate.api.nvidia.com/v1`
   - **Ollama**: `http://localhost:11434/v1`
5. Configure your **`LLM_MODEL`** (e.g., `llama3-70b-8192` for Groq or `gpt-4o` for OpenAI).

---

### Phase B: Configure Google Sheets (Contacts & Logs)

1. Go to the **[Google Cloud Console](https://console.cloud.google.com/)**.
2. Create a new project, navigate to **APIs & Services > Library**, search for and enable **Google Sheets API**.
3. Navigate to **APIs & Services > Credentials**, click **Create Credentials**, and select **Service Account**.
4. Download the generated credentials as a **JSON Key File** (e.g. `service_account.json`).
5. Copy the absolute path of this file or its raw JSON contents and paste it in `.env` as **`GOOGLE_SERVICE_ACCOUNT_JSON`**.
6. Create a new Google Sheet on your Google Drive.
7. Copy the Spreadsheet ID from the URL (the string between `/d/` and `/edit` in the URL: `https://docs.google.com/spreadsheets/d/SPREADSHEET_ID/edit`).
8. Paste this ID in `.env` as **`GOOGLE_SHEETS_SPREADSHEET_ID`**.
9. Share the Google Sheet with your Service Account's email (found in your downloaded JSON key) as an **Editor**.
10. Turn **`USE_MOCK_SERVICES=False`** in `.env` and restart the server. Aura will automatically initialize the `Contacts` and `Call Logs` tabs!

---

### Phase C: Configure Google Calendar (Bookings)

1. In the Google Cloud Console, enable the **Google Calendar API** for your project.
2. Open your Google Calendar in the browser.
3. Under **My Calendars**, click the three dots next to the calendar you want to use (or create a new one called "Solstice Pilates Bookings"), and click **Settings and sharing**.
4. Under **Share with specific people or groups**, click **Add people** and paste your Service Account email. Select **Make changes to events** under permissions.
5. Scroll down to the **Integrate calendar** section and copy the **Calendar ID** (e.g., `primary` or `xxxxxxx@group.calendar.google.com`).
6. Paste this ID in `.env` as **`GOOGLE_CALENDAR_ID`**.
7. Restart your server. You are now fully connected to the live Google APIs!

---

## 🎙️ Phase 2: Vapi Voice Integration

This project is fully wired for Phase 2 voice capabilities using **Vapi**. A custom REST endpoint (`/api/vapi/chat`) has been implemented to serve as a **Custom LLM** for Vapi. This means Vapi handles the transcription/TTS, and forwards the conversation array directly to our FastAPI server which retains full control over the AI tools, guidelines, and booking context.

### Setup Instructions

1. **Expose Your Server Locally:**
   Run Ngrok (or a similar tool) to expose your local FastAPI server to the internet so that Vapi can communicate with it:
   ```bash
   ngrok http 8000
   ```
   Take note of your public URL (e.g. `https://1234abcd.ngrok.app`).

2. **Run the Vapi Provisioning Script:**
   Set the required environment variables and run the provided automated setup script to provision a highly-optimized, low-latency Vapi assistant.
   ```bash
   export VAPI_API_KEY="your-vapi-private-api-key"
   export SERVER_URL="https://1234abcd.ngrok.app" # Your ngrok URL
   python scripts/setup_vapi_assistant.py
   ```

3. **Optimized Voice Knobs:**
   The provisioning script configures exactly the right "knobs" on Vapi for <1.2s latency and a human-like tempo:
   - Uses `Deepgram` (nova-2) for ultra-fast, accurate transcription.
   - Pings your local LLM custom endpoint bridging directly into the core `llm_service` agent engine.
   - Sets a `40-second` silence timeout (fast turn-taking) and prevents robotic hangs. 
   - Configures an energetic local voice (`11labs` ID).
   - Once initialized, you can use the returned `Assistant ID` to place web calls or connect a Vapi inbound phone number directly via the Vapi Dashboard!
