"""
This module provides functions to connect to an IMAP server,
list folders, and fetch emails from a specific folder.
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


from src.utils.base.libraries import logging, IMAP4_SSL, parse_fetch_response, BodyData, email, status, re, datetime, calendar, base64, quopri, Optional
from src.utils.models import All_Exceptions, SearchMail


def compress_ranges(nums: list[int]) -> str:
    """
    Compress a list of integers into a string of ranges.

    Args:
        nums (list[int]): A list of integers to compress.

    Returns:
        str: A string representing the compressed ranges.
    """
    nums = sorted(set(nums))
    ranges = []

    start = prev = nums[0]

    for n in nums[1:]:
        if n == prev + 1:
            prev = n
        else:
            ranges.append(f"{start}:{prev}" if start != prev else str(start))
            start = prev = n

    ranges.append(f"{start}:{prev}" if start != prev else str(start))

    return ",".join(ranges)


def list_folders(connection: IMAP4_SSL) -> list[dict]:
    """
    List all folders in the mailbox, returning dicts with:
      - flags (list[str])
      - delimiter (str | None)
      - folder_name (str)
      - unread_count (int)
      - status (dict)
    """
    try:
        connection_status, folders = connection.list()
        if connection_status != "OK" or not folders:
            logging.error(f"Failed to list folders: {connection_status}")
            return []

        list_re = re.compile(
            r'^\((?P<flags>.*?)\)\s+"?(?P<delimiter>[^"]+)"?\s+(?P<folder_name>.+)$'
        )

        processed = []

        for folder in folders:
            try:
                decoded_folder = folder.decode("utf-8", errors="replace")

                match = list_re.match(decoded_folder)
                if not match:
                    continue

                flags = [
                    flag.lstrip("\\")
                    for flag in match.group("flags").split()
                ]

                delimiter = match.group("delimiter").strip('"')

                folder_name = match.group("folder_name").strip()

                if (
                    folder_name.startswith('"')
                    and folder_name.endswith('"')
                ):
                    folder_name = folder_name[1:-1]

                # Single STATUS call instead of SELECT + SEARCH
                status_cmd = "(UNSEEN UIDNEXT UIDVALIDITY MESSAGES)"
                status_result, status_data = connection.status(
                    f'"{folder_name}"',
                    status_cmd
                )

                unread_mail_count = 0
                parsed_status = {}

                if (
                    status_result == "OK"
                    and status_data
                    and status_data[0]
                ):
                    status_string = (
                        status_data[0].decode("utf-8", errors="replace")
                        if isinstance(status_data[0], bytes)
                        else str(status_data[0])
                    )

                    pairs = {
                        k: int(v)
                        for k, v in re.findall(
                            r'(\w+)\s+(\d+)',
                            status_string
                        )
                    }

                    unread_mail_count = pairs.get("UNSEEN", 0)

                    parsed_status = {
                        k: v
                        for k, v in pairs.items()
                        if k in {"UIDNEXT", "UIDVALIDITY", "MESSAGES"}
                    }

                processed.append(
                    {
                        "flags": flags,
                        "delimiter": (
                            None
                            if delimiter == "NIL"
                            else delimiter
                        ),
                        "folder_name": folder_name,
                        "unread_count": unread_mail_count,
                        "status": parsed_status,
                    }
                )

            except Exception:
                logging.exception(
                    "Failed processing folder %s",
                    folder
                )

        return processed

    except Exception:
        logging.exception("Error listing mailboxes")
        return []


def parse_acl_response(folder_name: str, acl_entry: str) -> list[dict]:
    """
    Parses the IMAP ACL response for a given folder.
    
    Args:
        folder_name (str): The folder name (with or without quotes).
        acl_entry (str): The ACL entry string which contains user and permissions.

    Returns:
        list[dict]: A list of dictionaries containing 'user' and 'permissions'.
    """
    try:
        # Remove the folder name safely
        cleaned_folder_name = folder_name.strip('"')
        acl_entry = acl_entry.replace(f'{cleaned_folder_name}', "").strip()

        # Split the rest into parts (user1 perms1 user2 perms2 ...)
        parts = acl_entry.split()

        # Sanity check: parts should always come in pairs
        if len(parts) % 2 != 0:
            raise ValueError("Malformed ACL data: unmatched user/permissions pair.")

        entries = []
        for i in range(0, len(parts), 2):
            entry = {
                "user": parts[i],
                "permissions": parts[i + 1]
            }
            entries.append(entry)

        return entries

    except Exception as e:
        logging.error(f"Error parsing ACL response for {folder_name}: {e}", exc_info=True)
        return []


def parse_imap_response(imap_response: tuple, operation_name: str) -> str:
    """
    Parse IMAP response tuple (status, data) and return the decoded data.
    This function checks if the response is OK and if data is not empty.
    Args:
        imap_response (tuple): The IMAP response tuple.
        operation_name (str): The name of the operation for logging.
    Returns:
        str: The decoded response data.
    Raises:
        Exception: If the response is not OK or if data is empty.
    """
    if not imap_response:
        raise All_Exceptions(
            message=f"Failed to parse IMAP response: {operation_name} returned None",
            status_code=status.HTTP_204_NO_CONTENT
        )
    
    imap_status, data = imap_response
    if imap_status != "OK":
        raise All_Exceptions(
            message=f"Failed to parse IMAP response: {operation_name} did not return OK: {imap_status}; {str(data)}",
            status_code=status.HTTP_424_FAILED_DEPENDENCY
        )

    if not data or not isinstance(data, list):
        raise All_Exceptions(
            message=f"Failed to parse IMAP response: {operation_name} returned empty data: {str(data)}",
            status_code=status.HTTP_409_CONFLICT
        )

    return data[0].decode('utf-8')


def email_headers_cleanup(headers: dict) -> dict:
    """
    Clean up email headers by decoding any encoded words and stripping whitespace.
    Args:
        headers (dict): The original email headers.
    Returns:
        dict: The cleaned-up email headers.
    """
    cleaned_headers = {}

    for key, value in headers.items():
        if isinstance(value, str):
            try:
                # Decode any encoded words in the header value
                decoded_value = email.header.decode_header(value)

                parts = []
                for part, encoding in decoded_value:
                    if not isinstance(part, bytes):
                        parts.append(part)
                        continue

                    # Try the declared charset first, then fall back to utf-8;
                    # senders sometimes mislabel or corrupt the charset.
                    for charset in (encoding, 'utf-8'):
                        if not charset:
                            continue
                        try:
                            parts.append(part.decode(charset))
                            break
                        except (UnicodeDecodeError, LookupError):
                            continue
                    else:
                        parts.append(part.decode('utf-8', errors='replace'))

                cleaned_value = ''.join(parts).strip()

            except Exception as e:
                logging.warning(f"Failed to decode header {key!r}, using raw value: {e}")
                cleaned_value = value

            # Replace any characters that can't be encoded in UTF-8 to avoid JSON serialization issues
            cleaned_headers[key] = cleaned_value.encode('utf-8', errors='replace').decode('utf-8')

        else:
            cleaned_headers[key] = value  # Non-string values are left as is

    return cleaned_headers


def _part_has_attachment(part, parent_sub_type: str = "") -> bool:
    """
    Walk a parsed BODYSTRUCTURE (imapclient BodyData) and return True if any part is an attachment.
    A part counts as an attachment if:
        - its Content-Disposition is "attachment", or
        - it is a forwarded email (message/rfc822), or
        - it has a filename/name and is not marked "inline" (inline parts are usually embedded images)
    Except: a part inside multipart/related with a Content-ID is an embedded resource of the html body
    (e.g. Outlook signature images - they have a name but no Content-Disposition), unless it is marked "attachment".
    """
    def _str(value) -> str:
        return value.decode(errors="ignore").lower() if isinstance(value, bytes) else str(value or "").lower()

    if part.is_multipart:
        return any(_part_has_attachment(sub_part, parent_sub_type=_str(part[1])) for sub_part in part[0])

    main_type, sub_type = _str(part[0]), _str(part[1])
    if (main_type, sub_type) == ("message", "rfc822"):
        return True

    # The Content-Disposition position depends on the part type (RFC 3501 - BODYSTRUCTURE)
    if main_type == "text":
        disposition_index = 9
    else:
        disposition_index = 8

    disposition_type, disposition_params = "", None
    if len(part) > disposition_index and isinstance(part[disposition_index], tuple) and part[disposition_index]:
        disposition_type = _str(part[disposition_index][0])
        if len(part[disposition_index]) > 1:
            disposition_params = part[disposition_index][1]

    if disposition_type == "attachment":
        return True

    # Embedded resource of the html body (referenced as "cid:<content_id>")
    if parent_sub_type == "related" and _str(part[3]).strip():
        return False

    # Look for a filename in the disposition params or a name in the content-type params
    has_file_name = False
    for params in (disposition_params, part[2]):
        if isinstance(params, tuple):
            param_keys = [_str(key) for key in params[0::2]]
            if any(key in ("filename", "name") or key.startswith(("filename*", "name*")) for key in param_keys):
                has_file_name = True
                break

    return has_file_name and disposition_type != "inline"


def get_attachment_status(connection: IMAP4_SSL, id_range: str) -> dict[str, bool]:
    """
    Get the attachment status of emails in a range using BODYSTRUCTURE (no message body is downloaded).
    Returns a dictionary with email ids as keys and True/False as values.
    Never raises - on any failure it returns what it could parse (missing ids are treated as no attachment).
    """
    attachment_status = {}
    try:
        resp_status, data = connection.fetch(id_range, '(BODYSTRUCTURE)')
        if resp_status != "OK":
            logging.error(f"Failed to fetch BODYSTRUCTURE for range {id_range}: {resp_status}")
            return attachment_status

        for email_id, fetch_data in parse_fetch_response(data, normalise_times=False, uid_is_key=False).items():
            try:
                attachment_status[str(email_id)] = _part_has_attachment(BodyData.create(fetch_data[b'BODYSTRUCTURE']))
            except Exception as e:
                logging.error(f"Failed to parse BODYSTRUCTURE of email {email_id} in range {id_range}: {e}", exc_info=True)

    except Exception as e:
        logging.error(f"Failed to get attachment status for range {id_range}: {e}", exc_info=True)

    return attachment_status


EMAIL_SORT_KEYS = {
    "date": "DATE",         # Date header of the email (falls back to arrival date if missing)
    "arrival": "ARRIVAL",   # When the email arrived in the mailbox
    "from": "FROM",
    "subject": "SUBJECT",
    "size": "SIZE"
}

EMAIL_FILTER_KEYS = {
    "all": "ALL",
    "unread": "UNSEEN",
    "read": "SEEN",
    "flagged": "FLAGGED",
    "unflagged": "UNFLAGGED"
}


def get_sorted_email_ids(connection: IMAP4_SSL, folder_path: str, sort_by: str, sort_order: str, filter_by: str) -> list[str]:
    """
    Get the email ids of a folder filtered and sorted on the IMAP server (RFC 5256 SORT) - no email data is downloaded.
    Falls back to SEARCH (arrival order) if the server does not support SORT.
    Returns the list of email ids in the requested order.
    """
    connection.select(mailbox=folder_path, readonly=True)

    search_key = EMAIL_FILTER_KEYS[filter_by]

    # Always sort ascending and reverse here for desc - IMAP breaks ties (same date/sender) by mailbox order
    # ascending even with REVERSE, reversing the whole list keeps the newest email first among ties
    try:
        resp_status, data = connection.sort(f"({EMAIL_SORT_KEYS[sort_by]})", "UTF-8", search_key)
        if resp_status == "OK":
            email_ids = data[0].decode().split() if data and data[0] else []
            return email_ids[::-1] if sort_order == "desc" else email_ids
        logging.error(f"IMAP SORT failed for folder {folder_path}: {resp_status}; {data}")

    except Exception as e:
        logging.warning(f"IMAP SORT not available for folder {folder_path}, falling back to SEARCH: {e}")

    # Fallback - SEARCH returns ids in arrival order
    resp_status, data = connection.search(None, search_key)
    if resp_status != "OK":
        raise All_Exceptions(
            message=f"Failed to search emails: {resp_status}; {str(data)}",
            status_code=status.HTTP_424_FAILED_DEPENDENCY
        )

    email_ids = data[0].decode().split() if data and data[0] else []
    return email_ids[::-1] if sort_order == "desc" else email_ids


def get_email_details(connection: IMAP4_SSL, id_range: str, folder_path: str, full_headers: bool) -> list[dict]:
    """
    Get headers and flags of specific emails in a range.
    Returns a dictionary with email ids as keys and email headers and flags as values.
    """
    # Encode folder name to handle special characters
    connection.select(folder_path)

    # Request both headers and flags for a range of emails
    query_string = '(FLAGS BODY.PEEK[HEADER])' if full_headers else '(FLAGS BODY.PEEK[HEADER.FIELDS (FROM TO SUBJECT DATE)])'
    resp_status, data = connection.fetch(id_range, query_string)

    if resp_status == "OK":
        emails = []

        # Iterate through each response part
        for response_part in data:
            if isinstance(response_part, tuple):
                try:
                    # Parse the email header
                    email_message = email.message_from_bytes(response_part[1])
                    email_id = response_part[0].decode().split()[0]  # Extract email ID from response

                    # Extract flags from the same response part
                    flags = []
                    if 'FLAGS' in response_part[0].decode():
                        flags = response_part[0].decode().split('FLAGS (')[1].split(')')[0].split()

                    # Add both headers and flags to the email dictionary
                    email_details = dict(email_message._headers)
                    email_details['FLAGS'] = flags  # Add the flags as a new key-value pair
                    email_details['id'] = email_id  # Add the email ID to the details

                    # Clean up header values by doing basic decoding (e.g., for encoded words)
                    email_details = email_headers_cleanup(headers=email_details)
                    emails.append(email_details)
                except Exception as e:
                    # One malformed message shouldn't fail the whole batch fetch
                    logging.error(f"Skipping unparsable email in range {id_range}: {e}", exc_info=True)

        if not emails:
            raise All_Exceptions(
                message="No emails found in the specified range",
                status_code=status.HTTP_204_NO_CONTENT
            )

        # Add attachment status (separate FETCH so the header parsing above is not affected)
        attachment_status = get_attachment_status(connection=connection, id_range=id_range)
        for email_details in emails:
            email_details['has_attachment'] = attachment_status.get(email_details['id'], False)

        # Return the list of email details
        return emails

    else:
        raise All_Exceptions(
            message=f"Failed to fetch email details: {resp_status}; {str(data)}",
            status_code=status.HTTP_424_FAILED_DEPENDENCY
        )


def get_raw_email(connection: IMAP4_SSL, email_id: str, folder: str, read_only: bool) -> bytes:
    """
    Get raw email by ID
    Returns the raw email content as bytes
    """
    # Encode folder name to handle special characters
    encoded_folder = folder.encode('utf-7')
    connection.select(encoded_folder, readonly=read_only)

    # Fetch the raw email by ID
    fetch_status, data = connection.fetch(email_id, '(RFC822)')
    if fetch_status == "OK":
        return data[0][1]

    raise All_Exceptions(
        message=f"Failed to fetch raw email: {fetch_status}; {str(data)}",
        status_code=status.HTTP_424_FAILED_DEPENDENCY
    )


def _bs_str(value) -> str:
    """Convert a BODYSTRUCTURE value (bytes / str / None) to str"""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return "" if value is None else str(value)


def _bs_params(params) -> dict:
    """
    Convert BODYSTRUCTURE params (key, value, key, value ...) to a dict with lower-case keys.
    Decodes RFC 2231 (filename*=utf-8''...) and RFC 2047 (=?utf-8?b?...?=) encoded values.
    """
    if not isinstance(params, tuple):
        return {}

    raw_params = [(_bs_str(key).lower(), _bs_str(value)) for key, value in zip(params[0::2], params[1::2])]
    result = {}
    try:
        # decode_params expects the first item to be the main value, it is skipped in the result
        for key, value in email.utils.decode_params([("", "")] + raw_params)[1:]:
            result[key] = email.utils.unquote(email.utils.collapse_rfc2231_value(value))
    except Exception:
        result = dict(raw_params)

    for key, value in result.items():
        if "=?" in value:
            try:
                result[key] = str(email.header.make_header(email.header.decode_header(value)))
            except Exception:
                pass

    return result


def _bs_leaf_parts(part, part_id: str = "") -> list[dict]:
    """
    Flatten a BODYSTRUCTURE (imapclient BodyData) into a list of leaf parts with their IMAP section ids (e.g. "1", "1.2").
    message/rfc822 parts (forwarded emails) are not opened, they are treated as a single part.
    """
    if part.is_multipart:
        leaf_parts = []
        for index, sub_part in enumerate(part[0], start=1):
            leaf_parts.extend(_bs_leaf_parts(sub_part, f"{part_id}.{index}" if part_id else str(index)))
        return leaf_parts

    main_type, sub_type = _bs_str(part[0]).lower(), _bs_str(part[1]).lower()

    # The Content-Disposition position depends on the part type (RFC 3501 - BODYSTRUCTURE)
    if main_type == "text":
        disposition_index = 9
    elif (main_type, sub_type) == ("message", "rfc822"):
        disposition_index = 11
    else:
        disposition_index = 8

    disposition_type, disposition_params = "", {}
    if len(part) > disposition_index and isinstance(part[disposition_index], tuple) and part[disposition_index]:
        disposition_type = _bs_str(part[disposition_index][0]).lower()
        if len(part[disposition_index]) > 1:
            disposition_params = _bs_params(part[disposition_index][1])

    content_params = _bs_params(part[2])
    content_id = _bs_str(part[3]).strip("<>") or None
    encoded_size = part[6] if isinstance(part[6], int) else 0
    encoding = _bs_str(part[5]).lower()

    return [{
        "part_id": part_id or "1",  # A single part email has its body at section 1
        "content_type": f"{main_type}/{sub_type}",
        "charset": content_params.get("charset"),
        "encoding": encoding,
        "filename": disposition_params.get("filename") or content_params.get("name"),
        "disposition": disposition_type or None,
        "content_id": content_id,
        "encoded_size": encoded_size,
        # base64 is ~33% bigger than the real file
        "size": encoded_size * 3 // 4 if encoding == "base64" else encoded_size
    }]


def _part_filename(leaf_part: dict) -> str:
    """Filename of a part, or a generated one if the email does not give one"""
    if leaf_part["filename"]:
        return leaf_part["filename"]
    if leaf_part["content_type"] == "message/rfc822":
        return f"forwarded-{leaf_part['part_id']}.eml"
    return f"attachment-{leaf_part['part_id']}.{leaf_part['content_type'].split('/')[-1]}"


def _decode_part_content(content: bytes, encoding: str) -> bytes:
    """Decode the Content-Transfer-Encoding (base64 / quoted-printable) of a part"""
    if content is None:
        return b""
    if encoding == "base64":
        return base64.b64decode(re.sub(rb"[^A-Za-z0-9+/=]", b"", content) + b"==", validate=False)
    if encoding == "quoted-printable":
        return quopri.decodestring(content)
    return content


def _decode_part_text(content: bytes, charset: str) -> str:
    """Decode text bytes using the charset of the part, fall back to utf-8"""
    for candidate in (charset, "utf-8"):
        if not candidate:
            continue
        try:
            return content.decode(candidate)
        except (UnicodeDecodeError, LookupError):
            continue
    return content.decode("utf-8", errors="replace")


def _fetch_email_structure(connection: IMAP4_SSL, email_id: str, with_headers: bool) -> dict:
    """FETCH the flags, BODYSTRUCTURE and (optionally) the headers of a single email"""
    query_string = "(FLAGS BODYSTRUCTURE BODY.PEEK[HEADER])" if with_headers else "(BODYSTRUCTURE)"
    try:
        resp_status, data = connection.fetch(email_id, query_string)
    except connection.error as e:
        # The IMAP server rejects ids that do not exist in the folder (e.g. "Invalid messageset")
        raise All_Exceptions(
            message=f"Email not found: {email_id}; {e}",
            status_code=status.HTTP_404_NOT_FOUND
        )
    if resp_status != "OK" or not data or data == [None]:
        raise All_Exceptions(
            message=f"Email not found: {email_id}",
            status_code=status.HTTP_404_NOT_FOUND
        )

    for fetch_data in parse_fetch_response(data, normalise_times=False, uid_is_key=False).values():
        if b"BODYSTRUCTURE" in fetch_data:
            return fetch_data

    raise All_Exceptions(
        message=f"Email not found: {email_id}",
        status_code=status.HTTP_404_NOT_FOUND
    )


def get_email_view(connection: IMAP4_SSL, email_id: str, folder: str, mark_as_read: bool) -> dict:
    """
    Get an email for viewing - headers, flags, the text/html body and the list of attachments.
    Only the body parts are downloaded, attachments are NOT downloaded (use get_email_attachment for that).
    """
    connection.select(mailbox=folder, readonly=not mark_as_read)

    fetch_data = _fetch_email_structure(connection=connection, email_id=email_id, with_headers=True)
    leaf_parts = _bs_leaf_parts(BodyData.create(fetch_data[b"BODYSTRUCTURE"]))

    # Body parts are text/plain and text/html parts that are not attachments, everything else is an attachment
    body_parts, attachments = [], []
    for leaf_part in leaf_parts:
        if leaf_part["content_type"] in ("text/plain", "text/html") and leaf_part["disposition"] != "attachment" and not leaf_part["filename"]:
            body_parts.append(leaf_part)
        else:
            attachments.append(leaf_part)

    # Download only the body parts
    body = {"html": None, "text": None}
    if body_parts:
        resp_status, data = connection.fetch(email_id, "(" + " ".join(f"BODY.PEEK[{part['part_id']}]" for part in body_parts) + ")")
        if resp_status != "OK":
            raise All_Exceptions(
                message=f"Failed to fetch email body: {resp_status}; {str(data)}",
                status_code=status.HTTP_424_FAILED_DEPENDENCY
            )
        body_data = next(iter(parse_fetch_response(data, normalise_times=False, uid_is_key=False).values()), {})

        # Join the parts of the same type in order (some emails have more than one text part)
        for body_part in body_parts:
            content = body_data.get(f"BODY[{body_part['part_id']}]".encode())
            text = _decode_part_text(_decode_part_content(content, body_part["encoding"]), body_part["charset"])
            body_type = "html" if body_part["content_type"] == "text/html" else "text"
            body[body_type] = text if body[body_type] is None else body[body_type] + "\n" + text

    if mark_as_read:
        connection.store(email_id, "+FLAGS", "\\Seen")

    # Same header cleanup as the email listing
    email_message = email.message_from_bytes(fetch_data.get(b"BODY[HEADER]") or b"")
    headers = email_headers_cleanup(headers=dict(email_message._headers))

    flags = [_bs_str(flag) for flag in fetch_data.get(b"FLAGS", ())]
    if mark_as_read and "\\Seen" not in flags:
        flags.append("\\Seen")

    return {
        "id": email_id,
        "folder_path": folder,
        "headers": headers,
        "flags": flags,
        "body": body,
        "has_attachment": _part_has_attachment(BodyData.create(fetch_data[b"BODYSTRUCTURE"])),
        "attachments": [
            {
                "part_id": attachment["part_id"],
                "filename": _part_filename(attachment),
                "content_type": attachment["content_type"],
                "size": attachment["size"],
                "content_id": attachment["content_id"],
                # Inline parts (e.g. embedded images) are referenced from the html body as "cid:<content_id>"
                "is_inline": attachment["disposition"] != "attachment" and attachment["content_id"] is not None
            }
            for attachment in attachments
        ]
    }


def get_email_attachment(connection: IMAP4_SSL, email_id: str, folder: str, part_id: str) -> dict:
    """
    Download a single attachment (part) of an email.
    Returns a dict with content (decoded bytes), content_type and filename.
    """
    connection.select(mailbox=folder, readonly=True)

    fetch_data = _fetch_email_structure(connection=connection, email_id=email_id, with_headers=False)
    leaf_parts = {leaf_part["part_id"]: leaf_part for leaf_part in _bs_leaf_parts(BodyData.create(fetch_data[b"BODYSTRUCTURE"]))}
    if part_id not in leaf_parts:
        raise All_Exceptions(
            message=f"Attachment part {part_id} not found in email {email_id}",
            status_code=status.HTTP_404_NOT_FOUND
        )
    attachment = leaf_parts[part_id]

    resp_status, data = connection.fetch(email_id, f"(BODY.PEEK[{part_id}])")
    if resp_status != "OK":
        raise All_Exceptions(
            message=f"Failed to fetch attachment: {resp_status}; {str(data)}",
            status_code=status.HTTP_424_FAILED_DEPENDENCY
        )
    part_data = next(iter(parse_fetch_response(data, normalise_times=False, uid_is_key=False).values()), {})

    return {
        "content": _decode_part_content(part_data.get(f"BODY[{part_id}]".encode()), attachment["encoding"]),
        "content_type": attachment["content_type"],
        "filename": _part_filename(attachment)
    }


def parse_quota_response(quota_response: str) -> dict:
    """
    Parses a response like: "User quota" (STORAGE 11850 1048576)
    Returns a dict: {'used_kb': 11850, 'total_kb': 1048576, 'used_mb': 11.58, 'total_mb': 1024.0, 'used_percent': 1.13}
    """
    # Example: '"User quota" (STORAGE 11850 1048576)'
    match = re.search(r'STORAGE\s+(\d+)\s+(\d+)', quota_response)
    if not match:
        return {
            'used_kb': 0,
            'total_kb': 0,
            'used_mb': 0.0,
            'total_mb': 0.0,
            'used_percent': 0.0
        }

    used_kb = int(match.group(1))
    total_kb = int(match.group(2))
    return {
        'used_kb': used_kb,
        'total_kb': total_kb,
        'used_mb': round(used_kb / 1024, 2),
        'total_mb': round(total_kb / 1024, 2),
        'used_percent': round((used_kb / total_kb) * 100, 2)
    }


def move_multiple_emails(connection: IMAP4_SSL, email_ids: list[str], source_folder: str, dest_folder: str) -> dict:
    """
    Move multiple emails from source_folder to dest_folder
    """
    # Select the source folder
    select_status, _ = connection.select(mailbox=source_folder, readonly=False)
    if select_status != 'OK':
        return {"error": f"Failed to select source folder: {source_folder}"}

    results = {}
    for email_id in map(str, email_ids):
        try:
            copy_status, _ = connection.copy(email_id, dest_folder)
            if copy_status != 'OK':
                results[email_id] = "Copy failed"
                continue

            store_status, _ = connection.store(email_id, '+FLAGS', '\\Deleted')
            if store_status != 'OK':
                results[email_id] = "Failed to mark as deleted"
                continue

            results[email_id] = "Moved successfully"

        except Exception as e:
            results[email_id] = f"Error: {str(e)}"

    expunge_status, _ = connection.expunge()
    if expunge_status != 'OK':
        results["expunge"] = "Failed to expunge deleted emails"

    return results


def copy_multiple_emails(connection: IMAP4_SSL, email_ids: list[str], source_folder: str, dest_folder: str) -> dict:
    """
    Copy multiple emails from source_folder to dest_folder
    """
    # Select the source folder
    select_status, _ = connection.select(mailbox=source_folder, readonly=True)
    if select_status != 'OK':
        return {"error": f"Failed to select source folder: {source_folder}"}

    results = {}
    for email_uid in map(str, email_ids):
        try:
            copy_status, _ = connection.copy(email_uid, dest_folder)
            if copy_status != 'OK':
                results[email_uid] = "Copy failed"
                continue

            results[email_uid] = "Copied successfully"

        except Exception as e:
            results[email_uid] = f"Error: {str(e)}"

    return results


def mark_emails_as_read(connection: IMAP4_SSL, folder: str, email_ids: list[int]) -> dict:
    """
    Mark specified emails in the folder as read.
    """
    # Select the folder
    select_status, _ = connection.select(mailbox=folder, readonly=False)
    if select_status != 'OK':
        raise All_Exceptions(
            message=f"Failed to select folder: {folder}",
            status_code=status.HTTP_424_FAILED_DEPENDENCY
        )

    results = {}
    for email_uid in map(str, email_ids):
        try:
            store_status, _ = connection.store(email_uid, '+FLAGS', '\\Seen')
            if store_status != 'OK':
                results[email_uid] = "Failed to mark as read"
                continue

            results[email_uid] = "Marked as read"

        except Exception as e:
            results[email_uid] = f"Error: {str(e)}"

    return results


def mark_emails_as_unseen(connection: IMAP4_SSL, folder: str, email_ids: list[int]) -> dict:
    """
    Mark specified emails in the folder as unread.
    """
    # Select the folder
    select_status, _ = connection.select(mailbox=folder, readonly=False)
    if select_status != 'OK':
        raise All_Exceptions(
            message=f"Failed to select folder: {folder}",
            status_code=status.HTTP_424_FAILED_DEPENDENCY
        )

    results = {}
    for email_uid in map(str, email_ids):
        try:
            store_status, _ = connection.store(email_uid, '-FLAGS', '\\Seen')
            if store_status != 'OK':
                results[email_uid] = "Failed to mark as unread"
                continue

            results[email_uid] = "Marked as unread"

        except Exception as e:
            results[email_uid] = f"Error: {str(e)}"

    return results


def mark_emails_as_flagged(connection: IMAP4_SSL, folder: str, email_ids: list[int]) -> dict:
    """
    Mark specified emails in the folder as flagged.
    """
    # Select the folder
    select_status, _ = connection.select(mailbox=folder, readonly=False)
    if select_status != 'OK':
        raise All_Exceptions(
            message=f"Failed to select folder: {folder}",
            status_code=status.HTTP_424_FAILED_DEPENDENCY
        )

    results = {}
    for email_uid in map(str, email_ids):
        try:
            store_status, _ = connection.store(email_uid, '+FLAGS', '\\Flagged')
            if store_status != 'OK':
                results[email_uid] = "Failed to mark as flagged"
                continue

            results[email_uid] = "Marked as flagged"

        except Exception as e:
            results[email_uid] = f"Error: {str(e)}"

    return results


def mark_emails_as_unflagged(connection: IMAP4_SSL, folder: str, email_ids: list[int]) -> dict:
    """
    Mark specified emails in the folder as unflagged.
    """
    # Select the folder
    select_status, _ = connection.select(mailbox=folder, readonly=False)
    if select_status != 'OK':
        raise All_Exceptions(
            message=f"Failed to select folder: {folder}",
            status_code=status.HTTP_424_FAILED_DEPENDENCY
        )

    results = {}
    for email_uid in map(str, email_ids):
        try:
            store_status, _ = connection.store(email_uid, '-FLAGS', '\\Flagged')
            if store_status != 'OK':
                results[email_uid] = "Failed to mark as unflagged"
                continue

            results[email_uid] = "Marked as unflagged"

        except Exception as e:
            results[email_uid] = f"Error: {str(e)}"

    return results


def delete_emails_permanently(connection: IMAP4_SSL, folder: str, email_ids: list[int]) -> dict:
    """
    Permanently delete specified emails in the folder.
    """
    # Select the folder
    select_status, _ = connection.select(mailbox=folder, readonly=False)
    if select_status != 'OK':
        raise All_Exceptions(
            message=f"Failed to select folder: {folder}",
            status_code=status.HTTP_424_FAILED_DEPENDENCY
        )

    if not email_ids:
        return {"status": "No emails provided"}

    try:
        # Convert list -> IMAP ranges
        # Example: 1:10,15:20,25
        uid_set = compress_ranges(email_ids)

        # Bulk delete in ONE command

        store_status, _ = connection.store(
            uid_set,
            '+FLAGS',
            r'(\Deleted)'
        )

        if store_status != 'OK':
            return {"status": "Failed to mark emails deleted", "uid_set": uid_set}

        # Permanently remove
        expunge_status, _ = connection.expunge()

        if expunge_status != 'OK':
            return {"status": "Expunge failed", "uid_set": uid_set, "expunge": str(expunge_status)}

        return {
            "status": "success",
            "expunge": str(expunge_status),
            "deleted_count": len(email_ids),
            "uid_set": uid_set
        }

    except Exception as e:
        return {
            "status": "error",
            "message": str(e)
        }


# Folder names used for Trash / Spam when the server does not mark them with special-use flags (RFC 6154)
TRASH_AND_JUNK_FOLDER_NAMES = {"trash", "deleted", "deleted items", "deleted messages", "bin", "junk", "spam", "junk e-mail", "junk email", "bulk mail"}


def is_trash_or_junk_folder(connection: IMAP4_SSL, folder: str) -> Optional[bool]:
    """
    Check if a folder is a Trash or Spam/Junk folder - by its special-use flag (\\Trash, \\Junk),
    or by its name if the server does not set these flags.
    Returns None if the folder does not exist.
    """
    # LIST wildcards would match other folders
    if "*" in folder or "%" in folder:
        return False

    resp_status, data = connection.list('""', _imap_quote(folder))
    if resp_status != "OK" or not data or data[0] is None:
        return None

    entry = data[0].decode("utf-8", errors="replace") if isinstance(data[0], bytes) else str(data[0])
    match = re.match(r'^\((?P<flags>.*?)\)\s+(?P<delimiter>NIL|"(?:[^"\\]|\\.)*")\s+', entry)
    if not match:
        return None

    flags = {flag.lower() for flag in match.group("flags").split()}
    if flags & {"\\trash", "\\junk"}:
        return True

    # By name only for top level folders (or directly under INBOX) - a user's own "Projects/Trash" is not the Trash
    delimiter = match.group("delimiter").strip('"').replace("\\\\", "\\")
    folder_parts = folder.split(delimiter) if delimiter and delimiter != "NIL" else [folder]
    if len(folder_parts) == 2 and folder_parts[0].upper() == "INBOX":
        folder_parts = folder_parts[1:]
    return len(folder_parts) == 1 and folder_parts[0].strip().lower() in TRASH_AND_JUNK_FOLDER_NAMES


def mark_folder_as_read(connection: IMAP4_SSL, folder: str) -> int:
    """
    Mark all unread emails in a folder as read.
    Only the emails that are unread right now are marked (an email arriving at the same time stays unread).
    Returns the number of emails marked as read.
    """
    select_status, _ = connection.select(mailbox=_imap_quote(folder), readonly=False)
    if select_status != "OK":
        raise All_Exceptions(
            message=f"Folder not found: {folder}",
            status_code=status.HTTP_404_NOT_FOUND
        )

    resp_status, data = connection.search(None, "UNSEEN")
    if resp_status != "OK":
        raise All_Exceptions(
            message=f"Failed to search unread emails: {resp_status}; {str(data)}",
            status_code=status.HTTP_424_FAILED_DEPENDENCY
        )

    unread_ids = [int(email_id) for email_id in data[0].split()] if data and data[0] else []
    if not unread_ids:
        return 0

    store_status, data = connection.store(compress_ranges(unread_ids), "+FLAGS.SILENT", "(\\Seen)")
    if store_status != "OK":
        raise All_Exceptions(
            message=f"Failed to mark emails as read: {store_status}; {str(data)}",
            status_code=status.HTTP_424_FAILED_DEPENDENCY
        )

    return len(unread_ids)


def empty_folder(connection: IMAP4_SSL, folder: str) -> int:
    """
    Permanently delete all emails in a folder (for emptying Trash / Spam).
    The caller must check that the folder is a Trash / Spam folder (is_trash_or_junk_folder).
    Returns the number of emails deleted.
    """
    select_status, data = connection.select(mailbox=_imap_quote(folder), readonly=False)
    if select_status != "OK":
        raise All_Exceptions(
            message=f"Folder not found: {folder}",
            status_code=status.HTTP_404_NOT_FOUND
        )

    email_count = int(data[0]) if data and data[0] else 0
    if email_count == 0:
        return 0

    store_status, data = connection.store("1:*", "+FLAGS.SILENT", "(\\Deleted)")
    if store_status != "OK":
        raise All_Exceptions(
            message=f"Failed to mark emails as deleted: {store_status}; {str(data)}",
            status_code=status.HTTP_424_FAILED_DEPENDENCY
        )

    expunge_status, data = connection.expunge()
    if expunge_status != "OK":
        raise All_Exceptions(
            message=f"Failed to delete emails: {expunge_status}; {str(data)}",
            status_code=status.HTTP_424_FAILED_DEPENDENCY
        )

    # EXPUNGE returns one id per deleted email
    return len([email_id for email_id in data if email_id]) if data and data != [None] else email_count


def _build_search_criteria(query: dict) -> str:
    """
    Returns a single valid IMAP search criteria string (parenthesized).
    - For has_words: uses BODY with the full phrase (joined with spaces) to avoid stray tokens.
    - does_not_have_words: wraps each phrase with NOT (BODY "phrase").
    - size: supports simple comparators using LARGER / SMALLER.
    - date_within: expects "YYYY-MM-DD" and converts to "DD-Mon-YYYY" and uses ON.
    """
    parts = []

    if "from" in query and query["from"]:
        parts.append(f'FROM "{query["from"]}"')

    if "to" in query and query["to"]:
        parts.append(f'TO "{query["to"]}"')

    if "subject" in query and query["subject"]:
        parts.append(f'SUBJECT "{query["subject"]}"')

    # size: IMAP supports LARGER n (size > n) and SMALLER n (size < n)
    if "size" in query and query["size"]:
        comp = query["size"].get("comparator", "")
        size_val = int(query["size"].get("size", 0))
        if comp in (">", "LARGER"):
            parts.append(f'LARGER {size_val}')
        elif comp in ("<", "SMALLER"):
            parts.append(f'SMALLER {size_val}')
        elif comp == "=":
            # exact size equality isn't directly supported; approximate by LARGER size-1 SMALLER size+1
            parts.append(f'LARGER {max(0, size_val-1)}')
            parts.append(f'SMALLER {size_val+1}')
        else:
            # If comparator provided as ">" etc, handled above; otherwise ignore/skip
            pass

    # date: expect ISO 8601 format. Use ON or SINCE per need. Here we'll use ON for exact date.
    if "date_on" in query and query["date_on"]:
        try:
            dt = datetime.fromisoformat(query["date_on"])
            cal_date = calendar.month_abbr[dt.month]
            imap_date = f"{dt.day:02d}-{cal_date}-{dt.year}"
            parts.append(f'ON {imap_date}')
        except Exception:
            # fallback: ignore date if parsing fails
            pass

    if "date_since" in query and query["date_since"]:
        try:
            dt = datetime.fromisoformat(query["date_since"])
            cal_date = calendar.month_abbr[dt.month]
            imap_date = f"{dt.day:02d}-{cal_date}-{dt.year}"
            parts.append(f'SINCE {imap_date}')
        except Exception:
            # fallback: ignore date if parsing fails
            pass

    if not parts:
        return "ALL"

    # join with spaces and parenthesize (safe)
    criteria = "(" + " ".join(parts) + ")"
    return criteria


def _paginate_sorted_search(connection: IMAP4_SSL, search_criteria: SearchMail, data: list) -> dict:
    """Paginate the result of an IMAP SORT for search_emails, keeping the sorted order in the result"""
    # Sorted ascending on the server, reversed here for desc so ties keep the newest email first
    email_ids = data[0].decode().split() if data and data[0] else []
    if search_criteria.sort_order != "asc":
        email_ids = email_ids[::-1]

    if not email_ids:
        return {
            "total_count": 0,
            "folder_path": search_criteria.folder,
            "data": []
        }

    page, limit = search_criteria.page or 1, search_criteria.limit or 50
    page_email_ids = email_ids[(page - 1) * limit: page * limit]
    if not page_email_ids:
        return {
            "total_count": len(email_ids),
            "folder_path": search_criteria.folder,
            "data": []
        }

    email_details = get_email_details(
        connection=connection,
        id_range=",".join(page_email_ids),
        folder_path=search_criteria.folder,
        full_headers=search_criteria.full_headers
    )

    # IMAP FETCH returns emails in id order, put them back in the sorted order
    sorted_position = {email_id: position for position, email_id in enumerate(page_email_ids)}
    email_details.sort(key=lambda email_detail: sorted_position.get(email_detail["id"], len(sorted_position)))

    return {
        "total_count": len(email_ids),
        "folder_path": search_criteria.folder,
        "data": email_details
    }


def search_emails(connection: IMAP4_SSL, search_criteria: SearchMail) -> dict:
    """
    Search Emails and return results
    """
    search_query = _build_search_criteria(
        query={
            "from": search_criteria.from_,
            "to": search_criteria.to,
            "subject": search_criteria.subject,
            "size": {
                "comparator": search_criteria.size.comparator,
                "size": search_criteria.size.size
            } if search_criteria.size else None,
            "date_on": search_criteria.date_on,
            "date_since": search_criteria.date_since
        }
    )

    connection.select(mailbox=search_criteria.folder, readonly=True)

    # Sorted search (only when requested) - the whole result is sorted on the IMAP server before pagination
    if search_criteria.sort_by:
        try:
            resp_status, data = connection.sort(f"({EMAIL_SORT_KEYS[search_criteria.sort_by]})", "UTF-8", search_query)
            if resp_status == "OK":
                return _paginate_sorted_search(connection=connection, search_criteria=search_criteria, data=data)
            logging.error(f"IMAP SORT failed for search in folder {search_criteria.folder}: {resp_status}; {data}")
        except Exception as e:
            logging.warning(f"IMAP SORT not available for search in folder {search_criteria.folder}, using the old behaviour: {e}")

    result = connection.search(None, search_query)

    if result[0] != "OK":
        return {}

    all_results = []
    for nums in result[1:]:
        all_results.extend(nums)

    # If no emails found, return empty
    if not all_results or all_results == [b'']:
        return {
            "total_count": 0,
            "folder_path": search_criteria.folder,
            "data": []
        }

    all_search_ids = []
    for ids_str in all_results:
        ids_str: bytes
        all_search_ids.extend(int(num) for num in ids_str.split())

    # Handle the pagination
    if search_criteria.page and search_criteria.limit:
        start = (search_criteria.page - 1) * search_criteria.limit
        end = start + search_criteria.limit
        all_search_ids.sort(reverse=True)  # Sort in descending order to get latest emails first
        search_ids = all_search_ids[start:end]

    return {
        "total_count": len(all_search_ids),
        "folder_path": search_criteria.folder,
        "data": get_email_details(
            connection=connection,
            id_range=",".join(str(id) for id in search_ids),
            folder_path=search_criteria.folder,
            full_headers=search_criteria.full_headers
        )
    }


def get_email_details_by_message_id(imap_connection: IMAP4_SSL, message_ids: list[str], folder: str) -> list[dict]:
    """
    Fetch email details by Message-ID
    """
    imap_connection.select(folder, readonly=True)

    # Search all the Message-IDs in one go (the folder is scanned once instead of once per Message-ID)
    email_ids = _search_message_ids(imap_connection=imap_connection, message_ids=message_ids)

    if not email_ids:
        raise All_Exceptions(
            message="No emails found with the specified Message-IDs",
            status_code=status.HTTP_204_NO_CONTENT
        )

    findings = get_email_details(
        connection=imap_connection,
        id_range=",".join(email_ids),
        folder_path=folder,
        full_headers=True
    )

    # Add a new key 'Message-ID' to each finding (the requested Message-ID it was found by)
    uids = _map_findings_to_message_ids(findings=findings, message_ids=message_ids)
    if uids is None:
        # Could not match every finding from its headers - use the per Message-ID search (old behaviour)
        uids = {}
        for message_id in message_ids:
            status_, data = imap_connection.search(None, f'(HEADER Message-ID {_imap_quote(message_id)})')
            if status_ == "OK" and data != [b'']:
                for uid in data[0].split():
                    uids[uid.decode()] = message_id

    for finding in findings:
        uid = finding['id']
        finding['Message-ID'] = uids.get(uid, None)

    return findings


def _imap_quote(value: str) -> str:
    """Quote a string for an IMAP command (escape backslash and double quote)"""
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _search_message_ids(imap_connection: IMAP4_SSL, message_ids: list[str], chunk_size: int = 50) -> list[str]:
    """
    Search emails by Message-ID with a single SEARCH per chunk of Message-IDs (OR of all of them).
    Returns the email ids (sorted ascending, no duplicates).
    """
    unique_message_ids = list(dict.fromkeys(message_ids))
    email_ids = set()

    for start in range(0, len(unique_message_ids), chunk_size):
        search_terms = [f"HEADER Message-ID {_imap_quote(message_id)}" for message_id in unique_message_ids[start:start + chunk_size]]

        # IMAP OR takes 2 keys: "OR a OR b c" matches a, b or c
        search_query = search_terms[-1]
        for search_term in reversed(search_terms[:-1]):
            search_query = f"OR {search_term} {search_query}"

        status_, data = imap_connection.search(None, f"({search_query})")
        if status_ == "OK" and data and data[0]:
            email_ids.update(data[0].decode().split())

    return sorted(email_ids, key=int)


def _map_findings_to_message_ids(findings: list[dict], message_ids: list[str]) -> Optional[dict[str, str]]:
    """
    Match each finding to the requested Message-ID it was found by, using its Message-ID header.
    IMAP HEADER search is a case-insensitive substring match, same is done here - if more than one requested
    Message-ID matches, the last one wins (same as the per Message-ID search).
    Returns None if any finding can not be matched.
    """
    uids = {}
    for finding in findings:
        header_value = next((str(value) for key, value in finding.items() if key.lower() == "message-id"), "").lower()
        matched_message_id = None
        for message_id in message_ids:
            if message_id.lower() in header_value:
                matched_message_id = message_id
        if matched_message_id is None:
            return None
        uids[finding['id']] = matched_message_id

    return uids
