# -*- coding: utf-8 -*-
import mod.server.extraServerApi as serverApi
from TeleportGUI_Script.rules import Locations, Requests
from TeleportGUI_Script.platform_server import WorldStore, PlayerPositions

ServerSystem = serverApi.GetServerSystemCls()

class TeleportServer(ServerSystem):
    def __init__(self, namespace, system_name):
        ServerSystem.__init__(self, namespace, system_name)
        self.store = WorldStore()
        self.positions = PlayerPositions()
        self.requests = Requests()
        self.back = {}
        self.ListenForEvent('TeleportGUI', 'client', 'Action', self, self.on_action)
        self.ListenForEvent(serverApi.GetEngineNamespace(), serverApi.GetEngineSystemName(), 'DelServerPlayerEvent', self, self.on_leave)

    def on_leave(self, args):
        player = args.get('id')
        self.requests.remove_player(player)
        self.back.pop(player, None)

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

    def move(self, player, location):
        before = self.positions.capture(player)
        if before is None or location is None:
            return False
        if not self.positions.teleport(player, location):
            return False
        self.back[player] = before
        return True

    def on_action(self, args):
        player = args.get('__id__')
        action = args.get('action')
        if player not in serverApi.GetPlayerList() or not isinstance(action, str):
            return
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
            self.reply(player, action, 'ok', homes=homes.data, warps=warps.data, players=online, allow_requests=data.get('allow_requests', True), admin=self.is_admin(player, uid))
            return
        if action in ('home_add', 'warp_add'):
            if action == 'warp_add' and not self.is_admin(player, uid):
                self.reply(player, action, 'forbidden'); return
            position = self.positions.capture(player)
            if position is None:
                self.reply(player, action, 'unavailable'); return
            result = (homes if action == 'home_add' else warps).add(name, position, 10 if action == 'home_add' else 100)
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
