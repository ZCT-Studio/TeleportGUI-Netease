# -*- coding: utf-8 -*-
"""Platform-independent rules for named teleport locations and requests."""
import time

MAX_NAME_LENGTH = 32

def valid_name(name):
    return isinstance(name, (str, type(u''))) and 0 < len(name.strip()) <= MAX_NAME_LENGTH and not any(ord(c) < 32 for c in name)

class Locations(object):
    def __init__(self, data=None):
        self.data = data if isinstance(data, dict) else {}

    def add(self, name, location, limit):
        if not valid_name(name):
            return 'invalid_name'
        name = name.strip()
        if name in self.data:
            return 'exists'
        if len(self.data) >= limit:
            return 'limit'
        self.data[name] = location
        return 'ok'

    def rename(self, old, new):
        if old not in self.data:
            return 'missing'
        if not valid_name(new):
            return 'invalid_name'
        new = new.strip()
        if new in self.data:
            return 'exists'
        self.data[new] = self.data.pop(old)
        return 'ok'

    def delete(self, name):
        if name not in self.data:
            return 'missing'
        del self.data[name]
        return 'ok'

class Requests(object):
    def __init__(self, lifetime=120, clock=None):
        self.lifetime = lifetime
        self.clock = clock or time.time
        self.items = {}

    def expire(self):
        now = self.clock()
        for key, item in list(self.items.items()):
            if now >= item['expires']:
                del self.items[key]

    def send(self, sender, target, here=False):
        self.expire()
        if sender == target:
            return 'self'
        key = (sender, target)
        if key in self.items:
            return 'exists'
        self.items[key] = {'here': bool(here), 'expires': self.clock() + self.lifetime}
        return 'ok'

    def take(self, sender, target):
        self.expire()
        return self.items.pop((sender, target), None)

    def remove_player(self, player):
        for key in list(self.items):
            if player in key:
                del self.items[key]
