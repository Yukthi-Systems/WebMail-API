"""
This file has all the necessary libraries for the project to run
any new library should be added here and imported in the respective files
"""

# FastAPI libraries
from fastapi import FastAPI, Request, status, Response, Depends, APIRouter, BackgroundTasks, File, UploadFile, Form
from fastapi.responses import JSONResponse, HTMLResponse, PlainTextResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.templating import Jinja2Templates


# Object data modeling libraries
from pydantic import BaseModel, Field


# E-Mail libraries
from sievelib.factory import FiltersSet as SieveFiltersSet
from sievelib.managesieve import Client as SieveClient
from sievelib import parser as SieveParser
from imaplib import IMAP4_SSL
import smtplib
import email


# DB libraries
from typing import Annotated, AsyncGenerator, Optional, TypeAlias, List
from contextlib import asynccontextmanager
import aiomcache
import requests
import asyncpg


# other libraries
from datetime import datetime, timezone
from deprecated import deprecated
from threading import Thread
from functools import wraps
import calendar
import base64
import orjson
import time
import pika
import json
import uuid
import re
import os


# Configure logging 
from src.utils.base.constants import LOG_LEVEL, LOG_FILE_PATH
from src.utils.base.log_utils import configure_return_logger

logging = configure_return_logger(LOG_LEVEL=LOG_LEVEL, LOG_FILE_PATH=LOG_FILE_PATH)
