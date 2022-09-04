class User:
    def __init__(self, meta):
        self.id = meta["user"]["id"]
        self.name = meta["user"]["name"]
        self.account = meta["user"]["account"]
