# -*- coding: utf-8 -*-
# SPDX-FileCopyrightText: ZCT Studio
# SPDX-License-Identifier: GPL-3.0-only
import copy
import math
import mod.server.extraServerApi as serverApi
import random
import time
from TeleportGUI_Script.commands import execute as execute_command
from TeleportGUI_Script.platform_server import WorldStore, PlayerPositions
from TeleportGUI_Script.rules import Locations, Requests
from TeleportGUI_Script.settings import DEFAULTS, validate, POPUP_POSITIONS

ServerSystem = serverApi.GetServerSystemCls()


class TeleportServer(ServerSystem):
    def __init__(self, namespace, system_name):
        ServerSystem.__init__(self, namespace, system_name)
        self.ListenForEvent(serverApi.GetEngineNamespace(), serverApi.GetEngineSystemName(),
                            'CustomCommandTriggerServerEvent', self, self.on_command)
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
        self.spawn_jobs = {}
        self.back = {}
        self.deaths = {}
        self.cooldowns = {}
        self.last_action = {}
        self.ListenForEvent(serverApi.GetEngineNamespace(), serverApi.GetEngineSystemName(), "PlayerDieEvent", self,
                            self.on_death)
        self.ListenForEvent('TeleportGUI', 'client', 'Action', self, self.on_action)
        self.ListenForEvent(serverApi.GetEngineNamespace(), serverApi.GetEngineSystemName(), 'DelServerPlayerEvent',
                            self, self.on_leave)

    def on_command(self, args):
        execute_command(self, args)

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
        self.spawn_jobs.pop(player, None)
        self.back.pop(player, None)
        self.deaths.pop(player, None)
        self.last_action.pop(player, None)

    def reply(self, player, action, status, **payload):
        cooldown_player = payload.pop('cooldown_player', player)
        if status == 'cooldown':
            payload['remaining'] = max(1, self.cooldown_remaining(cooldown_player))
            payload['other_player'] = cooldown_player != player
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
        return names[1] in air and names[2] in air and names[0] not in air and not any(
            word in names[0] for word in hazards)

    def random_tp(self, player):
        if self.cooldown_remaining(player):
            self.reply(player, 'random', 'cooldown')
            return
        if player in self.random_jobs:
            self.reply(player, 'random', 'busy');
            return
        origin = self.positions.capture(player)
        if not origin:
            self.reply(player, 'random', 'unavailable');
            return
        token = object()
        self.random_jobs[player] = token
        factory = serverApi.GetEngineCompFactory()
        level = serverApi.GetLevelId()
        radius = self.config['random_radius']
        game = factory.CreateGame(level)

        def finish(status):
            if self.random_jobs.get(player) is not token:
                return
            self.random_jobs.pop(player, None)
            if player in serverApi.GetPlayerList():
                self.reply(player, 'random', status)

        def attempt(count):
            if self.random_jobs.get(player) is not token or player not in serverApi.GetPlayerList():
                return
            if count >= 12:
                finish('random_no_safe');
                return
            x = int(math.floor(origin['pos'][0])) + random.randint(-radius, radius)
            z = int(math.floor(origin['pos'][2])) + random.randint(-radius, radius)

            def retry():
                if self.random_jobs.get(player) is token:
                    game.AddTimer(0.1, lambda: attempt(count + 1))

            def loaded(result):
                if self.random_jobs.get(player) is not token or player not in serverApi.GetPlayerList():
                    return
                if not result or result.get('code') != 1:
                    retry();
                    return
                block = factory.CreateBlockInfo(level)
                offsets = [(0, 0), (2, 0), (-2, 0), (0, 2), (0, -2), (4, 4), (-4, 4), (4, -4), (-4, -4)]
                for dx, dz in offsets:
                    px, pz = x + dx, z + dz
                    height = block.GetTopBlockHeight((px, pz), origin['dimension'])
                    if height is None or height >= 32766:
                        continue
                    target = {'dimension': origin['dimension'], 'pos': [px + 0.5, height + 1, pz + 0.5]}
                    if self.safe(target):
                        status = self.move_status(player, target)
                        finish(status)
                        return
                retry()

            if not factory.CreateChunkSource(level).DoTaskOnChunkAsync(origin['dimension'], (x - 5, 0, z - 5),
                                                                       (x + 5, 1, z + 5), loaded):
                retry()

        game.AddTimer(45, lambda: finish('random_timeout'))
        attempt(0)

    def world_spawn_tp(self, player):
        if self.cooldown_remaining(player):
            self.reply(player, 'world_spawn', 'cooldown')
            return
        if player in self.spawn_jobs:
            self.reply(player, 'world_spawn', 'busy')
            return
        factory = serverApi.GetEngineCompFactory()
        level = serverApi.GetLevelId()
        game = factory.CreateGame(level)
        pos = game.GetSpawnPosition()
        dimension = game.GetSpawnDimension()
        if not pos or dimension is None:
            self.reply(player, 'world_spawn', 'unavailable')
            return
        token = object()
        self.spawn_jobs[player] = token
        x, y, z = pos

        def finish(location):
            if self.spawn_jobs.get(player) is not token:
                return
            self.spawn_jobs.pop(player, None)
            if player not in serverApi.GetPlayerList():
                return
            if location is None:
                self.reply(player, 'world_spawn', 'unavailable')
                return
            self.reply(player, 'world_spawn', self.move_status(player, location))

        def loaded(result):
            if self.spawn_jobs.get(player) is not token:
                return
            if result.get('code') != 1:
                finish(None)
                return
            # Explicit setworldspawn positions retain their specified height.
            if y != 32767:
                finish({'dimension': dimension, 'pos': [x + 0.5, y, z + 0.5]})
                return
            block = factory.CreateBlockInfo(level)
            offsets = sorted(((dx, dz) for dx in range(-4, 5) for dz in range(-4, 5)),
                             key=lambda p: p[0] * p[0] + p[1] * p[1])
            for dx, dz in offsets:
                height = block.GetTopBlockHeight((x + dx, z + dz), dimension)
                if height is None or height >= 32766:
                    continue
                location = {'dimension': dimension, 'pos': [x + dx + 0.5, height + 1, z + dz + 0.5]}
                if self.safe(location):
                    finish(location)
                    return
            finish(None)

        game.AddTimer(15, lambda: finish(None))
        if not factory.CreateChunkSource(level).DoTaskOnChunkAsync(dimension, (x - 4, 0, z - 4), (x + 4, 1, z + 4),
                                                                   loaded):
            finish(None)

    def cooldown_remaining(self, player):
        return max(0, int(math.ceil(self.cooldowns.get(player, 0) - time.time())))

    def move_status(self, player, location, force=False, passive=False):
        if not passive and self.cooldown_remaining(player):
            return 'cooldown'
        if self.move(player, location, force, passive):
            return 'ok'
        return 'risk' if player in self.pending_safety else 'unavailable'

    def move(self, player, location, force=False, passive=False):
        if not passive and time.time() < self.cooldowns.get(player, 0):
            return False
        before = self.positions.capture(player)
        if before is None or location is None:
            return False
        self.pending_safety.pop(player, None)
        if self.config['safety_check'] and not force and not self.safe(location):
            self.pending_safety[player] = (time.time() + 30, copy.deepcopy(location), passive)
            self.NotifyToClient(player, 'Risk', {'message': u'目的地可能不安全，是否继续传送？'})
            return False
        if not self.positions.teleport(player, location):
            return False
        self.spawn_jobs.pop(player, None)
        if not passive:
            self.cooldowns[player] = time.time() + self.config['cooldown']
        self.back[player] = before
        return True

    def on_action(self, args):
        player = args.get('__id__')
        action = args.get('action')
        if player not in serverApi.GetPlayerList() or not isinstance(action, (str, type(u""))):
            return
        now = time.time()
        if action not in ('list', 'accept', 'deny', 'confirm_risk', 'config_batch') and now - self.last_action.get(
                player, 0) < 0.15:
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
            self.requests.expire()
            incoming = []
            for (sender, target), request in self.requests.items.items():
                if target == player and sender in serverApi.GetPlayerList():
                    incoming.append(
                        {'id': sender, 'name': serverApi.GetEngineCompFactory().CreateName(sender).GetName(),
                         'here': request['here'], 'remaining': max(0, int(request['expires'] - time.time()))})
            incoming.sort(key=lambda item: item['remaining'])
            self.reply(player, action, 'ok',
                       features={'home': self.config['home_limit'] > 0, 'warp': self.config['warp_limit'] > 0,
                                 'random': self.config['random_radius'] > 0},
                       popup_position=data.get('popup_position', 'left_middle'), incoming=incoming, homes=homes.data,
                       warps=warps.data, players=online, allow_requests=data.get('allow_requests', True),
                       admin=self.is_admin(player, uid), config=self.config if self.is_admin(player, uid) else {})
            return
        disabled = ((action == 'random' and not self.config['random_radius']) or (
                    action.startswith('home_') and not self.config['home_limit']) or (
                                action.startswith('warp_') and not self.config['warp_limit']))
        if disabled:
            self.reply(player, action, 'disabled');
            return
        if action == 'random':
            self.random_tp(player);
            return
        if action == 'popup_position':
            position = args.get('value')
            if position not in POPUP_POSITIONS:
                self.reply(player, action, 'invalid');
                return
            previous = data.get('popup_position', 'left_middle')
            data['popup_position'] = position
            if not self.store.save():
                data['popup_position'] = previous
                self.reply(player, action, 'save_failed', popup_position=previous)
            else:
                self.reply(player, action, 'ok', popup_position=position)
            return
        if action == 'confirm_risk':
            pending = self.pending_safety.get(player)
            result = 'expired'
            if pending and pending[0] > time.time():
                passive = len(pending) > 2 and pending[2]
                result = self.move_status(player, pending[1], True, passive)
            else:
                self.pending_safety.pop(player, None)
            self.reply(player, action, result);
            return
        if action == 'cancel_risk':
            self.pending_safety.pop(player, None);
            return
        if action == 'config_batch':
            if not self.is_admin(player, uid):
                self.reply(player, action, 'forbidden');
                return
            values = args.get('values')
            if not isinstance(values, dict) or set(values) != set(DEFAULTS):
                self.reply(player, action, 'invalid');
                return
            updated = {}
            for key in DEFAULTS:
                value = validate(key, values[key])
                if value is None:
                    self.reply(player, action, 'invalid');
                    return
                updated[key] = value
            previous = copy.deepcopy(self.store.data.get('config'))
            self.store.data['config'] = updated
            if self.store.save():
                self.config = updated
                self.requests.lifetime = updated['request_lifetime']
                self.reply(player, action, 'ok')
            else:
                if previous is None:
                    self.store.data.pop('config', None)
                else:
                    self.store.data['config'] = previous
                self.reply(player, action, 'save_failed')
            return
        if action == 'config_set':
            if not self.is_admin(player, uid):
                self.reply(player, action, 'forbidden');
                return
            key = args.get('key')
            if not isinstance(key, (str, type(u''))):
                self.reply(player, action, 'invalid');
                return
            value = validate(key, args.get('value'))
            if value is None:
                self.reply(player, action, 'invalid');
                return
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
                self.reply(player, action, 'forbidden');
                return
            position = self.positions.capture(player)
            if position is None:
                self.reply(player, action, 'unavailable');
                return
            result = (homes if action == 'home_add' else warps).add(name, position, self.config[
                'home_limit'] if action == 'home_add' else self.config['warp_limit'])
            if result == 'ok' and not self.store.save(): result = 'save_failed'
        elif action in ('home_delete', 'warp_delete', 'home_rename', 'warp_rename'):
            if action.startswith('warp_') and not self.is_admin(player, uid):
                self.reply(player, action, 'forbidden');
                return
            locations = homes if action.startswith('home_') else warps
            result = locations.rename(name, args.get('new_name')) if action.endswith('rename') else locations.delete(
                name)
            if result == 'ok' and not self.store.save(): result = 'save_failed'
        elif action in ('home_go', 'warp_go'):
            locations = homes if action == 'home_go' else warps
            location = locations.data.get(name) if isinstance(name, (str, type(u''))) else None
            result = self.move_status(player, location)
        elif action == 'personal_spawn':
            spawn = serverApi.GetEngineCompFactory().CreatePlayer(player).GetPlayerRespawnPos()
            location = None
            if spawn and spawn.get('pos') and spawn['pos'][1] != 32767:
                location = {'dimension': spawn['dimensionId'], 'pos': list(spawn['pos'])}
            result = self.move_status(player, location) if location else 'no_spawn'
        elif action == 'death':
            result = self.move_status(player, self.deaths[player]) if player in self.deaths else 'no_death'
        elif action == 'world_spawn':
            self.world_spawn_tp(player)
            return
        elif action == 'back':
            result = self.move_status(player, self.back[player]) if player in self.back else 'no_back'
        elif action == 'allow_requests':
            value = args.get('value')
            if not isinstance(value, bool):
                self.reply(player, action, 'invalid');
                return
            data['allow_requests'] = value
            result = 'ok' if self.store.save() else 'save_failed'
        elif action == 'tpa':
            if self.cooldown_remaining(player):
                self.reply(player, action, 'cooldown');
                return
            target = args.get('target')
            if target not in serverApi.GetPlayerList():
                self.reply(player, action, 'offline');
                return
            target_uid = self.identity(target)
            if not target_uid or not players.get(target_uid, {}).get('allow_requests', True):
                self.reply(player, action, 'forbidden');
                return
            result = self.requests.send(player, target, args.get('here') is True)
            if result == 'ok':
                self.cooldowns[player] = time.time() + self.config['cooldown']
                self.NotifyToClient(target, 'RequestsChanged', {})
            if result == 'ok' and players.get(target_uid, {}).get('notifications', True):
                self.NotifyToClient(target, 'Request', {'sender': player,
                                                        'name': serverApi.GetEngineCompFactory().CreateName(
                                                            player).GetName(), 'here': args.get('here') is True,
                                                        'remaining': self.config['request_lifetime']})
        elif action in ('accept', 'deny'):
            sender = args.get('sender')
            self.requests.expire()
            request = self.requests.items.get((sender, player))
            request = self.requests.take(sender, player)
            self.NotifyToClient(player, 'RequestsChanged', {})
            if not request or sender not in serverApi.GetPlayerList():
                result = 'expired'
            elif action == 'deny':
                self.reply(sender, 'request_result', 'denied');
                result = 'request_denied'
            else:
                mover, destination = (player, sender) if request['here'] else (sender, player)
                result = self.move_status(mover, self.positions.capture(destination), passive=True)
                if result == 'ok':
                    self.reply(sender, 'request_result', 'request_accepted_other')
                    self.reply(player, action, 'request_accepted')
                else:
                    self.reply(sender, 'request_result', result, cooldown_player=mover)
                    self.reply(player, action, result, cooldown_player=mover)
                return
        else:
            return
        if result == 'unavailable' and player in self.pending_safety:
            result = 'risk'
        self.reply(player, action, result)
