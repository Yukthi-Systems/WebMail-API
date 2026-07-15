"""
This module contains all the query forms for the application
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


from src.utils.base.libraries import BaseModel, Field, List, Optional


class AuthRequest(BaseModel):
    """
    Login form for the endpoint
    email: Email address of the user
    password: Password of the user
    domain: Domain name of the user (e.g. nekonik.com)
    """
    email: str = Field(..., title="Email", description="Email address of the user")
    password: str = Field(..., title="Password", description="Password of the user")
    domain: str = Field(..., title="Domain", description="Domain name of the user (e.g. nekonik.com)")
    recaptcha_token: str = Field(..., title="reCAPTCHA Token", description="Token from reCAPTCHA verification")

    class Config:
        """
        Configuration for the model
        """
        json_schema_extra = {
            "example": {
                "email": "test@nekonik.com",
                "password": "RAW_PASSWORD_STRING",
                "domain": "nekonik.com",
                "recaptcha_token": "<reCAPTCHA token obtained from client-side verification>"
            }
        }


class SetAclForm(BaseModel):
    """
    Set ACL form for the endpoint
    folder_path: Name of the folder to set ACL for
    user: User to set ACL for
    permissions: Permissions to set for the user
    """
    folder_path: str = Field(..., title="Folder Name", description="Name of the folder to set ACL for")
    user: str = Field(..., title="User", description="User to set ACL for")
    permissions: str = Field(..., title="Permissions", description="Permissions to set for the user")

    class Config:
        """
        Configuration for the model
        """
        json_schema_extra = {
            "example": {
                "folder_path": "'Nik 04/Nik 03'",
                "user": "test@nekonik.com",
                "permissions": "lrswipkxte"
            }
        }


class Contact(BaseModel):
    """
    Contact form for the endpoint
    name: Name of the contact
    email: Email address of the contact
    phone: Phone number of the contact
    notes: Notes about the contact
    """
    name: str = Field(..., title="Name", description="Name of the contact")
    email: str = Field(..., title="Email", description="Email address of the contact")
    phone: str = Field('', title="Phone", description="Phone number of the contact")
    notes: str = Field('', title="Notes", description="Notes about the contact")

    class Config:
        """
        Configuration for the model
        """
        json_schema_extra = {
            "example": {
                "name": "Neko Nik",
                "email": "contact@nekonik.com",
                "phone": "+911234567890",
                "notes": "This is a test contact"
            }
        }


class Attachment(BaseModel):
    filename: str = Field(..., title="Filename", description="Name of the attachment file")
    mime_type: str = Field(..., title="MIME Type", description="MIME type of the attachment")
    data: str = Field(..., title="Data", description="Base64 encoded content of the attachment")


class EmailAddress(BaseModel):
    name: Optional[str] = Field(None, title="Name", description="Name of the email address")
    email: str = Field(..., title="Email", description="Email address")


class InLineAttachment(BaseModel):
    filename: str = Field(..., title="Filename", description="Name of the in-line attachment file")
    content_id: str = Field(..., title="Content ID", description="Content ID for referencing the in-line attachment")
    mime_type: str = Field(..., title="MIME Type", description="MIME type of the in-line attachment")
    data: str = Field(..., title="Data", description="Base64 encoded content of the in-line attachment")


class SendMailForm(BaseModel):
    """Send mail form for the endpoint"""
    from_id: EmailAddress = Field(..., title="From", description="Sender in format 'Name <email>'")
    to: List[EmailAddress] = Field(..., title="To", description="List of recipients in format 'Name <email>'")
    cc: List[EmailAddress] = Field(default_factory=list, title="CC", description="List of CC recipients")
    bcc: List[EmailAddress] = Field(default_factory=list, title="BCC", description="List of BCC recipients")
    reply_to: Optional[EmailAddress] = Field(None, title="Reply To", description="Reply-To in format 'Name <email>'")
    subject: Optional[str] = Field('', title="Subject", description="Subject of the email")
    body_text: Optional[str] = Field('', title="Body Text", description="Plain text body of the email")
    body_html: Optional[str] = Field('', title="Body HTML", description="HTML body of the email")
    folder_path: Optional[str] = Field('', title="Folder Path", description="Path where the email is saved")
    headers: Optional[dict] = Field(default_factory=dict, title="Headers", description="Custom email headers")
    priority: Optional[str] = Field('normal', title="Priority", description="Email priority: normal, high, or low")
    timestamp: Optional[str] = Field('', title="Timestamp", description="ISO 8601 timestamp of the email")
    draft_saved: bool = Field(False, title="Draft Saved", description="Flag to indicate if the email is saved as draft")
    draft_folder_name: Optional[str] = Field(None, title="Draft Folder Name", description="Name of the folder where the draft is saved")
    draft_message_id: Optional[str] = Field(None, title="Draft Message ID", description="ID of the draft message")

    class Config:
        json_schema_extra = {
            "example": {
                "from_id": {
                    "name": "From Neko Nik",
                    "email": "from@nekonik.com"
                },
                "to": [
                    {
                        "name": "To User",
                        "email": "to@nekonik.com"
                    }
                ],
                "cc": [
                    {
                        "name": "CC Person",
                        "email": "cc@nekonik.com"
                    }
                ],
                "bcc": [
                    {
                        "name": "BCC Person",
                        "email": "bcc@nekonik.com"
                    }
                ],
                "subject": "Any subject and is optional",
                "body_text": "This is a test email",
                "body_html": "<h1>This is a test email</h1>",
                "folder_path": "Nik 04/Nik 03",
                "reply_to": {
                    "name": "Reply Person",
                    "email": "reply-to@nekonik.com"
                },
                "headers": {
                    "X-Custom-Header": "Value"
                },
                "priority": "high",
                "timestamp": "2025-05-02T10:15:30Z",
                "draft_saved": False,
                "draft_folder_name": None,
                "draft_message_id": None
            }
        }


class SearchMailSize(BaseModel):
    comparator: str = Field(..., title="Comparator", description="Comparator for size filter, e.g. '>', '<', '='")
    size: int = Field(..., title="Size", description="Size in bytes for the filter")

    class Config:
        json_schema_extra = {
            "example": {
                "comparator": ">",
                "size": 10686
            }
        }


class SearchMail(BaseModel):
    """Search mail form for the endpoint"""
    folder: str = Field(..., title="Folder", description="Folder to search in")
    from_: Optional[str] = Field(None, title="From", description="Sender email address")
    to: Optional[str] = Field(None, title="To", description="Recipient email address")
    subject: Optional[str] = Field(None, title="Subject", description="Email subject")
    size: Optional[SearchMailSize] = Field(None, title="Size", description="Size filter for the email")
    date_on: Optional[str] = Field(None, title="Date On", description="Date filter for the email, in ISO 8601 format")
    date_since: Optional[str] = Field(None, title="Date Since", description="Date filter for the email, in ISO 8601 format")
    limit: Optional[int] = Field(50, title="Limit", description="Maximum number of emails to return")
    page: Optional[int] = Field(1, title="Page", description="Page number for pagination")
    full_headers: Optional[bool] = Field(False, title="Full Headers", description="Whether to fetch full email headers")

    class Config:
        json_schema_extra = {
            "example": {
                "folder": "Inbox",
                "from_": "sender@example.com",
                "to": "recipient@example.com",
                "subject": "Test Email",
                "size": {
                    "comparator": ">",
                    "size": 10686
                },
                "full_headers": False,
                "date_on": "2025-05-02T10:15:30Z",
                "date_since": "2025-05-02T10:15:30Z",
                "limit": 50,
                "page": 1
            }
        }


class EmailTemplate(BaseModel):
    """Email template form for the endpoint"""
    name: str = Field(..., title="Template Name", description="Name of the email template")
    subject: str = Field(..., title="Subject", description="Subject of the email template")
    body: str = Field(..., title="Body", description="Body of the email template")
    is_public: bool = Field(..., title="Is Public", description="Flag to indicate if the template is public")
    meta_data: dict = Field(..., title="Meta Data", description="Additional meta data for the email template")

    class Config:
        json_schema_extra = {
            "example": {
                "name": "Welcome Email",
                "subject": "Welcome to Our Service",
                "body": "Thank you for signing up!",
                "is_public": True,
                "meta_data": {
                    "created_by": "admin@example.com",
                    "created_at": "2025-05-02T10:15:30Z"
                }
            }
        }


class SieveFilters(BaseModel):
    """Sieve filter form for the endpoint"""
    name: str = Field(..., title="Sieve Filter Name", description="Name of the sieve filter")
    conditions: List[List] = Field(..., title="Conditions", description="List of conditions for the filter")
    actions: List[List] = Field(..., title="Actions", description="List of actions for the filter")
    match_type: str = Field(..., title="Match Type", description="Match type for the filter, e.g. 'allof', 'anyof'")

    class Config:
        json_schema_extra = {
            "example": {
                "name": "Move Junk to Junks Folder",
                "conditions": [["Subject", ":matches", "Junk*"]],
                "actions": [["fileinto", "Junks"]],
                "match_type": "allof"
            }
        }
