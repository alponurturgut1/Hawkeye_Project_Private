import time
import logging

def setup_logger(level: str = "INFO") -> logging.Logger:
    logger = logging.getLogger("uavtrk")
    if logger.handlers:
        return logger
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    ch = logging.StreamHandler()
    fmt = logging.Formatter("[%(asctime)s] %(levelname)s - %(message)s")
    ch.setFormatter(fmt)
    logger.addHandler(ch)
    return logger

class RateLimiter:
    def __init__(self, period_s: float):
        self.period = period_s
        self.t_last = 0.0

    def ready(self) -> bool:
        now = time.time()
        if now - self.t_last >= self.period:
            self.t_last = now
            return True
        return False
