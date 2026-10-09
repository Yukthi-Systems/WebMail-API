"""
This is the main app file which contains all the endpoints of the API
This file is used to run the API
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
    CORSMiddleware,
    JSONResponse,
    FastAPI,
    Request
)
from src.utils.base.constants import ALLOWED_ORIGINS
from src.utils.models import All_Exceptions
from src.database import lifespan
from .routers import *


# Initialization
app = FastAPI(
    title="Yukthi WebMail - API",
    description="This is the API for Yukthi WebMail",
    version="2.2.7",
    docs_url=None,
    redoc_url=None,
    # docs_url="/docs",
    # redoc_url="/redoc",
    include_in_schema=True,
    lifespan=lifespan
)

# Add CORS middleware to allow cross origin requests
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

# Exception handler for wrong input
@app.exception_handler(All_Exceptions)
async def input_data_exception_handler(request: Request, exc: All_Exceptions):
    return JSONResponse(
        status_code=exc.status_code,
        content={"message": f"Oops! {exc.message}"}
    )


#    Endpoints    #
app.include_router(router=logs_router, prefix="/logs")
app.include_router(router=user_router, prefix="/user")
app.include_router(router=sieve_router, prefix="/sieve")
app.include_router(router=email_router, prefix="/email")
app.include_router(router=folder_router, prefix="/folder")
app.include_router(router=contacts_router, prefix="/contacts")
