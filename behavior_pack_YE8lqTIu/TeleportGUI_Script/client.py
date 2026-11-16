# -*- coding: utf-8 -*-
import mod.client.extraClientApi as clientApi

ClientSystem = clientApi.GetClientSystemCls()

class TeleportClient(ClientSystem):
    def __init__(self, namespace, system_name):
        ClientSystem.__init__(self, namespace, system_name)
        self.ListenForEvent(clientApi.GetEngineNamespace(), clientApi.GetEngineSystemName(), 'UiInitFinished', self, self.on_ui_init)
        self.ListenForEvent('TeleportGUI', 'server', 'Result', self, self.on_result)
        self.ListenForEvent('TeleportGUI', 'server', 'Request', self, self.on_request)
        self.menu = None
        self.hud = None

    def on_ui_init(self, args):
        clientApi.RegisterUI('TeleportGUI', 'hud', 'TeleportGUI_Script.ui.Hud', 'tpgui.hud')
        clientApi.RegisterUI('TeleportGUI', 'menu', 'TeleportGUI_Script.ui.Menu', 'tpgui.menu')
        self.hud = clientApi.CreateUI('TeleportGUI', 'hud', {'isHud': 1})

    def open_menu(self):
        self.menu = clientApi.PushScreen('TeleportGUI', 'menu', {})
        self.send('list')

    def send(self, action, **data):
        data['action'] = action
        self.NotifyToServer('Action', data)

    def on_result(self, args):
        if self.menu:
            self.menu.receive(args)
        if self.hud and args.get('status') != 'ok':
            self.hud.notify(args.get('status', 'error'))

    def on_request(self, args):
        if self.hud:
            self.hud.request(args)
