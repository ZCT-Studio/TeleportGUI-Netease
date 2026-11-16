# -*- coding: utf-8 -*-
import mod.client.extraClientApi as clientApi
ScreenNode = clientApi.GetScreenNodeCls()

def system():
    return clientApi.GetSystem('TeleportGUI', 'client')

def bind(node, path, callback):
    control = node.GetBaseUIControl(path).asButton()
    control.AddTouchEventParams({'isSwallow': True})
    control.SetButtonTouchUpCallback(callback)

class Hud(ScreenNode):
    def __init__(self, namespace, name, param):
        ScreenNode.__init__(self, namespace, name, param)
        self.pending = None

    def Create(self):
        bind(self, '/root/open', self.open)
        bind(self, '/root/accept', self.accept)
        bind(self, '/root/deny', self.deny)
        self.show_request(False)

    def open(self, args):
        system().open_menu()

    def show_request(self, visible):
        for name in ('notice', 'accept', 'deny'):
            self.GetBaseUIControl('/root/' + name).SetVisible(visible)

    def request(self, args):
        self.pending = args.get('sender')
        self.GetBaseUIControl('/root/notice').asLabel().SetText(u'%s 请求传送' % args.get('name', u'玩家'))
        self.show_request(True)

    def accept(self, args):
        if self.pending:
            system().send('accept', sender=self.pending)
        self.pending = None
        self.show_request(False)

    def deny(self, args):
        if self.pending:
            system().send('deny', sender=self.pending)
        self.pending = None
        self.show_request(False)

    def notify(self, text):
        pass

class Menu(ScreenNode):
    def __init__(self, namespace, name, param):
        ScreenNode.__init__(self, namespace, name, param)
        self.page = 'homes'
        self.items = []
        self.data = {}

    def Create(self):
        for name, callback in [('close', self.close), ('homes', self.homes), ('warps', self.warps), ('players', self.players), ('add', self.add), ('back', self.go_back)]:
            bind(self, '/root/' + name, callback)
        for i in range(6):
            bind(self, '/root/row%d' % i, self.make_row(i))
        system().send('list')

    def Destroy(self):
        system().menu = None

    def close(self, args):
        clientApi.PopScreen()

    def homes(self, args):
        self.page = 'homes'; self.render()

    def warps(self, args):
        self.page = 'warps'; self.render()

    def players(self, args):
        self.page = 'players'; self.render()

    def add(self, args):
        name = self.GetBaseUIControl('/root/input').asTextEditBox().GetEditText()
        if self.page in ('homes', 'warps'):
            system().send('home_add' if self.page == 'homes' else 'warp_add', name=name)

    def go_back(self, args):
        system().send('back')

    def make_row(self, index):
        def click(args):
            if index >= len(self.items): return
            item = self.items[index]
            if self.page == 'players': system().send('tpa', target=item['id'], here=False)
            else: system().send('home_go' if self.page == 'homes' else 'warp_go', name=item)
        return click

    def receive(self, args):
        if args.get('action') == 'list' and args.get('status') == 'ok':
            self.data = args; self.render()
        elif args.get('status') == 'ok':
            system().send('list')
        else:
            self.GetBaseUIControl('/root/status').asLabel().SetText(str(args.get('status', 'error')))

    def render(self):
        value = self.data.get(self.page, {})
        self.items = value if self.page == 'players' else sorted(value.keys())
        for i in range(6):
            control = self.GetBaseUIControl('/root/row%d' % i)
            control.SetVisible(i < len(self.items))
            if i < len(self.items):
                value = self.items[i]
                text = value.get('name', '') if self.page == 'players' else value
                self.GetBaseUIControl('/root/row%d/button_label' % i).asLabel().SetText(text)
