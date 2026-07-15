"""
Logs of API are stored in a file and can be viewed in a web page
Use the password "neko-nik" to view the logs
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
    Jinja2Templates,
    JSONResponse,
    HTMLResponse,
    APIRouter,
    Request,
    status,
    json
)
from src.utils.base.constants import NUMBER_OF_LOGS_TO_DISPLAY, LOG_FILE_PATH, LOGS_API_PASSWORD
import socket

# Load templates
templates = Jinja2Templates(directory="templates")


# Router
router = APIRouter()


# Logs of API
@router.get("/api", response_class=HTMLResponse, tags=["Logs"], summary="Logs of API")
def view_logs(request: Request, passwd: str="") -> HTMLResponse:
    """
    This endpoint is used to view the logs of the API in a web page
    Just go to /logs/api?passwd=neko-nik to view the logs
    """
    if passwd != LOGS_API_PASSWORD:
        # Fake 404 error to prevent unauthorized access
        return JSONResponse(content={"detail": "Not Found"}, status_code=status.HTTP_404_NOT_FOUND)

    logs = []
    with open(LOG_FILE_PATH, 'r') as file:
        for line in file:
            try:
                log_entry = json.loads(line)
                logs.append(log_entry)
            except json.JSONDecodeError:
                pass    # Skip the line if it is not a valid JSON

    logs.reverse()  # To show the latest logs first

    # To show only the latest 100 logs
    logs = logs[:NUMBER_OF_LOGS_TO_DISPLAY]
    response = {"request": request, "logs": logs}

    return templates.TemplateResponse("logs.html", response)


@router.get("/1219/whoami", tags=["Logs"], summary="Who am I")
def whoami() -> JSONResponse:
    """
    This endpoint is used to check if the API is running and to get the IP address of the container
    Just go to /logs/1219/whoami to check if the API is running and to get the IP address of the container
    """
    hostname = socket.gethostname()
    return JSONResponse(content={"hostname": hostname, "ip_address": socket.gethostbyname(hostname)})
