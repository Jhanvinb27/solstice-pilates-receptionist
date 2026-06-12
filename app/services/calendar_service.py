import os
import re
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from app.config import settings

# Set up logger
logger = logging.getLogger("calendar_service")
logger.setLevel(logging.INFO)
if not logger.handlers:
    ch = logging.StreamHandler()
    ch.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
    logger.addHandler(ch)

SCOPES = ["https://www.googleapis.com/auth/calendar"]

# Class-type keywords used for fuzzy matching a model-supplied class id to a real class.
CLASS_TYPE_KEYWORDS = {
    "reformer", "mat", "flow", "express", "advanced",
    "intro", "intermediate", "essentials", "lunch", "morning"
}


def _time_tokens(text: str) -> set:
    """Extracts canonical time tokens (e.g. {'7pm', '8am'}) from any text."""
    tokens = set()
    for hour, _minute, ampm in re.findall(r"(\d{1,2})(?::(\d{2}))?\s*([ap]m)", text.lower()):
        tokens.add(f"{int(hour)}{ampm}")
    return tokens


def class_matches(class_obj: Dict[str, Any], query_id: str) -> bool:
    """
    Robustly decides whether `query_id` (often produced by the LLM, e.g.
    'reformer_thurs_7pm') refers to the given class object whose real id may be
    something like 'reformer_weekday_7pm_2026-05-28'.

    Matching strategy, in order:
      1. Exact id match (case-insensitive).
      2. Either-direction substring match.
      3. Time-based match (e.g. '7pm') combined with a compatible class type so
         the 6pm and 7pm Reformer classes never collide.
    """
    if not query_id:
        return False

    real_id = str(class_obj.get("id", "")).lower()
    q = query_id.lower().strip()

    if real_id == q or q in real_id or real_id in q:
        return True

    q_times = _time_tokens(q)
    c_times = _time_tokens(class_obj.get("time", "")) | _time_tokens(real_id)
    if q_times and c_times and (q_times & c_times):
        # Time matches — confirm the class type is compatible (if the query named one).
        q_types = {tok for tok in re.split(r"[_\s\-]+", q) if tok in CLASS_TYPE_KEYWORDS}
        class_text = f"{class_obj.get('name', '')} {real_id}".lower()
        if not q_types or any(t in class_text for t in q_types):
            return True

    return False


class CalendarService:
    def __init__(self):
        self.use_mock = settings.USE_MOCK_SERVICES
        self.mock_file_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "data",
            "mock_calendar.json"
        )
        self.client = None
        self.calendar_id = settings.GOOGLE_CALENDAR_ID
        
        # Check if we should try initializing Google APIs
        if not self.use_mock:
            if not settings.GOOGLE_SERVICE_ACCOUNT_JSON:
                logger.warning("Google Calendar Service Account JSON missing. Defaulting to Mock Mode.")
                self.use_mock = True
            else:
                try:
                    from google.oauth2 import service_account
                    from googleapiclient.discovery import build

                    json_input = settings.GOOGLE_SERVICE_ACCOUNT_JSON.strip()
                    if json_input.startswith("{") and json_input.endswith("}"):
                        info = json.loads(json_input)
                        credentials = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
                    else:
                        credentials = service_account.Credentials.from_service_account_file(json_input, scopes=SCOPES)
                    
                    self.client = build("calendar", "v3", credentials=credentials)
                    logger.info("Successfully authenticated Google Calendar API client.")
                except Exception as e:
                    logger.error(f"Failed to initialize Google Calendar API: {e}. Falling back to Mock Mode.", exc_info=True)
                    self.use_mock = True

        # In mock mode, ensure mock file exists
        if self.use_mock:
            self._ensure_mock_file_exists()

    def _ensure_mock_file_exists(self):
        """Creates default calendar file if it doesn't exist."""
        if not os.path.exists(self.mock_file_path):
            os.makedirs(os.path.dirname(self.mock_file_path), exist_ok=True)
            # Create a base structure
            default_data = {"classes": []}
            with open(self.mock_file_path, "w") as f:
                json.dump(default_data, f, indent=2)
            logger.info("Created mock calendar JSON file.")

    def _load_mock_data(self) -> Dict[str, List[Dict[str, Any]]]:
        """Loads data from mock calendar JSON."""
        try:
            with open(self.mock_file_path, "r") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading mock calendar data: {e}")
            return {"classes": []}

    def _save_mock_data(self, data: Dict[str, List[Dict[str, Any]]]):
        """Saves data to mock calendar JSON."""
        try:
            with open(self.mock_file_path, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving mock calendar data: {e}")

    def _generate_dynamic_classes_for_date(self, date_str: str) -> List[Dict[str, Any]]:
        """
        Dynamically generates Pilates classes for a given date if they do not exist,
        ensuring the calendar is always populated.
        """
        try:
            # Parse day of week to check if weekend or weekday
            dt = datetime.strptime(date_str, "%Y-%m-%d")
            day_name = dt.strftime("%A")
            is_weekend = day_name in ("Saturday", "Sunday")
        except ValueError:
            is_weekend = False
            day_name = "Thursday"

        classes = []
        if is_weekend:
            # Weekend Classes (Hours: 8:00 AM - 4:00 PM)
            classes = [
                {
                    "id": f"reformer_sat_9am_{date_str}",
                    "name": "Morning Flow Reformer",
                    "instructor": "Emma",
                    "date": date_str,
                    "time": "9:00 AM",
                    "capacity": 10,
                    "booked_count": 4,
                    "attendees": [
                        {"name": "Jack Adams", "phone": "415-555-5001"},
                        {"name": "Grace Nelson", "phone": "415-555-5002"},
                        {"name": "Henry Carter", "phone": "415-555-5003"},
                        {"name": "Zoe Mitchell", "phone": "415-555-5004"}
                    ]
                },
                {
                    "id": f"reformer_sat_11am_{date_str}",
                    "name": "Intermediate Reformer",
                    "instructor": "Emma",
                    "date": date_str,
                    "time": "11:00 AM",
                    "capacity": 10,
                    "booked_count": 10,
                    "attendees": [
                        {"name": "Attendee A", "phone": "415-555-9001"},
                        {"name": "Attendee B", "phone": "415-555-9002"},
                        {"name": "Attendee C", "phone": "415-555-9003"},
                        {"name": "Attendee D", "phone": "415-555-9004"},
                        {"name": "Attendee E", "phone": "415-555-9005"},
                        {"name": "Attendee F", "phone": "415-555-9006"},
                        {"name": "Attendee G", "phone": "415-555-9007"},
                        {"name": "Attendee H", "phone": "415-555-9008"},
                        {"name": "Attendee I", "phone": "415-555-9009"},
                        {"name": "Attendee J", "phone": "415-555-9010"}
                    ]
                },
                {
                    "id": f"mat_sat_1pm_{date_str}",
                    "name": "Mat Pilates Essentials",
                    "instructor": "Lucas",
                    "date": date_str,
                    "time": "1:00 PM",
                    "capacity": 15,
                    "booked_count": 2,
                    "attendees": [
                        {"name": "Ava White", "phone": "415-555-3001"},
                        {"name": "Ethan Harris", "phone": "415-555-3002"}
                    ]
                }
            ]
        else:
            # Weekday Classes (Hours: 7:00 AM - 8:00 PM)
            # Thursday 2026-05-28 has specific booked counts for user conversation testing
            thurs_6pm_booked = 10 if date_str == "2026-05-28" else 8
            thurs_7pm_booked = 8 if date_str == "2026-05-28" else 5
            
            classes = [
                {
                    "id": f"mat_weekday_8am_{date_str}",
                    "name": "Intro Mat Pilates",
                    "instructor": "Lucas",
                    "date": date_str,
                    "time": "8:00 AM",
                    "capacity": 12,
                    "booked_count": 3,
                    "attendees": [
                        {"name": "Ava White", "phone": "415-555-3001"},
                        {"name": "Ethan Harris", "phone": "415-555-3002"},
                        {"name": "Chloe Martin", "phone": "415-555-3003"}
                    ]
                },
                {
                    "id": f"reformer_weekday_9am_{date_str}",
                    "name": "Advanced Reformer",
                    "instructor": "Sophia",
                    "date": date_str,
                    "time": "9:00 AM",
                    "capacity": 10,
                    "booked_count": 6,
                    "attendees": [
                        {"name": "Attendee 1", "phone": "415-555-6001"},
                        {"name": "Attendee 2", "phone": "415-555-6002"},
                        {"name": "Attendee 3", "phone": "415-555-6003"},
                        {"name": "Attendee 4", "phone": "415-555-6004"},
                        {"name": "Attendee 5", "phone": "415-555-6005"},
                        {"name": "Attendee 6", "phone": "415-555-6006"}
                    ]
                },
                {
                    "id": f"reformer_weekday_12pm_{date_str}",
                    "name": "Lunch Express Reformer",
                    "instructor": "Sophia",
                    "date": date_str,
                    "time": "12:00 PM",
                    "capacity": 10,
                    "booked_count": 4,
                    "attendees": [
                        {"name": "Attendee 1", "phone": "415-555-6001"},
                        {"name": "Attendee 2", "phone": "415-555-6002"},
                        {"name": "Attendee 3", "phone": "415-555-6003"},
                        {"name": "Attendee 4", "phone": "415-555-6004"}
                    ]
                },
                {
                    "id": f"reformer_weekday_6pm_{date_str}",
                    "name": "Reformer Pilates",
                    "instructor": "Emma",
                    "date": date_str,
                    "time": "6:00 PM",
                    "capacity": 10,
                    "booked_count": thurs_6pm_booked,
                    "attendees": [
                        {"name": "Michael Chen", "phone": "415-555-1001"},
                        {"name": "Sophia Rodriguez", "phone": "415-555-1002"},
                        {"name": "Liam Johnston", "phone": "415-555-1003"},
                        {"name": "Isabella Smith", "phone": "415-555-1004"},
                        {"name": "James Lee", "phone": "415-555-1005"},
                        {"name": "Olivia Martinez", "phone": "415-555-1006"},
                        {"name": "Benjamin Wright", "phone": "415-555-1007"},
                        {"name": "Mia Thompson", "phone": "415-555-1008"},
                        {"name": "Lucas Davis", "phone": "415-555-1009"},
                        {"name": "Charlotte Garcia", "phone": "415-555-1010"}
                    ][:thurs_6pm_booked]
                },
                {
                    "id": f"reformer_weekday_7pm_{date_str}",
                    "name": "Reformer Pilates",
                    "instructor": "Emma",
                    "date": date_str,
                    "time": "7:00 PM",
                    "capacity": 10,
                    "booked_count": thurs_7pm_booked,
                    "attendees": [
                        {"name": "John Doe", "phone": "415-555-2001"},
                        {"name": "Jane Miller", "phone": "415-555-2002"},
                        {"name": "Robert Taylor", "phone": "415-555-2003"},
                        {"name": "Emily Brown", "phone": "415-555-2004"},
                        {"name": "William Wilson", "phone": "415-555-2005"},
                        {"name": "Elizabeth Anderson", "phone": "415-555-2006"},
                        {"name": "David Thomas", "phone": "415-555-2007"},
                        {"name": "Barbara Jackson", "phone": "415-555-2008"}
                    ][:thurs_7pm_booked]
                }
            ]
        return classes

    # --- PUBLIC API METHODS ---

    def get_classes(self, date_str: str) -> List[Dict[str, Any]]:
        """
        Gets all classes scheduled for a specific date (Format: YYYY-MM-DD).
        """
        logger.info(f"Getting classes for date: {date_str}")
        
        # Load from file mock or maintain in mock database
        data = self._load_mock_data()
        existing_classes = [c for c in data.get("classes", []) if c.get("date") == date_str]
        
        if not existing_classes:
            # Generate dynamically to ensure something is always scheduled
            new_classes = self._generate_dynamic_classes_for_date(date_str)
            
            # Save these generated classes to the mock list so booking state persists
            data["classes"].extend(new_classes)
            self._save_mock_data(data)
            existing_classes = new_classes

        # Filter out sensitive attendee phones if required, but for internal state we keep it
        return existing_classes

    def get_class(self, class_id: str, date_str: str) -> Optional[Dict[str, Any]]:
        """Retrieves a single class by id and date."""
        classes = self.get_classes(date_str)
        # Robust matching (handles short template ids, long date-specific ids,
        # and natural time-based ids the LLM tends to invent).
        for c in classes:
            if class_matches(c, class_id):
                return c
        return None

    def create_booking(self, client_name: str, phone: str, class_id: str, date_str: str) -> Dict[str, Any]:
        """
        Reserves a slot in a class.
        Checks for capacity and conflicts.
        """
        logger.info(f"Booking class '{class_id}' on {date_str} for {client_name} ({phone})")

        data = self._load_mock_data()
        classes = data.get("classes", [])

        # Find target class
        target_class = None
        target_idx = -1
        for i, c in enumerate(classes):
            if c.get("date") == date_str and class_matches(c, class_id):
                target_class = c
                target_idx = i
                break

        if not target_class:
            # Generate dynamically first and search again
            self.get_classes(date_str)
            data = self._load_mock_data()
            classes = data.get("classes", [])
            for i, c in enumerate(classes):
                if c.get("date") == date_str and class_matches(c, class_id):
                    target_class = c
                    target_idx = i
                    break

        if not target_class:
            raise ValueError(f"Class '{class_id}' not found on {date_str}.")

        # Check capacity
        if target_class["booked_count"] >= target_class["capacity"]:
            raise ValueError(f"Class is full. Capacity is {target_class['capacity']}.")

        # Check if already booked
        query_digits = "".join(filter(str.isdigit, phone))
        for attendee in target_class["attendees"]:
            attendee_digits = "".join(filter(str.isdigit, attendee.get("phone", "")))
            if query_digits == attendee_digits:
                logger.info(f"Client already booked in class: {target_class['name']}.")
                return {"status": "already_booked", "class": target_class}

        # Add booking
        target_class["attendees"].append({"name": client_name, "phone": phone})
        target_class["booked_count"] += 1
        classes[target_idx] = target_class
        data["classes"] = classes
        self._save_mock_data(data)

        # Real Google Calendar Event creation
        if not self.use_mock:
            try:
                # Calculate class time
                time_str = target_class["time"] # e.g. "6:00 PM"
                # Parse YYYY-MM-DD + Time
                dt_str = f"{date_str} {time_str}"
                start_dt = datetime.strptime(dt_str, "%Y-%m-%d %I:%M %p")
                end_dt = start_dt + timedelta(minutes=50) # pilates classes are usually 50 mins

                event = {
                    'summary': f"Solstice Pilates: Booking {client_name} - {target_class['name']}",
                    'description': f"Client: {client_name}\nPhone: {phone}\nInstructor: {target_class['instructor']}",
                    'start': {
                        'dateTime': start_dt.isoformat(),
                        'timeZone': 'America/Los_Angeles',
                    },
                    'end': {
                        'dateTime': end_dt.isoformat(),
                        'timeZone': 'America/Los_Angeles',
                    },
                    'reminders': {
                        'useDefault': True,
                    },
                }

                created_event = self.client.events().insert(
                    calendarId=self.calendar_id,
                    body=event
                ).execute()
                logger.info(f"Successfully created real Google Calendar event: {created_event.get('htmlLink')}")
                target_class["google_event_id"] = created_event.get("id")
                # Save Google Event ID
                classes[target_idx] = target_class
                data["classes"] = classes
                self._save_mock_data(data)
            except Exception as e:
                logger.error(f"Error creating real Google Calendar Event: {e}. Keeping local mock active.")

        return {"status": "success", "class": target_class}

    def cancel_booking(self, phone: str, class_id: str, date_str: str) -> Dict[str, Any]:
        """
        Cancels a booking for a client's phone number.
        """
        logger.info(f"Canceling booking for phone {phone} in class {class_id} on {date_str}")
        
        data = self._load_mock_data()
        classes = data.get("classes", [])
        
        target_class = None
        target_idx = -1
        for i, c in enumerate(classes):
            if c.get("date") == date_str and class_matches(c, class_id):
                target_class = c
                target_idx = i
                break

        if not target_class:
            raise ValueError(f"Class '{class_id}' not found on {date_str}.")

        # Find attendee
        attendee_idx = -1
        query_digits = "".join(filter(str.isdigit, phone))
        for idx, att in enumerate(target_class["attendees"]):
            att_digits = "".join(filter(str.isdigit, att.get("phone", "")))
            if query_digits == att_digits or att.get("phone", "").strip() == phone.strip():
                attendee_idx = idx
                break
                
        if attendee_idx == -1:
            raise ValueError(f"No booking found for phone {phone} in this class.")
            
        # Remove attendee
        target_class["attendees"].pop(attendee_idx)
        target_class["booked_count"] -= 1
        
        google_event_id = target_class.get("google_event_id")
        
        classes[target_idx] = target_class
        data["classes"] = classes
        self._save_mock_data(data)

        # Real Google Calendar cancellation
        if not self.use_mock and google_event_id:
            try:
                self.client.events().delete(
                    calendarId=self.calendar_id,
                    eventId=google_event_id
                ).execute()
                logger.info(f"Successfully deleted Google Calendar event: {google_event_id}")
            except Exception as e:
                logger.error(f"Error deleting Google Calendar event: {e}")
                
        return {"status": "success", "class": target_class}

    def reschedule_booking(self, phone: str, current_class_id: str, new_class_id: str, date_str: str) -> Dict[str, Any]:
        """
        Reschedules a booking from one class to another on a specific date.
        """
        logger.info(f"Rescheduling phone {phone} from class {current_class_id} to {new_class_id} on {date_str}")
        
        # 1. Retrieve the client's name from current class booking
        data = self._load_mock_data()
        classes = data.get("classes", [])
        
        current_class = None
        for c in classes:
            if c.get("date") == date_str and class_matches(c, current_class_id):
                current_class = c
                break
                
        if not current_class:
            raise ValueError(f"Current class '{current_class_id}' not found on {date_str}.")
            
        client_name = None
        query_digits = "".join(filter(str.isdigit, phone))
        for att in current_class["attendees"]:
            att_digits = "".join(filter(str.isdigit, att.get("phone", "")))
            if query_digits == att_digits:
                client_name = att["name"]
                break
                
        if not client_name:
            # Fallback to sheets_service to find the name if attendee was not found
            from app.services.sheets_service import sheets_service
            contact = sheets_service.get_contact(phone)
            if contact:
                client_name = contact.get("Name", "Valued Client")
            else:
                client_name = "Client"

        # 2. Validate the destination class BEFORE canceling, so a failed
        #    reschedule never leaves the client without their original spot.
        new_class = None
        for c in classes:
            if c.get("date") == date_str and class_matches(c, new_class_id):
                new_class = c
                break
        if not new_class:
            raise ValueError(f"New class '{new_class_id}' not found on {date_str}.")
        already_in_new = any(
            "".join(filter(str.isdigit, a.get("phone", ""))) == query_digits
            for a in new_class["attendees"]
        )
        if not already_in_new and new_class["booked_count"] >= new_class["capacity"]:
            raise ValueError(
                f"Cannot reschedule: the {new_class['time']} {new_class['name']} class is full."
            )

        # 3. Cancel old booking, then book the new one.
        try:
            self.cancel_booking(phone, current_class_id, date_str)
        except Exception as e:
            logger.warning(f"Error during reschedule cancellation step: {e}. Proceeding anyway.")

        return self.create_booking(client_name, phone, new_class["id"], date_str)

calendar_service = CalendarService()
