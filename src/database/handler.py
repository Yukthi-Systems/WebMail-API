"""
Handles all the database operations
"""

from src.utils.base.libraries import aiomcache, asyncpg, TypeAlias, logging, status, uuid, orjson
from src.utils.base.constants import MAX_AGE_OF_CACHE, PRE_DEFINED_SETTINGS
from src.utils.models import All_Exceptions


PgSession: TypeAlias = asyncpg.Connection
MemCacheSession: TypeAlias = aiomcache.Client


async def get_domain_details(db_session: PgSession, domain: str) -> dict:
    """
    Get domain details from the database
    """
    try:
        row = await db_session.fetchrow(
            """
            SELECT smtp_server, smtp_port, imap_server, is_v2_user,
            imap_port, sieve_server, sieve_port, is_active
            FROM domain_details WHERE domain = $1
            """,
            domain
        )
        if row:
            return {
                "smtp_server": row["smtp_server"],
                "smtp_port": row["smtp_port"],
                "imap_server": row["imap_server"],
                "imap_port": row["imap_port"],
                "sieve_server": row["sieve_server"],
                "sieve_port": row["sieve_port"],
                "is_active": row["is_active"],
                "is_v2_user": row["is_v2_user"]
            }
        else:
            return {}

    except Exception as e:
        logging.error(f"Error fetching domain details: {e}", exc_info=True)
        raise All_Exceptions(
            message=f"Failed to fetch domain details: {e}",
            status_code=status.HTTP_424_FAILED_DEPENDENCY
        )


async def create_user_session_in_cache(
    cache_session: MemCacheSession, user_email: str, raw_password: str,
    smtp_server: str, smtp_port: int, smtp_user: str, smtp_password: str,
    imap_server: str, imap_port: int, imap_user: str, imap_password: str,
    sieve_server: str, sieve_port: int, sieve_user: str, sieve_password: str,
    v2_mailbox_id: int = None, v2_domain_id: int = None
) -> tuple[str, str]:
    """
    Create a user session in the cache and return the session ID and CSRF token
    This function generates a session ID and CSRF token, and stores the user details in the cache
    """
    try:
        # Create a session ID (UUID)
        session_id = str(uuid.uuid4())
        csrf_token = str(uuid.uuid4())

        # Store the session details in the cache
        await cache_session.set(
            key=session_id.encode("utf-8"),
            value=orjson.dumps({
                "user_email": user_email,
                "raw_password": raw_password,

                # V2 Admin Details
                "v2_mailbox_id": v2_mailbox_id,
                "v2_domain_id": v2_domain_id,

                # SMTP details
                "smtp_server": smtp_server,
                "smtp_port": smtp_port,
                "smtp_user": smtp_user,
                "smtp_password": smtp_password,

                # IMAP details
                "imap_server": imap_server,
                "imap_port": imap_port,
                "imap_user": imap_user,
                "imap_password": imap_password,

                # Sieve details
                "sieve_server": sieve_server,
                "sieve_port": sieve_port,
                "sieve_user": sieve_user,
                "sieve_password": sieve_password,

                "csrf_token": csrf_token
            }),
            exptime=MAX_AGE_OF_CACHE
        )

        return session_id, csrf_token

    except Exception as e:
        logging.error(f"Error creating user session: {e}", exc_info=True)
        raise All_Exceptions(
            message=f"Failed to create user session: {e}",
            status_code=status.HTTP_424_FAILED_DEPENDENCY
        )


async def get_user_settings(db_session: PgSession, user_email: str) -> dict:
    """
    Get user settings from the database based on the user email
    """
    try:
        row = await db_session.fetchrow(
            """
            SELECT settings FROM users WHERE email = $1
            """,
            user_email
        )
        if row:
            return orjson.loads(row["settings"].encode("utf-8"))
        else:
            return {}

    except Exception as e:
        logging.error(f"Error while fetching user settings: {e}", exc_info=True)
        raise All_Exceptions(
            message=f"Failed to fetch user settings: {e}",
            status_code=status.HTTP_424_FAILED_DEPENDENCY
        )


async def replace_user_settings(db_session: PgSession, user_email: str, settings: dict) -> None:
    """
    Update user settings in the database
    Replaces the existing settings with the new settings
    """
    try:
        await db_session.execute(
            """
            UPDATE users SET settings = $1 WHERE email = $2
            """,
            orjson.dumps(settings).decode("utf-8"),
            user_email
        )

    except Exception as e:
        logging.error(f"Error while updating user settings: {e}", exc_info=True)
        raise All_Exceptions(
            message=f"Failed to update user settings: {e}",
            status_code=status.HTTP_424_FAILED_DEPENDENCY
        )


async def create_user_if_not_exists(db_session: PgSession, user_email: str, user_domain: str) -> None:
    """
    Create a user in the database if it does not exist
    """
    try:
        await db_session.execute(
            """
            INSERT INTO users (email, domain, settings)
            SELECT $1, $2::VARCHAR, $3::TEXT
            WHERE EXISTS (
                SELECT 1 FROM domain_details WHERE domain = $2::VARCHAR
            )
            ON CONFLICT (email) DO NOTHING
            """,
            user_email,
            user_domain,
            orjson.dumps(PRE_DEFINED_SETTINGS).decode("utf-8")
        )

    except Exception as e:
        logging.error(f"Error while creating user: {e}", exc_info=True)
        raise All_Exceptions(
            message=f"Failed to create user: {e}",
            status_code=status.HTTP_424_FAILED_DEPENDENCY
        )


async def create_contact(db_session: PgSession, user_email: str, contact_name: str, contact_email: str, contact_phone: str='', contact_notes: str='') -> None:
    """
    Create a new contact in the database
    """
    try:
        await db_session.execute(
            """
            INSERT INTO user_contacts (
                user_email, name, email, phone, notes
            ) VALUES (
                $1, $2, $3, $4, $5
            )
            """,
            user_email,
            contact_name,
            contact_email,
            contact_phone,
            contact_notes
        )

    except Exception as e:
        logging.error(f"Error while creating contact: {e}", exc_info=True)
        raise All_Exceptions(
            message=f"Failed to create contact: {e}",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY
        )


async def create_bulk_contacts(db_session: PgSession, user_email: str, contacts: list[dict]) -> None:
    """
    Create multiple contacts in the database (Skip if contact email already exists for the user)
    """
    try:
        values = []
        for contact in contacts:
            values.append((
                user_email,
                contact["contact_name"],
                contact["contact_email"],
                contact["contact_phone"],
                contact["contact_notes"]
            ))

        await db_session.executemany(
            """
            INSERT INTO user_contacts (
                user_email, name, email, phone, notes
            ) VALUES (
                $1, $2, $3, $4, $5
            )
            ON CONFLICT (user_email, email) DO NOTHING
            """,
            values
        )

    except Exception as e:
        logging.error(f"Error while creating contact: {e}", exc_info=True)
        raise All_Exceptions(
            message=f"Failed to create contact: {e}",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY
        )


async def edit_contact(db_session: PgSession, contact_id: int, user_email: str, contact_name: str, contact_email: str, contact_phone: str='', contact_notes: str='') -> None:
    """
    Edit an existing contact in the database
    """
    try:
        await db_session.execute(
            """
            UPDATE user_contacts
            SET name = $2, email = $3, phone = $4, notes = $5, modified_at = NOW()
            WHERE contact_id = $1 AND user_email = $6
            """,
            contact_id,
            contact_name,
            contact_email,
            contact_phone,
            contact_notes,
            user_email
        )

    except Exception as e:
        logging.error(f"Error while editing contact: {e}", exc_info=True)
        raise All_Exceptions(
            message=f"Failed to edit contact: {e}",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY
        )


async def delete_contact(db_session: PgSession, contact_id: int, user_email: str) -> None:
    """
    Delete a contact from the database
    """
    try:
        await db_session.execute(
            """
            DELETE FROM user_contacts
            WHERE contact_id = $1 AND user_email = $2
            """,
            contact_id,
            user_email
        )

    except Exception as e:
        logging.error(f"Error while deleting contact: {e}", exc_info=True)
        raise All_Exceptions(
            message=f"Failed to delete contact: {e}",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY
        )


async def get_one_contact(db_session: PgSession, contact_id: int, user_email: str) -> dict:
    """
    Get a single contact from the database
    """
    try:
        row = await db_session.fetchrow(
            """
            SELECT contact_id, name, email, phone, notes, created_at, modified_at
            FROM user_contacts
            WHERE contact_id = $1 AND user_email = $2
            """,
            contact_id,
            user_email
        )
        if row:
            return {
                "contact_id": row["contact_id"],
                "name": row["name"],
                "email": row["email"],
                "phone": row["phone"],
                "notes": row["notes"],
                "created_at": str(row["created_at"]),
                "modified_at": str(row["modified_at"])
            }

        raise All_Exceptions(
            message="Contact not found",
            status_code=status.HTTP_404_NOT_FOUND
        )

    except Exception as e:
        logging.error(f"Error while fetching contact: {e}", exc_info=True)
        raise All_Exceptions(
            message=f"Failed to fetch contact: {e}",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY
        )


async def get_contacts(db_session: PgSession, user_email: str, current_page: int, page_size: int=10) -> list[dict]:
    """
    Get a list of contacts from the database
    """
    total_count = await db_session.fetchval(
        """
        SELECT COUNT(*) FROM user_contacts
        WHERE user_email = $1
        """,
        user_email
    )

    if (total_count is None) or (total_count == 0):
        return {
            "message": "No contacts found",
            "total_count": 0,
            "current_page": current_page,
            "page_size": 0,
            "total_pages": 0,
            "has_next": False,
            "has_previous": False,
            "next_page": None,
            "previous_page": None,
            "first_page": None,
            "last_page": None,
            "page_number": current_page,
            "data": []
        }

    if current_page < 1:
        raise All_Exceptions(
            message="Invalid page number",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY
        )

    if page_size < 1:
        raise All_Exceptions(
            message="Invalid page size",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY
        )

    if current_page > (total_count + page_size - 1) // page_size:
        raise All_Exceptions(
            message="Page number exceeds total pages",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY
        )

    # Calculate the offset for pagination
    offset = (current_page - 1) * page_size        
    rows = await db_session.fetch(
        """
        SELECT contact_id, name, email, phone, notes, created_at, modified_at
        FROM user_contacts
        WHERE user_email = $1
        ORDER BY created_at DESC
        LIMIT $2 OFFSET $3
        """,
        user_email,
        page_size,
        offset
    )
    return {
        "message": "Contacts retrieved successfully",
        "total_count": total_count,
        "current_page": current_page,
        "page_size": len(rows),
        "total_pages": (total_count + page_size - 1) // page_size,
        "has_next": current_page < (total_count + page_size - 1) // page_size,
        "has_previous": current_page > 1,
        "next_page": current_page + 1 if current_page < (total_count + page_size - 1) // page_size else None,
        "previous_page": current_page - 1 if current_page > 1 else None,
        "first_page": 1,
        "last_page": (total_count + page_size - 1) // page_size,
        "page_number": current_page,
        "data": [
            {
                "contact_id": row["contact_id"],
                "name": row["name"],
                "email": row["email"],
                "phone": row["phone"],
                "notes": row["notes"],
                "created_at": str(row["created_at"]),
                "modified_at": str(row["modified_at"])
            }
            for row in rows
        ]
    }


async def contact_exists(db_session: PgSession, user_email: str, contact_email: str) -> bool:
    """
    Check if a contact exists in the database
    """
    row = await db_session.fetchrow(
        """
        SELECT 1 FROM user_contacts
        WHERE user_email = $1 AND email = $2
        """,
        user_email,
        contact_email
    )
    return row is not None


async def simple_email_search(db_session: PgSession, user_email: str, partial_email_string: str) -> list[dict]:
    """
    Search for contacts by a partial email string
    Used for the drop down effect while typing the email
    """
    rows = await db_session.fetch(
        """
        SELECT contact_id, name, email
        FROM user_contacts
        WHERE user_email = $1 AND email ILIKE $2
        ORDER BY created_at DESC
        LIMIT 25
        """,
        user_email,
        f"%{partial_email_string}%"
    )
    if not rows:
        return []

    return [
        {
            "contact_id": row["contact_id"],
            "name": row["name"],
            "email": row["email"]
        }
        for row in rows
    ]


async def get_all_templates(db_session: PgSession, user_email: str, is_public: bool) -> list[dict]:
    """
    Get the templates for a user (based on domain if its public)
    """
    if is_public:
        user_domain = user_email.split("@")[-1]

        rows = await db_session.fetch(
            """
            SELECT template_id, name, created_by, created_at, modified_at
            FROM email_templates
            WHERE is_public = TRUE AND domain = $1
            ORDER BY modified_at DESC
            """,
            user_domain
        )
        if not rows:
            return []

        return [
            {
                "template_id": row["template_id"],
                "name": row["name"],
                "created_by": row["created_by"],
                "created_at": str(row["created_at"]),
                "modified_at": str(row["modified_at"])
            }
            for row in rows
        ]

    # If user wants to see their own templates
    else:
        rows = await db_session.fetch(
            """
            SELECT template_id, name, created_at, modified_at
            FROM email_templates
            WHERE created_by = $1
            ORDER BY modified_at DESC
            """,
            user_email
        )
        if not rows:
            return []

        return [
            {
                "template_id": row["template_id"],
                "name": row["name"],
                "created_at": str(row["created_at"]),
                "modified_at": str(row["modified_at"])
            }
            for row in rows
        ]


async def create_template(db_session: PgSession, user_email: str, is_public: bool, data: dict) -> None:
    """
    Create a new email template
    """
    user_domain = user_email.split("@")[-1]

    try:
        await db_session.execute(
            """
            INSERT INTO email_templates (
                domain, created_by, name, is_public, data
            ) VALUES (
                $1, $2, $3, $4, $5
            )
            """,
            user_domain,
            user_email,
            data["name"],
            is_public,
            orjson.dumps(data).decode("utf-8")
        )

    except Exception as e:
        logging.error(f"Error while creating email template: {e}", exc_info=True)
        raise All_Exceptions(
            message=f"Failed to create email template: {e}",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY
        )


async def delete_template(db_session: PgSession, user_email: str, template_id: int) -> None:
    """
    Delete an email template
    """
    try:
        await db_session.execute(
            """
            DELETE FROM email_templates
            WHERE template_id = $1 AND created_by = $2
            """,
            template_id,
            user_email
        )

    except Exception as e:
        logging.error(f"Error while deleting email template: {e}", exc_info=True)
        raise All_Exceptions(
            message=f"Failed to delete email template: {e}",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY
        )


async def edit_template(db_session: PgSession, template_id: int, user_email: str, is_public: bool, data: dict) -> None:
    """
    Edit means just replacing all the data but keeping the id, thats it
    """
    try:
        await db_session.execute(
            """
            UPDATE email_templates
            SET name = $1, is_public = $2, data = $3
            WHERE template_id = $4 AND created_by = $5
            """,
            data["name"],
            is_public,
            orjson.dumps(data).decode("utf-8"),
            template_id,
            user_email
        )

    except Exception as e:
        logging.error(f"Error while editing email template: {e}", exc_info=True)
        raise All_Exceptions(
            message=f"Failed to edit email template: {e}",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY
        )


async def get_template(db_session: PgSession, template_id: int, user_email: str) -> dict:
    """
    Get an email template by ID
    """
    # If user is trying to fetch public template and is of same domain all ok
    user_domain = user_email.split("@")[-1]
    row = await db_session.fetchrow(
        """
        SELECT created_by, is_public, domain
        FROM email_templates
        WHERE template_id = $1
        """,
        template_id
    )
    if not row:
        return {}

    # if user is same then all ok
    if row["created_by"] == user_email:
        template_row = await db_session.fetchrow(
            """
            SELECT template_id, name, created_by, is_public, data, created_at, modified_at
            FROM email_templates
            WHERE template_id = $1
            """,
            template_id
        )
        if not template_row:
            return {}

        return {
            "template_id": template_row["template_id"],
            "name": template_row["name"],
            "created_by": template_row["created_by"],
            "is_public": template_row["is_public"],
            "data": orjson.loads(template_row["data"].encode("utf-8")),
            "created_at": str(template_row["created_at"]),
            "modified_at": str(template_row["modified_at"])
        }
    
    # if user is not same but is public and same domain then also we can give access
    if row["is_public"] and row["domain"] == user_domain:
        template_row = await db_session.fetchrow(
            """
            SELECT template_id, name, created_by, is_public, data, created_at, modified_at
            FROM email_templates
            WHERE template_id = $1
            """,
            template_id
        )
        if not template_row:
            return {}

        return {
            "template_id": template_row["template_id"],
            "name": template_row["name"],
            "created_by": template_row["created_by"],
            "is_public": template_row["is_public"],
            "data": orjson.loads(template_row["data"].encode("utf-8")),
            "created_at": str(template_row["created_at"]),
            "modified_at": str(template_row["modified_at"])
        }

    # If user is not same and its not public then deny access
    return {}


async def admin_create_new_domain(
    db_session: PgSession,
    domain: str,
    smtp_server: str,
    smtp_port: int,
    imap_server: str,
    imap_port: int,
    sieve_server: str,
    sieve_port: int,
    is_active: bool,
    is_v2_user: bool
) -> None:
    """
    Admin function to create a new domain in the database
    """
    try:
        await db_session.execute(
            """
            INSERT INTO domain_details (
                domain, smtp_server, smtp_port,
                imap_server, imap_port,
                sieve_server, sieve_port,
                is_active, is_v2_user
            ) VALUES (
                $1, $2, $3, $4, $5, $6, $7, $8, $9
            )
            """,
            domain,
            smtp_server,
            smtp_port,
            imap_server,
            imap_port,
            sieve_server,
            sieve_port,
            is_active,
            is_v2_user
        )

    except Exception as e:
        logging.error(f"Error while creating new domain: {e}", exc_info=True)
        raise All_Exceptions(
            message=f"Failed to create new domain: {e}",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY
        )


async def admin_edit_domain(
    db_session: PgSession,
    domain: str,
    smtp_server: str,
    smtp_port: int,
    imap_server: str,
    imap_port: int,
    sieve_server: str,
    sieve_port: int,
    is_active: bool,
    is_v2_user: bool
) -> None:
    """
    Admin function to edit an existing domain in the database
    """
    try:
        await db_session.execute(
            """
            UPDATE domain_details
            SET smtp_server = $2, smtp_port = $3,
                imap_server = $4, imap_port = $5,
                sieve_server = $6, sieve_port = $7,
                is_active = $8, is_v2_user = $9
            WHERE domain = $1
            """,
            domain,
            smtp_server,
            smtp_port,
            imap_server,
            imap_port,
            sieve_server,
            sieve_port,
            is_active,
            is_v2_user
        )

    except Exception as e:
        logging.error(f"Error while editing domain: {e}", exc_info=True)
        raise All_Exceptions(
            message=f"Failed to edit domain: {e}",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY
        )


async def admin_delete_domain(db_session: PgSession, domain: str) -> None:
    """
    Admin function to delete a domain from the database
    """
    try:
        await db_session.execute(
            """
            DELETE FROM domain_details
            WHERE domain = $1
            """,
            domain
        )

    except Exception as e:
        logging.error(f"Error while deleting domain: {e}", exc_info=True)
        raise All_Exceptions(
            message=f"Failed to delete domain: {e}",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY
        )


async def admin_get_all_domains(db_session: PgSession, page: int, size: int, search_query: str) -> dict:
    """
    Admin function to get all domains from the database with pagination
    """
    total_count = await db_session.fetchval(
        """
        SELECT COUNT(*) FROM domain_details WHERE domain ILIKE $1
        """,
        f"%{search_query}%"
    )

    if total_count is None or total_count == 0 or page < 1 or size < 5:
        raise All_Exceptions(
            message="No domains found or invalid page/size",
            status_code=status.HTTP_404_NOT_FOUND
        )

    if page > (total_count + size - 1) // size:
        raise All_Exceptions(
            message="Page number exceeds total pages, please check",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY
        )

    # Calculate the offset for pagination
    offset = (page - 1) * size        
    rows = await db_session.fetch(
        """
        SELECT domain, smtp_server, smtp_port,
               imap_server, imap_port, is_v2_user,
               sieve_server, sieve_port,
               is_active, created_at
        FROM domain_details
        WHERE domain ILIKE $3
        ORDER BY created_at DESC
        LIMIT $1 OFFSET $2
        """,
        size,
        offset,
        f"%{search_query}%"
    )
    return {
        "message": "Domains retrieved successfully",
        "total_count": total_count,
        "current_page": page,
        "page_size": len(rows),
        "total_pages": (total_count + size - 1) // size,
        "has_next": page < (total_count + size - 1) // size,
        "has_previous": page > 1,
        "next_page": page + 1 if page < (total_count + size - 1) // size else None,
        "previous_page": page - 1 if page > 1 else None,
        "first_page": 1,
        "last_page": (total_count + size - 1) // size,
        "page_number": page,
        "data": [
            {
                "domain": row["domain"],
                "smtp_server": row["smtp_server"],
                "smtp_port": row["smtp_port"],
                "imap_server": row["imap_server"],
                "imap_port": row["imap_port"],
                "sieve_server": row["sieve_server"],
                "sieve_port": row["sieve_port"],
                "is_active": row["is_active"],
                "is_v2_user": row["is_v2_user"],
                "created_at": str(row["created_at"])
            }
            for row in rows
        ]
    }


async def admin_get_domain_info(db_session: PgSession, domain: str) -> dict:
    """
    Admin function to get information about a specific domain
    """
    row = await db_session.fetchrow(
        """
        SELECT domain, smtp_server, smtp_port,
               imap_server, imap_port, is_v2_user,
               sieve_server, sieve_port,
               is_active, created_at
        FROM domain_details
        WHERE domain = $1
        """,
        domain
    )
    if not row:
        return {}

    return {
        "domain": row["domain"],
        "smtp_server": row["smtp_server"],
        "smtp_port": row["smtp_port"],
        "imap_server": row["imap_server"],
        "imap_port": row["imap_port"],
        "sieve_server": row["sieve_server"],
        "sieve_port": row["sieve_port"],
        "is_active": row["is_active"],
        "is_v2_user": row["is_v2_user"],
        "created_at": str(row["created_at"])
    }


async def validate_origin_ip_blocked(admin_db_session: PgSession, ip_address: str, user_email: str) -> bool:
    """
    Validate if the origin IP is blocked or not
    """
    logging.debug(f"Validating origin IP: {ip_address} for user: {user_email}")
    row = await admin_db_session.fetchrow(
        f"""
        SELECT
            inet('{ip_address}') <<= ANY(
                string_to_array(m.allow_nets, ',')::cidr[]
            ) AS ip_allowed,
            (
                NOT EXISTS (
                    SELECT 1
                    FROM mailmanager_countrymailboxrelationmodel cm
                    WHERE cm.mailbox_id = m.id
                )
                OR
                EXISTS (
                    SELECT 1
                    FROM geoip2_network gn
                    JOIN geoip2_location gl
                        ON gl.geoname_id = gn.geoname_id
                    AND gl.locale_code = 'en'
                    JOIN mailmanager_country c
                        ON UPPER(c.code) = UPPER(gl.country_iso_code)
                    JOIN mailmanager_countrymailboxrelationmodel cm
                        ON cm.country_id = c.id
                    AND cm.mailbox_id = m.id
                    WHERE gn.network >>= inet('{ip_address}')
                    ORDER BY masklen(gn.network) DESC
                    LIMIT 1
                )
            ) AS country_allowed
        FROM mailmanager_mailbox m
        WHERE m.email = $1;
        """,
        user_email
    )

    if not row:
        logging.debug(f"No mailbox found for user: {user_email}")
        return False

    # Both should be allowed for the user to be able to login, if any one of them is blocked then we will block the user
    return row["ip_allowed"] and row["country_allowed"]


async def get_v2_ids(admin_db_session: PgSession, user_email: str) -> tuple[int, int]:
    """
    Get the V2 email ID and domain ID for the user email from the mailmanager_mailbox table
    """
    row = await admin_db_session.fetchrow(
        """
        SELECT 
            m.id AS mailbox_id,
            m.domain_id AS domain_id
        FROM mailmanager_mailbox m
        WHERE m.email = $1
        """,
        user_email
    )

    if row:
        return row["mailbox_id"], row["domain_id"]

    return None, None


async def simple_email_search_v2(admin_db_session: PgSession, domain_id: int, partial_email_string: str) -> list[dict]:
    """
    Search for contacts by a partial email string
    Used for the drop down effect while typing the email
    """
    rows = await admin_db_session.fetch(
        """
        SELECT id AS contact_id, first_name AS name, email
        FROM mailmanager_mailbox
        WHERE domain_id = $1 AND email ILIKE $2
        LIMIT 25
        """,
        domain_id,
        f"%{partial_email_string}%"
    )
    if not rows:
        return []

    return [
        {
            "contact_id": row["contact_id"],
            "name": row["name"],
            "email": row["email"]
        }
        for row in rows
    ]
