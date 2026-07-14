"""
This module provides Contacts related API endpoints
Endpoints and their purposes:

    | Method | Endpoint               | Purpose              |
    |--------|------------------------|----------------------|
    | GET    | `/contacts/item/{id}`  | Get contact          |
    | PUT    | `/contacts/item/{id}`  | Update contact       |
    | DELETE | `/contacts/item/{id}`  | Delete contact       |
    | POST   | `/contacts/bulk`       | Bulk add             |
    | DELETE | `/contacts/bulk`       | Bulk delete          |
    | GET    | `/contacts/list`       | Get all contacts     |
    | POST   | `/contacts/create`     | Create new contact   |
"""

from src.utils.base.libraries import (
    JSONResponse,
    APIRouter,
    logging,
    status
)
from src.database import PostgresDep, AdminPostgresDep, create_contact, edit_contact, delete_contact, get_one_contact, get_contacts, contact_exists, simple_email_search, create_bulk_contacts, simple_email_search_v2
from src.utils.models import Contact
from src.main import CurrentUser


# Router
router = APIRouter()


# Create Single Contact
@router.post("/create", response_class=JSONResponse, tags=["Contacts"], summary="Create a single new contact")
async def create_new_contact(data: Contact, user: CurrentUser, PgDB: PostgresDep) -> JSONResponse:
    """Create a single new contact
    :param data: Contact data
    :param user: Current user
    :param PgDB: Postgres database connection
    :return: JSON response with the status of the operation
    """
    try:
        await create_contact(
            db_session=PgDB,
            user_email=user["user_email"],
            contact_email=data.email,
            contact_name=data.name,
            contact_phone=data.phone,
            contact_notes=data.notes
        )

        return JSONResponse(
            content={"message": "Contact created successfully"},
            status_code=status.HTTP_201_CREATED
        )
    except Exception as e:
        logging.error(f"Failed to create contact: {str(e)}", exc_info=True)
        return JSONResponse(
            content={"message": f"Failed to create contact: {str(e)}"},
            status_code=status.HTTP_424_FAILED_DEPENDENCY
        )


# Edit Single Contact
@router.put("/item/{contact_id}", response_class=JSONResponse, tags=["Contacts"], summary="Edit a single contact")
async def edit_single_contact(contact_id: int, data: Contact, user: CurrentUser, PgDB: PostgresDep) -> JSONResponse:
    """Create a single new contact
    :param contact_id: Contact ID
    :param data: Contact data
    :param user: Current user
    :param PgDB: Postgres database connection
    :return: JSON response with the status of the operation
    """
    try:
        await edit_contact(
            db_session=PgDB,
            user_email=user["user_email"],
            contact_id=contact_id,
            contact_email=data.email,
            contact_name=data.name,
            contact_phone=data.phone,
            contact_notes=data.notes
        )

        return JSONResponse(
            content={"message": "Contact updated successfully"},
            status_code=status.HTTP_200_OK
        )

    except Exception as e:
        logging.error(f"Failed to update contact: {str(e)}", exc_info=True)
        return JSONResponse(
            content={"message": f"Failed to update contact: {str(e)}"},
            status_code=status.HTTP_424_FAILED_DEPENDENCY
        )


# Delete Single Contact
@router.delete("/item/{contact_id}", response_class=JSONResponse, tags=["Contacts"], summary="Delete a single contact")
async def delete_single_contact(contact_id: int, user: CurrentUser, PgDB: PostgresDep) -> JSONResponse:
    """Delete a single contact
    :param contact_id: Contact ID
    :param user: Current user
    :param PgDB: Postgres database connection
    :return: JSON response with the status of the operation
    """
    try:
        await delete_contact(
            db_session=PgDB,
            user_email=user["user_email"],
            contact_id=contact_id
        )

        return JSONResponse(
            content={"message": "Contact deleted successfully"},
            status_code=status.HTTP_200_OK
        )
    except Exception as e:
        logging.error(f"Failed to delete contact: {str(e)}", exc_info=True)
        return JSONResponse(
            content={"message": f"Failed to delete contact: {str(e)}"},
            status_code=status.HTTP_424_FAILED_DEPENDENCY
        )


# Bulk Add Contacts
@router.post("/bulk", response_class=JSONResponse, tags=["Contacts"], summary="Bulk add contacts")
async def bulk_add_contacts(data: list[Contact], user: CurrentUser, PgDB: PostgresDep) -> JSONResponse:
    """Bulk add contacts
    :param data: List of contact data
    :param user: Current user
    :param PgDB: Postgres database connection
    :return: JSON response with the status of the operation
    """
    try:
        await create_bulk_contacts(
            db_session=PgDB,
            user_email=user["user_email"],
            contacts=[{
                "contact_email": contact.email,
                "contact_name": contact.name,
                "contact_phone": contact.phone,
                "contact_notes": contact.notes
            } for contact in data]
        )

        return JSONResponse(
            content={"message": "Contacts created successfully"},
            status_code=status.HTTP_201_CREATED
        )

    except Exception as e:
        logging.error(f"Failed to create contacts: {str(e)}", exc_info=True)
        return JSONResponse(
            content={"message": f"Failed to create contacts: {str(e)}"},
            status_code=status.HTTP_424_FAILED_DEPENDENCY
        )


# Bulk Delete Contacts
@router.delete("/bulk", response_class=JSONResponse, tags=["Contacts"], summary="Bulk delete contacts")
async def bulk_delete_contacts(data: list[int], user: CurrentUser, PgDB: PostgresDep) -> JSONResponse:
    """Bulk delete contacts
    :param data: List of contact IDs
    :param user: Current user
    :param PgDB: Postgres database connection
    :return: JSON response with the status of the operation
    """
    try:
        for contact_id in data:
            await delete_contact(
                db_session=PgDB,
                user_email=user["user_email"],
                contact_id=contact_id
            )

        return JSONResponse(
            content={"message": "Contacts deleted successfully"},
            status_code=status.HTTP_200_OK
        )
    except Exception as e:
        logging.error(f"Failed to delete contacts: {str(e)}", exc_info=True)
        return JSONResponse(
            content={"message": f"Failed to delete contacts: {str(e)}"},
            status_code=status.HTTP_424_FAILED_DEPENDENCY
        )


# Get Single Contact
@router.get("/item/{contact_id}", response_class=JSONResponse, tags=["Contacts"], summary="Get a single contact")
async def get_single_contact(contact_id: int, user: CurrentUser, PgDB: PostgresDep) -> JSONResponse:
    """Get a single contact
    :param contact_id: Contact ID
    :param user: Current user
    :param PgDB: Postgres database connection
    :return: JSON response with the contact data
    """
    try:
        contact = await get_one_contact(
            db_session=PgDB,
            contact_id=contact_id,
            user_email=user["user_email"]
        )

        return JSONResponse(
            content={"message": "Contact retrieved successfully", "contact": contact},
            status_code=status.HTTP_200_OK
        )
    except Exception as e:
        logging.error(f"Failed to get contact: {str(e)}", exc_info=True)
        return JSONResponse(
            content={"message": f"Failed to get contact: {str(e)}"},
            status_code=status.HTTP_424_FAILED_DEPENDENCY
        )


# Get Paginated Contacts
@router.get("/list", response_class=JSONResponse, tags=["Contacts"], summary="Get all contacts")
async def get_all_contacts(page: int, page_size: int, user: CurrentUser, PgDB: PostgresDep) -> JSONResponse:
    """Get all contacts
    :param user: Current user
    :param PgDB: Postgres database connection
    :return: JSON response with the list of contacts
    """
    contacts = await get_contacts(
        db_session=PgDB,
        user_email=user["user_email"],
        current_page=page,
        page_size=page_size
    )

    return JSONResponse(
        content=contacts,
        status_code=status.HTTP_200_OK
    )


# Check if Contact Exists
@router.get("/exists/{email}", response_class=JSONResponse, tags=["Contacts"], summary="Check if contact exists")
async def check_contact_exists(email: str, user: CurrentUser, PgDB: PostgresDep) -> JSONResponse:
    """Check if a contact exists
    :param email: Email of the contact
    :param user: Current user
    :param PgDB: Postgres database connection
    :return: JSON response with the status of the operation
    """
    try:
        exists = await contact_exists(
            db_session=PgDB,
            user_email=user["user_email"],
            contact_email=email
        )

        return JSONResponse(
            content={"message": "Contact exists" if exists else "Contact does not exist"},
            status_code=status.HTTP_200_OK
        )

    except Exception as e:
        logging.error(f"Failed to check contact existence: {str(e)}", exc_info=True)
        return JSONResponse(
            content={"message": f"Failed to check contact existence: {str(e)}"},
            status_code=status.HTTP_424_FAILED_DEPENDENCY
        )


# Simple Email Search for the drop down effect while typing the email
@router.get("/search", response_class=JSONResponse, tags=["Contacts"], summary="Search for contacts by email")
async def search_contacts(partial_email: str, user: CurrentUser, PgDB: PostgresDep) -> JSONResponse:
    """Search for contacts by email
    :param partial_email: Partial email to search for
    :param user: Current user
    :param PgDB: Postgres database connection
    :return: JSON response with the list of matching contacts
    """
    try:
        contacts = await simple_email_search(
            db_session=PgDB,
            user_email=user["user_email"],
            partial_email_string=partial_email
        )

        return JSONResponse(
            content={"message": "Contacts retrieved successfully", "contacts": contacts},
            status_code=status.HTTP_200_OK
        )

    except Exception as e:
        logging.error(f"Failed to search contacts: {str(e)}", exc_info=True)
        return JSONResponse(
            content={"message": f"Failed to search contacts: {str(e)}"},
            status_code=status.HTTP_424_FAILED_DEPENDENCY
        )


# Simple Email Search for the drop down effect while typing the email (V2 DB Email Search)
@router.get("/search/v2", response_class=JSONResponse, tags=["Contacts"], summary="Search for contacts by email (V2 DB Email Search)")
async def search_contacts_v2(partial_email: str, user: CurrentUser, AdminPgDB: AdminPostgresDep) -> JSONResponse:
    """Search for contacts by email (V2 DB Email Search)
    :param partial_email: Partial email to search for
    :param user: Current user
    :param AdminPgDB: Admin Postgres database connection
    :return: JSON response with the list of matching contacts
    """
    if not user.get("v2_domain_id"):
        return JSONResponse(
            content={"message": "User is not associated with any domain, cannot perform V2 contact search"},
            status_code=status.HTTP_400_BAD_REQUEST
        )

    try:
        logging.debug(f"Performing V2 contact search for user {user['user_email']} with partial email '{partial_email}' in domain ID {user['v2_domain_id']}")
        contacts = await simple_email_search_v2(
            admin_db_session=AdminPgDB,
            domain_id=user["v2_domain_id"],
            partial_email_string=partial_email
        )

        return JSONResponse(
            content={"message": "V2 Contacts retrieved successfully", "contacts": contacts},
            status_code=status.HTTP_200_OK
        )

    except Exception as e:
        logging.error(f"Failed to search V2 contacts: {str(e)}", exc_info=True)
        return JSONResponse(
            content={"message": f"Failed to search V2 contacts: {str(e)}"},
            status_code=status.HTTP_424_FAILED_DEPENDENCY
        )
