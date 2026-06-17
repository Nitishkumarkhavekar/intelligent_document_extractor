import logging
from functools import wraps

# Setup basic logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("DocumentExtractor")

def log_execution(func):
    """Aspect-oriented decorator for logging function execution."""
    @wraps(func)
    def wrapper(*args, **kwargs):
        logger.info(f"Executing: {func.__name__}")
        result = func(*args, **kwargs)
        logger.info(f"Completed: {func.__name__}")
        return result
    return wrapper

def handle_exceptions(func):
    """Aspect-oriented decorator for unified exception handling."""
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            logger.error(f"Exception in {func.__name__}: {str(e)}")
            raise e
    return wrapper
