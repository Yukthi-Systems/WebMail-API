"""
All the models used in the API are defined here
"""

from .generic import All_Exceptions, Error
from .query_forms import AuthRequest, SetAclForm, Contact, SendMailForm, SearchMail, EmailTemplate, SieveFilters


__version__ = "v1.5.0-phoenix-release"


__annotations__ = {
    "version": __version__,
    "All_Exceptions": "Class for handling wrong input exceptions",
    "Error": "Class for handling wrong input exceptions",
    "AuthRequest": "Login form for the endpoint",
    "SetAclForm": "Set ACL form for the endpoint",
    "Contact": "Contact form for the endpoint",
    "SendMailForm": "Send mail form for the endpoint",
    "SearchMail": "Search mail form for the endpoint",
    "EmailTemplate": "Email template form for the endpoint",
    "SieveFilters": "Sieve filter representation model"
}


__all__ = [
    "All_Exceptions",
    "Error",
    "AuthRequest",
    "SetAclForm",
    "Contact",
    "SendMailForm",
    "SearchMail",
    "EmailTemplate",
    "SieveFilters"
]
