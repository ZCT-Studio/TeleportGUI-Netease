# -*- coding: utf-8 -*-
"""Server-side persistence and player position adapters for ModSDK."""
import mod.server.extraServerApi as serverApi

DATA_KEY = 'zctstudio_teleportgui_v1'

class WorldStore(object):
    def __init__(self):
        self.component = serverApi.GetEngineCompFactory().CreateExtraData(serverApi.GetLevelId())
        loaded = self.component.GetExtraData(DATA_KEY)
        if loaded is None:
            self.data = {'version': 1, 'players': {}, 'warps': {}}
        elif isinstance(loaded, dict) and loaded.get('version') == 1 and isinstance(loaded.get('players'), dict) and isinstance(loaded.get('warps'), dict):
            self.data = loaded
        else:
            raise ValueError('Unsupported or malformed TeleportGUI world data')

    def save(self):
        return self.component.SetExtraData(DATA_KEY, self.data)

class PlayerPositions(object):
    def __init__(self):
        self.factory = serverApi.GetEngineCompFactory()

    def capture(self, player):
        position = self.factory.CreatePos(player).GetFootPos()
        dimension = self.factory.CreateDimension(player).GetEntityDimensionId()
        if position is None or dimension is None:
            return None
        return {'dimension': dimension, 'pos': list(position)}

    def teleport(self, player, location):
        current = self.factory.CreateDimension(player).GetEntityDimensionId()
        target = location['dimension']
        pos = location['pos']
        if current == target:
            return self.factory.CreatePos(player).SetFootPos(tuple(pos))
        # ChangePlayerDimension interprets its destination as head position.
        return self.factory.CreateDimension(player).ChangePlayerDimension(target, (pos[0], pos[1] + 1.62, pos[2]))
