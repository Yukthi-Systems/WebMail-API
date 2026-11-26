"""
This module provides User related API endpoints
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
    Request,
    logging,
    status,
    orjson
)
from src.database import (
    MemcachedDep,
    PostgresDep,
    get_v2_ids,
    get_domain_details,
    create_user_session_in_cache,
    get_user_settings,
    replace_user_settings,
    get_or_create_user,
    delete_user,
    admin_create_new_domain,
    validate_origin_ip_blocked,
    admin_edit_domain,
    admin_delete_domain,
    admin_get_all_domains,
    admin_get_domain_info
)
from src.main import check_smtp_login, check_imap_login, CurrentUser, validate_recaptcha
from src.utils.base.constants import MAX_AGE_OF_CACHE, API_KEY
from src.utils.models import All_Exceptions, AuthRequest


# Router
router = APIRouter()


# User friendly login error messages (the technical reason is written to the logs)
LOGIN_ERROR_MESSAGES = {
    "recaptcha_failed": "Verification failed. Please refresh the page and try again.",
    "domain_not_found": "This email domain isn't set up for WebMail. Please contact your administrator.",
    "domain_inactive": "This account is currently disabled. Please contact your administrator.",
    "ip_blocked": "Sign-in from your current location isn't allowed. Please contact your administrator.",
    "wrong_credentials": "Incorrect email or password.",
    "server_unreachable": "We couldn't reach your mail server. Please try again in a few minutes.",
    "smtp_failed": "Your account can't send email right now. Please contact your administrator.",
    "use_sso": "Your organization signs in with single sign-on (SSO). Please use Login with SSO."
}


# Login to WebMail - Validate IMAP and SMTP credentials (Create a session)
@router.post("/login", response_class=JSONResponse, tags=["User"], summary="Login to WebMail")
async def user_login_webmail(request: Request, data: AuthRequest, CacheDB: MemcachedDep, PgDB: PostgresDep) -> JSONResponse:
    """
    Login to WebMail - Validate IMAP and SMTP credentials (Create a session)
    """
    if not validate_recaptcha(token=data.recaptcha_token):
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"message": LOGIN_ERROR_MESSAGES["recaptcha_failed"]}
        )

    # Get IMAP and SMTP details from DB if domain is present
    server_details = await get_domain_details(db_session=PgDB, domain=data.domain)
    if not server_details:
        logging.warning(f"Login: domain {data.domain} is not registered (user {data.email})")
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"message": LOGIN_ERROR_MESSAGES["domain_not_found"]}
        )
    
    if not server_details["is_active"]:
        logging.warning(f"Login: domain {data.domain} is inactive (user {data.email})")
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"message": LOGIN_ERROR_MESSAGES["domain_inactive"]}
        )

    # Internal domain (no mail server configuration): its users log in with SSO, not with a password
    if server_details["mail_server_config_id"] is None:
        logging.info(f"Login: domain {data.domain} uses SSO (user {data.email})")
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"message": LOGIN_ERROR_MESSAGES["use_sso"], "login_method": "sso"}
        )

    # if is_v2_user:
    #     # Find the MailBox ID and Domain ID for the user from the DB (For V2 Users)
    #     # Checked before the IP check, so a missing user is not reported as a blocked IP
    #     v2_mailbox_id, v2_domain_id = await get_v2_ids(admin_db_session=AdminPgDB, user_email=data.email)
    #     if not v2_domain_id or not v2_mailbox_id:
    #         # Same message as a wrong password - do not reveal which email addresses exist
    #         logging.warning(f"Login: user {data.email} not found in the V2 admin DB")
    #         return JSONResponse(
    #             status_code=status.HTTP_401_UNAUTHORIZED,
    #             content={"message": LOGIN_ERROR_MESSAGES["wrong_credentials"]}
    #         )

    #     # Check if IP is blocked or not
    #     ip_validation_result = await validate_origin_ip_blocked(admin_db_session=AdminPgDB, ip_address=request.headers.get('X-Real-IP'), user_email=data.email)
    #     if not ip_validation_result:    # If it returns False, that means the IP is blocked
    #         logging.warning(f"Login: access blocked for user {data.email} from IP {request.headers.get('X-Real-IP')}")
    #         return JSONResponse(
    #             status_code=status.HTTP_403_FORBIDDEN,
    #             content={"message": LOGIN_ERROR_MESSAGES["ip_blocked"]}
    #         )

    # Validate the IMAP details (SMTP is checked only if IMAP login works)
    imap_result = check_imap_login(
        imap_server=server_details["imap_server"],
        imap_port=server_details["imap_port"],
        imap_user=data.email,
        imap_password=data.password
    )
    if imap_result == "auth_failed":
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"message": LOGIN_ERROR_MESSAGES["wrong_credentials"]}
        )
    if imap_result != "ok":
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"message": LOGIN_ERROR_MESSAGES["server_unreachable"]}
        )

    smtp_result = check_smtp_login(
        smtp_server=server_details["smtp_server"],
        smtp_port=server_details["smtp_port"],
        smtp_user=data.email,
        smtp_password=data.password
    )
    if smtp_result == "unreachable":
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"message": LOGIN_ERROR_MESSAGES["server_unreachable"]}
        )
    if smtp_result != "ok":
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"message": LOGIN_ERROR_MESSAGES["smtp_failed"]}
        )
    
    # The user in the database (created on the first login)
    db_user = await get_or_create_user(db_session=PgDB, user_email=data.email, user_domain=data.domain)

    # Create a session in the cache
    session_id = await create_user_session_in_cache(
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
        user_id=db_user["user_id"],
        organization_id=db_user["organization_id"],
        organization_name=db_user["organization_name"]
    )

    # Create a session as response headers and return the response
    response = JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "message": "All Credentials are valid - Login successful",
            "session_id": session_id
        }
    )

    # Set the session expiry in the response header
    response.headers["X-Session-Expiry"] = str(MAX_AGE_OF_CACHE)
    response.headers["Access-Control-Expose-Headers"] = "X-Session-Expiry"

    return response


# Logout from WebMail - Destroy the session and close the pool
@router.delete("/logout", response_class=JSONResponse, tags=["User"], summary="Logout from WebMail")
async def user_logout_webmail(request: Request, CacheDB: MemcachedDep) -> JSONResponse:
    """
    Logout from WebMail - Destroy the session and close the pool
    """
    session_id = request.headers.get("X-Session-Token")
    if not session_id:
        raise All_Exceptions(message="Session ID not found", status_code=status.HTTP_406_NOT_ACCEPTABLE)

    # Destroy the session in the cache
    await CacheDB.delete(key=session_id.encode("utf-8"))

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={"message": "Logout successful, session destroyed"}
    )


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
    user_settings = await get_user_settings(db_session=PgDB, user_id=user["user_id"])
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
    await replace_user_settings(db_session=PgDB, user_id=user["user_id"], settings=data)
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={"message": "User settings updated successfully"}
    )


# Delete User (Delete the user and all the associated data)
@router.delete("/delete", response_class=JSONResponse, tags=["User"], summary="Delete User and all the associated data")
async def delete_self_user(request: Request, CacheDB: MemcachedDep, PgDB: PostgresDep) -> JSONResponse:
    """
    Delete the user and all the associated data, destroy the session and close the pool
    """
    session_id = request.headers.get("X-Session-Token")
    if not session_id:
        raise All_Exceptions(message="Session ID not found", status_code=status.HTTP_406_NOT_ACCEPTABLE)

    user_data_bytes = await CacheDB.get(session_id.encode("utf-8"))
    if not user_data_bytes:
        raise All_Exceptions(message="Session expired", status_code=status.HTTP_401_UNAUTHORIZED)

    user_details = orjson.loads(user_data_bytes)

    # Destroy the session in the cache
    await CacheDB.delete(key=session_id.encode("utf-8"))

    # Delete the user from the database (sessions from before the new schema have no user_id)
    if user_details.get("user_id"):
        await delete_user(db_session=PgDB, user_id=user_details["user_id"])
    else:
        await PgDB.execute("DELETE FROM users WHERE email = $1", user_details["user_email"])

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={"message": "Deleted all your data and logged out successfully"}
    )


def _admin_domain_fields(data: dict) -> dict:
    """
    Mail server fields of an admin domain request: server_host + ports.
    The old form (smtp_server / imap_server / sieve_server) still works if the three are the same host.
    """
    return {
        "server_host": data.get("server_host"),
        "smtp_server": data.get("smtp_server"),
        "imap_server": data.get("imap_server"),
        "sieve_server": data.get("sieve_server"),
        "smtp_port": data.get("smtp_port"),
        "imap_port": data.get("imap_port"),
        "sieve_port": data.get("sieve_port")
    }


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
        is_active=data.get("is_active", True),
        **_admin_domain_fields(data)
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
        is_active=data.get("is_active", True),
        **_admin_domain_fields(data)
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
