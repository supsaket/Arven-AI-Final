from core.config import (
    APP_NAME,
    VERSION,
    BOSS_NAME
)


class Identity:

    def __init__(self):

        self.name = APP_NAME
        self.version = VERSION
        self.boss = BOSS_NAME
        self.creator = BOSS_NAME

    def status(self):

        return {
            "name": self.name,
            "version": self.version,
            "boss": self.boss,
            "creator": self.creator,
            "status": "online"
        }