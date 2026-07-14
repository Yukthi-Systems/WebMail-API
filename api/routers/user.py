"""
This module provides User related API endpoints
"""

from src.utils.base.libraries import (
    JSONResponse,
    APIRouter,
    Request,
    status,
    orjson
)
from src.database import (
    AdminPostgresDep,
    MemcachedDep,
    PostgresDep,
    get_v2_ids,
    get_domain_details,
    create_user_session_in_cache,
    get_user_settings,
    replace_user_settings,
    create_user_if_not_exists,
    admin_create_new_domain,
    validate_origin_ip_blocked,
    admin_edit_domain,
    admin_delete_domain,
    admin_get_all_domains,
    admin_get_domain_info
)
from src.main import validate_smtp_details, validate_imap_details, CurrentUser, validate_recaptcha
from src.utils.base.constants import MAX_AGE_OF_CACHE, API_KEY, API_COOKIE_DOMAIN
from src.utils.models import All_Exceptions, AuthRequest


# Router
router = APIRouter()


# Login to WebMail - Validate IMAP and SMTP credentials (Create a session)
@router.post("/login", response_class=JSONResponse, tags=["User"], summary="Login to WebMail")
async def user_login_webmail(request: Request, data: AuthRequest, CacheDB: MemcachedDep, PgDB: PostgresDep, AdminPgDB: AdminPostgresDep) -> JSONResponse:
    """
    Login to WebMail - Validate IMAP and SMTP credentials (Create a session)
    """
    if not validate_recaptcha(token=data.recaptcha_token):
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"message": "Recaptcha validation failed - Are you a bot?"}
        )

    # Get IMAP and SMTP details from DB if domain is present
    server_details = await get_domain_details(db_session=PgDB, domain=data.domain)
    if not server_details:
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"message": "Invalid domain, contact admin to register the domain"}
        )
    
    if not server_details["is_active"]:
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"message": "Domain is inactive, contact admin to activate the domain"}
        )

    # Check if the user is V2 User or not (That means the user is our platform user)
    is_v2_user = server_details["is_v2_user"]
    v2_domain_id, v2_mailbox_id = None, None

    if is_v2_user:
        # Check if IP is blocked or not
        ip_validation_result = await validate_origin_ip_blocked(admin_db_session=AdminPgDB, ip_address=request.headers.get('X-Real-IP'), user_email=data.email)
        if not ip_validation_result:    # If it returns False, that means the IP is blocked
            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content={"message": "Access from this IP or Region is blocked, contact admin for more details"}
            )

        # Find the MailBox ID and Domain ID for the user from the DB (For V2 Users)
        v2_mailbox_id, v2_domain_id = await get_v2_ids(admin_db_session=AdminPgDB, user_email=data.email)
        if not v2_domain_id or not v2_mailbox_id:
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"message": "User not found in the system, contact admin to register"}
            )

    # Validate the IMAP and SMTP details
    is_valid_imap = validate_imap_details(
        imap_server=server_details["imap_server"],
        imap_port=server_details["imap_port"],
        imap_user=data.email,
        imap_password=data.password
    )
    is_valid_smtp = validate_smtp_details(
        smtp_server=server_details["smtp_server"],
        smtp_port=server_details["smtp_port"],
        smtp_user=data.email,
        smtp_password=data.password
    )

    if not is_valid_imap:
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"message": "Invalid IMAP credentials"}
        )
    if not is_valid_smtp:
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"message": "Invalid SMTP credentials"}
        )
    
    # Create a session in the cache
    session_id, csrf_token = await create_user_session_in_cache(
        cache_session=CacheDB,
        user_email=data.email,
        raw_password=data.password,
        smtp_server=server_details["smtp_server"],
        smtp_port=server_details["smtp_port"],
        smtp_user=data.email,
        smtp_password=data.password,
        imap_server=server_details["imap_server"],
        imap_port=server_details["imap_port"],
        imap_user=data.email,
        sieve_user=data.email,
        sieve_password=data.password,
        sieve_server=server_details["sieve_server"],
        sieve_port=server_details["sieve_port"],
        imap_password=data.password,
        v2_domain_id=v2_domain_id,
        v2_mailbox_id=v2_mailbox_id
    )

    # Create a new user in DB if not exists
    await create_user_if_not_exists(db_session=PgDB, user_email=data.email, user_domain=data.domain)

    # Create a session as cookie and return the response
    response = JSONResponse(
        status_code=status.HTTP_200_OK,
        content={"message": "All Credentials are valid - Login successful"}
    )

    response.set_cookie(
        key="SESSION_ID",
        value=session_id,
        max_age=MAX_AGE_OF_CACHE,
        httponly=True,
        secure=True,
        samesite="strict",
        domain=API_COOKIE_DOMAIN
    )

    # Set the logged in status in the Cookie (for JS - to read)
    response.set_cookie(
        key="IS_SESSION_VALID",
        value="true",
        max_age=MAX_AGE_OF_CACHE,
        httponly=False,  # IMPORTANT: Let JS read it
        secure=True,
        samesite="strict",
        domain=API_COOKIE_DOMAIN
    )

    # Set the CSRF token in the response header
    response.headers["X-CSRF-Token"] = csrf_token
    response.headers["X-Session-Expiry"] = str(MAX_AGE_OF_CACHE)
    response.headers["X-V2-User"] = str(is_v2_user)
    # Allow Token and Expiry to be read by JS
    response.headers["Access-Control-Expose-Headers"] = "X-CSRF-Token, X-Session-Expiry, X-V2-User"

    return response


# Logout from WebMail - Destroy the session, cookie and close the pool
@router.delete("/logout", response_class=JSONResponse, tags=["User"], summary="Logout from WebMail")
async def user_logout_webmail(request: Request, CacheDB: MemcachedDep) -> JSONResponse:
    """
    Logout from WebMail - Destroy the session, cookie and close the pool
    """
    session_id = request.cookies.get("SESSION_ID")
    if not session_id:
        raise All_Exceptions(message="Session ID not found", status_code=status.HTTP_406_NOT_ACCEPTABLE)
    
    user_data_bytes = await CacheDB.get(session_id.encode("utf-8"))
    if not user_data_bytes:
        raise All_Exceptions(message="Session expired", status_code=status.HTTP_401_UNAUTHORIZED)

    user_details = orjson.loads(user_data_bytes)
    if user_details["csrf_token"] != request.headers.get("X-CSRF-Token"):
        raise All_Exceptions(message="CSRF token mismatch", status_code=status.HTTP_401_UNAUTHORIZED)

    # Destroy the session in the cache
    await CacheDB.delete(key=session_id.encode("utf-8"))

    # Send response to delete the cookie
    response = JSONResponse(
        status_code=status.HTTP_200_OK,
        content={"message": "Logout successful, session destroyed"}
    )

    response.delete_cookie(
        key="SESSION_ID",
        httponly=True,
        secure=True,
        samesite="strict",
        domain=API_COOKIE_DOMAIN
    )
    response.delete_cookie(
        key="IS_SESSION_VALID",
        httponly=False,
        secure=True,
        samesite="strict",
        domain=API_COOKIE_DOMAIN
    )

    return response


# Validate the session
@router.get("/validate", response_class=JSONResponse, tags=["User"], summary="Validate the session ID")
async def user_validate_session(user: CurrentUser) -> JSONResponse:
    """
    Validate the session ID
    """
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={"message": "Session is valid", "user_email": user["user_email"]}
    )


# Get the user details
@router.get("/settings", response_class=JSONResponse, tags=["User"], summary="Get the user details")
async def user_get_details(user: CurrentUser, PgDB: PostgresDep) -> JSONResponse:
    """
    Get the user details from the database
    """
    user_settings = await get_user_settings(db_session=PgDB, user_email=user["user_email"])
    if not user_settings:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"message": "User settings not found"}
        )

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={"message": "User settings from DB", "user_settings": user_settings}
    )


# Update the user details
@router.put("/settings", response_class=JSONResponse, tags=["User"], summary="Update the user details")
async def user_update_details(data: dict, user: CurrentUser, PgDB: PostgresDep) -> JSONResponse:
    """
    Update the user details in the database
    """
    await replace_user_settings(db_session=PgDB, user_email=user["user_email"], settings=data)
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={"message": "User settings updated successfully"}
    )


# Delete User (Delete the user and all the associated data)
@router.delete("/delete", response_class=JSONResponse, tags=["User"], summary="Delete User and all the associated data")
async def delete_self_user(request: Request, CacheDB: MemcachedDep, PgDB: PostgresDep) -> JSONResponse:
    """
    Logout from WebMail - Destroy the session, cookie and close the pool
    """
    session_id = request.cookies.get("SESSION_ID")
    if not session_id:
        raise All_Exceptions(message="Session ID not found", status_code=status.HTTP_406_NOT_ACCEPTABLE)
    
    user_data_bytes = await CacheDB.get(session_id.encode("utf-8"))
    if not user_data_bytes:
        raise All_Exceptions(message="Session expired", status_code=status.HTTP_401_UNAUTHORIZED)

    user_details = orjson.loads(user_data_bytes)
    if user_details["csrf_token"] != request.headers.get("X-CSRF-Token"):
        raise All_Exceptions(message="CSRF token mismatch", status_code=status.HTTP_401_UNAUTHORIZED)

    # Destroy the session in the cache
    await CacheDB.delete(key=session_id.encode("utf-8"))

    # Delete the user from the database
    await PgDB.execute(
        "DELETE FROM users WHERE email = $1",
        user_details["user_email"]
    )

    # Send response to delete the cookie
    response = JSONResponse(
        status_code=status.HTTP_200_OK,
        content={"message": "Logout successful, session destroyed"}
    )

    response.delete_cookie(
        key="SESSION_ID",
        httponly=True,
        secure=True,
        samesite="strict",
        domain=API_COOKIE_DOMAIN
    )
    response.delete_cookie(
        key="IS_SESSION_VALID",
        httponly=False,
        secure=True,
        samesite="strict",
        domain=API_COOKIE_DOMAIN
    )

    return response


# Create Domain
@router.post("/admin/domain", response_class=JSONResponse, tags=["Admin"], summary="Create Domain")
async def admin_create_domain(request: Request, data: dict, PgDB: PostgresDep) -> JSONResponse:
    """
    Create Domain
    """
    # API Key from Header
    api_key = request.headers.get("X-API-Key")
    if api_key != API_KEY:
        raise All_Exceptions(message="Unauthorized", status_code=status.HTTP_401_UNAUTHORIZED)
    
    await admin_create_new_domain(
        db_session=PgDB,
        domain=data["domain"],
        imap_server=data["imap_server"],
        imap_port=data["imap_port"],
        smtp_server=data["smtp_server"],
        smtp_port=data["smtp_port"],
        sieve_server=data["sieve_server"],
        sieve_port=data["sieve_port"],
        is_active=data.get("is_active", True),
        is_v2_user=data.get("is_v2_user", False)
    )

    return JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content={"message": "Domain created successfully"}
    )


# Edit Domain
@router.put("/admin/domain/{domain}", response_class=JSONResponse, tags=["Admin"], summary="Edit Domain")
async def admin_edit_domain_details(request: Request, domain: str, data: dict, PgDB: PostgresDep) -> JSONResponse:
    """
    Edit Domain
    """
    # API Key from Header
    api_key = request.headers.get("X-API-Key")
    if api_key != API_KEY:
        raise All_Exceptions(message="Unauthorized", status_code=status.HTTP_401_UNAUTHORIZED)

    await admin_edit_domain(
        db_session=PgDB,
        domain=domain,
        imap_server=data["imap_server"],
        imap_port=data["imap_port"],
        smtp_server=data["smtp_server"],
        smtp_port=data["smtp_port"],
        sieve_server=data["sieve_server"],
        sieve_port=data["sieve_port"],
        is_active=data["is_active"],
        is_v2_user=data["is_v2_user"]
    )

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={"message": "Domain edited successfully"}
    )


# Delete Domain
@router.delete("/admin/domain/{domain}", response_class=JSONResponse, tags=["Admin"], summary="Delete Domain")
async def admin_delete_domain_details(request: Request, domain: str, PgDB: PostgresDep) -> JSONResponse:
    """
    Delete Domain
    """
    # API Key from Header
    api_key = request.headers.get("X-API-Key")
    if api_key != API_KEY:
        raise All_Exceptions(message="Unauthorized", status_code=status.HTTP_401_UNAUTHORIZED)
    
    await admin_delete_domain(db_session=PgDB, domain=domain)

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={"message": "Domain deleted successfully"}
    )


# List Domains
@router.get("/admin/domains", response_class=JSONResponse, tags=["Admin"], summary="List Domains")
async def admin_list_all_domains(request: Request, page: int, size: int, PgDB: PostgresDep, query: str = "") -> JSONResponse:
    """
    List Domains
    """
    # API Key from Header
    api_key = request.headers.get("X-API-Key")
    if api_key != API_KEY:
        raise All_Exceptions(message="Unauthorized", status_code=status.HTTP_401_UNAUTHORIZED)
    
    domains_data = await admin_get_all_domains(db_session=PgDB, page=page, size=size, search_query=query)

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=domains_data
    )


# Get Domain Details
@router.get("/admin/domain/{domain}", response_class=JSONResponse, tags=["Admin"], summary="Get Domain Details")
async def admin_get_domain_details(request: Request, domain: str, PgDB: PostgresDep) -> JSONResponse:
    """
    Get Domain Details
    """
    # API Key from Header
    api_key = request.headers.get("X-API-Key")
    if api_key != API_KEY:
        raise All_Exceptions(message="Unauthorized", status_code=status.HTTP_401_UNAUTHORIZED)
    
    domain_data = await admin_get_domain_info(db_session=PgDB, domain=domain)

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "message": "Domain details fetched successfully",
            "data": domain_data
        }
    )
