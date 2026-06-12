import os
import sys
import json
import shutil
import tempfile
import unittest

# Setup sys path to import app correctly
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import settings
from app.services.calendar_service import calendar_service
from app.services.sheets_service import sheets_service

class TestSolsticePilatesServices(unittest.TestCase):
    def setUp(self):
        # Force Mock Services for deterministic testing
        calendar_service.use_mock = True
        sheets_service.use_mock = True

        # Redirect both services to isolated temp files so tests never mutate
        # the real app/data/*.json databases.
        self._tmp_dir = tempfile.mkdtemp(prefix="pilates_test_")
        self._orig_calendar_path = calendar_service.mock_file_path
        self._orig_sheets_path = sheets_service.mock_file_path
        calendar_service.mock_file_path = os.path.join(self._tmp_dir, "mock_calendar.json")
        sheets_service.mock_file_path = os.path.join(self._tmp_dir, "mock_sheets.json")

        # Overwrite calendar mock with fresh default test data
        self.test_date = "2026-05-28" # Thursday
        default_calendar = {
            "classes": [
                {
                    "id": "reformer_thurs_6pm",
                    "name": "Reformer Pilates",
                    "instructor": "Emma",
                    "date": self.test_date,
                    "time": "6:00 PM",
                    "capacity": 10,
                    "booked_count": 10,
                    "attendees": [{"name": f"Attendee {i}", "phone": f"415-555-100{i}"} for i in range(10)]
                },
                {
                    "id": "reformer_thurs_7pm",
                    "name": "Reformer Pilates",
                    "instructor": "Emma",
                    "date": self.test_date,
                    "time": "7:00 PM",
                    "capacity": 10,
                    "booked_count": 8,
                    "attendees": [{"name": f"Attendee {i}", "phone": f"415-555-200{i}"} for i in range(8)]
                },
                {
                    "id": "mat_thurs_8am",
                    "name": "Intro Mat Pilates",
                    "instructor": "Lucas",
                    "date": self.test_date,
                    "time": "8:00 AM",
                    "capacity": 12,
                    "booked_count": 2,
                    "attendees": [{"name": f"Mat {i}", "phone": f"415-555-700{i}"} for i in range(2)]
                }
            ]
        }
        with open(calendar_service.mock_file_path, "w") as f:
            json.dump(default_calendar, f, indent=2)

        # Overwrite sheets mock with clean data
        default_sheets = {
            "Contacts": [],
            "Call Logs": []
        }
        with open(sheets_service.mock_file_path, "w") as f:
            json.dump(default_sheets, f, indent=2)

    def tearDown(self):
        # Restore the real data paths and remove temp files.
        calendar_service.mock_file_path = self._orig_calendar_path
        sheets_service.mock_file_path = self._orig_sheets_path
        shutil.rmtree(self._tmp_dir, ignore_errors=True)

    def test_calendar_classes_loaded(self):
        """Verify that scheduled classes are loaded and have correct capacity attributes."""
        classes = calendar_service.get_classes(self.test_date)
        self.assertTrue(len(classes) > 0)
        
        # Search for 6pm Reformer class (Should be full)
        class_6pm = calendar_service.get_class("reformer_thurs_6pm", self.test_date)
        self.assertIsNotNone(class_6pm)
        self.assertEqual(class_6pm["booked_count"], class_6pm["capacity"]) # Full

        # Search for 7pm Reformer class (Should have 2 spots open)
        class_7pm = calendar_service.get_class("reformer_thurs_7pm", self.test_date)
        self.assertIsNotNone(class_7pm)
        spots_left = class_7pm["capacity"] - class_7pm["booked_count"]
        self.assertEqual(spots_left, 2)

    def test_calendar_booking_success(self):
        """Verify successful booking in a class with spots open (e.g., 7pm)."""
        class_7pm = calendar_service.get_class("reformer_thurs_7pm", self.test_date)
        initial_booked = class_7pm["booked_count"]

        # Attempt booking
        res = calendar_service.create_booking(
            client_name="Test Sara",
            phone="415-555-9999",
            class_id=class_7pm["id"],
            date_str=self.test_date
        )
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["class"]["booked_count"], initial_booked + 1)
        
        # Verify attendee is registered
        updated_class = calendar_service.get_class(class_7pm["id"], self.test_date)
        attendee_phones = [a["phone"] for a in updated_class["attendees"]]
        self.assertIn("415-555-9999", attendee_phones)

    def test_calendar_booking_full_raises_error(self):
        """Verify that booking in a full class raises a ValueError."""
        class_6pm = calendar_service.get_class("reformer_thurs_6pm", self.test_date)
        
        # Attempt booking on full class (Should raise exception)
        with self.assertRaises(ValueError):
            calendar_service.create_booking(
                client_name="Blocked Client",
                phone="415-555-0000",
                class_id=class_6pm["id"],
                date_str=self.test_date
            )

    def test_sheets_contact_upsert(self):
        """Verify Sheets service creates and updates contact records successfully."""
        phone = "415-555-8888"
        name = "Test Contact"
        email = "test@example.com"
        notes = "Needs rehabilitation focus."

        # Create new
        contact = sheets_service.upsert_contact(phone, name, email, notes)
        self.assertEqual(contact["Phone"], phone)
        self.assertEqual(contact["Name"], name)
        
        # Search contact
        fetched = sheets_service.get_contact(phone)
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched["Name"], name)
        
        # Update notes
        updated_notes = "Updated notes."
        sheets_service.upsert_contact(phone, name, email, updated_notes)
        fetched_updated = sheets_service.get_contact(phone)
        self.assertEqual(fetched_updated["Notes"], updated_notes)

    def test_sheets_call_logs(self):
        """Verify that call summary records are logged successfully."""
        phone = "415-555-7777"
        name = "Inquirer Name"
        summary = "Inquired about Saturday drop-in rates."
        handoff = False

        log = sheets_service.log_call_summary(phone, name, summary, handoff)
        self.assertEqual(log["Phone"], phone)
        self.assertEqual(log["Summary"], summary)
        self.assertFalse(log["Handoff Required"])

        # Verify list contains the new log
        logs = sheets_service.get_call_logs()
        logged_phones = [l["Phone"] for l in logs]
        self.assertIn(phone, logged_phones)

    def test_sheets_handoff_logging(self):
        """Verify a billing complaint is logged with the handoff flag set."""
        log = sheets_service.log_call_summary(
            phone="415-555-0190",
            name="Sara",
            summary="Inquiry [charge_complaint]: double charged $300.",
            handoff=True,
            handoff_reason="Double charge dispute",
        )
        self.assertTrue(log["Handoff Required"])
        self.assertEqual(log["Handoff Reason"], "Double charge dispute")

    def test_fuzzy_class_id_matching(self):
        """The LLM-style id 'reformer_thurs_7pm' should resolve to the real 7pm class."""
        real = calendar_service.get_class("reformer_thurs_7pm", self.test_date)
        self.assertIsNotNone(real)
        self.assertEqual(real["time"], "7:00 PM")

        # Booking with the fuzzy id must land in the correct (7pm) class, not the 6pm one.
        res = calendar_service.create_booking(
            client_name="Fuzzy Client",
            phone="415-555-4242",
            class_id="reformer_thurs_7pm",
            date_str=self.test_date,
        )
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["class"]["time"], "7:00 PM")

    def test_cancel_booking(self):
        """Booking then canceling should free the spot and remove the attendee."""
        phone = "415-555-1212"
        calendar_service.create_booking("Cancel Me", phone, "reformer_thurs_7pm", self.test_date)
        booked_after_add = calendar_service.get_class("reformer_thurs_7pm", self.test_date)["booked_count"]

        calendar_service.cancel_booking(phone, "reformer_thurs_7pm", self.test_date)
        cls = calendar_service.get_class("reformer_thurs_7pm", self.test_date)
        self.assertEqual(cls["booked_count"], booked_after_add - 1)
        self.assertNotIn(phone, [a["phone"] for a in cls["attendees"]])

    def test_reschedule_moves_booking(self):
        """Rescheduling should remove the client from the old class and add to the new one."""
        phone = "415-555-3434"
        calendar_service.create_booking("Mover", phone, "reformer_thurs_7pm", self.test_date)

        # Reschedule the 7pm booking to the 8am mat class (plenty of room).
        res = calendar_service.reschedule_booking(
            phone=phone,
            current_class_id="reformer_thurs_7pm",
            new_class_id="mat_thurs_8am",
            date_str=self.test_date,
        )
        self.assertEqual(res["status"], "success")
        old_cls = calendar_service.get_class("reformer_thurs_7pm", self.test_date)
        new_cls = calendar_service.get_class("mat_thurs_8am", self.test_date)
        self.assertNotIn(phone, [a["phone"] for a in old_cls["attendees"]])
        self.assertIn(phone, [a["phone"] for a in new_cls["attendees"]])

    def test_reschedule_to_full_class_keeps_original(self):
        """A reschedule into a full class must fail without dropping the original booking."""
        phone = "415-555-5656"
        calendar_service.create_booking("Stay Put", phone, "reformer_thurs_7pm", self.test_date)

        with self.assertRaises(ValueError):
            calendar_service.reschedule_booking(
                phone=phone,
                current_class_id="reformer_thurs_7pm",
                new_class_id="reformer_thurs_6pm",  # full
                date_str=self.test_date,
            )

        # Original 7pm booking must still be intact.
        cls = calendar_service.get_class("reformer_thurs_7pm", self.test_date)
        self.assertIn(phone, [a["phone"] for a in cls["attendees"]])

if __name__ == "__main__":
    unittest.main()
