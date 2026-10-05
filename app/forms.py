"""Field sets shared by HTML forms and the JSON API."""
from .reference_data import COUNTRIES, FEEDBACK_CATEGORIES, PURPOSES, SUPPORT_TOPICS
from .repositories.releases import CHANNELS
from .validation import F

PASSWORD_MIN = 12

PROFILE = [
    F("first_name", "First name", required=False, max_len=80, extra={"name": True}),
    F("last_name", "Last name", required=False, max_len=80, extra={"name": True}),
    F("country", "Country", kind="choice", required=False, choices=COUNTRIES),
    F("purpose", "Main use", kind="choice", required=False, choices=[k for k, _ in PURPOSES]),
]

REGISTER = [
    F("username", "Username", kind="username", max_len=32),
    F("email", "Email address", kind="email", max_len=254),
    F("password", "Password", kind="password", min_len=PASSWORD_MIN, max_len=128, extra={"strength": True}),
    *PROFILE,
    F("accept_privacy", "Privacy notice", kind="bool"),
    F("product_updates", "Product updates", kind="bool"),
]

LOGIN = [
    F("identifier", "Email or username", max_len=254),
    F("password", "Password", kind="password", min_len=1, max_len=128),
]

PROFILE_UPDATE = [F("email", "Email address", kind="email", max_len=254), *PROFILE]

CHANGE_PASSWORD = [
    F("current_password", "Current password", kind="password", min_len=1, max_len=128),
    F("new_password", "New password", kind="password", min_len=PASSWORD_MIN, max_len=128, extra={"strength": True}),
]

DELETE_ACCOUNT = [F("password", "Password", kind="password", min_len=1, max_len=128)]

FEEDBACK = [
    F("category", "Category", kind="choice", choices=[k for k, _ in FEEDBACK_CATEGORIES]),
    F("app_version", "App version", kind="semver", required=False, max_len=40),
    F("message", "Feedback", kind="text", min_len=10, max_len=4000),
]

SUPPORT = [
    F("name", "Name", max_len=120, extra={"name": True}),
    F("email", "Email address", kind="email", max_len=254),
    F("topic", "Topic", kind="choice", choices=[k for k, _ in SUPPORT_TOPICS]),
    F("message", "Message", kind="text", min_len=10, max_len=4000),
]

RELEASE = [
    F("version", "Version", kind="semver", max_len=40),
    F("channel", "Channel", kind="choice", choices=CHANNELS),
    F("release_date", "Release date", kind="date", max_len=10),
    F("release_notes_url", "Release notes URL", kind="https_url", required=False, max_len=500),
    F("download_url", "Download URL", kind="https_url", max_len=500, extra={"restrict_hosts": True}),
    F("installer_filename", "Installer file name", kind="filename", max_len=124),
    F("sha256", "SHA-256", kind="sha256", max_len=64),
    F("file_size_bytes", "File size (bytes)", kind="int", min_value=1, max_value=8 * 1024 ** 3),
    F("minimum_supported_version", "Minimum supported version", kind="semver", required=False, max_len=40),
    F("is_mandatory", "Mandatory update", kind="bool"),
    F("is_signed", "Installer is digitally signed", kind="bool"),
    F("is_published", "Published", kind="bool"),
]
