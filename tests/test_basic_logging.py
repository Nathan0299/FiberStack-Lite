from fiber_logging.configurator import init_logging

def test_logger_initialization():
    logger = init_logging("test-service")
    logger.info("test-message")
