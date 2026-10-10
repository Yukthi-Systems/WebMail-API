"""
This module provides Folder related API endpoints
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


from src.utils.base.libraries import (
    JSONResponse,
    APIRouter,
    status,
    re,
    logging
)
from src.imap import get_imap_connection_from_user_data, list_folders, parse_acl_response, parse_imap_response, parse_quota_response, mark_folder_as_read, is_trash_or_junk_folder, empty_folder
from src.utils.models import SetAclForm, All_Exceptions
from src.main import CurrentUser


# Router
router = APIRouter()


# Get all the folders paths for the user
@router.get("/path", response_class=JSONResponse, tags=["Folder"], summary="Get Folder Hierarchy as JSON")
def get_all_folders_paths(user: CurrentUser) -> JSONResponse:
    """Get all folders paths for the user"""
    imap_connection = get_imap_connection_from_user_data(user=user)

    # Get the folders
    folders = list_folders(connection=imap_connection)
    if not folders:
        return JSONResponse(
            content={"message": "Failed to list folders."},
            status_code=status.HTTP_204_NO_CONTENT
        )

    return JSONResponse(
        content={
            "message": "Folders fetched successfully",
            "folders": folders
        },
        status_code=status.HTTP_200_OK
    )


# Create a new folder path
@router.post("/path", response_class=JSONResponse, tags=["Folder"], summary="Create a new folder path")
def create_folder_path(folder_path: str, user: CurrentUser) -> JSONResponse:
    """Create a new folder path"""
    imap_connection = get_imap_connection_from_user_data(user=user)

    # Create the folder
    try:
        resp = parse_imap_response(
            imap_response=imap_connection.create(folder_path),
            operation_name="Create Folder"
        )
        
        return JSONResponse(
            content={
                "message": "Folder created successfully",
                "folder_path": folder_path,
                "response": resp
            },
            status_code=status.HTTP_201_CREATED
        )

    except Exception as e:
        return JSONResponse(
            content={"message": f"Failed to create folder: {str(e)}"},
            status_code=status.HTTP_410_GONE
        )



# Rename a folder path
@router.put("/path", response_class=JSONResponse, tags=["Folder"], summary="Rename a folder path")
def rename_folder_path(old_folder_path: str, new_folder_path: str, user: CurrentUser) -> JSONResponse:
    """Rename a folder path, if it does not exist, it will be created"""
    imap_connection = get_imap_connection_from_user_data(user=user)

    # Rename the folder
    try:
        resp = parse_imap_response(
            imap_response=imap_connection.rename(old_folder_path, new_folder_path),
            operation_name="Rename Folder"
        )

        return JSONResponse(
            content={
                "message": "Folder renamed successfully",
                "old_folder_path": old_folder_path,
                "new_folder_path": new_folder_path,
                "response": resp
            },
            status_code=status.HTTP_200_OK
        )
    except Exception as e:
        return JSONResponse(
            content={"message": f"Failed to rename folder: {str(e)}"},
            status_code=status.HTTP_410_GONE
        )


# Delete a folder path and all its contents
@router.delete("/path", response_class=JSONResponse, tags=["Folder"], summary="Delete a folder path")
def delete_folder_path(folder_path: str, user: CurrentUser) -> JSONResponse:
    """Delete a folder path and all its contents"""
    imap_connection = get_imap_connection_from_user_data(user=user)

    # Delete the folder
    try:
        resp = parse_imap_response(
            imap_response=imap_connection.delete(folder_path),
            operation_name="Delete Folder"
        )

        return JSONResponse(
            content={
                "message": "Folder deleted successfully",
                "folder_path": folder_path,
                "response": resp
            },
            status_code=status.HTTP_200_OK
        )

    except Exception as e:
        return JSONResponse(
            content={"message": f"Failed to delete folder: {str(e)}"},
            status_code=status.HTTP_410_GONE
        )


# Get ACL for a folder path
@router.get("/acl", response_class=JSONResponse, tags=["Folder", "ACL"], summary="Get ACL for a folder path")
def get_folder_acl(folder_path: str, user: CurrentUser) -> JSONResponse:
    """Get ACL for a folder path"""
    imap_connection = get_imap_connection_from_user_data(user=user)

    # Get the ACL
    try:
        acl_data = parse_imap_response(
            imap_response=imap_connection.getacl(folder_path),
            operation_name="Get ACL"
        )

        return JSONResponse(
            content={
                "message": "ACL fetched successfully",
                "folder_path": folder_path,
                "acl": parse_acl_response(folder_name=folder_path, acl_entry=acl_data)
            },
            status_code=status.HTTP_200_OK
        )

    except Exception as e:
        return JSONResponse(
            content={"message": f"Failed to get ACL: {str(e)}"},
            status_code=status.HTTP_410_GONE
        )


# List Own Rights for a folder path
@router.get("/acl/own", response_class=JSONResponse, tags=["Folder", "ACL"], summary="List only own rights")
def list_own_rights(folder_path: str, user: CurrentUser) -> JSONResponse:
    """List only own rights for a folder path"""
    imap_connection = get_imap_connection_from_user_data(user=user)

    # Get the ACL
    try:
        imap_resp = parse_imap_response(
            imap_response=imap_connection.myrights(mailbox=folder_path),
            operation_name="Get My Own Rights"
        )

        return JSONResponse(
            content={
                "message": "Own rights fetched successfully",
                "folder_path": folder_path,
                "acl": imap_resp.replace(f"{folder_path}", "").strip()
            },
            status_code=status.HTTP_200_OK
        )

    except Exception as e:
        return JSONResponse(
            content={"message": f"Failed to get ACL: {str(e)}"},
            status_code=status.HTTP_410_GONE
        )


# Set New ACL for a folder path
@router.post("/acl", response_class=JSONResponse, tags=["Folder", "ACL"], summary="Set new ACL for a folder path")
def set_new_acl(data: SetAclForm, user: CurrentUser) -> JSONResponse:
    """Set new ACL for a folder path"""
    imap_connection = get_imap_connection_from_user_data(user=user)

    # Set the ACL
    try:
        imap_resp = parse_imap_response(
            imap_response=imap_connection.setacl(mailbox=data.folder_path, who=data.user, what=data.permissions),
            operation_name="Set ACL"
        )

        return JSONResponse(
            content={
                "message": "ACL set successfully and updated",
                "folder_path": data.folder_path,
                "acl": imap_resp
            },
            status_code=status.HTTP_200_OK
        )

    except Exception as e:
        return JSONResponse(
            content={"message": f"Failed to set ACL: {str(e)}"},
            status_code=status.HTTP_410_GONE
        )


# Delete ACL for a folder path
@router.delete("/acl", response_class=JSONResponse, tags=["Folder", "ACL"], summary="Delete ACL for a folder path")
def delete_acl(folder_path: str, intended_user: str, user: CurrentUser) -> JSONResponse:
    """Delete ACL for a folder path"""
    imap_connection = get_imap_connection_from_user_data(user=user)

    # Delete the ACL
    try:
        imap_resp = parse_imap_response(
            imap_response=imap_connection.deleteacl(mailbox=folder_path, who=intended_user),
            operation_name="Delete ACL"
        )

        return JSONResponse(
            content={
                "message": "ACL deleted successfully",
                "folder_path": folder_path,
                "intended_user": intended_user,
                "response": imap_resp
            },
            status_code=status.HTTP_200_OK
        )

    except Exception as e:
        return JSONResponse(
            content={"message": f"Failed to delete ACL: {str(e)}"},
            status_code=status.HTTP_410_GONE
        )


# Get User quota for a folder path or root
@router.get("/quota", response_class=JSONResponse, tags=["Folder", "User"], summary="Get User quota for a folder path or root")
def get_user_quota(user: CurrentUser, folder_path: str = None) -> JSONResponse:
    """Get User quota for a folder path or root"""
    imap_connection = get_imap_connection_from_user_data(user=user)

    # Get the quota
    try:
        if folder_path:
            typ, (quota_roots, quota_lines) = imap_connection.getquotaroot(folder_path)

            # (no quota set, or its quota backend failed), imaplib then gives [None]
            folder_quota = next((line.decode() for line in quota_lines if isinstance(line, bytes) and b"STORAGE" in line.upper()), None)
            if typ != "OK" or folder_quota is None:
                logging.warning(f"No storage quota from IMAP server for {user['user_email']} folder {folder_path}: {typ} roots={quota_roots} quota={quota_lines}")
                return JSONResponse(
                    content={"message": "Quota is not available from the mail server right now"},
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE
                )
            quota = parse_quota_response(folder_quota)
        else:
            # TODO: Fix it
            return JSONResponse(
                content={"message": "Some issue, not yet implemented"},
                status_code=status.HTTP_501_NOT_IMPLEMENTED
            )
            # root_quota = imap_connection.getquota('"User quota"')[1][0].decode()
            # quota = parse_quota_response(root_quota)
        return JSONResponse(
            content={
                "message": "Quota fetched successfully",
                "folder_path": folder_path if folder_path else "root",
                "quota": quota
            },
            status_code=status.HTTP_200_OK
        )

    except Exception as e:
        return JSONResponse(
            content={"message": f"Failed to get quota: {str(e)}"},
            status_code=status.HTTP_410_GONE
        )


# Get the UID Validity for a folder path
@router.get("/uid-validity", response_class=JSONResponse, tags=["Folder"], summary="Get the UID Validity for a folder path")
def get_uid_validity(folder_path: str, user: CurrentUser) -> JSONResponse:
    """Get the UID Validity for a folder path"""
    imap_connection = get_imap_connection_from_user_data(user=user)

    uid_status, uid_data = imap_connection.status(f'"{folder_path}"', "(UIDNEXT UIDVALIDITY MESSAGES)")
    if uid_status == "OK":
        uid_string_data = uid_data[0].decode("utf-8") if len(uid_data) > 0 and isinstance(uid_data[0], bytes) else ""
        # Extract key-value pairs inside parentheses
        pairs = dict(re.findall(r'(\w+)\s+(\d+)', uid_string_data))
        uid_data = {k: int(v) for k, v in pairs.items()}
    else:
        return JSONResponse(
            content={"message": "Failed to get UID validity"},
            status_code=status.HTTP_204_NO_CONTENT
        )

    return JSONResponse(
        content={
            "message": "UID Validity fetched successfully",
            "folder_path": folder_path,
            "data": uid_data
        },
        status_code=status.HTTP_200_OK
    )


# Mark all emails in a folder as read
@router.put("/mark-read", response_class=JSONResponse, tags=["Folder"], summary="Mark all emails in a folder as read")
def mark_whole_folder_as_read(folder_path: str, user: CurrentUser) -> JSONResponse:
    """Mark all unread emails in a folder as read (one IMAP command, works for any folder size)"""
    imap_connection = get_imap_connection_from_user_data(user=user)

    try:
        marked_count = mark_folder_as_read(connection=imap_connection, folder=folder_path)
        return JSONResponse(
            content={
                "message": "All emails marked as read" if marked_count else "No unread emails in the folder",
                "folder_path": folder_path,
                "marked_count": marked_count
            },
            status_code=status.HTTP_200_OK
        )

    except All_Exceptions:
        raise

    except Exception as e:
        return JSONResponse(
            content={"message": f"Failed to mark emails as read: {str(e)}"},
            status_code=status.HTTP_424_FAILED_DEPENDENCY
        )


# Empty a Trash or Spam folder
@router.delete("/empty", response_class=JSONResponse, tags=["Folder"], summary="Permanently delete all emails in a Trash or Spam folder")
def empty_trash_or_spam_folder(folder_path: str, user: CurrentUser) -> JSONResponse:
    """
    Permanently delete all emails in a Trash or Spam/Junk folder.
    Only allowed for Trash / Spam folders (by the server's special-use flag or the folder name), to protect other folders.
    """
    imap_connection = get_imap_connection_from_user_data(user=user)

    try:
        is_allowed = is_trash_or_junk_folder(connection=imap_connection, folder=folder_path)
        if is_allowed is None:
            raise All_Exceptions(message=f"Folder not found: {folder_path}", status_code=status.HTTP_404_NOT_FOUND)
        if not is_allowed:
            raise All_Exceptions(message="Only the Trash and Spam folders can be emptied", status_code=status.HTTP_400_BAD_REQUEST)

        deleted_count = empty_folder(connection=imap_connection, folder=folder_path)
        return JSONResponse(
            content={
                "message": "Folder emptied" if deleted_count else "The folder is already empty",
                "folder_path": folder_path,
                "deleted_count": deleted_count
            },
            status_code=status.HTTP_200_OK
        )

    except All_Exceptions:
        raise

    except Exception as e:
        return JSONResponse(
            content={"message": f"Failed to empty the folder: {str(e)}"},
            status_code=status.HTTP_424_FAILED_DEPENDENCY
        )
