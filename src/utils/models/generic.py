"""
This module contains the basic models for the application
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


from src.utils.base.libraries import BaseModel, Field


class All_Exceptions(Exception):
    """Class for handling wrong input exceptions"""
    def __init__(self , message: str , status_code: int):
        self.message = message
        self.status_code = status_code


class Error(BaseModel):
    """
    Error model for API, if any error occurs, this model is returned
    Error message and status code is returned
    message: Error message
    status_code: Error status code
    """
    message: str = Field(..., title="Message", description="Error message")
    status_code: int = Field(..., title="Status Code", description="Error status code")

    class Config:
        """
        Configuration for the model
        """
        json_schema_extra = {
            "example": {
                "message": "Error message",
                "status_code": 400
            }
        }
