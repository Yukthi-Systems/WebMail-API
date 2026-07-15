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


from .connection import get_sieve_connection_from_user_data
from .script_handler import list_scripts, create_script, enable_script, delete_script, rename_script, get_script_raw_data
from .filter_handler import list_filters, create_filter, get_filter_data, delete_filter, disable_filter, enable_filter, update_filter


__version__ = "v1.0.0-phoenix-release"


__annotations__ = {
    "get_sieve_connection_from_user_data": "Function to connect to Sieve server",
    "list_scripts": "Function to list all Sieve scripts",
    "create_script": "Function to create a new Sieve script",
    "enable_script": "Function to enable a Sieve script",
    "delete_script": "Function to delete a Sieve script",
    "rename_script": "Function to rename a Sieve script",
    "get_script_raw_data": "Function to get raw data of a Sieve script",
    "list_filters": "Function to list all Sieve filters",
    "create_filter": "Function to create a new Sieve filter",
    "get_filter_data": "Function to get data of a Sieve filter",
    "delete_filter": "Function to delete a Sieve filter",
    "disable_filter": "Function to disable a Sieve filter",
    "enable_filter": "Function to enable a Sieve filter",
    "update_filter": "Function to update a Sieve filter"
}


__all__ = [
    "get_sieve_connection_from_user_data",
    "list_scripts",
    "create_script",
    "enable_script",
    "delete_script",
    "rename_script",
    "get_script_raw_data",
    "list_filters",
    "create_filter",
    "get_filter_data",
    "delete_filter",
    "disable_filter",
    "enable_filter",
    "update_filter"
]
