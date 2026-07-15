"""
All the Database related functions are defined here
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


from .connections import PostgresDep, MemcachedDep, lifespan, AdminPostgresDep
from .handler import (
    get_domain_details,
    create_user_session_in_cache,
    get_user_settings,
    replace_user_settings,
    create_user_if_not_exists,
    create_contact,
    edit_contact,
    delete_contact,
    get_one_contact,
    get_contacts,
    contact_exists,
    simple_email_search,
    get_all_templates,
    create_template,
    delete_template,
    edit_template,
    get_template,
    admin_create_new_domain,
    admin_edit_domain,
    admin_delete_domain,
    admin_get_all_domains,
    create_bulk_contacts,
    admin_get_domain_info,
    validate_origin_ip_blocked,
    get_v2_ids,
    simple_email_search_v2
)


__version__ = "v2.9.0-phoenix-release"


__annotations__ = {
    "version": __version__,
    "PostgresDep": "PostgresSQL connection dependency for FastAPI",
    "MemcachedDep": "Memcached connection dependency for FastAPI",
    "lifespan": "Lifespan context manager for FastAPI to manage database connections",
    "get_domain_details": "Function to get domain details from the database",
    "create_user_session_in_cache": "Function to create a user session in the cache",
    "get_user_settings": "Function to get user settings from the database",
    "replace_user_settings": "Function to replace user settings in the database",
    "create_user_if_not_exists": "Function to create a user if not exists in the database",
    "create_contact": "Function to create a contact in the database",
    "edit_contact": "Function to edit a contact in the database",
    "delete_contact": "Function to delete a contact from the database",
    "get_one_contact": "Function to get a single contact from the database",
    "get_contacts": "Function to get all contacts from the database in a paginated manner",
    "contact_exists": "Function to check if a contact exists in the database",
    "simple_email_search": "Function to perform a simple email search in the database",
    "get_all_templates": "Function to get all email templates for a user",
    "create_template": "Function to create a new email template for a user",
    "delete_template": "Function to delete an email template for a user",
    "edit_template": "Function to edit an email template for a user",
    "get_template": "Function to get an email template for a user",
    "admin_create_new_domain": "Function to create a new domain (Admin)",
    "admin_edit_domain": "Function to edit an existing domain (Admin)",
    "admin_delete_domain": "Function to delete a domain (Admin)",
    "admin_get_all_domains": "Function to get all domains with pagination (Admin)",
    "admin_get_domain_info": "Function to get detailed information about a specific domain (Admin)",
    "create_bulk_contacts": "Function to create multiple contacts in the database (Skip if contact email already exists for the user)",
    "AdminPostgresDep": "PostgreSQL connection dependency for FastAPI with admin privileges",
    "validate_origin_ip_blocked": "Function to check if the origin IP is blocked or not (Admin)",
    "get_v2_ids": "Function to get V2 Domain ID and Mailbox ID for a user based on their email address (For V2 Users)",
    "simple_email_search_v2": "Function to perform a simple email search in the database for V2 Users (Searches across all domains and mailboxes of the user)"
}


__all__ = [
    "PostgresDep",
    "MemcachedDep",
    "lifespan",
    "get_domain_details",
    "create_user_session_in_cache",
    "get_user_settings",
    "replace_user_settings",
    "create_user_if_not_exists",
    "create_contact",
    "edit_contact",
    "delete_contact",
    "get_one_contact",
    "get_contacts",
    "contact_exists",
    "simple_email_search",
    "get_all_templates",
    "create_template",
    "delete_template",
    "edit_template",
    "get_template",
    "admin_create_new_domain",
    "admin_edit_domain",
    "admin_delete_domain",
    "admin_get_all_domains",
    "admin_get_domain_info",
    "create_bulk_contacts",
    "AdminPostgresDep",
    "validate_origin_ip_blocked",
    "get_v2_ids",
    "simple_email_search_v2"
]
