"""
This module provides E-Mail Box related API endpoints
"""

from src.utils.base.libraries import (
    PlainTextResponse,
    JSONResponse,
    UploadFile,
    APIRouter,
    status,
    Form,
    File
)
from src.database import get_all_templates, PostgresDep, create_template, delete_template, edit_template, get_template
from src.main import CurrentUser, send_mail_rabbit, draft_mail_rabbit
from src.utils.models import SendMailForm, SearchMail, EmailTemplate
from src.imap import (
    get_imap_connection_from_user_data,
    get_email_details_by_message_id,
    delete_emails_permanently,
    mark_emails_as_unflagged,
    mark_emails_as_flagged,
    mark_emails_as_unseen,
    copy_multiple_emails,
    move_multiple_emails,
    mark_emails_as_read,
    parse_imap_response,
    mark_emails_as_read,
    get_email_details,
    get_raw_email,
    search_emails
)

# Router
router = APIRouter()


# Get all the emails in a folder
@router.get("/fetch/{batch_size}/{page_number}", response_class=JSONResponse, tags=["E-Mail"], summary="Fetch all emails from a given folder path")
def fetch_all_emails(folder_path: str, full_headers: bool, batch_size: int, page_number: int, user: CurrentUser) -> JSONResponse:
    """Fetch all emails from a given folder path"""
    imap_connection = get_imap_connection_from_user_data(user=user)

    # Fetch the emails
    try:
        total_count = int(parse_imap_response(
            imap_response=imap_connection.select(mailbox=folder_path, readonly=True),
            operation_name="Fetch Emails"
        ))
        if total_count == 0:
            return JSONResponse(
                content={
                    "message": "No emails found in the specified folder",
                    "folder_path": folder_path,
                    "total_count": total_count,
                    "total_pages": 0,
                    "batch_size": batch_size,
                    "emails": []
                },
                status_code=status.HTTP_200_OK
            )

        total_batches = total_count // batch_size + (total_count % batch_size > 0)
        if page_number > total_batches:
            return JSONResponse(
                content={"message": "Page number exceeds total pages"},
                status_code=status.HTTP_400_BAD_REQUEST
            )
        if page_number < 1:
            return JSONResponse(
                content={"message": "Page number must be greater than 0"},
                status_code=status.HTTP_400_BAD_REQUEST
            )

        # TODO: Sort by Arrival Date - Currently it is sorted by UID

        # Calculate the start and end index for the batch in reverse order
        start_index = total_count - (page_number * batch_size) + 1
        end_index = total_count - ((page_number - 1) * batch_size)
        start_index = max(start_index, 1)  # Ensure it doesn't go below 1

        email_details = get_email_details(
            connection=imap_connection,
            id_range=f"{start_index}:{end_index}",
            folder_path=folder_path,
            full_headers=full_headers
        )

        return JSONResponse(
            content={
                "message": "Emails fetched successfully",
                "folder_path": folder_path,
                "total_count": total_count,
                "total_pages": total_batches,
                "batch_size": batch_size,
                "emails": email_details
            },
            status_code=status.HTTP_200_OK
        )

    except Exception as e:
        return JSONResponse(
            content={"message": f"Failed to fetch emails: {str(e)}"},
            status_code=status.HTTP_424_FAILED_DEPENDENCY
        )


# Get Raw Email
@router.get("/raw/{email_id}", response_class=PlainTextResponse, tags=["E-Mail"], summary="Get raw email by ID")
def get_raw_email_as_plain_text(email_id: str, folder_path: str, mark_as_read: bool, user: CurrentUser) -> PlainTextResponse:
    """Get raw email by ID"""
    imap_connection = get_imap_connection_from_user_data(user=user)

    # Fetch the raw email
    try:
        if raw_bytes := get_raw_email(connection=imap_connection, email_id=email_id, folder=folder_path, read_only=not mark_as_read):
            return PlainTextResponse(
                content=raw_bytes,
                status_code=status.HTTP_200_OK,
                media_type="message/rfc822",
                headers={
                    "Content-Disposition": f"attachment; filename={email_id}.eml",
                    "Content-Type": "message/rfc822"
                }
            )
        else:
            return PlainTextResponse(
                content="Failed to fetch raw email",
                status_code=status.HTTP_424_FAILED_DEPENDENCY
            )

    except Exception as e:
        return PlainTextResponse(
            content=f"Failed to fetch raw email: {str(e)}",
            status_code=status.HTTP_424_FAILED_DEPENDENCY
        )


# Get emails given in a list
@router.get("/fetch-all", response_class=JSONResponse, tags=["E-Mail"], summary="Fetch emails from a folder based on IDs")
def fetch_emails_based_on_ids(folder_path: str, full_headers: bool, email_ids: list[int], user: CurrentUser) -> JSONResponse:
    """Fetch emails from a folder based on IDs"""
    imap_connection = get_imap_connection_from_user_data(user=user)

    # Fetch the emails
    try:
        email_ids = sorted(email_ids, reverse=True)

        return JSONResponse(
            content={
                "message": "Emails fetched successfully",
                "folder_path": folder_path,
                "emails": get_email_details(
                    connection=imap_connection,
                    id_range=",".join(email_ids),
                    folder_path=folder_path,
                    full_headers=full_headers
                )
            },
            status_code=status.HTTP_200_OK
        )

    except Exception as e:
        return JSONResponse(
            content={"message": f"Failed to fetch emails: {str(e)}"},
            status_code=status.HTTP_424_FAILED_DEPENDENCY
        )


# Send Email - Send an email using RabbitMQ (TODO: Deprecate this endpoint in future and delete it)
@router.post("/send", response_class=JSONResponse, tags=["E-Mail"], summary="Send an email")
def send_email(user: CurrentUser, data: str = Form(...), attachments: list[UploadFile] = File(default=[]), in_line_attachments: list[UploadFile] = File(default=[])) -> JSONResponse:
    """Send an email"""
    email_data = SendMailForm.model_validate_json(data)

    send_mail_rabbit(email_data=email_data, user_data=user, attachments=attachments, in_line_attachments=in_line_attachments)
    return JSONResponse(
        content={"message": "Email sent successfully"},
        status_code=status.HTTP_200_OK
    )


# Create a email based draft also set it as draft (conn.store(num, '+FLAGS', '\\Draft'))
@router.post("/draft", response_class=JSONResponse, tags=["E-Mail"], summary="Create and save a draft email")
def create_draft_email(user: CurrentUser, data: str = Form(...), attachments: list[UploadFile] = File(default=[]), in_line_attachments: list[UploadFile] = File(default=[])) -> JSONResponse:
    """Create and save a draft email"""
    email_data = SendMailForm.model_validate_json(data)

    draft_mail_rabbit(email_data=email_data, user_data=user, attachments=attachments, in_line_attachments=in_line_attachments)
    return JSONResponse(
        content={"message": "Draft email created successfully"},
        status_code=status.HTTP_201_CREATED
    )


# Copy single or multiple emails from one folder to another
@router.patch("/copy", response_class=JSONResponse, tags=["E-Mail", "Folder"], summary="Copy emails from one folder to another")
def copy_emails(folder_path: str, email_ids: list[int], source_folder: str, dest_folder: str, user: CurrentUser) -> JSONResponse:
    """Copy emails from one folder to another"""
    imap_connection = get_imap_connection_from_user_data(user=user)
    email_ids = sorted(list(set(email_ids)), reverse=True)

    # Copy the emails
    try:
        resp = copy_multiple_emails(
            connection=imap_connection,
            email_ids=email_ids,
            source_folder=source_folder,
            dest_folder=dest_folder
        )

        return JSONResponse(
            content={
                "message": "Emails copied successfully",
                "folder_path": folder_path,
                "emails": email_ids,
                "responses": resp
            },
            status_code=status.HTTP_200_OK
        )

    except Exception as e:
        return JSONResponse(
            content={"message": f"Failed to copy emails: {str(e)}"},
            status_code=status.HTTP_412_PRECONDITION_FAILED
        )


# Move single or multiple emails from one folder to another
@router.put("/move", response_class=JSONResponse, tags=["E-Mail", "Folder"], summary="Move emails from one folder to another")
def move_emails(folder_path: str, email_ids: list[int], source_folder: str, dest_folder: str, user: CurrentUser) -> JSONResponse:
    """Move emails from one folder to another"""
    imap_connection = get_imap_connection_from_user_data(user=user)
    email_ids = sorted(list(set(email_ids)), reverse=True)

    # Move the emails
    try:
        resp = move_multiple_emails(
            connection=imap_connection,
            email_ids=email_ids,
            source_folder=source_folder,
            dest_folder=dest_folder
        )

        expunge_status = resp.pop("expunge", "Expunge not performed")

        return JSONResponse(
            content={
                "message": "Emails moved successfully",
                "folder_path": folder_path,
                "emails": email_ids,
                "expunge_status": expunge_status,
                "responses": resp
            },
            status_code=status.HTTP_200_OK
        )

    except Exception as e:
        return JSONResponse(
            content={"message": f"Failed to move emails: {str(e)}"},
            status_code=status.HTTP_412_PRECONDITION_FAILED
        )


# Mark selected emails as read
@router.put("/mark/read", response_class=JSONResponse, tags=["E-Mail"], summary="Mark selected emails as read")
def mark_all_emails_as_read(folder_path: str, email_ids: list[int], user: CurrentUser) -> JSONResponse:
    """Mark all emails in a folder as read"""
    imap_connection = get_imap_connection_from_user_data(user=user)

    # Mark all emails as read
    try:
        return JSONResponse(
            content={
                "message": "All emails marked as read successfully",
                "folder_path": folder_path,
                "results": mark_emails_as_read(
                    connection=imap_connection,
                    email_ids=email_ids,
                    folder=folder_path
                )
            },
            status_code=status.HTTP_200_OK
        )

    except Exception as e:
        return JSONResponse(
            content={"message": f"Failed to mark emails as read: {str(e)}"},
            status_code=status.HTTP_410_GONE
        )


# Mark selected emails as unread
@router.patch("/mark/unseen", response_class=JSONResponse, tags=["E-Mail"], summary="Mark selected emails as unread")
def mark_all_emails_as_unread(folder_path: str, email_ids: list[int], user: CurrentUser) -> JSONResponse:
    """Mark all emails in a folder as unread"""
    imap_connection = get_imap_connection_from_user_data(user=user)

    # Mark all emails as unread
    try:
        return JSONResponse(
            content={
                "message": "All emails marked as unseen successfully",
                "folder_path": folder_path,
                "results": mark_emails_as_unseen(
                    connection=imap_connection,
                    email_ids=email_ids,
                    folder=folder_path
                )
            },
            status_code=status.HTTP_200_OK
        )

    except Exception as e:
        return JSONResponse(
            content={"message": f"Failed to mark emails as unseen: {str(e)}"},
            status_code=status.HTTP_410_GONE
        )


# Mark selected emails as flagged
@router.put("/mark/flagged", response_class=JSONResponse, tags=["E-Mail"], summary="Mark selected emails as flagged")
def mark_all_emails_as_flagged(folder_path: str, email_ids: list[int], user: CurrentUser) -> JSONResponse:
    """Mark all emails in a folder as flagged"""
    imap_connection = get_imap_connection_from_user_data(user=user)

    # Mark all emails as flagged
    try:
        return JSONResponse(
            content={
                "message": "All emails marked as flagged successfully",
                "folder_path": folder_path,
                "results": mark_emails_as_flagged(
                    connection=imap_connection,
                    email_ids=email_ids,
                    folder=folder_path
                )
            },
            status_code=status.HTTP_200_OK
        )

    except Exception as e:
        return JSONResponse(
            content={"message": f"Failed to mark emails as flagged: {str(e)}"},
            status_code=status.HTTP_410_GONE
        )
    

# Mark selected emails as unflagged
@router.patch("/mark/unflagged", response_class=JSONResponse, tags=["E-Mail"], summary="Mark selected emails as unflagged")
def mark_all_emails_as_unflagged(folder_path: str, email_ids: list[int], user: CurrentUser) -> JSONResponse:
    """Mark all emails in a folder as unflagged"""
    imap_connection = get_imap_connection_from_user_data(user=user)

    # Mark all emails as unflagged
    try:
        return JSONResponse(
            content={
                "message": "All emails marked as unflagged successfully",
                "folder_path": folder_path,
                "results": mark_emails_as_unflagged(
                    connection=imap_connection,
                    email_ids=email_ids,
                    folder=folder_path
                )
            },
            status_code=status.HTTP_200_OK
        )

    except Exception as e:
        return JSONResponse(
            content={"message": f"Failed to mark emails as unflagged: {str(e)}"},
            status_code=status.HTTP_410_GONE
        )


# Permanently delete selected emails
@router.delete("/permanently", response_class=JSONResponse, tags=["E-Mail", "Folder"], summary="Permanently delete selected emails")
def permanently_delete_emails(folder_path: str, email_ids: list[int], user: CurrentUser) -> JSONResponse:
    """Permanently delete selected emails"""
    imap_connection = get_imap_connection_from_user_data(user=user)
    email_ids = sorted(list(set(email_ids)), reverse=True)

    # Permanently delete the emails
    try:
        resp = delete_emails_permanently(
            connection=imap_connection,
            email_ids=email_ids,
            folder=folder_path
        )

        expunge_status = resp.pop("expunge", "Expunge not performed")

        return JSONResponse(
            content={
                "message": "Emails deleted successfully",
                "expunge_status": expunge_status,
                "folder_path": folder_path,
                "emails": email_ids,
                "responses": resp
            },
            status_code=status.HTTP_200_OK
        )

    except Exception as e:
        return JSONResponse(
            content={"message": f"Failed to delete emails: {str(e)}"},
            status_code=status.HTTP_412_PRECONDITION_FAILED
        )


# Search the emails
@router.post("/search/all", response_class=JSONResponse, tags=["E-Mail"], summary="Search emails")
def search_all_emails(search_criteria: SearchMail, user: CurrentUser) -> JSONResponse:
    """Search emails based on the given criteria"""
    imap_connection = get_imap_connection_from_user_data(user=user)

    try:
        return JSONResponse(
            content={
                "message": "Search emails fetched successfully",
                "data" : search_emails(
                    search_criteria=search_criteria,
                    connection=imap_connection
                )
            },
            status_code=status.HTTP_200_OK
        )

    except Exception as e:
        return JSONResponse(
            content={"message": f"Failed to fetch emails: {str(e)}"},
            status_code=status.HTTP_424_FAILED_DEPENDENCY
        )


# Email Templates - Get all
@router.get("/templates", response_class=JSONResponse, tags=["Template"], summary="Fetch all email templates")
async def fetch_all_email_templates(is_public: bool, user: CurrentUser, PgDB: PostgresDep) -> JSONResponse:
    """
    Fetch all email templates
    :param is_public: Whether to fetch public templates or private templates
    """
    try:
        templates = await get_all_templates(
            db_session=PgDB,
            is_public=is_public,
            user_email=user["user_email"]
        )
        return JSONResponse(
            content={
                "message": "Email templates fetched successfully",
                "data": templates
            },
            status_code=status.HTTP_200_OK
        )

    except Exception as e:
        return JSONResponse(
            content={"message": f"Failed to fetch email templates: {str(e)}"},
            status_code=status.HTTP_424_FAILED_DEPENDENCY
        )


# Email Templates - Get One
@router.get("/template/{template_id}", response_class=JSONResponse, tags=["Template"], summary="Fetch a specific email template")
async def fetch_email_template(template_id: int, user: CurrentUser, PgDB: PostgresDep) -> JSONResponse:
    """
    Fetch a specific email template
    :param template_id: The ID of the email template to fetch
    """
    try:
        template = await get_template(
            db_session=PgDB,
            template_id=template_id,
            user_email=user["user_email"]
        )
        return JSONResponse(
            content={
                "message": "Email template fetched successfully",
                "data": template
            },
            status_code=status.HTTP_200_OK
        )

    except Exception as e:
        return JSONResponse(
            content={"message": f"Failed to fetch email template: {str(e)}"},
            status_code=status.HTTP_424_FAILED_DEPENDENCY
        )


# Create Email Template
@router.post("/template", response_class=JSONResponse, tags=["Template"], summary="Create a new email template")
async def create_email_template(template_data: EmailTemplate, user: CurrentUser, PgDB: PostgresDep) -> JSONResponse:
    """
    Create a new email template
    """
    try:
        await create_template(
            db_session=PgDB,
            user_email=user["user_email"],
            is_public=template_data.is_public,
            data={
                "name": template_data.name,
                "subject": template_data.subject,
                "body": template_data.body,
                "meta_data": template_data.meta_data
            }
        )
        return JSONResponse(
            content={"message": "Email template created successfully"},
            status_code=status.HTTP_201_CREATED
        )

    except Exception as e:
        return JSONResponse(
            content={"message": f"Failed to create email template: {str(e)}"},
            status_code=status.HTTP_424_FAILED_DEPENDENCY
        )


# Delete Email Template
@router.delete("/template/{template_id}", response_class=JSONResponse, tags=["Template"], summary="Delete an email template")
async def delete_email_template(template_id: int, user: CurrentUser, PgDB: PostgresDep) -> JSONResponse:
    """
    Delete an email template
    """
    try:
        await delete_template(
            db_session=PgDB,
            user_email=user["user_email"],
            template_id=template_id
        )
        return JSONResponse(
            content={"message": "Email template deleted successfully"},
            status_code=status.HTTP_204_NO_CONTENT
        )

    except Exception as e:
        return JSONResponse(
            content={"message": f"Failed to delete email template: {str(e)}"},
            status_code=status.HTTP_424_FAILED_DEPENDENCY
        )


# Edit Email Template
@router.patch("/template/{template_id}", response_class=JSONResponse, tags=["Template"], summary="Edit an email template")
async def edit_email_template(template_id: int, template_data: EmailTemplate, user: CurrentUser, PgDB: PostgresDep) -> JSONResponse:
    """
    Edit an email template
    """
    try:
        await edit_template(
            db_session=PgDB,
            user_email=user["user_email"],
            template_id=template_id,
            is_public=template_data.is_public,
            data={
                "name": template_data.name,
                "subject": template_data.subject,
                "body": template_data.body,
                "meta_data": template_data.meta_data
            }
        )
        return JSONResponse(
            content={"message": "Email template updated successfully"},
            status_code=status.HTTP_200_OK
        )

    except Exception as e:
        return JSONResponse(
            content={"message": f"Failed to update email template: {str(e)}"},
            status_code=status.HTTP_424_FAILED_DEPENDENCY
        )


# Get email details by Message-ID's
@router.post("/fetch-by-message-ids", response_class=JSONResponse, tags=["E-Mail"], summary="Fetch email details by Message-ID's")
def fetch_email_details_by_message_ids(folder_path: str, message_ids: list[str], user: CurrentUser) -> JSONResponse:
    """
    Fetch email details by Message-ID's
    """
    imap_connection = get_imap_connection_from_user_data(user=user)

    try:
        findings = get_email_details_by_message_id(
            imap_connection=imap_connection,
            message_ids=message_ids,
            folder=folder_path
        )
        return JSONResponse(
            content={
                "message": "Email details fetched successfully",
                "folder_path": folder_path,
                "emails": findings
            },
            status_code=status.HTTP_200_OK
        )

    except Exception as e:
        return JSONResponse(
            content={"message": f"Failed to fetch email details: {str(e)}"},
            status_code=status.HTTP_424_FAILED_DEPENDENCY
        )


# TODO: Report spam mail

# TODO: Write an E-Mail (AI)
