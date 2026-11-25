"""Constants for the ParentAdmin integration."""
from __future__ import annotations

from datetime import timedelta
import logging

DOMAIN = "parentadmin"
LOGGER = logging.getLogger(__package__)

BASE_URL = "https://uk.parentadmin.com"
LOGIN_PATH = "/login.php"
DIARY_PATH = "/child-diary.php"

SCAN_INTERVAL = timedelta(minutes=15)
# Outside these hours we keep the last fetched data instead of polling.
QUIET_START_HOUR = 19
QUIET_END_HOUR = 7

VERSION = "0.3.0"
CARD_URL = "/parentadmin_static/parentadmin-timeline-card.js"
CARD_FILE = "parentadmin-timeline-card.js"
PHOTO_PATH = "/api/parentadmin/{entry_id}/photo/{key}"
# Signed photo links are valid for 48h and re-signed when under 12h remain,
# so the URLs stay stable (and browser-cacheable) between polls.
PHOTO_LINK_VALID = timedelta(hours=48)
PHOTO_LINK_RESIGN = timedelta(hours=12)
PHOTO_CACHE_SIZE = 30

# Slower-changing pages (invoices, account balance, booking pattern)
ACCOUNT_SCAN_INTERVAL = timedelta(hours=3)
INVOICE_PATH = "/invoice-history.php"
ACCOUNT_PATH = "/account-history.php"
BOOKING_PATH = "/booking-pattern.php"
INCIDENTS_PATH = "/accident-incident-forms.php"
INBOX_PATH = "/notifications.php"

# When today has no diary, show the most recent day within this many days.
FALLBACK_LOOKBACK_DAYS = 10
# On days she isn't booked in, only re-check the diary this often.
UNBOOKED_REFRESH = timedelta(hours=2)

EVENT_NEW_INVOICE = "parentadmin_new_invoice"
EVENT_NEW_INCIDENT = "parentadmin_new_incident"
EVENT_NEW_MESSAGE = "parentadmin_new_message"
STORAGE_VERSION = 1
CURRENCY = "GBP"
