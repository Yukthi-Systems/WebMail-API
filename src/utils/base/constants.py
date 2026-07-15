"""
This file contains Global constants
Also storing all the env and config variables here
"""

# Copyright (C) 2026 Yukthi Systems Private Limited

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3
# as published by the Free Software Foundation.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# version 3 along with this program. If not, see
# <https://www.gnu.org/licenses/>.


import os


# environment Constants (Fetching from docker-compose)
POSTGRES_DB_USERNAME = os.environ.get("POSTGRES_DB_USERNAME", "postgres")
POSTGRES_DB_PASSWORD = os.environ.get("POSTGRES_DB_PASSWORD", "postgres")
POSTGRES_DB_HOST = os.environ.get("POSTGRES_DB_HOST", "0.0.0.0")
POSTGRES_DB_PORT = os.environ.get("POSTGRES_DB_PORT", "5432")
POSTGRES_DB_DATABASE = os.environ.get("POSTGRES_DB_DATABASE", "postgres")
POSTGRES_POOL_SIZE = int(os.environ.get("POSTGRES_POOL_SIZE", 10))
POSTGRES_DB_URI = os.environ.get("POSTGRES_DB_URI", f"postgresql://{POSTGRES_DB_USERNAME}:{POSTGRES_DB_PASSWORD}@{POSTGRES_DB_HOST}:{POSTGRES_DB_PORT}/{POSTGRES_DB_DATABASE}")

# Admin PostgreSQL DB Constants
ADMIN_POSTGRES_DB_USERNAME = os.environ.get("ADMIN_POSTGRES_DB_USERNAME", "postgres")
ADMIN_POSTGRES_DB_PASSWORD = os.environ.get("ADMIN_POSTGRES_DB_PASSWORD", "postgres")
ADMIN_POSTGRES_DB_HOST = os.environ.get("ADMIN_POSTGRES_DB_HOST", "0.0.0.0")
ADMIN_POSTGRES_DB_PORT = os.environ.get("ADMIN_POSTGRES_DB_PORT", "5432")
ADMIN_POSTGRES_DB_DATABASE = os.environ.get("ADMIN_POSTGRES_DB_DATABASE", "postgres")
ADMIN_POSTGRES_POOL_SIZE = int(os.environ.get("ADMIN_POSTGRES_POOL_SIZE", 10))
POSTGRES_POOL_MAX_INACTIVE_CONNECTION_LIFETIME = int(os.environ.get("POSTGRES_POOL_MAX_INACTIVE_CONNECTION_LIFETIME", 300))  # 5 minutes
ADMIN_POSTGRES_DB_URI = os.environ.get("ADMIN_POSTGRES_DB_URI", f"postgresql://{ADMIN_POSTGRES_DB_USERNAME}:{ADMIN_POSTGRES_DB_PASSWORD}@{ADMIN_POSTGRES_DB_HOST}:{ADMIN_POSTGRES_DB_PORT}/{ADMIN_POSTGRES_DB_DATABASE}")

# MemCache DB Constants
MEMCACHED_DB_HOST = os.environ.get("MEMCACHED_DB_HOST", "localhost")
MEMCACHED_DB_PORT = os.environ.get("MEMCACHED_DB_PORT", "11211")
MEMCACHED_DB_POOL_SIZE = int(os.environ.get("MEMCACHED_DB_POOL_SIZE", 10))
MAX_AGE_OF_CACHE = int(os.environ.get("MAX_AGE_OF_CACHE", 3*60*60)) # 3 hours

# Logging Constants
NUMBER_OF_LOGS_TO_DISPLAY = int(os.environ.get("NUMBER_OF_LOGS_TO_DISPLAY", 100))
LOG_LEVEL = int(os.environ.get("LOG_LEVEL", 20))
LOG_FILE_PATH = "/var/log/api/logs.jsonl"
LOGS_API_PASSWORD = os.environ.get("LOGS_API_PASSWORD", "logs-api-password")

# RabbitMQ Constants
RABBITMQ_HOST = os.environ.get("RABBITMQ_HOST", "0.0.0.0")
RABBITMQ_PORT = int(os.environ.get("RABBITMQ_PORT", "1234"))
RABBITMQ_VIRTUAL_HOST = os.environ.get("RABBITMQ_VIRTUAL_HOST", "vhost")
RABBITMQ_USERNAME = os.environ.get("RABBITMQ_USERNAME", "rabbitmq-username")
RABBITMQ_PASSWORD = os.environ.get("RABBITMQ_PASSWORD", "rabbitmq-password")
RABBITMQ_EXCHANGE = os.environ.get("RABBITMQ_EXCHANGE", "web_mail")
RABBITMQ_ROUTING_KEY = os.environ.get("RABBITMQ_ROUTING_KEY", "send_email")

# reCAPTCHA Constants
GOOGLE_RECAPTCHA_PROJECT_ID = os.getenv("GOOGLE_RECAPTCHA_PROJECT_ID", "google-recaptcha-project-id")
GOOGLE_RECAPTCHA_SITE_KEY = os.getenv("GOOGLE_RECAPTCHA_SITE_KEY", "google-recaptcha-site-key")
GOOGLE_RECAPTCHA_API_KEY = os.getenv("GOOGLE_RECAPTCHA_API_KEY", "google-recaptcha-api-key")

API_KEY = os.environ.get("API_KEY", "internal-api-key")
API_COOKIE_DOMAIN = os.environ.get("API_COOKIE_DOMAIN", ".example.com")
ALLOWED_ORIGINS = os.environ.get("ALLOWED_ORIGINS", "https://api.webmail.example.com,https://webmail-ui.example.com").split(",")
LOCAL_SMTP_HOST_NAME = os.environ.get("LOCAL_SMTP_HOST_NAME", "example.com")
SMTP_CONNECTION_TIMEOUT = int(os.environ.get("SMTP_CONNECTION_TIMEOUT", 10))  # Timeout in seconds

# Email Validation Constants
IMAP_CONNECTION_POOL_TIMEOUT = 30 # seconds
PRE_DEFINED_SETTINGS = {
    "ui": {
        "theme": "light",
        "language": "en",
        "font_size": 14,
        "show_notifications": True,
        "show_tooltips": True,
        "show_avatars": True,
        "show_sidebar": True,
        "show_quick_actions": True,
        "show_search_bar": True,
        "show_description": True
    },
    "folders": {
        "inbox": {
            "path": "INBOX",
            "show_unread_count": True,
            "show_starred_count": True,
            "color": "#FF5733",
            "icon": "inbox",
            "show_in_sidebar": True,
            "label": "Inbox",
            "show_label": True,
            "description": "Main inbox folder for incoming emails"
        },
        "sent": {
            "path": "Sent",
            "show_unread_count": False,
            "show_starred_count": False,
            "color": "#33FF57",
            "icon": "sent",
            "show_in_sidebar": True,
            "label": "Sent",
            "show_label": True,
            "description": "Folder for sent emails"
        },
        "drafts": {
            "path": "Drafts",
            "show_unread_count": False,
            "show_starred_count": False,
            "color": "#3357FF",
            "icon": "drafts",
            "show_in_sidebar": True,
            "label": "Drafts",
            "show_label": True,
            "description": "Folder for saved drafts"
        },
        "spam": {
            "path": "Spam",
            "show_unread_count": True,
            "show_starred_count": False,
            "color": "#FF33A1",
            "icon": "spam",
            "show_in_sidebar": True,
            "label": "Spam",
            "show_label": True,
            "description": "Folder for spam emails"
        },
        "trash": {
            "path": "Trash",
            "show_unread_count": False,
            "show_starred_count": False,
            "color": "#FF33FF",
            "icon": "trash",
            "show_in_sidebar": True,
            "label": "Trash",
            "show_label": True,
            "description": "Folder for deleted emails"
        }
    },
    "email": {
        "show_sender": True,
        "show_recipient": True,
        "show_subject": True,
        "show_date": True,
        "show_attachments": True,
        "show_body": True,
        "show_reply_button": True,
        "show_forward_button": True,
        "show_delete_button": True,
        "show_mark_as_read_button": True,
        "show_mark_as_unread_button": True,
        "show_star_button": True,
        "show_header_button": True
    },
    "compose": {
        "show_to_field": True,
        "show_cc_field": True,
        "show_bcc_field": True,
        "show_subject_field": True,
        "show_body_field": True,
        "show_send_button": True,
        "show_save_draft_button": True,
        "show_attach_file_button": True,
        "show_insert_link_button": True,
        "show_insert_image_button": True,
        "show_insert_table_button": True
    },
    "contacts": {
        "show_name": True,
        "show_email": True,
        "show_phone": True,
        "show_notes": True,
        "show_address": True,
        "show_website": True,
        "show_birthday": True,
        "show_created_date": True,
        "show_updated_date": True
    }
}
