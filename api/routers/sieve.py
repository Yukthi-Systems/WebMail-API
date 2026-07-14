"""
This module provides Sieve-related API endpoints for email management
"""

from src.utils.base.libraries import (
    JSONResponse,
    APIRouter,
    status
)
from src.utils.models import SieveFilters
from src.main import CurrentUser
from src.sieve import *


# Router
router = APIRouter()


# List scripts in the Sieve server
@router.get("/scripts", response_class=JSONResponse, tags=["Sieve"], summary="List all scripts in the Sieve server")
def list_sieve_scripts(user: CurrentUser) -> JSONResponse:
    """List all scripts in the Sieve server"""
    sieve_connection = get_sieve_connection_from_user_data(user=user)

    # List the scripts
    scripts_list = list_scripts(client=sieve_connection)

    return JSONResponse(
        content={
            "message": "Sieve scripts fetched successfully",
            "scripts": scripts_list
        },
        status_code=status.HTTP_200_OK
    )


# Create a new script in the Sieve server
@router.post("/scripts/{script_name}", response_class=JSONResponse, tags=["Sieve"], summary="Create a new script in the Sieve server")
def create_sieve_script(script_name: str, script_content: str, user: CurrentUser) -> JSONResponse:
    """Create a new script in the Sieve server"""
    sieve_connection = get_sieve_connection_from_user_data(user=user)

    # Create the script
    creation_status = create_script(client=sieve_connection, script_name=script_name, script_content=script_content)

    return JSONResponse(
        content={
            "message": f"Sieve script '{script_name}' created successfully" if creation_status else f"Failed to create Sieve script '{script_name}'",
            "created": creation_status
        },
        status_code=status.HTTP_201_CREATED if creation_status else status.HTTP_417_EXPECTATION_FAILED
    )


# Enable a script in the Sieve server
@router.post("/scripts/{script_name}/enable", response_class=JSONResponse, tags=["Sieve"], summary="Enable a script in the Sieve server")
def enable_sieve_script(script_name: str, user: CurrentUser) -> JSONResponse:
    """Enable a script in the Sieve server"""
    sieve_connection = get_sieve_connection_from_user_data(user=user)

    # Enable the script
    enable_status = enable_script(client=sieve_connection, script_name=script_name)

    return JSONResponse(
        content={
            "message": f"Sieve script '{script_name}' enabled successfully" if enable_status else f"Failed to enable Sieve script '{script_name}'",
            "enabled": enable_status
        },
        status_code=status.HTTP_200_OK if enable_status else status.HTTP_417_EXPECTATION_FAILED
    )


# Delete a script in the Sieve server
@router.delete("/scripts/{script_name}", response_class=JSONResponse, tags=["Sieve"], summary="Delete a script in the Sieve server")
def delete_sieve_script(script_name: str, user: CurrentUser) -> JSONResponse:
    """Delete a script in the Sieve server"""
    sieve_connection = get_sieve_connection_from_user_data(user=user)

    # Delete the script
    delete_status = delete_script(client=sieve_connection, script_name=script_name)

    return JSONResponse(
        content={
            "message": f"Sieve script '{script_name}' deleted successfully" if delete_status else f"Failed to delete Sieve script '{script_name}'",
            "deleted": delete_status
        },
        status_code=status.HTTP_200_OK if delete_status else status.HTTP_417_EXPECTATION_FAILED
    )


# Rename a script in the Sieve server
@router.put("/scripts/{old_script_name}/rename/{new_script_name}", response_class=JSONResponse, tags=["Sieve"], summary="Rename a script in the Sieve server")
def rename_sieve_script(old_script_name: str, new_script_name: str, user: CurrentUser) -> JSONResponse:
    """Rename a script in the Sieve server"""
    sieve_connection = get_sieve_connection_from_user_data(user=user)

    # Rename the script
    rename_status = rename_script(client=sieve_connection, old_name=old_script_name, new_name=new_script_name)

    return JSONResponse(
        content={
            "message": f"Sieve script '{old_script_name}' renamed to '{new_script_name}' successfully" if rename_status else f"Failed to rename Sieve script '{old_script_name}'",
            "renamed": rename_status
        },
        status_code=status.HTTP_200_OK if rename_status else status.HTTP_417_EXPECTATION_FAILED
    )


# Get raw data of a script in the Sieve server
@router.get("/scripts/{script_name}/raw", response_class=JSONResponse, tags=["Sieve"], summary="Get raw data of a script in the Sieve server")
def get_sieve_script_raw_data(script_name: str, user: CurrentUser) -> JSONResponse:
    """Get raw data of a script in the Sieve server"""
    sieve_connection = get_sieve_connection_from_user_data(user=user)

    # Get the raw data of the script
    raw_data = get_script_raw_data(client=sieve_connection, script_name=script_name)

    return JSONResponse(
        content={
            "message": f"Sieve script '{script_name}' raw data fetched successfully",
            "raw_data": raw_data
        },
        status_code=status.HTTP_200_OK
    )


# List filters in the Sieve server
@router.get("/filters/{script_name}", response_class=JSONResponse, tags=["Sieve"], summary="List all filters in a Sieve script")
def list_sieve_filters(script_name: str, user: CurrentUser) -> JSONResponse:
    """List all filters in a Sieve script"""
    sieve_connection = get_sieve_connection_from_user_data(user=user)

    # List the filters
    filters_list = list_filters(client=sieve_connection, script_name=script_name)

    return JSONResponse(
        content={
            "message": f"Sieve filters in script '{script_name}' fetched successfully",
            "filters": filters_list
        },
        status_code=status.HTTP_200_OK
    )


# Create a new filter in a Sieve script
@router.post("/filters/{script_name}", response_class=JSONResponse, tags=["Sieve"], summary="Create a new filter in a Sieve script")
def create_sieve_filter(script_name: str, data: SieveFilters, user: CurrentUser) -> JSONResponse:
    """Create a new filter in a Sieve script"""
    sieve_connection = get_sieve_connection_from_user_data(user=user)

    # Create the filter
    creation_status = create_filter(
        client=sieve_connection,
        script_name=script_name,
        filter_definition={
            "name": data.name,
            "conditions": [tuple(condition) for condition in data.conditions],
            "actions": [tuple(action) for action in data.actions],
            "match_type": data.match_type
        }
    )

    return JSONResponse(
        content={
            "message": f"Sieve filter '{data.name}' created successfully in script '{script_name}'" if creation_status else f"Failed to create Sieve filter '{data.name}' in script '{script_name}'",
            "created": creation_status
        },
        status_code=status.HTTP_201_CREATED if creation_status else status.HTTP_417_EXPECTATION_FAILED
    )


# Get filter data from a Sieve script
@router.get("/filters/{script_name}/{filter_name}", response_class=JSONResponse, tags=["Sieve"], summary="Get data of a filter in a Sieve script")
def get_sieve_filter_data(script_name: str, filter_name: str, user: CurrentUser) -> JSONResponse:
    """Get data of a filter in a Sieve script"""
    sieve_connection = get_sieve_connection_from_user_data(user=user)

    # Get the filter data
    filter_data = get_filter_data(
        client=sieve_connection,
        script_name=script_name,
        filter_name=filter_name
    )

    return JSONResponse(
        content={
            "message": f"Sieve filter '{filter_name}' data fetched successfully from script '{script_name}'",
            "filter_data": filter_data
        },
        status_code=status.HTTP_200_OK
    )


# Delete a filter from a Sieve script
@router.delete("/filters/{script_name}/{filter_name}", response_class=JSONResponse, tags=["Sieve"], summary="Delete a filter from a Sieve script")
def delete_sieve_filter(script_name: str, filter_name: str, user: CurrentUser) -> JSONResponse:
    """Delete a filter from a Sieve script"""
    sieve_connection = get_sieve_connection_from_user_data(user=user)

    # Delete the filter
    delete_status = delete_filter(
        client=sieve_connection,
        script_name=script_name,
        filter_name=filter_name
    )

    return JSONResponse(
        content={
            "message": f"Sieve filter '{filter_name}' deleted successfully from script '{script_name}'" if delete_status else f"Failed to delete Sieve filter '{filter_name}' from script '{script_name}'",
            "deleted": delete_status
        },
        status_code=status.HTTP_200_OK if delete_status else status.HTTP_417_EXPECTATION_FAILED
    )


# Disable a filter in a Sieve script
@router.post("/filters/{script_name}/{filter_name}/disable", response_class=JSONResponse, tags=["Sieve"], summary="Disable a filter in a Sieve script")
def disable_sieve_filter(script_name: str, filter_name: str, user: CurrentUser) -> JSONResponse:
    """Disable a filter in a Sieve script"""
    sieve_connection = get_sieve_connection_from_user_data(user=user)

    # Disable the filter
    disable_status = disable_filter(
        client=sieve_connection,
        script_name=script_name,
        filter_name=filter_name
    )

    return JSONResponse(
        content={
            "message": f"Sieve filter '{filter_name}' disabled successfully in script '{script_name}'" if disable_status else f"Failed to disable Sieve filter '{filter_name}' in script '{script_name}'",
            "disabled": disable_status
        },
        status_code=status.HTTP_200_OK if disable_status else status.HTTP_417_EXPECTATION_FAILED
    )


# Enable a filter in a Sieve script
@router.post("/filters/{script_name}/{filter_name}/enable", response_class=JSONResponse, tags=["Sieve"], summary="Enable a filter in a Sieve script")
def enable_sieve_filter(script_name: str, filter_name: str, user: CurrentUser) -> JSONResponse:
    """Enable a filter in a Sieve script"""
    sieve_connection = get_sieve_connection_from_user_data(user=user)

    # Enable the filter
    enable_status = enable_filter(
        client=sieve_connection,
        script_name=script_name,
        filter_name=filter_name
    )

    return JSONResponse(
        content={
            "message": f"Sieve filter '{filter_name}' enabled successfully in script '{script_name}'" if enable_status else f"Failed to enable Sieve filter '{filter_name}' in script '{script_name}'",
            "enabled": enable_status
        },
        status_code=status.HTTP_200_OK if enable_status else status.HTTP_417_EXPECTATION_FAILED
    )


# Update a filter in a Sieve script
@router.put("/filters/{script_name}/{filter_name}", response_class=JSONResponse, tags=["Sieve"], summary="Update a filter in a Sieve script")
def update_sieve_filter(script_name: str, filter_name: str, data: SieveFilters, user: CurrentUser) -> JSONResponse:
    """Update a filter in a Sieve script"""
    sieve_connection = get_sieve_connection_from_user_data(user=user)

    # Update the filter
    update_status = update_filter(
        client=sieve_connection,
        script_name=script_name,
        filter_name=filter_name,
        filter_definition={
            "name": data.name,
            "conditions": [tuple(condition) for condition in data.conditions],
            "actions": [tuple(action) for action in data.actions],
            "match_type": data.match_type
        }
    )

    return JSONResponse(
        content={
            "message": f"Sieve filter '{filter_name}' updated successfully in script '{script_name}'" if update_status else f"Failed to update Sieve filter '{filter_name}' in script '{script_name}'",
            "updated": update_status
        },
        status_code=status.HTTP_200_OK if update_status else status.HTTP_417_EXPECTATION_FAILED
    )
