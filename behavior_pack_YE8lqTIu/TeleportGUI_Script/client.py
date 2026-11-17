# -*- coding: utf-8 -*-
# SPDX-FileCopyrightText: ZCT Studio
# SPDX-License-Identifier: GPL-3.0-only
import mod.client.extraClientApi as clientApi
import time
from TeleportGUI_Script.settings import POPUP_POSITIONS

ClientSystem = clientApi.GetClientSystemCls()


class TeleportClient(ClientSystem):
    def __init__(self, namespace, system_name):
        ClientSystem.__init__(self, namespace, system_name)
        self.ListenForEvent(clientApi.GetEngineNamespace(), clientApi.GetEngineSystemName(), 'UiInitFinished', self,
                            self.on_ui_init)
        self.ListenForEvent('TeleportGUI', 'server', 'Result', self, self.on_result)
        self.ListenForEvent('TeleportGUI', 'server', 'Request', self, self.on_request)
        self.ListenForEvent('TeleportGUI', 'server', 'Risk', self, self.on_risk)
        self.ListenForEvent('TeleportGUI', 'server', 'RequestsChanged', self, self.on_requests_changed)
        self.banner_text = u''
        self.banner_until = 0
        self.popup_position = 'left_middle'
        self.menu = None
        self.hud = None
        self.toggle_held = False
        self.held_keys = set()
        self.ListenForEvent(clientApi.GetEngineNamespace(), clientApi.GetEngineSystemName(), 'OnKeyPressInGame', self,
                            self.on_key)

    def on_ui_init(self, args):
        clientApi.RegisterUI('TeleportGUI', 'hud', 'TeleportGUI_Script.ui.Hud', 'tpgui.hud')
        clientApi.RegisterUI('TeleportGUI', 'menu', 'TeleportGUI_Script.ui.Menu', 'tpgui.menu')
        self.hud = clientApi.CreateUI('TeleportGUI', 'hud', {'isHud': 1})
        self.send('list')

    def tip(self, text):
        pass

    def keyboard_mouse(self):
        view = clientApi.GetEngineCompFactory().CreatePlayerView(clientApi.GetLevelId())
        mode = view.GetToggleOption(clientApi.GetMinecraftEnum().OptionId.INPUT_MODE)
        return mode == clientApi.GetMinecraftEnum().InputMode.Mouse

    def on_key(self, args):
        key = str(args.get('key'))
        down = str(args.get('isDown')) == '1'
        repeated = key in self.held_keys
        if down:
            self.held_keys.add(key)
        else:
            self.held_keys.discard(key)
            return
        if repeated:
            return
        menu_active = self.menu is not None and clientApi.GetTopScreen() == self.menu
        hud_active = self.menu is None and args.get('screenName') == 'hud_screen'
        if not menu_active and not hud_active:
            return
        if key == '220' and menu_active:
            self.menu.close(args)
            return
        if menu_active and (self.menu.edit_action or self.menu.risk_visible):
            return
        if key in ('89', '78') and '17' in self.held_keys and self.keyboard_mouse():
            screen = self.menu if menu_active else self.hud
            if screen and not (hud_active and screen.pending == '__risk__'):
                screen.invite.handle(key == '89')
            return
        if key == '220':
            if menu_active:
                self.menu.close(args)
            else:
                self.open_menu()

    def open_menu(self):
        if self.menu is not None or self.hud is None:
            return
        self.menu = clientApi.PushScreen('TeleportGUI', 'menu', {})
        if self.menu:
            invite = self.hud.invite
            for entry in ([invite.current] if invite.current else []) + invite.queue:
                self.menu.invite.request(entry)
            invite.current = None
            invite.queue = []
            invite.update()
        self.send('list')

    def clear_invitation(self, sender):
        for screen in (self.hud, self.menu):
            if screen:
                screen.invite.remove(sender)

    def send(self, action, **data):
        data['action'] = action
        self.NotifyToServer('Action', data)

    def show_banner(self, text):
        self.banner_text = text
        self.banner_until = time.time() + 4

    def on_result(self, args):
        if args.get('action') != 'list' and args.get('status') != 'risk' and not (
                self.menu and args.get('status') == 'ok'):
            from TeleportGUI_Script.messages import result_message
            self.show_banner(result_message(args.get('status'), args))
        if args.get('popup_position') in POPUP_POSITIONS:
            self.popup_position = args['popup_position']
        if self.menu:
            self.menu.receive(args)

    def on_request(self, args):
        if self.menu:
            self.menu.invite.request(args)
            self.send('list')
        elif self.hud:
            self.hud.invite.request(args)

    def on_risk(self, args):
        if self.menu:
            self.menu.risk(args)
        elif self.hud:
            self.hud.risk(args)

    def on_requests_changed(self, args):
        if self.menu:
            self.send('list')
