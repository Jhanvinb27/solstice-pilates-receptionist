import os
import json
import logging
from datetime import datetime
from typing import Dict, List, Optional, Any
from app.config import settings

# Set up logger
logger = logging.getLogger("sheets_service")
logger.setLevel(logging.INFO)
if not logger.handlers:
    ch = logging.StreamHandler()
    ch.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
    logger.addHandler(ch)

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

class SheetsService:
    def __init__(self):
        self.use_mock = settings.USE_MOCK_SERVICES
        self.mock_file_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "data",
            "mock_sheets.json"
        )
        self.client = None
        self.spreadsheet_id = settings.GOOGLE_SHEETS_SPREADSHEET_ID
        
        # Check if we should try initializing Google APIs
        if not self.use_mock:
            if not settings.GOOGLE_SERVICE_ACCOUNT_JSON or not settings.GOOGLE_SHEETS_SPREADSHEET_ID:
                logger.warning("Google credentials or Spreadsheet ID missing. Defaulting to Mock Mode.")
                self.use_mock = True
            else:
                try:
                    from google.oauth2 import service_account
                    from googleapiclient.discovery import build

                    # Handle service account JSON either as a filepath or as a direct JSON string
                    json_input = settings.GOOGLE_SERVICE_ACCOUNT_JSON.strip()
                    if json_input.startswith("{") and json_input.endswith("}"):
                        info = json.loads(json_input)
                        credentials = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
                    else:
                        credentials = service_account.Credentials.from_service_account_file(json_input, scopes=SCOPES)
                    
                    self.client = build("sheets", "v4", credentials=credentials)
                    logger.info("Successfully authenticated Google Sheets API client.")
                    
                    # Ensure spreadsheet tabs exist
                    self._ensure_real_sheets_exist()
                except Exception as e:
                    logger.error(f"Failed to initialize real Google Sheets API: {e}. Falling back to Mock Mode.", exc_info=True)
                    self.use_mock = True

        # In mock mode, ensure mock file exists
        if self.use_mock:
            self._ensure_mock_file_exists()

    def _ensure_mock_file_exists(self):
        """Creates prepopulated mock sheets file if not exists."""
        if not os.path.exists(self.mock_file_path):
            os.makedirs(os.path.dirname(self.mock_file_path), exist_ok=True)
            default_data = {
                "Contacts": [],
                "Call Logs": []
            }
            with open(self.mock_file_path, "w") as f:
                json.dump(default_data, f, indent=2)
            logger.info("Created mock sheets JSON file.")

    def _load_mock_data(self) -> Dict[str, List[Dict[str, Any]]]:
        """Loads data from mock sheets JSON."""
        try:
            with open(self.mock_file_path, "r") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading mock sheets data: {e}")
            return {"Contacts": [], "Call Logs": []}

    def _save_mock_data(self, data: Dict[str, List[Dict[str, Any]]]):
        """Saves data to mock sheets JSON."""
        try:
            with open(self.mock_file_path, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving mock sheets data: {e}")

    def _ensure_real_sheets_exist(self):
        """Verifies or creates necessary tabs (Contacts, Call Logs) in the real Google Spreadsheet."""
        try:
            spreadsheet = self.client.spreadsheets().get(spreadsheetId=self.spreadsheet_id).execute()
            sheets = [s["properties"]["title"] for s in spreadsheet.get("sheets", [])]
            
            requests = []
            if "Contacts" not in sheets:
                requests.append({
                    "addSheet": {
                        "properties": {"title": "Contacts"}
                    }
                })
            if "Call Logs" not in sheets:
                requests.append({
                    "addSheet": {
                        "properties": {"title": "Call Logs"}
                    }
                })
            
            if requests:
                body = {"requests": requests}
                self.client.spreadsheets().batchUpdate(spreadsheetId=self.spreadsheet_id, body=body).execute()
                logger.info("Created missing tabs in Google Sheets.")

            # Add headers if sheet is empty
            for tab_name, headers in [("Contacts", ["Phone", "Name", "Email", "Notes", "Created At"]),
                                      ("Call Logs", ["Call ID", "Phone", "Name", "Summary", "Handoff Required", "Handoff Reason", "Created At"])]:
                result = self.client.spreadsheets().values().get(
                    spreadsheetId=self.spreadsheet_id,
                    range=f"{tab_name}!A1:A1"
                ).execute()
                if not result.get("values"):
                    self.client.spreadsheets().values().update(
                        spreadsheetId=self.spreadsheet_id,
                        range=f"{tab_name}!A1",
                        valueInputOption="RAW",
                        body={"values": [headers]}
                    ).execute()
                    logger.info(f"Initialized headers for {tab_name} tab.")
        except Exception as e:
            logger.error(f"Error ensuring real sheets exist: {e}")

    # --- PUBLIC API METHODS ---

    def get_contacts(self) -> List[Dict[str, Any]]:
        """Returns all contacts."""
        if self.use_mock:
            return self._load_mock_data().get("Contacts", [])
        
        try:
            result = self.client.spreadsheets().values().get(
                spreadsheetId=self.spreadsheet_id,
                range="Contacts!A1:E1000"
            ).execute()
            values = result.get("values", [])
            if not values or len(values) < 2:
                return []
            
            headers = values[0]
            contacts = []
            for row in values[1:]:
                contact = {}
                for idx, header in enumerate(headers):
                    contact[header] = row[idx] if idx < len(row) else ""
                contacts.append(contact)
            return contacts
        except Exception as e:
            logger.error(f"Error reading real Google Sheets Contacts: {e}")
            return []

    def get_contact(self, phone: str) -> Optional[Dict[str, Any]]:
        """Finds a contact by phone number."""
        contacts = self.get_contacts()
        # Clean both query phone and database phone for relaxed matching (digits only)
        query_digits = "".join(filter(str.isdigit, phone))
        for c in contacts:
            db_digits = "".join(filter(str.isdigit, c.get("Phone", "")))
            if query_digits == db_digits or c.get("Phone", "").strip() == phone.strip():
                return c
        return None

    def upsert_contact(self, phone: str, name: str, email: Optional[str] = None, notes: Optional[str] = None) -> Dict[str, Any]:
        """Creates or updates a contact in the Sheets Contacts database."""
        logger.info(f"Upserting contact for phone: {phone}, name: {name}")
        
        # Prepare the contact record
        existing = self.get_contact(phone)
        updated_notes = notes or (existing.get("Notes", "") if existing else "")
        updated_email = email or (existing.get("Email", "") if existing else "")
        created_at = existing.get("Created At", datetime.utcnow().isoformat() + "Z") if existing else datetime.utcnow().isoformat() + "Z"

        contact_record = {
            "Phone": phone,
            "Name": name,
            "Email": updated_email,
            "Notes": updated_notes,
            "Created At": created_at
        }

        if self.use_mock:
            data = self._load_mock_data()
            contacts = data.get("Contacts", [])
            
            # Find and update or append
            found_idx = -1
            query_digits = "".join(filter(str.isdigit, phone))
            for i, c in enumerate(contacts):
                db_digits = "".join(filter(str.isdigit, c.get("Phone", "")))
                if query_digits == db_digits or c.get("Phone", "").strip() == phone.strip():
                    found_idx = i
                    break
            
            if found_idx != -1:
                contacts[found_idx] = contact_record
            else:
                contacts.append(contact_record)
            
            data["Contacts"] = contacts
            self._save_mock_data(data)
            return contact_record

        # Real Google Sheet Upsert
        try:
            # Let's read the current table to find matching row
            result = self.client.spreadsheets().values().get(
                spreadsheetId=self.spreadsheet_id,
                range="Contacts!A1:A1000"
            ).execute()
            rows = result.get("values", [])
            
            row_idx = -1
            query_digits = "".join(filter(str.isdigit, phone))
            for idx, r in enumerate(rows):
                if idx == 0:
                    continue  # skip headers
                if r:
                    db_digits = "".join(filter(str.isdigit, r[0]))
                    if query_digits == db_digits or r[0].strip() == phone.strip():
                        row_idx = idx + 1 # 1-indexed for sheets
                        break
            
            headers = ["Phone", "Name", "Email", "Notes", "Created At"]
            row_values = [contact_record[h] for h in headers]

            if row_idx != -1:
                # Update existing row
                self.client.spreadsheets().values().update(
                    spreadsheetId=self.spreadsheet_id,
                    range=f"Contacts!A{row_idx}:E{row_idx}",
                    valueInputOption="RAW",
                    body={"values": [row_values]}
                ).execute()
                logger.info(f"Updated Google Sheets contact at row {row_idx}.")
            else:
                # Append new row
                self.client.spreadsheets().values().append(
                    spreadsheetId=self.spreadsheet_id,
                    range="Contacts!A1",
                    valueInputOption="RAW",
                    insertDataOption="INSERT_ROWS",
                    body={"values": [row_values]}
                ).execute()
                logger.info("Appended new contact to Google Sheets.")
            
            return contact_record
        except Exception as e:
            logger.error(f"Error upserting to real Google Sheets: {e}. Falling back to mock updates.")
            # Fail-safe local update
            self.use_mock = True
            self._ensure_mock_file_exists()
            return self.upsert_contact(phone, name, email, notes)

    def get_call_logs(self) -> List[Dict[str, Any]]:
        """Returns all call logs."""
        if self.use_mock:
            return self._load_mock_data().get("Call Logs", [])

        try:
            result = self.client.spreadsheets().values().get(
                spreadsheetId=self.spreadsheet_id,
                range="Call Logs!A1:G1000"
            ).execute()
            values = result.get("values", [])
            if not values or len(values) < 2:
                return []
            
            headers = values[0]
            logs = []
            for row in values[1:]:
                log = {}
                for idx, header in enumerate(headers):
                    log[header] = row[idx] if idx < len(row) else ""
                
                # Make sure fields that should be boolean are booleans
                if "Handoff Required" in log:
                    log["Handoff Required"] = str(log["Handoff Required"]).lower() in ("true", "1", "yes")
                logs.append(log)
            return logs
        except Exception as e:
            logger.error(f"Error reading real Google Sheets Call Logs: {e}")
            return []

    def log_call_summary(self, phone: str, name: str, summary: str, handoff: bool, handoff_reason: str = "") -> Dict[str, Any]:
        """Appends a new call log entry to Sheets Call Logs tab."""
        logger.info(f"Logging call for {phone} ({name}) - Handoff: {handoff}")
        
        call_id = f"call_{int(datetime.utcnow().timestamp())}"
        created_at = datetime.utcnow().isoformat() + "Z"
        
        log_record = {
            "Call ID": call_id,
            "Phone": phone,
            "Name": name,
            "Summary": summary,
            "Handoff Required": handoff,
            "Handoff Reason": handoff_reason,
            "Created At": created_at
        }

        if self.use_mock:
            data = self._load_mock_data()
            logs = data.get("Call Logs", [])
            logs.append(log_record)
            data["Call Logs"] = logs
            self._save_mock_data(data)
            return log_record

        # Real Google Sheet Append
        try:
            headers = ["Call ID", "Phone", "Name", "Summary", "Handoff Required", "Handoff Reason", "Created At"]
            row_values = [str(log_record[h]) for h in headers]
            
            self.client.spreadsheets().values().append(
                spreadsheetId=self.spreadsheet_id,
                range="Call Logs!A1",
                valueInputOption="RAW",
                insertDataOption="INSERT_ROWS",
                body={"values": [row_values]}
            ).execute()
            logger.info("Successfully logged call details in real Google Sheet.")
            return log_record
        except Exception as e:
            logger.error(f"Error logging to real Google Sheets Call Logs: {e}. Falling back to mock logging.")
            self.use_mock = True
            self._ensure_mock_file_exists()
            return self.log_call_summary(phone, name, summary, handoff, handoff_reason)

sheets_service = SheetsService()
