# -*- coding: utf-8 -*-
from mod.common.mod import Mod
import mod.server.extraServerApi as serverApi
import mod.client.extraClientApi as clientApi

@Mod.Binding(name="TeleportGUI_Script", version="0.1.0")
class TeleportGUI(object):
    @Mod.InitServer()
    def init_server(self):
        serverApi.RegisterSystem("TeleportGUI", "server", "TeleportGUI_Script.server.TeleportServer")

    @Mod.InitClient()
    def init_client(self):
        clientApi.RegisterSystem("TeleportGUI", "client", "TeleportGUI_Script.client.TeleportClient")
