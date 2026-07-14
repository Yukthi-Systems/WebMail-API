"""
All Routers are imported here and are exposed to the main app file
"""

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
