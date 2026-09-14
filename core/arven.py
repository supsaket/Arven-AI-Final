from core.config import APP_NAME, VERSION, BOSS_NAME


class Arven:
    def __init__(self):
        self.name = APP_NAME
        self.version = VERSION
        self.boss = BOSS_NAME

    def status(self):
        return {
            "name": self.name,
            "version": self.version,
            "boss": self.boss,
            "status": "online"
        }
