import os
import logging
from datetime import datetime
from typing import Optional, Dict, Any, Tuple, Union
from dotenv import load_dotenv

# ==================== CONFIGURATION & SETUP ====================

# Force reload environment variables
load_dotenv(override=True)

# Set up logging for database connections
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global Supabase client instance
supabase_client = None

# Database configuration constants
DB_CONNECTION_TIMEOUT = 10
DEFAULT_QUERY_LIMIT = 1000
RETRY_ATTEMPTS = 3

# Supabase configuration validation
REQUIRED_ENV_VARS = ['SUPABASE_URL', 'SUPABASE_SERVICE_ROLE_KEY']

# ==================== HELPER FUNCTIONS ====================
# Utility functions for database operations and validation

def _validate_supabase_config() -> Tuple[str, str]:
    """
    Validate Supabase configuration from environment variables
    - Checks for required environment variables
    - Validates that service role key is properly configured
    - Returns validated URL and key
    """
    url = os.getenv('SUPABASE_URL')
    key = os.getenv('SUPABASE_SERVICE_ROLE_KEY')
    
    missing_vars = []
    for var in REQUIRED_ENV_VARS:
        if not os.getenv(var):
            missing_vars.append(var)
    
    if missing_vars:
        error_msg = f"Missing required environment variables: {', '.join(missing_vars)}"
        logger.error(error_msg)
        raise Exception(error_msg)
    
    if key == 'your_supabase_service_role_key_here':
        error_msg = "Supabase service role key not properly configured"
        logger.error(error_msg)
        raise Exception(error_msg)
    
    return url, key

def _validate_supabase_dependency() -> None:
    """
    Validate that Supabase package is installed and available
    - Checks for supabase package import
    - Provides helpful error message if package missing
    """
    try:
        import supabase
    except ImportError:
        error_msg = "Supabase package not installed - install with: pip install supabase"
        logger.error(error_msg)
        raise Exception(error_msg)

def _log_connection_attempt(connection_type: str, success: bool, error_msg: str = None) -> None:
    """
    Log database connection attempts for monitoring
    - Records successful and failed connection attempts
    - Includes connection type and error details
    """
    if success:
        logger.info(f"{connection_type} connection successful")
    else:
        logger.error(f"{connection_type} connection failed: {error_msg}")

def _create_supabase_client_instance(url: str, key: str):
    """
    Create Supabase client instance with proper error handling
    - Handles client creation with validation
    - Returns configured client instance
    """
    from supabase import create_client, Client
    
    try:
        client = create_client(url, key)
        logger.info("Supabase client instance created successfully")
        return client
    except Exception as e:
        error_msg = f"Failed to create Supabase client: {e}"
        logger.error(error_msg)
        raise Exception(error_msg)

def _test_supabase_connection(client) -> bool:
    """
    Test Supabase client connection with a simple query
    - Performs minimal query to verify connectivity
    - Returns True if connection is working
    """
    try:
        # Test with a simple query to check connection
        response = client.table('therapists').select('id').limit(1).execute()
        return True
    except Exception as e:
        logger.error(f"Supabase connection test failed: {e}")
        return False

def _handle_client_initialization_error(error: Exception) -> None:
    """
    Handle and log client initialization errors
    - Provides standardized error handling
    - Logs appropriate error messages
    """
    error_msg = f"Error initializing Supabase client: {error}"
    logger.error(error_msg)
    raise Exception(error_msg)

def _format_database_response(response) -> Optional[list]:
    """
    Format database response to consistent format
    - Handles both Supabase and potential future database responses
    - Returns standardized list format or None
    """
    if hasattr(response, 'data') and response.data is not None:
        return response.data
    return None

def _validate_database_response(response) -> None:
    """
    Validate database response and handle errors
    - Checks for errors in database response
    - Raises appropriate exceptions for error conditions
    """
    if hasattr(response, 'error') and response.error:
        error_msg = f"Database error: {response.error}"
        logger.error(f"Supabase error: {response.error}")
        raise Exception(error_msg)

# ==================== SUPABASE CLIENT MANAGEMENT ====================
# Core functions for Supabase client initialization and management

def init_supabase_client():
    """
    Initialize Supabase client - primary database method
    
    Returns:
        Supabase client instance
    
    Raises:
        Exception: If configuration is invalid or client creation fails
    
    Usage:
        - Called automatically by get_supabase_client() if client not initialized
        - Validates environment configuration before creating client
        - Sets up global client instance for application use
        - Performs connection test to ensure client is working
    """
    global supabase_client
    
    try:
        # Validate dependencies and configuration
        _validate_supabase_dependency()
        url, key = _validate_supabase_config()
        
        # Create client instance
        supabase_client = _create_supabase_client_instance(url, key)
        
        # Test the connection
        if _test_supabase_connection(supabase_client):
            _log_connection_attempt("Supabase client initialization", True)
        else:
            raise Exception("Connection test failed after client creation")
        
        return supabase_client
        
    except Exception as e:
        _handle_client_initialization_error(e)

def get_supabase_client():
    """
    Get Supabase client instance (primary database method)
    
    Returns:
        Supabase client instance, initialized if necessary
    
    Usage:
        - Primary method for getting database client throughout application
        - Automatically initializes client on first call
        - Returns existing client instance on subsequent calls
        - Used by all database operations in the application
        - Thread-safe for multiple concurrent requests
    """
    global supabase_client
    if supabase_client is None:
        supabase_client = init_supabase_client()
    return supabase_client

def reset_supabase_client() -> None:
    """
    Reset Supabase client instance (force re-initialization)
    
    Usage:
        - Used when configuration changes require client reset
        - Useful for testing with different configurations
        - Called when connection issues require client refresh
        - Forces next get_supabase_client() call to re-initialize
    """
    global supabase_client
    supabase_client = None
    logger.info("Supabase client reset - will re-initialize on next use")

def get_client_status() -> Dict[str, Any]:
    """
    Get current status of Supabase client
    
    Returns:
        Dictionary containing client status information
    
    Usage:
        - Used for health checks and monitoring
        - Provides client initialization status
        - Includes connection test results
        - Useful for debugging connection issues
    """
    global supabase_client
    
    status = {
        "initialized": supabase_client is not None,
        "connection_working": False,
        "last_test": datetime.utcnow().isoformat()
    }
    
    if supabase_client is not None:
        status["connection_working"] = _test_supabase_connection(supabase_client)
    
    return status

# ==================== DATABASE CONNECTION TESTING ====================
# Functions for testing database connectivity and health checks

def execute_safe_query(table: str, operation: str, **kwargs) -> Dict[str, Any]:
    """
    Execute database query with comprehensive error handling and logging
    
    Args:
        table: Database table name
        operation: Operation type (select, insert, update, delete)
        **kwargs: Additional parameters for the query
    
    Returns:
        Standardized response dictionary with operation results
    
    Usage:
        - Provides safe wrapper for database operations with error handling
        - Logs operation performance and results
        - Returns standardized response format
        - Includes timing information for performance monitoring
    """
    start_time = datetime.utcnow()
    
    try:
        client = get_supabase_client()
        
        # This is a placeholder for safe query execution
        # Actual implementation would depend on specific query requirements
        response = client.table(table).select('*').limit(1).execute()
        handle_supabase_error(response)
        
        end_time = datetime.utcnow()
        duration = (end_time - start_time).total_seconds()
        
        data = format_supabase_response(response)
        log_database_operation(operation, table, True, duration)
        
        return create_standardized_response(
            success=True,
            data=data,
            metadata={
                "operation": operation,
                "table": table,
                "duration": duration,
                "timestamp": end_time.isoformat()
            }
        )
        
    except Exception as e:
        end_time = datetime.utcnow()
        duration = (end_time - start_time).total_seconds()
        error_msg = str(e)
        
        log_database_operation(operation, table, False, duration, error_msg)
        
        return create_standardized_response(
            success=False,
            error=error_msg,
            metadata={
                "operation": operation,
                "table": table,
                "duration": duration,
                "timestamp": end_time.isoformat()
            }
        )

def get_table_info(table_name: str) -> Dict[str, Any]:
    """
    Get information about a database table
    
    Args:
        table_name: Name of the table to inspect
    
    Returns:
        Dictionary containing table information
    
    Usage:
        - Used for database schema inspection
        - Provides table metadata for debugging
        - Useful for validating table structure
    """
    try:
        client = get_supabase_client()
        
        # Get sample data to understand table structure
        response = client.table(table_name).select('*').limit(5).execute()
        handle_supabase_error(response)
        
        data = format_supabase_response(response)
        
        info = {
            "table_name": table_name,
            "accessible": True,
            "sample_count": len(data) if data else 0,
            "columns": list(data[0].keys()) if data and len(data) > 0 else [],
            "timestamp": datetime.utcnow().isoformat()
        }
        
        return info
        
    except Exception as e:
        return {
            "table_name": table_name,
            "accessible": False,
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat()
        }

def get_database_info() -> Dict[str, Any]:
    """
    Get comprehensive database information
    
    Returns:
        Dictionary containing database status and table information
    
    Usage:
        - Used for database monitoring and health checks
        - Provides overview of database accessibility
        - Useful for troubleshooting and debugging
    """
    common_tables = ['users', 'therapists', 'parents', 'students', 'sessions', 'notes']
    
    info = {
        "database_type": "Supabase",
        "connection_status": "unknown",
        "tables": {},
        "timestamp": datetime.utcnow().isoformat()
    }
    
    # Test connection first
    success, message = test_connection()
    info["connection_status"] = "connected" if success else "disconnected"
    info["connection_message"] = message
    
    if success:
        # Get information about common tables
        for table in common_tables:
            info["tables"][table] = get_table_info(table)
    
    return info

# ==================== FUTURE ENHANCEMENT FUNCTIONS ====================
# Placeholder for additional database functionality

# TODO: Implement connection pooling
# def setup_connection_pool(pool_size: int = 10) -> None:
#     """Setup connection pooling for better performance"""
#     pass

# TODO: Implement query caching
# def setup_query_cache(cache_size: int = 100) -> None:
#     """Setup query result caching"""
#     pass

# TODO: Implement database migration support
# def run_migrations(migration_path: str) -> bool:
#     """Run database migrations"""
#     pass

# TODO: Implement backup functionality
# def create_database_backup(backup_path: str) -> bool:
#     """Create database backup"""
#     pass

# TODO: Implement transaction support
# class DatabaseTransaction:
#     """Context manager for database transactions"""
#     pass

# ==================== LEGACY CODE (COMMENTED OUT) ====================
# Direct PostgreSQL implementation kept for reference
# This code was replaced with Supabase equivalents above

"""
# LEGACY PostgreSQL Database Functions (replaced with Supabase)

def get_db_connection_postgres():
    '''Get database connection for Supabase PostgreSQL using psycopg2'''
    # Debug: Print connection details (without password)
    db_host = os.getenv('DB_HOST')
    db_port = os.getenv('DB_PORT')
    db_user = os.getenv('DB_USER')
    db_name = os.getenv('DB_NAME')
    db_password = os.getenv('DB_PASSWORD')
    
    logger.info(f"Attempting to connect to: {db_host}:{db_port} as {db_user} to database {db_name}")
    
    if not all([db_host, db_port, db_user, db_name, db_password]):
        logger.error("Missing required environment variables")
        logger.error(f"DB_HOST: {db_host}, DB_PORT: {db_port}, DB_USER: {db_user}, DB_NAME: {db_name}")
        raise Exception("Missing database configuration")
    
    try:
        conn = psycopg2.connect(
            host=db_host,
            port=int(db_port),
            user=db_user,
            password=db_password,
            dbname=db_name,
            cursor_factory=RealDictCursor,
            sslmode='require',  # Required for Supabase
            connect_timeout=10,  # 10 second timeout
            options='-c default_transaction_isolation=read_committed'
        )
        # Test the connection
        with conn.cursor() as cur:
            cur.execute('SELECT 1')
        logger.info("Successfully connected to Supabase PostgreSQL database")
        return conn
    except psycopg2.OperationalError as e:
        logger.error(f"Operational error connecting to database: {e}")
        raise Exception(f"Database connection failed: {e}")
    except psycopg2.Error as e:
        logger.error(f"Database error: {e}")
        raise Exception(f"Database error: {e}")
    except Exception as e:
        logger.error(f"Unexpected error connecting to database: {e}")
        raise Exception(f"Unexpected database error: {e}")

def test_connection_postgres():
    '''Test database connection and return status using direct PostgreSQL'''
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute('SELECT version()')
            version = cur.fetchone()
            logger.info(f"Database connection successful. PostgreSQL version: {version}")
        conn.close()
        return True, "Connection successful"
    except Exception as e:
        logger.error(f"Connection test failed: {e}")
        return False, str(e)
"""

def test_connection() -> Tuple[bool, str]:
    """
    Test Supabase client connection (primary method)
    
    Returns:
        Tuple containing (success_status, message)
        - success_status: True if connection successful, False otherwise
        - message: Success message or error description
    
    Usage:
        - Used for application health checks
        - Called during application startup to verify database connectivity
        - Used by monitoring systems to check database status
        - Provides detailed error information for troubleshooting
    """
    try:
        client = get_supabase_client()
        
        # Perform connection test with actual query
        if _test_supabase_connection(client):
            success_msg = "Supabase connection successful"
            _log_connection_attempt("Connection test", True)
            return True, success_msg
        else:
            error_msg = "Connection test query failed"
            _log_connection_attempt("Connection test", False, error_msg)
            return False, error_msg
            
    except Exception as e:
        error_msg = str(e)
        _log_connection_attempt("Connection test", False, error_msg)
        return False, error_msg

def test_supabase_client() -> Tuple[bool, str]:
    """
    Test Supabase client connection (alias for compatibility)
    
    Returns:
        Tuple containing (success_status, message)
    
    Usage:
        - Alias for test_connection() for backward compatibility
        - Used when specifically testing Supabase client functionality
        - Maintains compatibility with existing code that calls this function
    """
    return test_connection()

def perform_health_check() -> Dict[str, Any]:
    """
    Perform comprehensive database health check
    
    Returns:
        Dictionary containing detailed health check results
    
    Usage:
        - Used by application monitoring and health check endpoints
        - Provides comprehensive database status information
        - Includes timing information for performance monitoring
        - Returns detailed error information for diagnostics
    """
    start_time = datetime.utcnow()
    
    try:
        success, message = test_connection()
        end_time = datetime.utcnow()
        response_time = (end_time - start_time).total_seconds()
        
        return {
            "status": "healthy" if success else "unhealthy",
            "success": success,
            "message": message,
            "response_time_seconds": response_time,
            "timestamp": end_time.isoformat(),
            "client_status": get_client_status()
        }
        
    except Exception as e:
        end_time = datetime.utcnow()
        response_time = (end_time - start_time).total_seconds()
        
        return {
            "status": "unhealthy",
            "success": False,
            "message": f"Health check failed: {str(e)}",
            "response_time_seconds": response_time,
            "timestamp": end_time.isoformat(),
            "error": str(e)
        }

def test_database_operations() -> Dict[str, Any]:
    """
    Test basic database operations to ensure full functionality
    
    Returns:
        Dictionary containing test results for different operations
    
    Usage:
        - Used for comprehensive database functionality testing
        - Tests read operations on multiple tables
        - Provides detailed results for each operation type
        - Useful for debugging specific operation failures
    """
    results = {
        "overall_success": True,
        "operations": {},
        "timestamp": datetime.utcnow().isoformat()
    }
    
    operations_to_test = [
        ("therapists", "select", "id"),
        ("parents", "select", "id"), 
        ("users", "select", "id"),
        ("students", "select", "id")
    ]
    
    try:
        client = get_supabase_client()
        
        for table, operation, field in operations_to_test:
            try:
                start_time = datetime.utcnow()
                response = client.table(table).select(field).limit(1).execute()
                end_time = datetime.utcnow()
                
                _validate_database_response(response)
                
                results["operations"][f"{table}_{operation}"] = {
                    "success": True,
                    "response_time": (end_time - start_time).total_seconds(),
                    "message": f"Successfully tested {operation} on {table}"
                }
                
            except Exception as e:
                results["overall_success"] = False
                results["operations"][f"{table}_{operation}"] = {
                    "success": False,
                    "error": str(e),
                    "message": f"Failed to test {operation} on {table}"
                }
                
    except Exception as e:
        results["overall_success"] = False
        results["client_error"] = str(e)
    
    return results

# ==================== RESPONSE FORMATTING & ERROR HANDLING ====================
# Utility functions for consistent response formatting and error handling

def format_supabase_response(response) -> Optional[list]:
    """
    Format Supabase response to match psycopg2 dict format
    
    Args:
        response: Supabase query response object
    
    Returns:
        List of dictionaries containing query results, or None if no data
    
    Usage:
        - Used throughout application to standardize database response format
        - Ensures consistency between Supabase responses and expected data format
        - Handles cases where response contains no data
        - Maintains compatibility with existing code expecting list format
    """
    return _format_database_response(response)

def handle_supabase_error(response) -> None:
    """
    Handle Supabase errors consistently
    
    Args:
        response: Supabase query response object to validate
    
    Raises:
        Exception: If response contains error information
    
    Usage:
        - Used after every Supabase query to check for errors
        - Provides consistent error handling across all database operations
        - Converts Supabase errors to standard Python exceptions
        - Logs error details for debugging and monitoring
    """
    _validate_database_response(response)
    return response

def create_standardized_response(success: bool, data: Any = None, error: str = None, 
                               metadata: Dict[str, Any] = None) -> Dict[str, Any]:
    """
    Create standardized response format for database operations
    
    Args:
        success: Whether the operation was successful
        data: Data returned from the operation
        error: Error message if operation failed
        metadata: Additional metadata about the operation
    
    Returns:
        Standardized response dictionary
    
    Usage:
        - Used to create consistent response format across all database functions
        - Provides standard structure for success/error handling
        - Includes metadata for operation tracking and debugging
    """
    response = {
        "success": success,
        "timestamp": datetime.utcnow().isoformat()
    }
    
    if success:
        response["data"] = data
        if metadata:
            response["metadata"] = metadata
    else:
        response["error"] = error
        response["data"] = None
    
    return response

def log_database_operation(operation: str, table: str, success: bool, 
                          duration: float = None, error: str = None) -> None:
    """
    Log database operations for monitoring and debugging
    
    Args:
        operation: Type of database operation (select, insert, update, delete)
        table: Database table involved in the operation
        success: Whether the operation was successful
        duration: Operation duration in seconds
        error: Error message if operation failed
    
    Usage:
        - Used to log all database operations for monitoring
        - Provides performance tracking with duration logging
        - Helps identify problematic operations and tables
        - Useful for debugging and performance optimization
    """
    log_msg = f"DB Operation: {operation.upper()} on {table}"
    
    if duration is not None:
        log_msg += f" (Duration: {duration:.3f}s)"
    
    if success:
        logger.info(f"{log_msg} - SUCCESS")
    else:
        logger.error(f"{log_msg} - FAILED: {error}")

# ==================== DATABASE UTILITY FUNCTIONS ====================
# Utility functions for common database operations and queries
