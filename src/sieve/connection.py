"""
This file contains functions to manage connections to a Sieve server
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


from src.utils.base.libraries import logging, status, SieveClient
from src.utils.models import All_Exceptions


def connect_to_sieve(server_name: str, user_name: str, password: str, starttls: bool = True, port: int = 4190) -> SieveClient:
    """
    Establish a connection to the Sieve server.

    This function initializes the connection to the Sieve server,
    handling authentication and any necessary setup.

    param server_name: The hostname or IP address of the Sieve server.
    param user_name: The username for authentication.
    param password: The password for authentication.
    param starttls: Whether to use STARTTLS for secure connection (default is True).
    param port: The port number to connect to (default is 4190).

    Returns:
        Client: An authenticated Sieve client instance.
    """
    try:
        client = SieveClient(srvaddr=server_name, srvport=port, debug=True)
        client.connect(user_name, password, starttls=starttls, authmech="PLAIN")

        return client

    except Exception as e:
        logging.error(f"Failed to connect to Sieve server: {e} username: {user_name} server: {server_name}", exc_info=True)
        raise All_Exceptions(
            message="Failed to connect to Sieve server.",
            status_code=status.HTTP_401_UNAUTHORIZED
        )


def get_sieve_connection_from_user_data(user: dict) -> SieveClient:
    """
    Get Sieve connection using user data

    param user: User data dictionary containing Sieve connection details

    Returns:
        Client: An authenticated Sieve client instance.
    """
    return connect_to_sieve(
        server_name=user["sieve_server"],
        user_name=user["sieve_user"],
        password=user["sieve_password"],
        starttls=True,
        port=user["sieve_port"]
    )
