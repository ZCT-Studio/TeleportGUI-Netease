# -*- coding: utf-8 -*-
# SPDX-FileCopyrightText: ZCT Studio
# SPDX-License-Identifier: GPL-3.0-only
import mod.client.extraClientApi as clientApi
import mod.server.extraServerApi as serverApi
from mod.common.mod import Mod


@Mod.Binding(name="TeleportGUI_Script", version="1.0.0")
class TeleportGUI(object):
    @Mod.InitServer()
    def init_server(self):
        serverApi.RegisterSystem("TeleportGUI", "server", "TeleportGUI_Script.server.TeleportServer")

    @Mod.InitClient()
    def init_client(self):
        clientApi.RegisterSystem("TeleportGUI", "client", "TeleportGUI_Script.client.TeleportClient")
