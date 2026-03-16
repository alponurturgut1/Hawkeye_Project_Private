from enum import Enum, auto

class SystemState(Enum):
    INITIALIZING = auto()
    DETECTING = auto()
    TRACKING = auto()
    FOLLOWING = auto()
    LOST_TARGET = auto()
    RETURNING_HOME = auto()
    EMERGENCY = auto()
