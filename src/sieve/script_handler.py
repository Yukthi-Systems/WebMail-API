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


from src.utils.base.libraries import logging, SieveClient, status
from src.utils.models import All_Exceptions


def list_scripts(client: SieveClient) -> dict:
    """
    List all scripts on the Sieve server.
    This function retrieves the list of scripts stored on the Sieve server,
    including the active script.

    :param client: An authenticated Sieve client instance.

    Returns:
        dict: A dictionary containing the active script and a list of all scripts.

    Example:
        {
            "active": "roundcube",
            "scripts": ["vacation", "sogo"]
        }
    """
    try:
        active, scripts = client.listscripts()
        return {
            "active": active,
            "scripts": scripts
        }

    except Exception as e:
        logging.error(f"Failed to list scripts: {e}", exc_info=True)
        raise All_Exceptions(
            message="Failed to list scripts from Sieve server.",
            status_code=status.HTTP_424_FAILED_DEPENDENCY
        )


def create_script(client: SieveClient, script_name: str, script_content: str) -> bool:
    """
    Create a new script on the Sieve server.
    This function creates a new script with the specified name on the Sieve server.

    :param client: An authenticated Sieve client instance.
    :param script_name: The name of the script to be created.
    :param script_content: The content of the script to be created.

    Returns:
        bool: True if the script was created successfully, False otherwise.
    """
    try:
        creation_status: bool = client.putscript(name=script_name, content=script_content)
        return creation_status

    except Exception as e:
        logging.error(f"Failed to create script '{script_name}': {e}", exc_info=True)
        raise All_Exceptions(
            message=f"Failed to create script '{script_name}' on Sieve server.",
            status_code=status.HTTP_424_FAILED_DEPENDENCY
        )


def enable_script(client: SieveClient, script_name: str) -> bool:
    """
    Enable a script on the Sieve server.

    This function sets the specified script as the active script on the Sieve server.

    :param client: An authenticated Sieve client instance.
    :param script_name: The name of the script to be enabled.

    Returns:
        bool: True if the script was enabled successfully, False otherwise.
    """
    try:
        return client.setactive(scriptname=script_name)

    except Exception as e:
        logging.error(f"Failed to enable script '{script_name}': {e}", exc_info=True)
        raise All_Exceptions(
            message=f"Failed to enable script '{script_name}' on Sieve server.",
            status_code=status.HTTP_424_FAILED_DEPENDENCY
        )


def delete_script(client: SieveClient, script_name: str) -> bool:
    """
    Delete a script from the Sieve server.

    This function removes the specified script from the Sieve server.

    :param client: An authenticated Sieve client instance.
    :param script_name: The name of the script to be deleted.

    Returns:
        bool: True if the script was deleted successfully, False otherwise.
    """
    try:
        return client.deletescript(name=script_name)

    except Exception as e:
        logging.error(f"Failed to delete script '{script_name}': {e}", exc_info=True)
        raise All_Exceptions(
            message=f"Failed to delete script '{script_name}' on Sieve server.",
            status_code=status.HTTP_424_FAILED_DEPENDENCY
        )


def rename_script(client: SieveClient, old_name: str, new_name: str) -> bool:
    """
    Rename a script on the Sieve server.

    This function renames an existing script from old_name to new_name on the Sieve server.

    :param client: An authenticated Sieve client instance.
    :param old_name: The current name of the script.
    :param new_name: The new name for the script.

    Returns:
        bool: True if the script was renamed successfully, False otherwise.
    """
    try:
       return client.renamescript(oldname=old_name, newname=new_name)

    except Exception as e:
        logging.error(f"Failed to rename script from '{old_name}' to '{new_name}': {e}", exc_info=True)
        raise All_Exceptions(
            message=f"Failed to rename script from '{old_name}' to '{new_name}' on Sieve server.",
            status_code=status.HTTP_424_FAILED_DEPENDENCY
        )


def get_script_raw_data(client: SieveClient, script_name: str) -> str:
    """
    Retrieve the raw Sieve script content from the server.

    This function fetches the entire Sieve script as a string.

    param client: An authenticated Sieve client instance.
    param script_name: The name of the Sieve script to retrieve.

    Returns:
        str: The raw Sieve script content as a string, or None if retrieval fails.
    """
    try:
        script_content = client.getscript(name=script_name)
        return script_content

    except Exception as e:
        logging.error(f"Failed to get raw script data from script '{script_name}': {e}", exc_info=True)
        raise All_Exceptions(
            message=f"Failed to get raw script data from script '{script_name}' on Sieve server.",
            status_code=status.HTTP_424_FAILED_DEPENDENCY
        )
