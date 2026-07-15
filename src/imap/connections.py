"""
This file contains the database connection and session creation functions
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


from src.utils.base.libraries import logging, IMAP4_SSL, time, status
from src.utils.models import All_Exceptions


def get_imap_connection(imap_user: str, imap_password: str, imap_server: str, imap_port: int) -> IMAP4_SSL:
    """
    Retrieves an IMAP connection from the pool if available and not expired.
    If not, creates a new one and returns it.
    """
    MAX_RETRIES = 3
    retry_delay_ms = 800  # Initial delay of 800ms

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            connection = IMAP4_SSL(host=imap_server, port=imap_port, timeout=60)
            connection.login(user=imap_user, password=imap_password)
            return connection

        except Exception as e:
            logging.error(f"Attempt {attempt}: Error connecting to IMAP server: {imap_server}:{imap_port} for user {imap_user}: {e}", exc_info=True)

            if attempt == MAX_RETRIES:
                raise All_Exceptions(f"Failed to connect to IMAP server: {imap_server}:{imap_port} for user {imap_user} after {MAX_RETRIES} attempts: {e}", status.HTTP_429_TOO_MANY_REQUESTS)
            else:
                # Exponential backoff: [800ms, 1600ms, 3200ms]
                time.sleep(retry_delay_ms / 1000)  # Convert ms to seconds
                retry_delay_ms *= 2  # Exponential backoff


def get_imap_connection_from_user_data(user: dict) -> IMAP4_SSL:
    """A wrapper function to get IMAP connection using user data"""
    if not user:
        raise ValueError("User data is required to establish an IMAP connection.")

    if not all(key in user for key in ["user_email", "imap_password", "imap_server", "imap_port"]):
        raise ValueError("User data must contain 'user_email', 'imap_password', 'imap_server', and 'imap_port' keys.")

    if not (conn := get_imap_connection(
        imap_user=user["user_email"],
        imap_password=user["imap_password"],
        imap_server=user["imap_server"],
        imap_port=user["imap_port"]
    )):
        raise All_Exceptions(
            message="Failed to establish IMAP connection",
            status_code=status.HTTP_417_EXPECTATION_FAILED
        )

    return conn
