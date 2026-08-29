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


from src.utils.base.libraries import logging, IMAP4_SSL, email, status, re, datetime, calendar
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
        store_status, _ = connection.uid(
            'STORE',
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

    uids: dict[str, str] = {}
    for message_id in message_ids:
        status_, data = imap_connection.search(None, f'(HEADER Message-ID "{message_id}")')
        if status_ == "OK" and data != [b'']:
            for uid in data[0].split():
                uids[uid.decode()] = message_id

    if not uids:
        raise All_Exceptions(
            message="No emails found with the specified Message-IDs",
            status_code=status.HTTP_204_NO_CONTENT
        )

    findings = get_email_details(
        connection=imap_connection,
        id_range=",".join(uid for uid in uids.keys()),
        folder_path=folder,
        full_headers=True
    )

    # Add a new key 'Message-ID' to each finding
    for finding in findings:
        uid = finding['id']
        finding['Message-ID'] = uids.get(uid, None)

    return findings
