"""
All the models used in the API are defined here
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
