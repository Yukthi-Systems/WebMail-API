"""
Basic functions required for the project are defined here
"""

from .utils.base.libraries import smtplib, logging, Request, orjson, status, Annotated, Depends, pika, uuid, datetime, timezone, requests, UploadFile, base64
from .utils.base.constants import RABBITMQ_HOST, RABBITMQ_PORT, RABBITMQ_VIRTUAL_HOST, RABBITMQ_USERNAME, RABBITMQ_PASSWORD, RABBITMQ_EXCHANGE, RABBITMQ_ROUTING_KEY, GOOGLE_RECAPTCHA_PROJECT_ID, GOOGLE_RECAPTCHA_API_KEY, GOOGLE_RECAPTCHA_SITE_KEY, LOCAL_SMTP_HOST_NAME, SMTP_CONNECTION_TIMEOUT
from .utils.models import All_Exceptions, SendMailForm
from .imap import get_imap_connection
from .database import MemcachedDep


def validate_smtp_details(smtp_server: str, smtp_port: int, smtp_user: str, smtp_password: str) -> bool:
    """
    Validate SMTP details
    """
    try:
        # Create a connection to the SMTP server
        with smtplib.SMTP(
            host=smtp_server,
            port=smtp_port,
            timeout=SMTP_CONNECTION_TIMEOUT, # Set a timeout for the connection
            local_hostname=LOCAL_SMTP_HOST_NAME  # Use a local hostname for the SMTP connection
        ) as server:
            # Start TLS for security
            server.starttls()
            # Login to the server
            server.login(user=smtp_user, password=smtp_password)
        return True

    except smtplib.SMTPException as e:
        logging.error(f"Error occurred while validating SMTP details: {e}")
        return False

    except Exception as e:
        logging.critical(f"Unexpected error occurred while validating SMTP details: {e}", exc_info=True)
        return False


def validate_imap_details(imap_server: str, imap_port: int, imap_user: str, imap_password: str) -> bool:
    """
    Validate IMAP details
    """
    if get_imap_connection(
        imap_server=imap_server,
        imap_port=imap_port,
        imap_user=imap_user,
        imap_password=imap_password
    ) is not None:
        return True
    else:
        logging.error("Failed to establish IMAP connection")
        return False


async def get_current_user_session_details(request: Request, CacheDB: MemcachedDep) -> dict:
    """
    Get current user session details from the cache
    """
    session_id = request.cookies.get("SESSION_ID")
    if not session_id:
        raise All_Exceptions(message="Session ID not found", status_code=status.HTTP_406_NOT_ACCEPTABLE)

    csrf_token = request.headers.get("X-CSRF-Token")
    if not csrf_token:
        raise All_Exceptions(message="CSRF token not found", status_code=status.HTTP_406_NOT_ACCEPTABLE)

    user_data_bytes = await CacheDB.get(session_id.encode("utf-8"))
    if not user_data_bytes:
        raise All_Exceptions(message="Session expired", status_code=status.HTTP_401_UNAUTHORIZED)
    
    user_data = orjson.loads(user_data_bytes)
    if user_data["csrf_token"] != csrf_token:
        raise All_Exceptions(message="CSRF token mismatch", status_code=status.HTTP_401_UNAUTHORIZED)

    return user_data


CurrentUser = Annotated[dict, Depends(get_current_user_session_details)]


def _send_message_to_rabbitmq(message: dict) -> None:
    """
    Send message to RabbitMQ
    :param message: The message to be sent to RabbitMQ
    :return: None
    """
    try:
        queue_msg_id = str(uuid.uuid4())
        connection = pika.BlockingConnection(
            pika.ConnectionParameters(
                host=RABBITMQ_HOST,
                port=RABBITMQ_PORT,
                virtual_host=RABBITMQ_VIRTUAL_HOST,
                credentials=pika.PlainCredentials(username=RABBITMQ_USERNAME, password=RABBITMQ_PASSWORD)
            )
        )
        channel = connection.channel()
        channel.basic_publish(
            exchange=RABBITMQ_EXCHANGE,
            routing_key=RABBITMQ_ROUTING_KEY,
            body=orjson.dumps(message),
            properties=pika.BasicProperties(
                delivery_mode=2,  # Make the message persistent
                headers={
                    "queue_msg_id": queue_msg_id,
                    "timestamp": datetime.now(tz=timezone.utc).isoformat()
                }
            )
        )
        connection.close()
        logging.debug(f"Message sent to RabbitMQ: From: {message['from']}, To: {message['to']}, Subject: {message['subject']}, Queue Msg ID: {queue_msg_id}")

    except Exception as e:
        logging.error(f"Error while sending message to RabbitMQ: {e}", exc_info=True)
        raise All_Exceptions(message="Failed to send message to RabbitMQ", status_code=status.HTTP_503_SERVICE_UNAVAILABLE)


def _validate_email_data(data: SendMailForm, user_email: str) -> None:
    """
    Validate email data
    :param data: Email data
    :return: None
    """
    # If from id is same as user id, then it is a valid email
    if user_email != data.from_id.email:
        raise All_Exceptions(message="User's session email ID does not match with the sender's intended email ID", status_code=status.HTTP_406_NOT_ACCEPTABLE)

    # TODO: Add more validation checks as per requirements


def _email_address_to_dict(email_address) -> dict:
    """
    Convert EmailAddress model to dictionary
    :param email_address: EmailAddress model
    :return: Dictionary representation of EmailAddress
    """
    return {
        "name": email_address.name,
        "email": email_address.email
    }


def send_mail_rabbit(email_data: SendMailForm, user_data: dict, attachments: list[UploadFile], in_line_attachments: list[UploadFile]) -> None:
    """
    Send email using RabbitMQ
    :param email_data: Email data
    :param user_data: User data
    :param attachments: List of attachments
    :param in_line_attachments: List of in-line attachments
    :return: None
    """
    try:
        # Validate the email data
        _validate_email_data(data=email_data, user_email=user_data["user_email"])

        # Prepare the message to be sent to RabbitMQ
        message = {
            "from": _email_address_to_dict(email_data.from_id),
            "to": [_email_address_to_dict(addr) for addr in email_data.to],
            "cc": [_email_address_to_dict(addr) for addr in email_data.cc],
            "bcc": [_email_address_to_dict(addr) for addr in email_data.bcc],
            "reply_to": _email_address_to_dict(email_data.reply_to) if email_data.reply_to else None,
            "subject": email_data.subject,
            "body_text": email_data.body_text,
            "body_html": email_data.body_html,
            "attachments": [
                {
                    "filename": attachment.filename,
                    "content_type": attachment.content_type,
                    "data": base64.b64encode(attachment.file.read()).decode('utf-8')  # Convert bytes to base64 string for JSON serialization
                } for attachment in attachments
            ],
            "in_line_attachments": [
                {
                    "filename": attachment.filename,
                    "content_type": attachment.content_type,
                    "data": base64.b64encode(attachment.file.read()).decode('utf-8')  # Convert bytes to base64 string for JSON serialization
                } for attachment in in_line_attachments
            ],
            "folder_path": email_data.folder_path,
            "headers": email_data.headers,
            "priority": email_data.priority,
            "timestamp": email_data.timestamp,
            "is_draft": False,
            "server_details": {
                "smtp": {
                    "server": user_data["smtp_server"],
                    "port": user_data["smtp_port"],
                    "user": user_data["smtp_user"],
                    "password": user_data["smtp_password"] # TODO: Raw password, consider encrypting?
                },
                "imap": {
                    "server": user_data["imap_server"],
                    "port": user_data["imap_port"],
                    "user": user_data["imap_user"],
                    "password": user_data["imap_password"] # TODO: Raw password, consider encrypting?
                }
            },
            "draft_saved": email_data.draft_saved,
            "draft_folder_name": email_data.draft_folder_name,
            "draft_message_id": email_data.draft_message_id
        }
        _send_message_to_rabbitmq(message=message)

    except Exception as e:
        logging.error(f"Error while sending mail: {e}", exc_info=True)
        raise All_Exceptions(message="Failed to send mail", status_code=status.HTTP_503_SERVICE_UNAVAILABLE)


def draft_mail_rabbit(email_data: SendMailForm, user_data: dict, attachments: list[UploadFile], in_line_attachments: list[UploadFile]) -> None:
    """
    Draft email using RabbitMQ
    :param email_data: Email data
    :param user_data: User data
    :return: None
    """
    try:
        # Validate the email data
        _validate_email_data(data=email_data, user_email=user_data["user_email"])

        # Prepare the message to be sent to RabbitMQ
        message = {
            "from": _email_address_to_dict(email_data.from_id),
            "to": [_email_address_to_dict(addr) for addr in email_data.to],
            "cc": [_email_address_to_dict(addr) for addr in email_data.cc],
            "bcc": [_email_address_to_dict(addr) for addr in email_data.bcc],
            "reply_to": _email_address_to_dict(email_data.reply_to) if email_data.reply_to else None,
            "subject": email_data.subject,
            "body_text": email_data.body_text,
            "body_html": email_data.body_html,
            "attachments": [
                {
                    "filename": attachment.filename,
                    "content_type": attachment.content_type,
                    "data": base64.b64encode(attachment.file.read()).decode('utf-8')  # Convert bytes to base64 string for JSON serialization
                } for attachment in attachments
            ],
            "in_line_attachments": [
                {
                    "filename": attachment.filename,
                    "content_type": attachment.content_type,
                    "data": base64.b64encode(attachment.file.read()).decode('utf-8')  # Convert bytes to base64 string for JSON serialization
                } for attachment in in_line_attachments
            ],
            "folder_path": email_data.folder_path,
            "headers": email_data.headers,
            "priority": email_data.priority,
            "timestamp": email_data.timestamp,
            "is_draft": True,
            "server_details": {
                "imap": {
                    "server": user_data["imap_server"],
                    "port": user_data["imap_port"],
                    "user": user_data["imap_user"],
                    "password": user_data["imap_password"] # TODO: Raw password, consider encrypting?
                }
            },
            "draft_saved": email_data.draft_saved,
            "draft_folder_name": email_data.draft_folder_name,
            "draft_message_id": email_data.draft_message_id
        }
        _send_message_to_rabbitmq(message=message)

    except Exception as e:
        logging.error(f"Error while sending mail: {e}", exc_info=True)
        raise All_Exceptions(message="Failed to send mail", status_code=status.HTTP_503_SERVICE_UNAVAILABLE)


def validate_recaptcha(token: str) -> bool:
    """
    Validate Google Recaptcha token
    :param token: The recaptcha token to be validated
    :return: True if the token is valid, False otherwise
    """
    url = f"https://recaptchaenterprise.googleapis.com/v1/projects/{GOOGLE_RECAPTCHA_PROJECT_ID}/assessments?key={GOOGLE_RECAPTCHA_API_KEY}"
    payload = {
        "event": {
            "token": token,
            "siteKey": GOOGLE_RECAPTCHA_SITE_KEY,
        }
    }
    headers = {
        "Content-Type": "application/json"
    }

    try:
        response = requests.post(url, json=payload, headers=headers, timeout=5)
        result = response.json()
        logging.debug(f"Recaptcha validation response: {result}")

        response.raise_for_status()
        if "tokenProperties" in result:
            token_properties = result["tokenProperties"]
            if token_properties.get("valid"):
                return True

        return False

    except Exception as e:
        logging.error(f"Error validating recaptcha token: {e}", exc_info=True)
        return False
