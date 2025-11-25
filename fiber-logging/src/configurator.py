from .logger import get_logger

def init_logging(service: str, env: str = "dev"):
    return get_logger(service, env)
