"""
All the IMAP related functions and classes are defined in this module
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


from .connections import get_imap_connection, get_imap_connection_from_user_data
from .handlers import list_folders, parse_acl_response, parse_imap_response, get_email_details, get_raw_email, parse_quota_response, move_multiple_emails, copy_multiple_emails, mark_emails_as_read, mark_emails_as_unseen, mark_emails_as_flagged, mark_emails_as_unflagged, delete_emails_permanently, search_emails, get_email_details_by_message_id


__version__ = "v2.6.2-phoenix-release"


__annotations__ = {
    "version": __version__,
    "get_imap_connection": "Function to get IMAP connection, if it doesn't exist, create a new one",
    "list_folders": "Function to list all folders in the mailbox",
    "parse_acl_response": "Function to parse the ACL response from the server",
    "get_imap_connection_from_user_data": "Function to get IMAP connection using user data",
    "parse_imap_response": "Function to parse the IMAP response from the server",
    "get_email_details": "Function to get email details from the server",
    "get_raw_email": "Function to get raw email by ID",
    "parse_quota_response": "Function to parse the quota response from the server",
    "move_multiple_emails": "Function to move multiple emails from one folder to another",
    "copy_multiple_emails": "Function to copy multiple emails from one folder to another",
    "mark_emails_as_read": "Function to mark emails as read",
    "mark_emails_as_unseen": "Function to mark emails as Unseen or Unread",
    "mark_emails_as_flagged": "Function to mark emails as flagged",
    "mark_emails_as_unflagged": "Function to mark emails as unflagged",
    "delete_emails_permanently": "Function to delete emails permanently from the server",
    "search_emails": "Function to search emails in the mailbox",
    "get_email_details_by_message_id": "Function to get email details by Message-ID"
}


__all__ = [
    "get_imap_connection",
    "list_folders",
    "parse_acl_response",
    "get_imap_connection_from_user_data",
    "parse_imap_response",
    "get_email_details",
    "get_raw_email",
    "parse_quota_response",
    "move_multiple_emails",
    "copy_multiple_emails",
    "mark_emails_as_read",
    "mark_emails_as_unseen",
    "mark_emails_as_flagged",
    "mark_emails_as_unflagged",
    "delete_emails_permanently",
    "search_emails",
    "get_email_details_by_message_id"
]
