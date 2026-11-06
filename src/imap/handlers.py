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


from src.utils.base.libraries import logging, IMAP4_SSL, parse_fetch_response, BodyData, email, status, re, datetime, timezone, calendar, base64, quopri, time, Optional
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


def _imap_command(connection: IMAP4_SSL, use_uid: bool, command: str, *args):
    """
    Run an IMAP command (FETCH, STORE, COPY, MOVE) on email ids.
    use_uid=True: the ids are UIDs (UID FETCH / UID STORE ...) - a UID never changes when other emails are deleted or moved.
    use_uid=False: the ids are sequence numbers (old behaviour).
    """
    if use_uid:
        return connection.uid(command, *args)
    return getattr(connection, command.lower())(*args)


def _server_capabilities(connection: IMAP4_SSL) -> set[str]:
    """
    Capabilities of the IMAP server after login (e.g. MOVE, UIDPLUS, THREAD=REFERENCES).
    imaplib only keeps the capabilities sent before login, so ask the server again (once per connection).
    """
    if getattr(connection, "_post_login_capabilities", None) is None:
        capabilities = set()
        try:
            resp_status, data = connection.capability()
            if resp_status == "OK" and data and data[0]:
                capabilities = {capability.upper() for capability in data[0].decode(errors="ignore").split()}
        except Exception as e:
            logging.warning(f"Failed to get IMAP capabilities: {e}")
        connection._post_login_capabilities = capabilities
    return connection._post_login_capabilities


def _expunge_uids(connection: IMAP4_SSL, uids: list) -> tuple:
    """
    Expunge only the given UIDs (UID EXPUNGE - RFC 4315 UIDPLUS), so other emails marked as deleted are not touched.
    Falls back to a plain EXPUNGE if the server does not support UIDPLUS.
    """
    if uids and "UIDPLUS" in _server_capabilities(connection):
        return connection.uid("EXPUNGE", compress_ranges([int(uid) for uid in uids]))
    return connection.expunge()


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


def get_attachment_status(connection: IMAP4_SSL, id_range: str, use_uid: bool = False) -> dict[str, bool]:
    """
    Get the attachment status of emails in a range using BODYSTRUCTURE (no message body is downloaded).
    Returns a dictionary with email ids (UIDs if use_uid) as keys and True/False as values.
    Never raises - on any failure it returns what it could parse (missing ids are treated as no attachment).
    """
    attachment_status = {}
    try:
        resp_status, data = _imap_command(connection, use_uid, "FETCH", id_range, '(UID BODYSTRUCTURE)' if use_uid else '(BODYSTRUCTURE)')
        if resp_status != "OK":
            logging.error(f"Failed to fetch BODYSTRUCTURE for range {id_range}: {resp_status}")
            return attachment_status

        for email_id, fetch_data in parse_fetch_response(data, normalise_times=False, uid_is_key=use_uid).items():
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


# Threading algorithms of the IMAP THREAD command
#   refs (default): References / In-Reply-To headers only - emails sharing only a subject stay separate
#   references: RFC 5256 - the same headers, and also groups emails by subject (unrelated emails with a short subject like "test" get merged)
THREAD_ALGORITHMS = {
    "references": "REFERENCES",
    "refs": "REFS"
}

THREAD_FILTER_KEYS = {
    "unread": ("UNSEEN", True),     # Threads with at least one unread email
    "read": ("UNSEEN", False),      # Threads with no unread email
    "flagged": ("FLAGGED", True),   # Threads with at least one flagged email
    "unflagged": ("FLAGGED", False) # Threads with no flagged email
}


def _parse_thread_response(data: list) -> list[list[str]]:
    """
    Parse an IMAP THREAD response (RFC 5256) into a list of threads, each a flat list of email ids.
    Example: b'(2)(3 6 (4 23)(44 7 96))' -> [['2'], ['3', '6', '4', '23', '44', '7', '96']]
    Not recursive - a deep thread (long reply chain) can not hit the recursion limit.
    """
    raw = b" ".join(part for part in data if isinstance(part, bytes)).decode(errors="ignore")

    threads, current_thread, current_number, depth = [], [], "", 0
    for char in raw:
        if char.isdigit():
            current_number += char
            continue

        if current_number:
            current_thread.append(current_number)
            current_number = ""

        if char == "(":
            depth += 1
        elif char == ")":
            depth = max(depth - 1, 0)
            if depth == 0 and current_thread:
                threads.append(current_thread)
                current_thread = []

    if current_number:
        current_thread.append(current_number)
    if current_thread:
        threads.append(current_thread)

    return threads


def _uid_search(connection: IMAP4_SSL, search_criteria: str) -> list[str]:
    """UID SEARCH in the selected folder, returns the UIDs"""
    resp_status, data = connection.uid("SEARCH", search_criteria)
    if resp_status != "OK":
        raise All_Exceptions(
            message=f"Failed to search emails: {resp_status}; {str(data)}",
            status_code=status.HTTP_424_FAILED_DEPENDENCY
        )
    return data[0].decode().split() if data and data[0] else []


def _thread_by_headers(connection: IMAP4_SSL) -> list[list[str]]:
    """
    Group the emails of the selected folder by their Message-ID / In-Reply-To / References headers.
    Only used when the IMAP server does not support THREAD. Emails sharing any Message-ID end up in one thread.
    Returns the threads as lists of UIDs.
    """
    resp_status, data = connection.uid("FETCH", "1:*", "(UID BODY.PEEK[HEADER.FIELDS (MESSAGE-ID IN-REPLY-TO REFERENCES)])")
    if resp_status != "OK":
        raise All_Exceptions(
            message=f"Failed to fetch email headers: {resp_status}; {str(data)}",
            status_code=status.HTTP_424_FAILED_DEPENDENCY
        )

    parent = {}

    def find(node: str) -> str:
        parent.setdefault(node, node)
        root = node
        while parent[root] != root:
            root = parent[root]
        while parent[node] != root:
            parent[node], node = root, parent[node]
        return root

    uids = []
    for uid, fetch_data in parse_fetch_response(data, normalise_times=False, uid_is_key=True).items():
        uid = str(uid)
        uids.append(uid)
        header_bytes = next((value for key, value in fetch_data.items() if isinstance(key, bytes) and key.startswith(b"BODY[")), b"") or b""
        headers = email.message_from_bytes(header_bytes)
        referenced_ids = re.findall(r"<[^<>\s]+>", " ".join(str(headers.get(name, "")) for name in ("Message-ID", "In-Reply-To", "References")))

        node = find(f"uid:{uid}")
        for message_id in referenced_ids:
            message_root = find(message_id.lower())
            if message_root != node:
                parent[message_root] = node

    threads = {}
    for uid in uids:
        threads.setdefault(find(f"uid:{uid}"), []).append(uid)
    return list(threads.values())


def _get_folder_threads(connection: IMAP4_SSL, folder_path: str, algorithm: str) -> dict:
    """
    Group all emails of a folder into conversations (threads) on the IMAP server - UID THREAD (RFC 5256).
    Uses the requested algorithm, then the other one, then (server without THREAD) the Message-ID headers.
    Returns:
        threads: list of threads, each a list of UIDs sorted by date (oldest first)
        date_position: position of every UID by its Date header (higher = newer)
        total_messages: number of emails in the folder
        uid_validity: UIDVALIDITY of the folder (if it changes, all UIDs the client has are invalid)
        algorithm: the algorithm that was used
    """
    resp_status, data = connection.select(mailbox=_quoted_folder(folder_path), readonly=True)
    if resp_status != "OK":
        raise All_Exceptions(
            message=f"Folder not found: {folder_path}",
            status_code=status.HTTP_404_NOT_FOUND
        )
    total_messages = int(data[0]) if data and data[0] else 0
    _, uid_validity = connection.response("UIDVALIDITY")
    uid_validity = uid_validity[0].decode() if uid_validity and isinstance(uid_validity[0], bytes) else None

    result = {"threads": [], "date_position": {}, "total_messages": total_messages, "uid_validity": uid_validity, "algorithm": None}
    if total_messages == 0:
        return result

    # Position of every email by its Date header (same ordering as sort_by=date in the email listing)
    date_position = {}
    try:
        resp_status, data = connection.uid("SORT", "(DATE)", "UTF-8", "ALL")
        if resp_status == "OK" and data and data[0]:
            date_position = {uid: position for position, uid in enumerate(data[0].decode().split())}
        else:
            logging.error(f"IMAP SORT failed for folder {folder_path}: {resp_status}; {data}")
    except Exception as e:
        logging.warning(f"IMAP SORT not available for folder {folder_path}, using arrival order for threads: {e}")

    threads = None
    for algorithm_name in [algorithm] + [name for name in THREAD_ALGORITHMS if name != algorithm]:
        try:
            resp_status, data = connection.uid("THREAD", THREAD_ALGORITHMS[algorithm_name], "UTF-8", "ALL")
            if resp_status == "OK":
                threads = _parse_thread_response(data)
                result["algorithm"] = algorithm_name
                break
            logging.warning(f"IMAP THREAD {algorithm_name} failed for folder {folder_path}: {resp_status}; {data}")
        except Exception as e:
            logging.warning(f"IMAP THREAD {algorithm_name} not available for folder {folder_path}: {e}")

    if threads is None:
        threads = _thread_by_headers(connection=connection)
        result["algorithm"] = "headers"

    # An email that arrived after the SORT (not in date_position) is the newest
    newest_position = len(date_position)

    def _position(uid: str) -> int:
        return date_position[uid] if uid in date_position else newest_position + int(uid)

    result["threads"] = [sorted(thread, key=_position) for thread in threads if thread]
    result["date_position"] = {uid: _position(uid) for thread in result["threads"] for uid in thread}
    return result


# Headers fetched for the emails of a thread (to find the related emails in the Sent folder)
THREAD_HEADER_FIELDS = ("MESSAGE-ID", "IN-REPLY-TO", "REFERENCES")

# Sent folder names used when the server does not mark it with the \Sent special-use flag (RFC 6154)
# Matched at the top level or directly under INBOX ("Sent", "INBOX/Sent", "INBOX.Sent Items"), not inside other folders
SENT_FOLDER_NAMES = ("sent", "sent items", "sent messages", "sent mail")


def _list_folder_entries(connection: IMAP4_SSL) -> list[tuple[set[str], Optional[str], str]]:
    """LIST all folders, returns (flags in lower case, delimiter, folder name) for each"""
    resp_status, data = connection.list()
    if resp_status != "OK" or not data:
        return []

    pattern = re.compile(r'^\((?P<flags>.*?)\)\s+(?P<delimiter>NIL|"(?:[^"\\]|\\.)*")\s+(?P<name>.*)$')
    entries = []
    for item in data:
        literal_name = None
        if isinstance(item, tuple):     # Folder name sent as a literal
            line, literal_name = item[0], item[1]
        elif isinstance(item, bytes):
            line = item
        else:
            continue

        match = pattern.match(line.decode("utf-8", errors="replace"))
        if not match:
            continue

        if literal_name is not None:
            name = literal_name.decode("utf-8", errors="replace")
        else:
            name = match.group("name").strip()
            if len(name) >= 2 and name.startswith('"') and name.endswith('"'):
                name = name[1:-1].replace('\\"', '"').replace("\\\\", "\\")

        delimiter = match.group("delimiter")
        delimiter = None if delimiter == "NIL" else delimiter[1:-1].replace("\\\\", "\\")
        entries.append(({flag.lower() for flag in match.group("flags").split()}, delimiter, name))

    return entries


def _sent_name_rank(name: str, delimiter: Optional[str]) -> Optional[int]:
    """Position of a folder in SENT_FOLDER_NAMES, ignoring an INBOX parent. None if it is not a Sent folder name."""
    parts = name.split(delimiter) if delimiter else [name]
    if len(parts) == 2 and parts[0].upper() == "INBOX":
        parts = parts[1:]
    if len(parts) != 1:
        return None     # A user's own "Projects/Sent" is not the Sent folder
    base_name = parts[0].strip().lower()
    return SENT_FOLDER_NAMES.index(base_name) if base_name in SENT_FOLDER_NAMES else None


def _folder_message_count(connection: IMAP4_SSL, folder: str) -> int:
    """Number of emails in a folder (STATUS, the folder is not selected), -1 if it can not be read"""
    try:
        resp_status, data = connection.status(_quoted_folder(folder), "(MESSAGES)")
        match = re.search(rb"MESSAGES\s+(\d+)", data[0]) if resp_status == "OK" and data and isinstance(data[0], bytes) else None
        return int(match.group(1)) if match else -1
    except Exception as e:
        logging.warning(f"Failed to get the number of emails of folder {folder}: {e}")
        return -1


def find_sent_folder(connection: IMAP4_SSL) -> Optional[str]:
    """
    Find the Sent folder - by its special-use flag (\\Sent) and by its name (also directly under INBOX, e.g. "INBOX/Sent").
    The flag alone can not be trusted: a mailbox can have an empty "Sent Messages" with the flag, while the emails
    are saved in "Sent". With more than one candidate, the one with the most emails is used (the flagged one on a tie).
    Returns None if there is no Sent folder.
    """
    entries = [entry for entry in _list_folder_entries(connection) if not entry[0] & {"\\noselect", "\\nonexistent"}]

    named = [(_sent_name_rank(name, delimiter), name) for _, delimiter, name in entries]
    candidates = [name for flags, _, name in entries if "\\sent" in flags]
    candidates += [name for rank, name in sorted((item for item in named if item[0] is not None), key=lambda item: item[0])]
    candidates = list(dict.fromkeys(candidates))

    if len(candidates) <= 1:
        return candidates[0] if candidates else None

    # max() keeps the first candidate on a tie, the flagged folders are first
    return max(candidates, key=lambda folder: _folder_message_count(connection, folder))


def _header_value(email_details: dict, header_name: str) -> str:
    """Value of a header (case-insensitive name) of an email of get_email_details"""
    header_name = header_name.lower()
    return next((str(value) for key, value in email_details.items() if isinstance(key, str) and key.lower() == header_name), "")


def _header_message_ids(value: str) -> list[str]:
    """Message-IDs in a header value, in lower case (Message-IDs are compared case-insensitive, like the IMAP search)"""
    return [message_id.lower() for message_id in re.findall(r"<[^<>\s]+>", value)]


def _searchable_message_id(message_id: str) -> bool:
    """Only printable ASCII can be sent in an IMAP search. Another character would make the search of all emails on the page fail."""
    return all(33 <= ord(char) <= 126 for char in message_id)


def _own_message_id(email_details: dict) -> Optional[str]:
    message_ids = _header_message_ids(_header_value(email_details, "Message-ID"))
    return message_ids[0] if message_ids else None


def _referenced_message_ids(email_details: dict) -> set[str]:
    return set(_header_message_ids(_header_value(email_details, "In-Reply-To") + " " + _header_value(email_details, "References")))


def _email_datetime(email_details: dict) -> Optional[datetime]:
    """Date header as an aware datetime (UTC if the header has no timezone), None if it can not be parsed"""
    try:
        email_datetime = email.utils.parsedate_to_datetime(_header_value(email_details, "Date"))
        return email_datetime if email_datetime.tzinfo else email_datetime.replace(tzinfo=timezone.utc)
    except Exception:   # Any text can be in a Date header, e.g. a year too large for a number (OverflowError)
        return None


def _merge_by_date(folder_emails: list[dict], other_emails: list[dict]) -> list[dict]:
    """
    Insert other_emails into folder_emails (already in date order) by their Date header.
    The order of folder_emails is kept as it is (it comes from the IMAP server SORT).
    """
    merged = list(folder_emails)
    for other_email in sorted(other_emails, key=lambda other: (_email_datetime(other) is None, _email_datetime(other) or datetime.min.replace(tzinfo=timezone.utc))):
        other_datetime = _email_datetime(other_email)
        position = len(merged)
        if other_datetime is not None:
            for index, merged_email in enumerate(merged):
                merged_datetime = _email_datetime(merged_email)
                if merged_datetime is not None and merged_datetime > other_datetime:
                    position = index
                    break
        merged.insert(position, other_email)
    return merged


def _quoted_folder(folder: str) -> str:
    """Folder name quoted for SELECT (a name from LIST can have spaces, e.g. "Sent Items") - kept as it is if already quoted"""
    return folder if len(folder) >= 2 and folder.startswith('"') and folder.endswith('"') else _imap_quote(folder)


def _search_any(connection: IMAP4_SSL, search_terms: list[str], chunk_size: int = 60) -> set[str]:
    """UID SEARCH for emails matching any of the search terms (OR), in chunks so a command never gets too long"""
    uids = set()
    for start in range(0, len(search_terms), chunk_size):
        chunk = search_terms[start:start + chunk_size]
        search_query = chunk[-1]
        for search_term in reversed(chunk[:-1]):
            search_query = f"OR {search_term} {search_query}"
        uids.update(_uid_search(connection=connection, search_criteria=f"({search_query})"))
    return uids


def _find_sent_emails(connection: IMAP4_SSL, threads_emails: list[list[dict]], sent_folder: str, full_headers: bool) -> list[list[dict]]:
    """
    Find the emails of the Sent folder that belong to each thread (your own replies).
    An email of the Sent folder belongs to a thread if:
        - an email of the thread replies to it (its Message-ID is in the In-Reply-To / References of the thread), or
        - it replies to an email of the thread (its In-Reply-To / References has a Message-ID of the thread)
    Emails that are in both folders (e.g. sent with yourself in Cc) are not added twice.
    threads_emails: the emails (get_email_details with THREAD_HEADER_FIELDS) of each thread
    Returns the Sent emails of each thread (same order as threads_emails), each with folder_path.
    """
    own_ids_per_thread = [{message_id for message_id in map(_own_message_id, thread_emails) if message_id} for thread_emails in threads_emails]
    referenced_ids_per_thread = [set().union(*map(_referenced_message_ids, thread_emails)) for thread_emails in threads_emails]
    all_own_ids = set().union(*own_ids_per_thread)
    all_referenced_ids = set().union(*referenced_ids_per_thread) - all_own_ids

    sent_emails_per_thread = [[] for _ in threads_emails]
    search_terms = [f"HEADER Message-ID {_imap_quote(message_id)}" for message_id in sorted(all_referenced_ids) if _searchable_message_id(message_id)]
    for message_id in sorted(filter(_searchable_message_id, all_own_ids)):
        search_terms.append(f"HEADER References {_imap_quote(message_id)}")
        search_terms.append(f"HEADER In-Reply-To {_imap_quote(message_id)}")
    if not search_terms:
        return sent_emails_per_thread

    resp_status, _ = connection.select(mailbox=_quoted_folder(sent_folder), readonly=True)
    if resp_status != "OK":
        logging.warning(f"Failed to select the Sent folder {sent_folder}: {resp_status}")
        return sent_emails_per_thread

    sent_uids = _search_any(connection=connection, search_terms=search_terms)
    if not sent_uids:
        return sent_emails_per_thread

    sent_emails = get_email_details(
        connection=connection,
        id_range=compress_ranges([int(uid) for uid in sent_uids]),
        folder_path=_quoted_folder(sent_folder),
        full_headers=full_headers,
        use_uid=True,
        extra_header_fields=THREAD_HEADER_FIELDS
    )

    for sent_email in sent_emails:
        sent_own_id = _own_message_id(sent_email)
        if sent_own_id and sent_own_id in all_own_ids:
            continue    # Already in the folder

        sent_referenced_ids = _referenced_message_ids(sent_email)
        for index, (own_ids, referenced_ids) in enumerate(zip(own_ids_per_thread, referenced_ids_per_thread)):
            # IMAP HEADER search is a substring match - check the exact Message-IDs here
            if (sent_own_id and sent_own_id in referenced_ids) or (sent_referenced_ids & own_ids):
                sent_email["folder_path"] = sent_folder
                sent_emails_per_thread[index].append(sent_email)
                break

    return sent_emails_per_thread


def _resolve_sent_folder(connection: IMAP4_SSL, folder_path: str, include_sent: bool, sent_folder: Optional[str]) -> Optional[str]:
    """
    The Sent folder to add to the threads of folder_path - None if not wanted, not found, or folder_path is the Sent folder.
    A given sent_folder that does not exist (e.g. the default "Sent" on a mailbox with "INBOX/Sent") falls back to find_sent_folder.
    """
    if not include_sent:
        return None
    try:
        if sent_folder and _folder_message_count(connection, sent_folder) < 0:
            logging.warning(f"Sent folder {sent_folder} not found, looking for the Sent folder of the mailbox")
            sent_folder = None
        sent_folder = sent_folder or find_sent_folder(connection)
    except Exception as e:
        logging.warning(f"Failed to find the Sent folder: {e}")
        return None
    if not sent_folder or sent_folder.strip('"').lower() == folder_path.strip('"').lower():
        return None
    return sent_folder


def _add_sent_emails(connection: IMAP4_SSL, threads_emails: list[list[dict]], sent_folder: Optional[str], full_headers: bool) -> Optional[list[list[dict]]]:
    """_find_sent_emails that never fails the request - the threads are still returned without the Sent emails"""
    if not sent_folder:
        return None
    try:
        return _find_sent_emails(connection=connection, threads_emails=threads_emails, sent_folder=sent_folder, full_headers=full_headers)
    except Exception as e:
        logging.error(f"Failed to add the emails of the Sent folder {sent_folder} to the threads: {e}", exc_info=True)
        return [[] for _ in threads_emails]


def _thread_summary(thread: list[str], email_details_by_uid: dict[str, dict], matched_uids: Optional[set] = None, sent_emails: Optional[list[dict]] = None, sent_folder: Optional[str] = None) -> Optional[dict]:
    """
    Build the summary of one thread (latest email + combined flags) from the details of its emails.
    sent_emails: your replies from the Sent folder - they are counted in message_count, participants, flags and attachments.
    id, thread_id, email_ids and latest are always the emails of the folder itself (the thread's position in the list).
    """
    thread_emails = [email_details_by_uid[uid] for uid in thread if uid in email_details_by_uid]
    if not thread_emails:
        return None

    all_emails = _merge_by_date(thread_emails, sent_emails) if sent_emails else thread_emails

    participants = []
    for thread_email in all_emails:
        sender = thread_email.get("From")
        if sender and sender not in participants:
            participants.append(sender)

    unread_count = sum(1 for thread_email in all_emails if "\\Seen" not in thread_email.get("FLAGS", []))

    summary = {
        "id": thread_emails[-1]["id"],                  # UID of the latest email of the thread (in this folder)
        "thread_id": thread_emails[0]["id"],            # UID of the oldest email of the thread (in this folder)
        "email_ids": [thread_email["id"] for thread_email in thread_emails],     # UIDs in this folder, oldest first
        "subject": all_emails[0].get("Subject"),        # Subject of the first email of the conversation
        "message_count": len(all_emails),
        "unread_count": unread_count,
        "is_unread": unread_count > 0,
        "is_flagged": any("\\Flagged" in thread_email.get("FLAGS", []) for thread_email in all_emails),
        "has_attachment": any(thread_email.get("has_attachment", False) for thread_email in all_emails),
        "participants": participants,
        "latest": thread_emails[-1]
    }
    if matched_uids is not None:
        summary["matched_email_ids"] = [thread_email["id"] for thread_email in thread_emails if thread_email["id"] in matched_uids]
    if sent_folder:
        sent_in_order = [thread_email for thread_email in all_emails if thread_email.get("folder_path") == sent_folder]
        summary["folder_message_count"] = len(thread_emails)
        summary["sent_count"] = len(sent_in_order)
        summary["sent_folder_path"] = sent_folder
        summary["sent_email_ids"] = [sent_email["id"] for sent_email in sent_in_order]     # UIDs in the Sent folder, oldest first
        summary["last_message"] = all_emails[-1]       # Latest email of the whole conversation (can be your reply)
    return summary


def _filter_threads(connection: IMAP4_SSL, threads: list[list[str]], filter_by: str, search_criteria: Optional[str]) -> tuple[list[list[str]], Optional[set]]:
    """
    Keep the threads that pass filter_by and contain at least one email matching search_criteria.
    Returns the threads and the UIDs that match the search (None without a search).
    """
    if filter_by != "all" and threads:
        search_key, must_match = THREAD_FILTER_KEYS[filter_by]
        matching_uids = set(_uid_search(connection=connection, search_criteria=search_key))
        threads = [thread for thread in threads if any(uid in matching_uids for uid in thread) == must_match]

    if search_criteria is None:
        return threads, None
    if not threads:
        return threads, set()

    matched_uids = set(_uid_search(connection=connection, search_criteria=search_criteria))
    return [thread for thread in threads if any(uid in matched_uids for uid in thread)], matched_uids


def get_thread_page(connection: IMAP4_SSL, folder_path: str, batch_size: int, page_number: int, sort_order: str, filter_by: str, full_headers: bool, algorithm: str = "refs", search_criteria: Optional[str] = None, include_sent: bool = False, sent_folder: Optional[str] = None) -> dict:
    """
    Get a page of conversations (threads) of a folder - one row per conversation.
    All ids are UIDs. Threads are grouped across the whole folder and ordered by their latest email (Date header).
    filter_by: unread / flagged = threads with at least one such email, read / unflagged = threads with none
    search_criteria: IMAP search - only threads with at least one matching email (matched_email_ids lists them)
    include_sent: add your replies from the Sent folder to each thread (sent_folder, or found by find_sent_folder)
    """
    folder_threads = _get_folder_threads(connection=connection, folder_path=folder_path, algorithm=algorithm)
    date_position = folder_threads["date_position"]
    threads, matched_uids = _filter_threads(connection=connection, threads=folder_threads["threads"], filter_by=filter_by, search_criteria=search_criteria)

    # Order the threads by their latest email (UID breaks ties, the newer email first for desc)
    threads.sort(key=lambda thread: (date_position[thread[-1]], int(thread[-1])), reverse=sort_order == "desc")

    total_count = len(threads)
    total_pages = total_count // batch_size + (total_count % batch_size > 0)
    page_threads = threads[(page_number - 1) * batch_size: page_number * batch_size] if page_number >= 1 else []

    sent_folder = _resolve_sent_folder(connection=connection, folder_path=folder_path, include_sent=include_sent, sent_folder=sent_folder) if page_threads else None

    result = {
        "total_count": total_count,
        "total_pages": total_pages,
        "total_messages": sum(len(thread) for thread in threads),
        "uid_validity": folder_threads["uid_validity"],
        "algorithm": folder_threads["algorithm"],
        "sent_folder_path": sent_folder,
        "threads": []
    }
    if not page_threads:
        return result

    # Fetch only the emails of the threads on this page (one FETCH)
    email_details = get_email_details(
        connection=connection,
        id_range=compress_ranges([int(uid) for thread in page_threads for uid in thread]),
        folder_path=_quoted_folder(folder_path),
        full_headers=full_headers,
        use_uid=True,
        extra_header_fields=THREAD_HEADER_FIELDS
    )
    email_details_by_uid = {email_detail["id"]: email_detail for email_detail in email_details}
    if sent_folder:
        for email_detail in email_details:
            email_detail["folder_path"] = folder_path

    # Your replies from the Sent folder (one SEARCH + one FETCH in the Sent folder)
    sent_emails_per_thread = _add_sent_emails(
        connection=connection,
        threads_emails=[[email_details_by_uid[uid] for uid in thread if uid in email_details_by_uid] for thread in page_threads],
        sent_folder=sent_folder,
        full_headers=full_headers
    )

    for index, thread in enumerate(page_threads):
        thread_details = {"thread": thread, "email_details_by_uid": email_details_by_uid, "matched_uids": matched_uids, "sent_folder": sent_folder}
        try:
            thread_summary = _thread_summary(sent_emails=sent_emails_per_thread[index] if sent_emails_per_thread else None, **thread_details)
        except Exception as e:
            # One malformed email must not fail the whole page: show the row without the Sent emails
            logging.error(f"Failed to add the Sent emails to thread {thread[0]}: {e}", exc_info=True)
            thread_summary = _thread_summary(**thread_details)
        if thread_summary:
            result["threads"].append(thread_summary)

    return result


def get_thread_emails(connection: IMAP4_SSL, folder_path: str, email_uid: str, full_headers: bool, algorithm: str = "refs", include_sent: bool = False, sent_folder: Optional[str] = None) -> dict:
    """
    Get the conversation (thread) that contains the given email (UID): its summary and all its emails, oldest first.
    include_sent: also your replies from the Sent folder, in date order (each email has folder_path)
    """
    folder_threads = _get_folder_threads(connection=connection, folder_path=folder_path, algorithm=algorithm)

    thread = next((thread for thread in folder_threads["threads"] if email_uid in thread), None)
    if thread is None:
        raise All_Exceptions(
            message=f"Email not found: {email_uid}",
            status_code=status.HTTP_404_NOT_FOUND
        )

    email_details = get_email_details(
        connection=connection,
        id_range=compress_ranges([int(uid) for uid in thread]),
        folder_path=_quoted_folder(folder_path),
        full_headers=full_headers,
        use_uid=True,
        extra_header_fields=THREAD_HEADER_FIELDS
    )
    email_details_by_uid = {email_detail["id"]: email_detail for email_detail in email_details}
    thread_emails = [email_details_by_uid[uid] for uid in thread if uid in email_details_by_uid]

    sent_folder = _resolve_sent_folder(connection=connection, folder_path=folder_path, include_sent=include_sent, sent_folder=sent_folder)
    if sent_folder:
        for email_detail in email_details:
            email_detail["folder_path"] = folder_path
    sent_emails = _add_sent_emails(connection=connection, threads_emails=[thread_emails], sent_folder=sent_folder, full_headers=full_headers)

    thread_summary = _thread_summary(
        thread=thread,
        email_details_by_uid=email_details_by_uid,
        sent_emails=sent_emails[0] if sent_emails else None,
        sent_folder=sent_folder
    )
    if thread_summary is None:
        raise All_Exceptions(
            message=f"Email not found: {email_uid}",
            status_code=status.HTTP_404_NOT_FOUND
        )

    # Emails in date order (oldest first), with your replies from the Sent folder if include_sent
    thread_summary["emails"] = _merge_by_date(thread_emails, sent_emails[0]) if sent_emails else thread_emails
    thread_summary["uid_validity"] = folder_threads["uid_validity"]
    thread_summary["algorithm"] = folder_threads["algorithm"]
    thread_summary["sent_folder_path"] = sent_folder
    return thread_summary


def _fill_missing_date(headers: dict, internal_date) -> dict:
    """
    Some senders do not add a Date header (e.g. CERSAI system mails).
    Use the IMAP INTERNALDATE (time the server received the email) in that case, like Roundcube does.
    internal_date can be a datetime or the raw INTERNALDATE string ("03-Oct-2026 15:30:42 +0530").
    """
    if any(key.lower() == "date" and str(value).strip() for key, value in headers.items()):
        return headers
    try:
        if isinstance(internal_date, (bytes, str)):
            internal_date = datetime.strptime(_bs_str(internal_date).strip(), "%d-%b-%Y %H:%M:%S %z")
        if isinstance(internal_date, datetime):
            headers["Date"] = email.utils.format_datetime(internal_date)
    except (ValueError, TypeError) as e:
        logging.warning(f"Failed to parse INTERNALDATE {internal_date!r}: {e}")
    return headers


def get_email_details(connection: IMAP4_SSL, id_range: str, folder_path: str, full_headers: bool, use_uid: bool = False, extra_header_fields: tuple = ()) -> list[dict]:
    """
    Get headers and flags of specific emails in a range.
    Returns a dictionary with email ids as keys and email headers and flags as values.
    use_uid: id_range has UIDs and "id" of each email is its UID (default: sequence numbers, old behaviour).
    Every email also has "uid" (its UID) - use it with use_uid=true on the other endpoints.
    extra_header_fields: more headers to fetch when full_headers is false (e.g. ("MESSAGE-ID",)), default: none (old behaviour)
    """
    # Encode folder name to handle special characters
    connection.select(folder_path)

    # Request both headers and flags for a range of emails (and the UID, it is returned as "uid")
    header_fields = " ".join(("FROM", "TO", "SUBJECT", "DATE") + tuple(extra_header_fields))
    query_string = '(UID FLAGS INTERNALDATE BODY.PEEK[HEADER])' if full_headers else f'(UID FLAGS INTERNALDATE BODY.PEEK[HEADER.FIELDS ({header_fields})])'
    resp_status, data = _imap_command(connection, use_uid, "FETCH", id_range, query_string)

    if resp_status == "OK":
        emails = []

        # Iterate through each response part
        for part_index, response_part in enumerate(data):
            if isinstance(response_part, tuple):
                try:
                    # Parse the email header
                    email_message = email.message_from_bytes(response_part[1])
                    # What the server sends about the email: some servers send UID / FLAGS after the headers, in the next response part
                    next_part = data[part_index + 1] if part_index + 1 < len(data) else None
                    fetch_info = (response_part[0] + (next_part if isinstance(next_part, bytes) else b"")).decode(errors="replace")
                    uid_match = re.search(r'\bUID (\d+)', fetch_info)
                    email_uid = uid_match.group(1) if uid_match else None
                    email_id = fetch_info.split()[0]  # Extract email ID from response
                    if use_uid:
                        if email_uid is None:
                            raise ValueError(f"UID missing in FETCH response: {response_part[0]!r}")
                        email_id = email_uid

                    # Extract flags from the same response part
                    flags = []
                    if 'FLAGS (' in fetch_info:
                        flags = fetch_info.split('FLAGS (')[1].split(')')[0].split()

                    # Add both headers and flags to the email dictionary
                    email_details = dict(email_message._headers)
                    email_details['FLAGS'] = flags  # Add the flags as a new key-value pair
                    email_details['id'] = email_id  # Add the email ID to the details
                    email_details['uid'] = email_uid  # UID of the email (does not change when other emails are deleted / moved)

                    # Clean up header values by doing basic decoding (e.g., for encoded words)
                    email_details = email_headers_cleanup(headers=email_details)

                    # Fall back to the arrival time if the email has no Date header
                    internal_date = re.search(r'INTERNALDATE "([^"]+)"', fetch_info)
                    email_details = _fill_missing_date(email_details, internal_date.group(1) if internal_date else None)
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
        attachment_status = get_attachment_status(connection=connection, id_range=id_range, use_uid=use_uid)
        for email_details in emails:
            email_details['has_attachment'] = attachment_status.get(email_details['id'], False)

        # Return the list of email details
        return emails

    else:
        raise All_Exceptions(
            message=f"Failed to fetch email details: {resp_status}; {str(data)}",
            status_code=status.HTTP_424_FAILED_DEPENDENCY
        )


def get_raw_email(connection: IMAP4_SSL, email_id: str, folder: str, read_only: bool, use_uid: bool = False) -> bytes:
    """
    Get raw email by ID (UID if use_uid)
    Returns the raw email content as bytes
    """
    # Encode folder name to handle special characters
    encoded_folder = folder.encode('utf-7')
    connection.select(encoded_folder, readonly=read_only)

    # Fetch the raw email by ID
    fetch_status, data = _imap_command(connection, use_uid, "FETCH", email_id, '(RFC822)')
    if fetch_status == "OK":
        # UID FETCH of a UID that does not exist returns OK without data
        if use_uid and (not data or not isinstance(data[0], tuple)):
            raise All_Exceptions(
                message=f"Email not found: {email_id}",
                status_code=status.HTTP_404_NOT_FOUND
            )
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
        try:
            return base64.b64decode(re.sub(rb"[^A-Za-z0-9+/=]", b"", content) + b"==", validate=False)
        except ValueError:
            # Damaged base64 (e.g. a cut off email): decode what is there instead of failing
            data = re.sub(rb"[^A-Za-z0-9+/]", b"", content)
            data = data[:-1] if len(data) % 4 == 1 else data
            return base64.b64decode(data + b"=" * (-len(data) % 4))
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


def _fetch_email_structure(connection: IMAP4_SSL, email_id: str, with_headers: bool, use_uid: bool = False) -> dict:
    """FETCH the flags, BODYSTRUCTURE and (optionally) the headers of a single email (email_id is a UID if use_uid)"""
    query_string = "(UID FLAGS INTERNALDATE BODYSTRUCTURE BODY.PEEK[HEADER])" if with_headers else "(BODYSTRUCTURE)"
    try:
        resp_status, data = _imap_command(connection, use_uid, "FETCH", email_id, query_string)
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


def get_email_view(connection: IMAP4_SSL, email_id: str, folder: str, mark_as_read: bool, use_uid: bool = False) -> dict:
    """
    Get an email for viewing - headers, flags, the text/html body and the list of attachments.
    Only the body parts are downloaded, attachments are NOT downloaded (use get_email_attachment for that).
    email_id is a UID if use_uid (default: sequence number).
    """
    connection.select(mailbox=folder, readonly=not mark_as_read)

    fetch_data = _fetch_email_structure(connection=connection, email_id=email_id, with_headers=True, use_uid=use_uid)
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
        resp_status, data = _imap_command(connection, use_uid, "FETCH", email_id, "(" + " ".join(f"BODY.PEEK[{part['part_id']}]" for part in body_parts) + ")")
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
        _imap_command(connection, use_uid, "STORE", email_id, "+FLAGS", "\\Seen")

    # Same header cleanup as the email listing
    email_message = email.message_from_bytes(fetch_data.get(b"BODY[HEADER]") or b"")
    headers = email_headers_cleanup(headers=dict(email_message._headers))
    headers = _fill_missing_date(headers, fetch_data.get(b"INTERNALDATE"))

    flags = [_bs_str(flag) for flag in fetch_data.get(b"FLAGS", ())]
    if mark_as_read and "\\Seen" not in flags:
        flags.append("\\Seen")

    return {
        "id": email_id,
        "uid": str(fetch_data[b"UID"]) if b"UID" in fetch_data else None,
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


def get_email_attachment(connection: IMAP4_SSL, email_id: str, folder: str, part_id: str, use_uid: bool = False) -> dict:
    """
    Download a single attachment (part) of an email (email_id is a UID if use_uid).
    Returns a dict with content (decoded bytes), content_type and filename.
    """
    connection.select(mailbox=folder, readonly=True)

    fetch_data = _fetch_email_structure(connection=connection, email_id=email_id, with_headers=False, use_uid=use_uid)
    leaf_parts = {leaf_part["part_id"]: leaf_part for leaf_part in _bs_leaf_parts(BodyData.create(fetch_data[b"BODYSTRUCTURE"]))}
    if part_id not in leaf_parts:
        raise All_Exceptions(
            message=f"Attachment part {part_id} not found in email {email_id}",
            status_code=status.HTTP_404_NOT_FOUND
        )
    attachment = leaf_parts[part_id]

    resp_status, data = _imap_command(connection, use_uid, "FETCH", email_id, f"(BODY.PEEK[{part_id}])")
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


def move_multiple_emails(connection: IMAP4_SSL, email_ids: list[str], source_folder: str, dest_folder: str, use_uid: bool = False) -> dict:
    """
    Move multiple emails from source_folder to dest_folder
    use_uid: email_ids are UIDs - uses UID MOVE (RFC 6851) if the server supports it, otherwise UID COPY + UID STORE \\Deleted
    and expunges only the moved emails (UID EXPUNGE, if the server supports UIDPLUS)
    """
    # Select the source folder
    select_status, _ = connection.select(mailbox=source_folder, readonly=False)
    if select_status != 'OK':
        return {"error": f"Failed to select source folder: {source_folder}"}

    use_move = use_uid and "MOVE" in _server_capabilities(connection)

    results = {}
    deleted_ids = []
    for email_id in map(str, email_ids):
        try:
            if use_move:
                move_status, _ = connection.uid("MOVE", email_id, dest_folder)
                results[email_id] = "Moved successfully" if move_status == 'OK' else "Move failed"
                continue

            copy_status, _ = _imap_command(connection, use_uid, "COPY", email_id, dest_folder)
            if copy_status != 'OK':
                results[email_id] = "Copy failed"
                continue

            store_status, _ = _imap_command(connection, use_uid, "STORE", email_id, '+FLAGS', '\\Deleted')
            if store_status != 'OK':
                results[email_id] = "Failed to mark as deleted"
                continue

            deleted_ids.append(email_id)
            results[email_id] = "Moved successfully"

        except Exception as e:
            results[email_id] = f"Error: {str(e)}"

    if use_move:
        return results

    expunge_status, _ = _expunge_uids(connection, deleted_ids) if use_uid else connection.expunge()
    if expunge_status != 'OK':
        results["expunge"] = "Failed to expunge deleted emails"

    return results


def copy_multiple_emails(connection: IMAP4_SSL, email_ids: list[str], source_folder: str, dest_folder: str, use_uid: bool = False) -> dict:
    """
    Copy multiple emails from source_folder to dest_folder (email_ids are UIDs if use_uid)
    """
    # Select the source folder
    select_status, _ = connection.select(mailbox=source_folder, readonly=True)
    if select_status != 'OK':
        return {"error": f"Failed to select source folder: {source_folder}"}

    results = {}
    for email_uid in map(str, email_ids):
        try:
            copy_status, _ = _imap_command(connection, use_uid, "COPY", email_uid, dest_folder)
            if copy_status != 'OK':
                results[email_uid] = "Copy failed"
                continue

            results[email_uid] = "Copied successfully"

        except Exception as e:
            results[email_uid] = f"Error: {str(e)}"

    return results


def mark_emails_as_read(connection: IMAP4_SSL, folder: str, email_ids: list[int], use_uid: bool = False) -> dict:
    """
    Mark specified emails in the folder as read (email_ids are UIDs if use_uid).
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
            store_status, _ = _imap_command(connection, use_uid, "STORE", email_uid, '+FLAGS', '\\Seen')
            if store_status != 'OK':
                results[email_uid] = "Failed to mark as read"
                continue

            results[email_uid] = "Marked as read"

        except Exception as e:
            results[email_uid] = f"Error: {str(e)}"

    return results


def mark_emails_as_unseen(connection: IMAP4_SSL, folder: str, email_ids: list[int], use_uid: bool = False) -> dict:
    """
    Mark specified emails in the folder as unread (email_ids are UIDs if use_uid).
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
            store_status, _ = _imap_command(connection, use_uid, "STORE", email_uid, '-FLAGS', '\\Seen')
            if store_status != 'OK':
                results[email_uid] = "Failed to mark as unread"
                continue

            results[email_uid] = "Marked as unread"

        except Exception as e:
            results[email_uid] = f"Error: {str(e)}"

    return results


def mark_emails_as_flagged(connection: IMAP4_SSL, folder: str, email_ids: list[int], use_uid: bool = False) -> dict:
    """
    Mark specified emails in the folder as flagged (email_ids are UIDs if use_uid).
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
            store_status, _ = _imap_command(connection, use_uid, "STORE", email_uid, '+FLAGS', '\\Flagged')
            if store_status != 'OK':
                results[email_uid] = "Failed to mark as flagged"
                continue

            results[email_uid] = "Marked as flagged"

        except Exception as e:
            results[email_uid] = f"Error: {str(e)}"

    return results


def mark_emails_as_unflagged(connection: IMAP4_SSL, folder: str, email_ids: list[int], use_uid: bool = False) -> dict:
    """
    Mark specified emails in the folder as unflagged (email_ids are UIDs if use_uid).
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
            store_status, _ = _imap_command(connection, use_uid, "STORE", email_uid, '-FLAGS', '\\Flagged')
            if store_status != 'OK':
                results[email_uid] = "Failed to mark as unflagged"
                continue

            results[email_uid] = "Marked as unflagged"

        except Exception as e:
            results[email_uid] = f"Error: {str(e)}"

    return results


def delete_emails_permanently(connection: IMAP4_SSL, folder: str, email_ids: list[int], use_uid: bool = False) -> dict:
    """
    Permanently delete specified emails in the folder.
    use_uid: email_ids are UIDs - only these emails are expunged (UID EXPUNGE, if the server supports UIDPLUS)
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

        store_status, _ = _imap_command(
            connection,
            use_uid,
            "STORE",
            uid_set,
            '+FLAGS',
            r'(\Deleted)'
        )

        if store_status != 'OK':
            return {"status": "Failed to mark emails deleted", "uid_set": uid_set}

        # Permanently remove
        expunge_status, _ = _expunge_uids(connection, email_ids) if use_uid else connection.expunge()

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


# Actions that change a flag: (STORE command, flag, IMAP search of the emails that still need the change)
BULK_FLAG_ACTIONS = {
    "read": ("+FLAGS.SILENT", "(\\Seen)", "UNSEEN"),
    "unread": ("-FLAGS.SILENT", "(\\Seen)", "SEEN"),
    "flag": ("+FLAGS.SILENT", "(\\Flagged)", "UNFLAGGED"),
    "unflag": ("-FLAGS.SILENT", "(\\Flagged)", "FLAGGED")
}
BULK_BATCH_SIZE = 5000          # Emails per IMAP command. Scattered UIDs stay well below the 64 KB command limit of Dovecot.
BULK_TIME_BUDGET_SECONDS = 20   # A request stops starting new batches after this long, the client calls again for the rest


def _select_for_bulk(connection: IMAP4_SSL, folder: str, uid_validity: str) -> None:
    """Select the folder for writing. Refuses if its UIDVALIDITY changed: the selection was made with UIDs that are no longer valid."""
    resp_status, _ = connection.select(mailbox=_quoted_folder(folder), readonly=False)
    if resp_status != "OK":
        raise All_Exceptions(
            message=f"Folder not found: {folder}",
            status_code=status.HTTP_404_NOT_FOUND
        )

    _, current_validity = connection.response("UIDVALIDITY")
    current_validity = current_validity[0].decode() if current_validity and isinstance(current_validity[0], bytes) else None
    if current_validity != str(uid_validity):
        raise All_Exceptions(
            message=f"The folder has changed (UIDVALIDITY {current_validity}), reload it and select the emails again",
            status_code=status.HTTP_409_CONFLICT
        )


def _bulk_selection(connection: IMAP4_SSL, folder: str, action: str, max_uid: int, excluded: set[str], filter_by: str, search_query: Optional[str], conversations: bool, algorithm: str, uid_validity: str) -> list[list[str]]:
    """
    The emails a bulk action still has to change, in groups that must be handled together.
    Emails that already have the new state are left out, so calling again continues where the last call stopped.

    conversations=True: filter_by and search_query choose conversations and every email of a chosen conversation counts,
    like the rows of /email/threads, except "unread", which only changes the latest email of each conversation.
    conversations=False: they choose single emails, like /email/fetch. No THREAD needed either when nothing narrows the folder down.
    """
    pending_key = BULK_FLAG_ACTIONS[action][2] if action in BULK_FLAG_ACTIONS else None
    needs_threads = conversations and (filter_by != "all" or search_query is not None or action == "unread")

    if not needs_threads:
        criteria = [f"UID 1:{max_uid}"]
        if filter_by != "all":
            criteria.append(EMAIL_FILTER_KEYS[filter_by])
        if search_query is not None:
            criteria.append(search_query)
        if pending_key:
            criteria.append(pending_key)
        return [[uid] for uid in _uid_search(connection=connection, search_criteria=" ".join(criteria)) if uid not in excluded]

    # _get_folder_threads selects the folder read-only, so select it for writing again afterwards
    threads = _get_folder_threads(connection=connection, folder_path=folder, algorithm=algorithm)["threads"]
    threads, _ = _filter_threads(connection=connection, threads=threads, filter_by=filter_by, search_criteria=search_query)
    pending = set(_uid_search(connection=connection, search_criteria=pending_key)) if pending_key else None
    _select_for_bulk(connection=connection, folder=folder, uid_validity=uid_validity)

    groups = []
    for thread in threads:
        uids = [uid for uid in thread if int(uid) <= max_uid and uid not in excluded]
        if action == "unread":
            uids = uids[-1:]
        if pending is not None:
            uids = [uid for uid in uids if uid in pending]
        if uids:
            groups.append(uids)
    return groups


def _bulk_batches(groups: list[list[str]], batch_size: int) -> list[list[str]]:
    """
    Split into batches of about batch_size UIDs, without splitting a group. If a request stopped in the middle of a conversation,
    the part already changed could make the conversation drop out of the filter (e.g. flagging in the "unflagged" view) and the rest would be skipped.
    """
    batches, current = [], []
    for group in groups:
        if current and len(current) + len(group) > batch_size:
            batches.append(current)
            current = []
        current.extend(group)
    if current:
        batches.append(current)
    return batches


def _bulk_apply(connection: IMAP4_SSL, action: str, uids: list[str], dest_folder: Optional[str]) -> None:
    """Run one action on one batch of UIDs, in as few IMAP commands as possible"""
    uid_set = compress_ranges([int(uid) for uid in uids])

    if action in BULK_FLAG_ACTIONS:
        store_command, flag, _ = BULK_FLAG_ACTIONS[action]
        responses = [connection.uid("STORE", uid_set, store_command, flag)]
    elif action == "move" and "MOVE" in _server_capabilities(connection):
        responses = [connection.uid("MOVE", uid_set, _quoted_folder(dest_folder))]
    else:
        responses = []
        if action == "move":
            responses.append(connection.uid("COPY", uid_set, _quoted_folder(dest_folder)))
        if all(resp_status == "OK" for resp_status, _ in responses):
            responses.append(connection.uid("STORE", uid_set, "+FLAGS.SILENT", "(\\Deleted)"))
        if all(resp_status == "OK" for resp_status, _ in responses):
            responses.append(_expunge_uids(connection, uids))

    for resp_status, data in responses:
        if resp_status != "OK":
            raise All_Exceptions(
                message=f"IMAP refused the {action}: {resp_status}; {str(data)}",
                status_code=status.HTTP_424_FAILED_DEPENDENCY
            )


def bulk_email_action(connection: IMAP4_SSL, folder: str, action: str, max_uid: int, uid_validity: str, exclude_uids: Optional[list[int]] = None, filter_by: str = "all", search_criteria: Optional[SearchMail] = None, conversations: bool = True, dest_folder: Optional[str] = None, algorithm: str = "refs", time_budget: float = BULK_TIME_BUDGET_SECONDS, batch_size: int = BULK_BATCH_SIZE) -> dict:
    """
    Run an action on all emails of a folder (or of a filter / search), not only on the loaded page.
    max_uid: the newest email when the user selected all - mail that arrives later is not touched.
    exclude_uids: emails the user unselected.
    Returns done (changed by this call) and remaining (call again while it is above 0).
    unread_affected: unread emails among those moved or deleted, for the folder counts.
    """
    if action == "delete" and not is_trash_or_junk_folder(connection, folder):
        raise All_Exceptions(
            message="Emails can only be deleted permanently from a Trash or Spam folder, move them to Trash instead",
            status_code=status.HTTP_403_FORBIDDEN
        )

    _select_for_bulk(connection=connection, folder=folder, uid_validity=uid_validity)

    result = {"folder_path": folder, "action": action, "done": 0, "remaining": 0, "unread_affected": 0}
    if max_uid < 1:     # 1:0 would mean UID 1 in IMAP
        return result

    groups = _bulk_selection(
        connection=connection,
        folder=folder,
        action=action,
        max_uid=max_uid,
        excluded={str(uid) for uid in exclude_uids or []},
        filter_by=filter_by,
        search_query=_search_mail_criteria(search_criteria) if search_criteria else None,
        conversations=conversations,
        algorithm=algorithm,
        uid_validity=uid_validity
    )
    unread_uids = set(_uid_search(connection=connection, search_criteria="UNSEEN")) if action in ("move", "delete") and groups else set()

    batches = _bulk_batches(groups=groups, batch_size=batch_size)
    started_at = time.monotonic()
    for index, batch in enumerate(batches):
        if index and time.monotonic() - started_at >= time_budget:
            result["remaining"] = sum(len(uids) for uids in batches[index:])
            break
        _bulk_apply(connection=connection, action=action, uids=batch, dest_folder=dest_folder)
        result["done"] += len(batch)
        result["unread_affected"] += sum(uid in unread_uids for uid in batch)

    return result


def _search_text(value: str) -> str:
    """Text typed by the user as a quoted IMAP string: a quote, a backslash or a line break can not change the command"""
    return _imap_quote(re.sub(r"[\r\n]+", " ", value))


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
        parts.append(f'FROM {_search_text(query["from"])}')

    if "to" in query and query["to"]:
        parts.append(f'TO {_search_text(query["to"])}')

    if "subject" in query and query["subject"]:
        parts.append(f'SUBJECT {_search_text(query["subject"])}')

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


def _search_mail_criteria(search_criteria: SearchMail) -> str:
    """The IMAP search of a search form (the same one for the search endpoints and for bulk actions)"""
    return _build_search_criteria(
        {
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


def search_threads(connection: IMAP4_SSL, search_criteria: SearchMail, filter_by: str = "all", algorithm: str = "refs", include_sent: bool = False, sent_folder: Optional[str] = None) -> dict:
    """
    Search emails and return the conversations (threads) that contain at least one matching email.
    Uses the same search criteria as search_emails, pagination (page / limit) is by conversation.
    """
    search_query = _search_mail_criteria(search_criteria)

    page, limit = search_criteria.page or 1, search_criteria.limit or 50
    return {
        "folder_path": search_criteria.folder,
        "page": page,
        "limit": limit,
        **get_thread_page(
            connection=connection,
            folder_path=search_criteria.folder,
            batch_size=limit,
            page_number=page,
            sort_order=search_criteria.sort_order or "desc",
            filter_by=filter_by,
            full_headers=bool(search_criteria.full_headers),
            algorithm=algorithm,
            search_criteria=search_query,
            include_sent=include_sent,
            sent_folder=sent_folder
        )
    }


def get_email_details_by_message_id(imap_connection: IMAP4_SSL, message_ids: list[str], folder: str, use_uid: bool = False) -> list[dict]:
    """
    Fetch email details by Message-ID ("id" of each email is its UID if use_uid)
    """
    imap_connection.select(folder, readonly=True)

    # Search all the Message-IDs in one go (the folder is scanned once instead of once per Message-ID)
    email_ids = _search_message_ids(imap_connection=imap_connection, message_ids=message_ids, use_uid=use_uid)

    if not email_ids:
        raise All_Exceptions(
            message="No emails found with the specified Message-IDs",
            status_code=status.HTTP_204_NO_CONTENT
        )

    findings = get_email_details(
        connection=imap_connection,
        id_range=",".join(email_ids),
        folder_path=folder,
        full_headers=True,
        use_uid=use_uid
    )

    # Add a new key 'Message-ID' to each finding (the requested Message-ID it was found by)
    uids = _map_findings_to_message_ids(findings=findings, message_ids=message_ids)
    if uids is None:
        # Could not match every finding from its headers - use the per Message-ID search (old behaviour)
        uids = {}
        for message_id in message_ids:
            search_query = f'(HEADER Message-ID {_imap_quote(message_id)})'
            status_, data = imap_connection.uid("SEARCH", search_query) if use_uid else imap_connection.search(None, search_query)
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


def _search_message_ids(imap_connection: IMAP4_SSL, message_ids: list[str], chunk_size: int = 50, use_uid: bool = False) -> list[str]:
    """
    Search emails by Message-ID with a single SEARCH per chunk of Message-IDs (OR of all of them).
    Returns the email ids (UIDs if use_uid) sorted ascending, no duplicates.
    """
    unique_message_ids = list(dict.fromkeys(message_ids))
    email_ids = set()

    for start in range(0, len(unique_message_ids), chunk_size):
        search_terms = [f"HEADER Message-ID {_imap_quote(message_id)}" for message_id in unique_message_ids[start:start + chunk_size]]

        # IMAP OR takes 2 keys: "OR a OR b c" matches a, b or c
        search_query = search_terms[-1]
        for search_term in reversed(search_terms[:-1]):
            search_query = f"OR {search_term} {search_query}"

        status_, data = imap_connection.uid("SEARCH", f"({search_query})") if use_uid else imap_connection.search(None, f"({search_query})")
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
