"""
Handles all the database operations
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


from src.utils.base.libraries import aiomcache, asyncpg, TypeAlias, Optional, logging, status, uuid, orjson
from src.utils.base.constants import MAX_AGE_OF_CACHE, PRE_DEFINED_SETTINGS
from src.utils.models import All_Exceptions


PgSession: TypeAlias = asyncpg.Connection
MemCacheSession: TypeAlias = aiomcache.Client



# everyone on the same domain shares one organization. The id is derived from the domain, so it is
# the same on every login without storing it anywhere, and organization_name is the domain.
EXTERNAL_ORGANIZATION_NAMESPACE = uuid.UUID("3b2f6a58-4f0e-4c8e-9a51-6f3c2d8e7b10")


def external_organization_id(domain: str) -> uuid.UUID:
    """Organization id of an external domain (the same for every user of that domain)"""
    return uuid.uuid5(EXTERNAL_ORGANIZATION_NAMESPACE, domain.lower())


def _ts(value) -> Optional[str]:
    return str(value) if value is not None else None


async def get_domain_details(db_session: PgSession, domain: str) -> dict:
    """
    Get the domain and its mail server from the database. Empty dict if the domain is not registered.
    mail_server_config_id is None for an internal domain (no mail server configuration, its users log in with SSO).
    """
    try:
        row = await db_session.fetchrow(
            """
            SELECT d.is_active, d.mail_server_config_id,
                   c.server_host, c.smtp_port, c.imap_port, c.sieve_port
            FROM domains d
            LEFT JOIN mail_server_config c ON c.config_id = d.mail_server_config_id
            WHERE d.domain = $1
            """,
            domain
        )
        if not row:
            return {}

        details = {
            "is_active": row["is_active"],
            "mail_server_config_id": row["mail_server_config_id"]
        }
        if row["mail_server_config_id"] is not None:
            # One host serves IMAP, SMTP and Sieve
            details.update({
                "smtp_server": row["server_host"],
                "smtp_port": row["smtp_port"],
                "imap_server": row["server_host"],
                "imap_port": row["imap_port"],
                "sieve_server": row["server_host"],
                "sieve_port": row["sieve_port"]
            })
        return details

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
    user_id: str, organization_id: str, organization_name: str
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

                # User in the database
                "user_id": str(user_id),
                "organization_id": str(organization_id),
                "organization_name": organization_name,

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


async def get_user_settings(db_session: PgSession, user_id: str) -> dict:
    """
    Get user settings from the database (private_info -> settings)
    """
    try:
        settings = await db_session.fetchval(
            """
            SELECT private_info -> 'settings' FROM users WHERE user_id = $1
            """,
            uuid.UUID(str(user_id))
        )
        return orjson.loads(settings) if settings else {}

    except Exception as e:
        logging.error(f"Error while fetching user settings: {e}", exc_info=True)
        raise All_Exceptions(
            message=f"Failed to fetch user settings: {e}",
            status_code=status.HTTP_424_FAILED_DEPENDENCY
        )


async def replace_user_settings(db_session: PgSession, user_id: str, settings: dict) -> None:
    """
    Update user settings in the database
    Replaces the existing settings with the new settings (the rest of private_info is kept)
    """
    try:
        await db_session.execute(
            """
            UPDATE users
            SET private_info = jsonb_set(private_info, '{settings}', $1::jsonb, true)
            WHERE user_id = $2
            """,
            orjson.dumps(settings).decode("utf-8"),
            uuid.UUID(str(user_id))
        )

    except Exception as e:
        logging.error(f"Error while updating user settings: {e}", exc_info=True)
        raise All_Exceptions(
            message=f"Failed to update user settings: {e}",
            status_code=status.HTTP_424_FAILED_DEPENDENCY
        )


async def get_or_create_user(db_session: PgSession, user_email: str, user_domain: str) -> dict:
    """
    Get the user by email, or create it (random user_id, the default settings) on the first login.
    Users of external domains share one organization per domain (see external_organization_id).
    Returns user_id, organization_id and organization_name.
    """
    try:
        row = await db_session.fetchrow(
            """
            WITH new_user AS (
                INSERT INTO users (user_id, email, domain, organization_id, organization_name, private_info, public_info)
                VALUES ($1, $2, $3, $4, $5, $6::jsonb, '{}'::jsonb)
                ON CONFLICT (email) DO NOTHING
                RETURNING user_id, organization_id, organization_name
            )
            SELECT user_id, organization_id, organization_name FROM new_user
            UNION ALL
            SELECT user_id, organization_id, organization_name FROM users WHERE email = $2
            LIMIT 1
            """,
            uuid.uuid4(),
            user_email,
            user_domain,
            external_organization_id(user_domain),
            user_domain,
            orjson.dumps({"settings": PRE_DEFINED_SETTINGS}).decode("utf-8")
        )
        return {
            "user_id": str(row["user_id"]),
            "organization_id": str(row["organization_id"]),
            "organization_name": row["organization_name"]
        }

    except Exception as e:
        logging.error(f"Error while creating user: {e}", exc_info=True)
        raise All_Exceptions(
            message=f"Failed to create user: {e}",
            status_code=status.HTTP_424_FAILED_DEPENDENCY
        )


async def delete_user(db_session: PgSession, user_id: str) -> None:
    """Delete a user. Their contacts and templates are deleted with them (ON DELETE CASCADE)."""
    await db_session.execute("DELETE FROM users WHERE user_id = $1", uuid.UUID(str(user_id)))


def _contact_row(row) -> dict:
    # modified_at is the old name of updated_at, kept for the API clients
    return {
        "contact_id": row["contact_id"],
        "name": row["name"],
        "email": row["email"],
        "phone": row["phone"],
        "notes": row["notes"],
        "created_at": _ts(row["created_at"]),
        "modified_at": _ts(row["updated_at"])
    }


async def create_contact(db_session: PgSession, user_id: str, organization_id: str, contact_name: str, contact_email: str, contact_phone: str='', contact_notes: str='') -> None:
    """
    Create a new contact in the database
    """
    try:
        await db_session.execute(
            """
            INSERT INTO contacts (
                user_id, organization_id, name, email, phone, notes
            ) VALUES (
                $1, $2, $3, $4, $5, $6
            )
            """,
            uuid.UUID(str(user_id)),
            uuid.UUID(str(organization_id)),
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


async def create_bulk_contacts(db_session: PgSession, user_id: str, organization_id: str, contacts: list[dict]) -> None:
    """
    Create multiple contacts in the database (Skip if contact email already exists for the user)
    """
    try:
        await db_session.executemany(
            """
            INSERT INTO contacts (
                user_id, organization_id, name, email, phone, notes
            ) VALUES (
                $1, $2, $3, $4, $5, $6
            )
            ON CONFLICT (user_id, email) DO NOTHING
            """,
            [
                (
                    uuid.UUID(str(user_id)),
                    uuid.UUID(str(organization_id)),
                    contact["contact_name"],
                    contact["contact_email"],
                    contact["contact_phone"],
                    contact["contact_notes"]
                )
                for contact in contacts
            ]
        )

    except Exception as e:
        logging.error(f"Error while creating contact: {e}", exc_info=True)
        raise All_Exceptions(
            message=f"Failed to create contact: {e}",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY
        )


async def edit_contact(db_session: PgSession, contact_id: int, user_id: str, contact_name: str, contact_email: str, contact_phone: str='', contact_notes: str='') -> None:
    """
    Edit an existing contact in the database
    """
    try:
        await db_session.execute(
            """
            UPDATE contacts
            SET name = $2, email = $3, phone = $4, notes = $5, updated_at = NOW()
            WHERE contact_id = $1 AND user_id = $6
            """,
            contact_id,
            contact_name,
            contact_email,
            contact_phone,
            contact_notes,
            uuid.UUID(str(user_id))
        )

    except Exception as e:
        logging.error(f"Error while editing contact: {e}", exc_info=True)
        raise All_Exceptions(
            message=f"Failed to edit contact: {e}",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY
        )


async def delete_contact(db_session: PgSession, contact_id: int, user_id: str) -> None:
    """
    Delete a contact from the database
    """
    try:
        await db_session.execute(
            """
            DELETE FROM contacts
            WHERE contact_id = $1 AND user_id = $2
            """,
            contact_id,
            uuid.UUID(str(user_id))
        )

    except Exception as e:
        logging.error(f"Error while deleting contact: {e}", exc_info=True)
        raise All_Exceptions(
            message=f"Failed to delete contact: {e}",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY
        )


async def get_one_contact(db_session: PgSession, contact_id: int, user_id: str) -> dict:
    """
    Get a single contact from the database
    """
    try:
        row = await db_session.fetchrow(
            """
            SELECT contact_id, name, email, phone, notes, created_at, updated_at
            FROM contacts
            WHERE contact_id = $1 AND user_id = $2
            """,
            contact_id,
            uuid.UUID(str(user_id))
        )
        if row:
            return _contact_row(row)

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


async def get_contacts(db_session: PgSession, user_id: str, current_page: int, page_size: int=10) -> list[dict]:
    """
    Get a list of contacts from the database
    """
    user_id = uuid.UUID(str(user_id))
    total_count = await db_session.fetchval(
        """
        SELECT COUNT(*) FROM contacts
        WHERE user_id = $1
        """,
        user_id
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
        SELECT contact_id, name, email, phone, notes, created_at, updated_at
        FROM contacts
        WHERE user_id = $1
        ORDER BY created_at DESC
        LIMIT $2 OFFSET $3
        """,
        user_id,
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
        "data": [_contact_row(row) for row in rows]
    }


async def contact_exists(db_session: PgSession, user_id: str, contact_email: str) -> bool:
    """
    Check if a contact exists in the database
    """
    row = await db_session.fetchrow(
        """
        SELECT 1 FROM contacts
        WHERE user_id = $1 AND email = $2
        """,
        uuid.UUID(str(user_id)),
        contact_email
    )
    return row is not None


async def simple_email_search(db_session: PgSession, user_id: str, partial_email_string: str) -> list[dict]:
    """
    Search for contacts by a partial email string
    Used for the drop down effect while typing the email
    """
    rows = await db_session.fetch(
        """
        SELECT contact_id, name, email
        FROM contacts
        WHERE user_id = $1 AND email ILIKE $2
        ORDER BY created_at DESC
        LIMIT 25
        """,
        uuid.UUID(str(user_id)),
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


async def get_all_templates(db_session: PgSession, user_id: str, organization_id: str, is_public: bool) -> list[dict]:
    """
    Get the templates of a user, or the public templates of their organization.
    created_by is the email of the user who made the template, modified_at is updated_at (names kept for the API clients).
    """
    if is_public:
        # Filtered on the organization of the template itself, no join needed for the filter
        rows = await db_session.fetch(
            """
            SELECT t.template_id, t.name, u.email AS created_by, t.created_at, t.updated_at
            FROM email_templates t
            JOIN users u ON u.user_id = t.user_id
            WHERE t.is_public = TRUE AND t.organization_id = $1
            ORDER BY t.updated_at DESC
            """,
            uuid.UUID(str(organization_id))
        )
        return [
            {
                "template_id": row["template_id"],
                "name": row["name"],
                "created_by": row["created_by"],
                "created_at": _ts(row["created_at"]),
                "modified_at": _ts(row["updated_at"])
            }
            for row in rows
        ]

    # If user wants to see their own templates
    rows = await db_session.fetch(
        """
        SELECT template_id, name, created_at, updated_at
        FROM email_templates
        WHERE user_id = $1
        ORDER BY updated_at DESC
        """,
        uuid.UUID(str(user_id))
    )
    return [
        {
            "template_id": row["template_id"],
            "name": row["name"],
            "created_at": _ts(row["created_at"]),
            "modified_at": _ts(row["updated_at"])
        }
        for row in rows
    ]


async def create_template(db_session: PgSession, user_id: str, organization_id: str, user_domain: str, is_public: bool, data: dict) -> None:
    """
    Create a new email template
    """
    try:
        await db_session.execute(
            """
            INSERT INTO email_templates (
                domain, user_id, organization_id, name, is_public, details
            ) VALUES (
                $1, $2, $3, $4, $5, $6::jsonb
            )
            """,
            user_domain,
            uuid.UUID(str(user_id)),
            uuid.UUID(str(organization_id)),
            data["name"],
            is_public,
            orjson.dumps(data).decode("utf-8")
        )

    except asyncpg.UniqueViolationError:
        raise All_Exceptions(
            message=f"You already have a template named {data['name']!r}",
            status_code=status.HTTP_409_CONFLICT
        )

    except Exception as e:
        logging.error(f"Error while creating email template: {e}", exc_info=True)
        raise All_Exceptions(
            message=f"Failed to create email template: {e}",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY
        )


async def delete_template(db_session: PgSession, user_id: str, template_id: int) -> None:
    """
    Delete an email template
    """
    try:
        await db_session.execute(
            """
            DELETE FROM email_templates
            WHERE template_id = $1 AND user_id = $2
            """,
            template_id,
            uuid.UUID(str(user_id))
        )

    except Exception as e:
        logging.error(f"Error while deleting email template: {e}", exc_info=True)
        raise All_Exceptions(
            message=f"Failed to delete email template: {e}",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY
        )


async def edit_template(db_session: PgSession, template_id: int, user_id: str, is_public: bool, data: dict) -> None:
    """
    Edit means just replacing all the data but keeping the id, thats it
    """
    try:
        await db_session.execute(
            """
            UPDATE email_templates
            SET name = $1, is_public = $2, details = $3::jsonb, updated_at = NOW()
            WHERE template_id = $4 AND user_id = $5
            """,
            data["name"],
            is_public,
            orjson.dumps(data).decode("utf-8"),
            template_id,
            uuid.UUID(str(user_id))
        )

    except asyncpg.UniqueViolationError:
        raise All_Exceptions(
            message=f"You already have a template named {data['name']!r}",
            status_code=status.HTTP_409_CONFLICT
        )

    except Exception as e:
        logging.error(f"Error while editing email template: {e}", exc_info=True)
        raise All_Exceptions(
            message=f"Failed to edit email template: {e}",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY
        )


async def get_template(db_session: PgSession, template_id: int, user_id: str, organization_id: str) -> dict:
    """
    Get an email template by ID: your own, or a public one of your organization. Empty dict otherwise.
    """
    row = await db_session.fetchrow(
        """
        SELECT t.template_id, t.name, u.email AS created_by, t.is_public, t.details, t.created_at, t.updated_at
        FROM email_templates t
        JOIN users u ON u.user_id = t.user_id
        WHERE t.template_id = $1
          AND (t.user_id = $2 OR (t.is_public AND t.organization_id = $3))
        """,
        template_id,
        uuid.UUID(str(user_id)),
        uuid.UUID(str(organization_id))
    )
    if not row:
        return {}

    return {
        "template_id": row["template_id"],
        "name": row["name"],
        "created_by": row["created_by"],
        "is_public": row["is_public"],
        "data": orjson.loads(row["details"]),
        "created_at": _ts(row["created_at"]),
        "modified_at": _ts(row["updated_at"])
    }


def _admin_mail_server(server_host: Optional[str], smtp_server: Optional[str], imap_server: Optional[str], sieve_server: Optional[str]) -> Optional[str]:
    """
    The one host of a mail server configuration. Accepts the old form (smtp_server / imap_server / sieve_server)
    as long as they are the same host. None if no host is given.
    """
    hosts = {host.strip().lower() for host in (server_host, smtp_server, imap_server, sieve_server) if host and host.strip()}
    if len(hosts) > 1:
        raise All_Exceptions(
            message="IMAP, SMTP and Sieve must use the same server host",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY
        )
    return hosts.pop() if hosts else None


def _admin_required_mail_server(server_host, smtp_server, imap_server, sieve_server, smtp_port, imap_port, sieve_port) -> str:
    """The host of an admin domain request, refused if the host or a port is missing"""
    host = _admin_mail_server(server_host, smtp_server, imap_server, sieve_server)
    if not host or None in (smtp_port, imap_port, sieve_port):
        raise All_Exceptions(
            message="A domain needs server_host, smtp_port, imap_port and sieve_port",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY
        )
    return host


async def admin_create_new_domain(
    db_session: PgSession,
    domain: str,
    is_active: bool,
    server_host: Optional[str] = None,
    smtp_port: Optional[int] = None,
    imap_port: Optional[int] = None,
    sieve_port: Optional[int] = None,
    smtp_server: Optional[str] = None,
    imap_server: Optional[str] = None,
    sieve_server: Optional[str] = None
) -> None:
    """
    Admin function to create a new domain with its mail server configuration (server_host + ports)
    """
    host = _admin_required_mail_server(server_host, smtp_server, imap_server, sieve_server, smtp_port, imap_port, sieve_port)

    try:
        async with db_session.transaction():
            config_id = await db_session.fetchval(
                """
                INSERT INTO mail_server_config (server_host, smtp_port, imap_port, sieve_port)
                VALUES ($1, $2, $3, $4)
                RETURNING config_id
                """,
                host, smtp_port, imap_port, sieve_port
            )
            await db_session.execute(
                """
                INSERT INTO domains (domain, mail_server_config_id, is_active)
                VALUES ($1, $2, $3)
                """,
                domain, config_id, is_active
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
    is_active: bool,
    server_host: Optional[str] = None,
    smtp_port: Optional[int] = None,
    imap_port: Optional[int] = None,
    sieve_port: Optional[int] = None,
    smtp_server: Optional[str] = None,
    imap_server: Optional[str] = None,
    sieve_server: Optional[str] = None
) -> None:
    """
    Admin function to edit an existing domain: its mail server configuration (created if it had none) and is_active
    """
    host = _admin_required_mail_server(server_host, smtp_server, imap_server, sieve_server, smtp_port, imap_port, sieve_port)

    try:
        async with db_session.transaction():
            config_id = await db_session.fetchval(
                "SELECT mail_server_config_id FROM domains WHERE domain = $1 FOR UPDATE", domain
            )

            if config_id is None:
                config_id = await db_session.fetchval(
                    """
                    INSERT INTO mail_server_config (server_host, smtp_port, imap_port, sieve_port)
                    VALUES ($1, $2, $3, $4)
                    RETURNING config_id
                    """,
                    host, smtp_port, imap_port, sieve_port
                )
            else:
                await db_session.execute(
                    """
                    UPDATE mail_server_config
                    SET server_host = $2, smtp_port = $3, imap_port = $4, sieve_port = $5, updated_at = NOW()
                    WHERE config_id = $1
                    """,
                    config_id, host, smtp_port, imap_port, sieve_port
                )
            await db_session.execute(
                "UPDATE domains SET mail_server_config_id = $2, is_active = $3 WHERE domain = $1", domain, config_id, is_active
            )

    except All_Exceptions:
        raise

    except Exception as e:
        logging.error(f"Error while editing domain: {e}", exc_info=True)
        raise All_Exceptions(
            message=f"Failed to edit domain: {e}",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY
        )


async def admin_delete_domain(db_session: PgSession, domain: str) -> None:
    """
    Admin function to delete a domain from the database (and its mail server configuration).
    Its users, their contacts and templates are deleted with it (ON DELETE CASCADE).
    """
    try:
        async with db_session.transaction():
            config_id = await db_session.fetchval(
                "DELETE FROM domains WHERE domain = $1 RETURNING mail_server_config_id", domain
            )
            if config_id is not None:
                await db_session.execute("DELETE FROM mail_server_config WHERE config_id = $1", config_id)

    except Exception as e:
        logging.error(f"Error while deleting domain: {e}", exc_info=True)
        raise All_Exceptions(
            message=f"Failed to delete domain: {e}",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY
        )


ADMIN_DOMAIN_COLUMNS = """
    d.domain, d.is_active, d.created_at, d.mail_server_config_id,
    c.server_host, c.smtp_port, c.imap_port, c.sieve_port
"""


def _admin_domain_row(row) -> dict:
    """
    A domain for the admin API. The old fields smtp_server, imap_server and sieve_server are kept for the admin screen
    (one host for all three).
    """
    return {
        "domain": row["domain"],
        "server_host": row["server_host"],
        "smtp_server": row["server_host"],
        "smtp_port": row["smtp_port"],
        "imap_server": row["server_host"],
        "imap_port": row["imap_port"],
        "sieve_server": row["server_host"],
        "sieve_port": row["sieve_port"],
        "is_active": row["is_active"],
        "created_at": _ts(row["created_at"])
    }


async def admin_get_all_domains(db_session: PgSession, page: int, size: int, search_query: str) -> dict:
    """
    Admin function to get all domains from the database with pagination
    """
    total_count = await db_session.fetchval(
        """
        SELECT COUNT(*) FROM domains WHERE domain ILIKE $1
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
        f"""
        SELECT {ADMIN_DOMAIN_COLUMNS}
        FROM domains d
        LEFT JOIN mail_server_config c ON c.config_id = d.mail_server_config_id
        WHERE d.domain ILIKE $3
        ORDER BY d.created_at DESC
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
        "data": [_admin_domain_row(row) for row in rows]
    }


async def admin_get_domain_info(db_session: PgSession, domain: str) -> dict:
    """
    Admin function to get information about a specific domain
    """
    row = await db_session.fetchrow(
        f"""
        SELECT {ADMIN_DOMAIN_COLUMNS}
        FROM domains d
        LEFT JOIN mail_server_config c ON c.config_id = d.mail_server_config_id
        WHERE d.domain = $1
        """,
        domain
    )
    return _admin_domain_row(row) if row else {}


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
