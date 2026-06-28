import logging
from datetime import datetime
from PyQt6.QtCore import QObject, pyqtSignal

class LogSignaler(QObject):
    new_record = pyqtSignal(str, int) # message, level

class QtLogHandler(logging.Handler):
    """
    A logging handler that emits a signal for every log record.
    Useful for updating a UI component from a logger.
    """
    def __init__(self):
        super().__init__()
        self.signaler = LogSignaler()
        self.new_record = self.signaler.new_record
        self.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s', datefmt='%H:%M:%S'))

    def emit(self, record):
        try:
            msg = self.format(record)
            self.new_record.emit(msg, record.levelno)
        except Exception:
            pass

def setup_logger(name, level=logging.INFO):
    logger = logging.getLogger(name)
    logger.setLevel(level)
    
    # Prevent duplicate handlers if called multiple times
    if not logger.handlers:
        # Standard console output
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(name)s: %(message)s'))
        logger.addHandler(console_handler)
        
    return logger
