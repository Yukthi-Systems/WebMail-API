"""
This file contains functions to manage connections to a Sieve server
"""

from src.utils.base.libraries import logging, SieveClient, status, SieveFiltersSet, SieveParser
from src.utils.models import All_Exceptions


def list_filters(client: SieveClient, script_name: str) -> list:
    """
    List all filters in a given Sieve script.

    This function retrieves and parses the specified Sieve script to extract
    all defined filters.

    param client: An authenticated Sieve client instance.
    param script_name: The name of the Sieve script to retrieve filters from.

    Returns:
        list: A list of filter definitions found in the script.

    Example:
        filters = ["filter1", "filter2", ...]
    """
    try:
        script_content = client.getscript(name=script_name)
        parser = SieveParser.Parser()

        success = parser.parse(text=script_content.encode('utf-8'))
        if not success:
            logging.error(f"Parsing failed: {parser.error}")
            return []

        fs = SieveFiltersSet("test", "# rule:")
        fs.from_parser_result(parser=parser)

        return [{
            "name" : filter_["name"],
            "enabled": filter_["enabled"]
        } for filter_ in fs.filters]

    except Exception as e:
        logging.error(f"Failed to list filters from script '{script_name}': {e}", exc_info=True)
        raise All_Exceptions(
            message=f"Failed to list filters from script '{script_name}'",
            status_code=status.HTTP_412_PRECONDITION_FAILED
        )


def create_filter(client: SieveClient, script_name: str, filter_definition: dict) -> bool:
    """
    Create a new filter in a given Sieve script.

    This function adds a new filter definition to the specified Sieve script.

    param client: An authenticated Sieve client instance.
    param script_name: The name of the Sieve script to add the filter to.
    param filter_definition: The Sieve filter definition to be added.

    Returns:
        bool: True if the filter was added successfully, False otherwise.
    """
    try:
        current_script = client.getscript(name=script_name)
        if not current_script:
            logging.warning(f"Script '{script_name}' not found or empty. Creating new script with the filter.")

        parser = SieveParser.Parser()
        if not parser.parse(text=current_script.encode('utf-8')):
            logging.error(f"Failed to parse existing script!: {parser.error}")
            return False

        fs = SieveFiltersSet(name=filter_definition["name"], filter_name_pretext="# rule:")
        fs.from_parser_result(parser=parser)
        fs.addfilter(
            filter_definition["name"],
            filter_definition["conditions"],
            filter_definition["actions"],
            filter_definition["match_type"],
        )
        fs.enablefilter(filter_definition["name"])
        script_content = str(fs)

        if not script_content:
            logging.error(f"Failed to generate Sieve script. Invalid filter data for filter '{filter_definition['name']}'.")
            return False

        return client.putscript(name=script_name, content=script_content)

    except Exception as e:
        logging.error(f"Failed to create filter in script '{script_name}': {e}", exc_info=True)
        raise All_Exceptions(
            message=f"Failed to create filter in script '{script_name}'",
            status_code=status.HTTP_412_PRECONDITION_FAILED
        )


def get_filter_data(client: SieveClient, script_name: str, filter_name: str) -> dict:
    """
    Retrieve the details of a specific filter from a Sieve script.

    This function fetches and parses the specified Sieve script to extract
    the details of a given filter.

    param client: An authenticated Sieve client instance.
    param script_name: The name of the Sieve script to retrieve the filter from.
    param filter_name: The name of the filter to retrieve.

    Returns:
        dict: A dictionary containing the filter's details, or None if not found.

    Example:
        filter_data = {
            "name": "filter1",
            "conditions": [...],
            "actions": [...],
            "match_type": "...",
            "disabled": False,
            "content": "full sieve script content as string"
        }
    """
    try:
        script_content = client.getscript(name=script_name)
        parser = SieveParser.Parser()

        if not parser.parse(script_content):
            logging.error(f"Parsing failed: {parser.error}")
            raise All_Exceptions(
                message=f"Failed to parse script '{script_name}' with error: {parser.error}",
                status_code=status.HTTP_412_PRECONDITION_FAILED
            )

        fs = SieveFiltersSet("test", "# rule:")
        fs.from_parser_result(parser)
        filter= fs.getfilter(filter_name)
        if filter is None:
            raise All_Exceptions(
                message=f"Filter '{filter_name}' not found in script '{script_name}'",
                status_code=status.HTTP_404_NOT_FOUND
            )

        return {
            "name": filter_name,
            "conditions": fs.get_filter_conditions(filter_name),
            "actions": fs.get_filter_actions(filter_name),
            "match_type": fs.get_filter_matchtype(filter_name),
            "disabled": fs.is_filter_disabled(filter_name),
            "content": str(fs),
        }

    except Exception as e:
        logging.error(f"Failed to get filter data from script '{script_name}': {e}", exc_info=True)
        raise All_Exceptions(
            message=f"Failed to get filter data from script '{script_name}'",
            status_code=status.HTTP_412_PRECONDITION_FAILED
        )


def delete_filter(client: SieveClient, script_name: str, filter_name: str) -> bool:
    """
    Delete a specific filter from a Sieve script.

    This function removes the specified filter from the given Sieve script.

    param client: An authenticated Sieve client instance.
    param script_name: The name of the Sieve script to delete the filter from.
    param filter_name: The name of the filter to delete.

    Returns:
        bool: True if the filter was deleted successfully, False otherwise.
    """
    try:
        current_script = client.getscript(name=script_name)
        if not current_script:
            logging.error(f"Script '{script_name}' not found or there is no data in the server.")
            return False

        parser = SieveParser.Parser()
        if not parser.parse(current_script):
            logging.error(f"Failed to parse existing script! {parser.error}")
            return False

        fs = SieveFiltersSet(name=filter_name, filter_name_pretext="# rule:")
        fs.from_parser_result(parser=parser)
        if not fs.getfilter(filter_name):
            logging.error(f"Filter '{filter_name}' not found in script '{script_name}'.")
            return False

        fs.removefilter(filter_name)
        script_content = str(fs)
        if not script_content:
            logging.error("Failed to generate Sieve script. Invalid filter data.")
            return False

        return client.putscript(name=script_name, content=script_content)

    except Exception as e:
        logging.error(f"Failed to delete filter '{filter_name}' from script '{script_name}': {e}", exc_info=True)
        raise All_Exceptions(
            message=f"Failed to delete filter '{filter_name}' from script '{script_name}'",
            status_code=status.HTTP_412_PRECONDITION_FAILED
        )


def disable_filter(client: SieveClient, script_name: str, filter_name: str) -> bool:
    """
    Disable a specific filter in a Sieve script.

    This function marks the specified filter as disabled in the given Sieve script.

    param client: An authenticated Sieve client instance.
    param script_name: The name of the Sieve script to disable the filter in.
    param filter_name: The name of the filter to disable.

    Returns:
        bool: True if the filter was disabled successfully, False otherwise.
    """
    try:
        current_script = client.getscript(name=script_name)
        if not current_script:
            logging.error(f"Script '{script_name}' not found or there is no data in the server.")
            return False

        parser = SieveParser.Parser()
        if not parser.parse(current_script):
            logging.error(f"Failed to parse existing script! {parser.error}")
            return False

        fs = SieveFiltersSet(name=filter_name, filter_name_pretext="# rule:")
        fs.from_parser_result(parser=parser)
        if not fs.getfilter(filter_name):
            logging.error(f"Filter '{filter_name}' not found in script '{script_name}'.")
            return False

        fs.disablefilter(filter_name)
        script_content = str(fs)
        if not script_content:
            logging.error("Failed to generate Sieve script. Invalid filter data.")
            return False

        return client.putscript(name=script_name, content=script_content)

    except Exception as e:
        logging.error(f"Failed to disable filter '{filter_name}' in script '{script_name}': {e}", exc_info=True)
        raise All_Exceptions(
            message=f"Failed to disable filter '{filter_name}' in script '{script_name}'",
            status_code=status.HTTP_412_PRECONDITION_FAILED
        )


def enable_filter(client: SieveClient, script_name: str, filter_name: str) -> bool:
    """
    Enable a specific filter in a Sieve script.

    This function marks the specified filter as enabled in the given Sieve script.

    param client: An authenticated Sieve client instance.
    param script_name: The name of the Sieve script to enable the filter in.
    param filter_name: The name of the filter to enable.

    Returns:
        bool: True if the filter was enabled successfully, False otherwise.
    """
    try:
        current_script = client.getscript(name=script_name)
        if not current_script:
            logging.error(f"Script '{script_name}' not found or there is no data in the server.")
            return False

        parser = SieveParser.Parser()
        if not parser.parse(current_script):
            logging.error(f"Failed to parse existing script! {parser.error}")
            return False

        fs = SieveFiltersSet(name=filter_name, filter_name_pretext="# rule:")
        fs.from_parser_result(parser=parser)
        if not fs.getfilter(name=filter_name):
            logging.error(f"Filter '{filter_name}' not found in script '{script_name}'.")
            return False

        fs.enablefilter(name=filter_name)
        script_content = str(fs)
        if not script_content:
            logging.error("Failed to generate Sieve script. Invalid filter data.")
            return False

        return client.putscript(name=script_name, content=script_content)

    except Exception as e:
        logging.error(f"Failed to enable filter '{filter_name}' in script '{script_name}': {e}", exc_info=True)
        raise All_Exceptions(
            message=f"Failed to enable filter '{filter_name}' in script '{script_name}'",
            status_code=status.HTTP_412_PRECONDITION_FAILED
        )


def update_filter(client: SieveClient, script_name: str, filter_name: str, filter_definition: dict) -> bool:
    """
    Update an existing filter in a given Sieve script.

    This function updates an existing filter definition in the specified Sieve script.

    param client: An authenticated Sieve client instance.
    param script_name: The name of the Sieve script to update the filter in.
    param filter_definition: The updated Sieve filter definition.

    Returns:
        bool: True if the filter was updated successfully, False otherwise.
    """
    try:
        current_script = client.getscript(name=script_name)
        if not current_script:
            logging.debug(f"Script '{script_name}' no old filters found on server. Creating a new filter.")

        parser = SieveParser.Parser()
        if not parser.parse(current_script):
            logging.error(f"Failed to parse existing script!: {parser.error}")
            return False

        fs = SieveFiltersSet(name=filter_name, filter_name_pretext="# rule:")
        fs.from_parser_result(parser=parser)
        if not fs.getfilter(name=filter_name):
            logging.error(f"Filter '{filter_name}' not found in script '{script_name}'. Cannot update non-existing filter.")
            return False

        status = fs.updatefilter(
            oldname=filter_name,
            newname=filter_definition["name"],
            conditions=filter_definition["conditions"],
            actions=filter_definition["actions"],
            matchtype=filter_definition["match_type"],
        )
        if not status:
            logging.error(f"Failed to update filter '{filter_definition['name']}'")
            return False

        if filter_definition.get("enable", True):
            fs.enablefilter(name=filter_definition["name"])
        else:
            fs.disablefilter(name=filter_definition["name"])

        script_content = str(fs)
        if not script_content:
            logging.error("Failed to generate Sieve script. Invalid filter data.")
            return False

        return client.putscript(name=script_name, content=script_content)

    except Exception as e:
        logging.error(f"Failed to update filter in script '{script_name}': {e}", exc_info=True)
        raise All_Exceptions(
            message=f"Failed to update filter in script '{script_name}'",
            status_code=status.HTTP_412_PRECONDITION_FAILED
        )
