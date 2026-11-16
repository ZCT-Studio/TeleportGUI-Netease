# -*- coding: utf-8 -*-
import mod.server.extraServerApi as serverApi
import time
import math
import random
import copy
from TeleportGUI_Script.settings import DEFAULTS, validate
from TeleportGUI_Script.rules import Locations, Requests
from TeleportGUI_Script.platform_server import WorldStore, PlayerPositions

ServerSystem = serverApi.GetServerSystemCls()

class TeleportServer(ServerSystem):
    def __init__(self, namespace, system_name):
        ServerSystem.__init__(self, namespace, system_name)
        self.store = WorldStore()
        self.positions = PlayerPositions()
        self.config = dict(DEFAULTS)
        saved = self.store.data.get('config', {})
        for key in DEFAULTS:
            value = validate(key, saved.get(key))
            if value is not None:
                self.config[key] = value
        self.requests = Requests(self.config['request_lifetime'])
        self.pending_safety = {}
        self.random_jobs = {}
        self.back = {}
        self.deaths = {}
        self.cooldowns = {}
        self.last_action = {}
        self.ListenForEvent(serverApi.GetEngineNamespace(), serverApi.GetEngineSystemName(), "PlayerDieEvent", self, self.on_death)
        self.ListenForEvent('TeleportGUI', 'client', 'Action', self, self.on_action)
        self.ListenForEvent(serverApi.GetEngineNamespace(), serverApi.GetEngineSystemName(), 'DelServerPlayerEvent', self, self.on_leave)

    def on_death(self, args):
        player = args.get("id")
        location = self.positions.capture(player)
        if location:
            self.deaths[player] = location

    def on_leave(self, args):
        player = args.get('id')
        self.requests.remove_player(player)
        self.pending_safety.pop(player, None)
        self.random_jobs.pop(player, None)
        self.back.pop(player, None)
        self.deaths.pop(player, None)
        self.last_action.pop(player, None)

    def reply(self, player, action, status, **payload):
        payload.update({'action': action, 'status': status})
        self.NotifyToClient(player, 'Result', payload)

    def identity(self, player):
        uid = serverApi.GetEngineCompFactory().CreateHttp(serverApi.GetLevelId()).GetPlayerUid(player)
        return str(uid) if uid else None

    def is_admin(self, player, uid):
        factory = serverApi.GetEngineCompFactory()
        if factory.CreatePlayer(player).GetPlayerOperation() == 2:
            return True
        level = serverApi.GetLevelId()
        for method in ('CreateLobbyGame', 'CreateDomainGame'):
            try:
                host = getattr(factory, method)(level).GetHostPlayerUid()
                if host and str(host) == uid:
                    return True
            except Exception:
                pass
        return False

    def safe(self, location):
        block = serverApi.GetEngineCompFactory().CreateBlockInfo(serverApi.GetLevelId())
        x, y, z = [int(math.floor(v)) for v in location['pos']]
        names = []
        for dy in (-1, 0, 1):
            data = block.GetBlockNew((x, y + dy, z), location['dimension'])
            if not data or not data.get('name'):
                return False
            names.append(data['name'])
        air = ('minecraft:air', 'minecraft:cave_air', 'minecraft:void_air')
        hazards = ('lava', 'water', 'fire', 'cactus', 'magma', 'campfire', 'powder_snow', 'portal', 'sweet_berry')
        return names[1] in air and names[2] in air and names[0] not in air and not any(word in names[0] for word in hazards)

    def random_tp(self, player):
        if player in self.random_jobs:
            self.reply(player, 'random', 'busy'); return
        origin = self.positions.capture(player)
        if not origin:
            self.reply(player, 'random', 'unavailable'); return
        token = object()
        self.random_jobs[player] = token
        factory = serverApi.GetEngineCompFactory()
        level = serverApi.GetLevelId()
        radius = self.config['random_radius']
        def attempt(count):
            if self.random_jobs.get(player) is not token or player not in serverApi.GetPlayerList():
                return
            if count >= 8:
                self.random_jobs.pop(player, None)
                self.reply(player, 'random', 'unavailable'); return
            x = int(origin['pos'][0]) + random.randint(-radius, radius)
            z = int(origin['pos'][2]) + random.randint(-radius, radius)
            def loaded(result):
                if self.random_jobs.get(player) is not token or player not in serverApi.GetPlayerList():
                    return
                height = factory.CreateBlockInfo(level).GetTopBlockHeight((x, z), origin['dimension']) if result.get('code') == 1 else None
                target = {'dimension': origin['dimension'], 'pos': [x + 0.5, height + 1, z + 0.5]} if height is not None else None
                if target and self.safe(target):
                    self.random_jobs.pop(player, None)
                    self.reply(player, 'random', 'ok' if self.move(player, target) else 'unavailable')
                else:
                    attempt(count + 1)
            if not factory.CreateChunkSource(level).DoTaskOnChunkAsync(origin['dimension'], (x-1, 0, z-1), (x+1, 1, z+1), loaded):
                attempt(count + 1)
        attempt(0)

    def move(self, player, location, force=False):
        if time.time() < self.cooldowns.get(player, 0):
            return False
        before = self.positions.capture(player)
        if before is None or location is None:
            return False
        if self.config['safety_check'] and not force and not self.safe(location):
            self.pending_safety[player] = (time.time() + 30, copy.deepcopy(location))
            self.NotifyToClient(player, 'Risk', {'message': u'目的地可能不安全，是否继续传送？'})
            return False
        if not self.positions.teleport(player, location):
            return False
        self.cooldowns[player] = time.time() + self.config['cooldown']
        self.back[player] = before
        return True

    def on_action(self, args):
        player = args.get('__id__')
        action = args.get('action')
        if player not in serverApi.GetPlayerList() or not isinstance(action, (str, type(u""))):
            return
        now = time.time()
        if action != 'list' and now - self.last_action.get(player, 0) < 0.15:
            return
        self.last_action[player] = now
        uid = self.identity(player)
        if not uid:
            self.reply(player, action, 'identity_unavailable')
            return
        players = self.store.data['players']
        data = players.setdefault(uid, {'homes': {}, 'allow_requests': True})
        homes = Locations(data['homes'])
        warps = Locations(self.store.data['warps'])
        name = args.get('name')
        if action == 'list':
            online = []
            for other in serverApi.GetPlayerList():
                if other != player:
                    comp = serverApi.GetEngineCompFactory().CreateName(other)
                    online.append({'id': other, 'name': comp.GetName()})
            self.reply(player, action, 'ok', homes=homes.data, warps=warps.data, players=online, allow_requests=data.get('allow_requests', True), admin=self.is_admin(player, uid), config=self.config if self.is_admin(player, uid) else {})
            return
        if action == 'random':
            self.random_tp(player); return
        if action == 'confirm_risk':
            pending = self.pending_safety.pop(player, None)
            result = 'expired'
            if pending and pending[0] > time.time():
                result = 'ok' if self.move(player, pending[1], True) else 'unavailable'
            self.reply(player, action, result); return
        if action == 'cancel_risk':
            self.pending_safety.pop(player, None); return
        if action == 'config_set':
            if not self.is_admin(player, uid):
                self.reply(player, action, 'forbidden'); return
            key = args.get('key')
            if not isinstance(key, (str, type(u''))):
                self.reply(player, action, 'invalid'); return
            value = validate(key, args.get('value'))
            if value is None:
                self.reply(player, action, 'invalid'); return
            previous = copy.deepcopy(self.store.data.get('config'))
            updated = dict(self.config)
            updated[key] = value
            self.store.data['config'] = updated
            if self.store.save():
                self.config = updated
                self.requests.lifetime = updated['request_lifetime']
                result = 'ok'
            else:
                if previous is None:
                    self.store.data.pop('config', None)
                else:
                    self.store.data['config'] = previous
                result = 'save_failed'
        elif action in ('home_add', 'warp_add'):
            if action == 'warp_add' and not self.is_admin(player, uid):
                self.reply(player, action, 'forbidden'); return
            position = self.positions.capture(player)
            if position is None:
                self.reply(player, action, 'unavailable'); return
            result = (homes if action == 'home_add' else warps).add(name, position, self.config['home_limit'] if action == 'home_add' else self.config['warp_limit'])
            if result == 'ok' and not self.store.save(): result = 'save_failed'
        elif action in ('home_delete', 'warp_delete', 'home_rename', 'warp_rename'):
            if action.startswith('warp_') and not self.is_admin(player, uid):
                self.reply(player, action, 'forbidden'); return
            locations = homes if action.startswith('home_') else warps
            result = locations.rename(name, args.get('new_name')) if action.endswith('rename') else locations.delete(name)
            if result == 'ok' and not self.store.save(): result = 'save_failed'
        elif action in ('home_go', 'warp_go'):
            locations = homes if action == 'home_go' else warps
            location = locations.data.get(name) if isinstance(name, (str, type(u''))) else None
            result = 'ok' if location and self.move(player, location) else 'unavailable'
        elif action == 'death':
            result = 'ok' if self.move(player, self.deaths.get(player)) else 'unavailable'
        elif action == 'world_spawn':
            game = serverApi.GetEngineCompFactory().CreateGame(serverApi.GetLevelId())
            pos = game.GetSpawnPosition()
            location = {'dimension': game.GetSpawnDimension(), 'pos': list(pos)} if pos else None
            result = 'ok' if self.move(player, location) else 'unavailable'
        elif action == 'back':
            result = 'ok' if self.move(player, self.back.get(player)) else 'unavailable'
        elif action == 'allow_requests':
            value = args.get('value')
            if not isinstance(value, bool):
                self.reply(player, action, 'invalid'); return
            data['allow_requests'] = value
            result = 'ok' if self.store.save() else 'save_failed'
        elif action == 'tpa':
            target = args.get('target')
            if target not in serverApi.GetPlayerList():
                self.reply(player, action, 'offline'); return
            target_uid = self.identity(target)
            if not target_uid or not players.get(target_uid, {}).get('allow_requests', True):
                self.reply(player, action, 'forbidden'); return
            result = self.requests.send(player, target, args.get('here') is True)
            if result == 'ok':
                self.NotifyToClient(target, 'Request', {'sender': player, 'name': serverApi.GetEngineCompFactory().CreateName(player).GetName(), 'here': args.get('here') is True})
        elif action in ('accept', 'deny'):
            sender = args.get('sender')
            request = self.requests.take(sender, player)
            if not request or sender not in serverApi.GetPlayerList():
                result = 'expired'
            elif action == 'deny':
                self.reply(sender, 'tpa', 'denied'); result = 'ok'
            else:
                mover, destination = (player, sender) if request['here'] else (sender, player)
                result = 'ok' if self.move(mover, self.positions.capture(destination)) else 'unavailable'
                self.reply(sender, 'tpa', result)
        else:
            return
        self.reply(player, action, result)
