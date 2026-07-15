"""
All Routers are imported here and are exposed to the main app file
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


from .logs import router as logs_router
from .user import router as user_router
from .sieve import router as sieve_router
from .email import router as email_router
from .folder import router as folder_router
from .contacts import router as contacts_router


__version__ = "v1.3.0-phoenix-release"


__annotations__ = {
    "version": __version__,
    "logs_router": "Logs of API",
    "user_router": "User Login, Session management, Settings related routes",
    "folder_router": "Email Folder and Subfolder related routes",
    "email_router": "Email related routes",
    "contacts_router": "Contacts related routes",
    "sieve_router": "Sieve Script related routes"
}


__all__ = [
    "logs_router",
    "user_router",
    "folder_router",
    "email_router",
    "contacts_router",
    "sieve_router"
]
