"""
This module manages the database connections for PostgreSQL and Memcached.
It includes the following components:
1. **PostgreSQL Database Connection**: 
   - A class `Database` that manages the connection pool for PostgreSQL.
   - It provides methods to create a connection pool, acquire a connection, and close the pool.
2. **Memcached Database Connection**:
    - A class `MemcachedClient` that manages the connection to Memcached.
    - It provides methods to initialize the client, close the client, and get the client instance.
3. **Dependency Injection**:
    - `get_db` and `get_cache_client` functions that provide the PostgreSQL and Memcached clients respectively.
4. **Lifespan Context Manager**:
    - A context manager `lifespan` that initializes and closes the database connections when the FastAPI application starts and stops.
"""

from src.utils.base.libraries import Depends, status, asyncpg, aiomcache, logging, asynccontextmanager, Annotated, AsyncGenerator, Optional, FastAPI
from src.utils.base.constants import POSTGRES_DB_URI, POSTGRES_POOL_SIZE, MEMCACHED_DB_HOST, MEMCACHED_DB_PORT, MEMCACHED_DB_POOL_SIZE, ADMIN_POSTGRES_DB_URI, ADMIN_POSTGRES_POOL_SIZE, POSTGRES_POOL_MAX_INACTIVE_CONNECTION_LIFETIME
from src.utils.models import All_Exceptions


# ======= PostgreSQL DB Connection =======


class Database:
    """PostgreSQL database connection pool manager"""
    def __init__(self):
        """Initialize the database connection pool"""
        self.pool = None

    async def create_pool(self):
        """Create connection pool if it doesn't exist"""
        if self.pool is None:
            try:
                self.pool = await asyncpg.create_pool(
                    POSTGRES_DB_URI,
                    min_size=int(POSTGRES_POOL_SIZE / 2),
                    max_size=POSTGRES_POOL_SIZE,
                    max_inactive_connection_lifetime=POSTGRES_POOL_MAX_INACTIVE_CONNECTION_LIFETIME
                )
                logging.debug("PostgreSQL connection pool created successfully")

            except asyncpg.exceptions.PostgresError as e:
                logging.error(f"Error creating PostgreSQL connection pool: {e}")
                raise ValueError("Failed to create PostgreSQL connection pool")

            except Exception as e:
                logging.error(f"Unexpected error while creating connection pool: {e}", exc_info=True)
                raise

    @asynccontextmanager
    async def get_connection(self) -> AsyncGenerator[asyncpg.Connection, None]:
        """Get database connection from pool"""
        if not self.pool:
            await self.create_pool()
        async with self.pool.acquire() as connection:
            logging.info("Pool of connections acquired for PostgreSQL DB successfully")
            yield connection
            logging.info("Connection released back to the pool")

    async def close(self):
        """Close the pool when shutting down"""
        if self.pool:
            await self.pool.close()
            logging.debug("PostgreSQL connection pool closed successfully")
            self.pool = None


db = Database()


async def get_db() -> AsyncGenerator[asyncpg.Connection, None]:
    async with db.get_connection() as conn:
        yield conn


PostgresDep = Annotated[asyncpg.Connection, Depends(get_db)]


# ======= PostgreSQL V2 Admin DB Connection =======


class AdminDatabase:
    """PostgreSQL Admin V2 database connection pool manager"""
    def __init__(self):
        """Initialize the PostgreSQL Admin V2 database connection pool"""
        self.pool = None

    async def create_pool(self):
        """Create connection pool if it doesn't exist"""
        if self.pool is None:
            try:
                self.pool = await asyncpg.create_pool(
                    ADMIN_POSTGRES_DB_URI,
                    min_size=int(ADMIN_POSTGRES_POOL_SIZE / 2),
                    max_size=ADMIN_POSTGRES_POOL_SIZE,
                    max_inactive_connection_lifetime=300   # 5 minutes
                )
                logging.debug("PostgreSQL admin connection pool created successfully")

            except asyncpg.exceptions.PostgresError as e:
                logging.error(f"Error creating PostgreSQL admin connection pool: {e}")
                raise ValueError("Failed to create PostgreSQL admin connection pool")

            except Exception as e:
                logging.error(f"Unexpected error while creating PostgreSQL admin connection pool: {e}", exc_info=True)
                raise

    @asynccontextmanager
    async def get_connection(self) -> AsyncGenerator[asyncpg.Connection, None]:
        """Get database connection from pool"""
        if not self.pool:
            await self.create_pool()
        async with self.pool.acquire() as connection:
            logging.info("Pool of connections acquired for PostgreSQL admin DB successfully")
            yield connection
            logging.info("Connection released back to the pool")

    async def close(self):
        """Close the pool when shutting down"""
        if self.pool:
            await self.pool.close()
            logging.debug("PostgreSQL admin connection pool closed successfully")
            self.pool = None


AdminDB = AdminDatabase()


async def get_admin_db() -> AsyncGenerator[asyncpg.Connection, None]:
    async with AdminDB.get_connection() as conn:
        yield conn


AdminPostgresDep = Annotated[asyncpg.Connection, Depends(get_admin_db)]


# ======= Memcached DB Connection =======


class MemcachedClient:
    client: Optional[aiomcache.Client] = None

    @classmethod
    async def initialize(cls):
        """Initialize the Memcached client with connection pooling"""
        if not cls.client:
            cls.client = aiomcache.Client(
                host=MEMCACHED_DB_HOST,
                port=int(MEMCACHED_DB_PORT),
                pool_minsize=int(MEMCACHED_DB_POOL_SIZE / 2),
                pool_size=int(MEMCACHED_DB_POOL_SIZE)
            )

    @classmethod
    async def close(cls):
        """Close the Memcached client"""
        if cls.client:
            await cls.client.close()
            cls.client = None

    @classmethod
    def get_client(cls) -> aiomcache.Client:
        """Get the Memcached client instance"""
        if not cls.client:
            raise All_Exceptions(
                message="Memcached client is not initialized",
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE
            )
        return cls.client


async def get_cache_client() -> AsyncGenerator[aiomcache.Client, None]:
    """Dependency for getting Memcached client"""
    client = MemcachedClient.get_client()
    try:
        yield client
    except aiomcache.exceptions.ClientException as e:
        raise All_Exceptions(
            message=f"Memcached error: {str(e)}",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE
        )


MemcachedDep = Annotated[aiomcache.Client, Depends(get_cache_client)]


# ======= Lifespan Context Manager =======


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for database connection"""
    logging.info("Initializing all database connections (PostgreSQL and Memcached)")
    try:
        # Initialize PostgreSQL connection pool
        logging.debug("Beginning to create database pool")
        await db.create_pool()
        logging.info("PostgreSQL Db pool created successfully")

        # Initialize PostgreSQL Admin connection pool
        logging.debug("Beginning to create PostgreSQL admin pool")
        await AdminDB.create_pool()
        logging.info("PostgreSQL Admin Db pool created successfully")

        # Initialize Memcached connection pool
        logging.debug("Beginning to create Memcached pool")
        await MemcachedClient.initialize()
        logging.info("Memcached pool created successfully")

        yield

    except Exception as e:
        logging.error(f"Error during lifespan initialization: {e}", exc_info=True)
        raise

    finally:
        # Shutdown: close all connections
        logging.debug("Shutting down all database connections")
        await db.close()
        await AdminDB.close()
        await MemcachedClient.close()
        logging.info("All database connections closed successfully")
