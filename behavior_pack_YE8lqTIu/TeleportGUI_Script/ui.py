# -*- coding: utf-8 -*-
import mod.client.extraClientApi as clientApi
import time
from TeleportGUI_Script.settings import LABELS, LIMITS
ScreenNode = clientApi.GetScreenNodeCls()
messages = {'busy': u'正在寻找传送位置，请稍候', 'invalid': u'数值无效，请检查输入范围', 'ok': u'操作成功', 'forbidden': u'没有权限或对方拒收请求', 'exists': u'名称或请求已存在', 'limit': u'已达到数量上限', 'invalid_name': u'请输入 1 至 32 字的名称', 'missing': u'位置不存在', 'offline': u'玩家已离线', 'expired': u'请求已过期', 'denied': u'对方拒绝了请求', 'unavailable': u'当前位置无法传送', 'save_failed': u'数据保存失败', 'identity_unavailable': u'暂时无法读取玩家身份', 'self': u'不能向自己发送请求'}

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
        self.queue = []
        self.notice_until = 0
        self.toast_until = 0
        self.drag_start = None
        self.dragged = False

    def Create(self):
        bind(self, '/root/open', self.open)
        bind(self, '/root/accept', self.accept)
        bind(self, '/root/deny', self.deny)
        self.show_request(False)
        self.GetBaseUIControl('/root/toast_bg').SetVisible(False)
        button = self.GetBaseUIControl('/root/open').asButton()
        button.SetButtonTouchDownCallback(self.drag_down)
        button.SetButtonTouchMoveCallback(self.drag_move)

    def drag_down(self, args):
        self.drag_start = (args.get('TouchPosX', 0), args.get('TouchPosY', 0))
        self.drag_origin = self.GetBaseUIControl('/root/open').GetPosition()
        self.dragged = False

    def drag_move(self, args):
        if self.drag_start is None:
            return
        dx = args.get('TouchPosX', self.drag_start[0]) - self.drag_start[0]
        dy = args.get('TouchPosY', self.drag_start[1]) - self.drag_start[1]
        if abs(dx) + abs(dy) > 6:
            self.dragged = True
            self.GetBaseUIControl('/root/open').SetPosition((self.drag_origin[0] + dx, self.drag_origin[1] + dy))

    def open(self, args):
        if not self.dragged:
            system().open_menu()

    def show_request(self, visible):
        for name in ('notice', 'notice_bg', 'notice_accent', 'notice_title', 'accept', 'deny'):
            self.GetBaseUIControl('/root/' + name).SetVisible(visible)

    def request(self, args):
        if len(self.queue) < 20:
            self.queue.append((time.time() + 120, args))
        if self.pending is None:
            self.next_request()

    def next_request(self):
        self.pending = None
        self.show_request(False)
        while self.queue:
            expires, args = self.queue.pop(0)
            if expires <= time.time():
                continue
            self.pending = args.get('sender')
            self.notice_until = expires
            verb = u'邀请你传送过去' if args.get('here') else u'请求传送到你身边'
            self.GetBaseUIControl('/root/notice').asLabel().SetText(args.get('name', u'玩家') + u'\n' + verb)
            self.GetBaseUIControl('/root/accept/button_label').asLabel().SetText(u'接受')
            self.GetBaseUIControl('/root/deny/button_label').asLabel().SetText(u'拒绝')
            self.show_request(True)
            break

    def Update(self):
        if self.pending and time.time() >= self.notice_until:
            self.next_request()
        if self.toast_until and time.time() >= self.toast_until:
            self.GetBaseUIControl('/root/toast').asLabel().SetText(u'')
            self.GetBaseUIControl('/root/toast_bg').SetVisible(False)
            self.toast_until = 0

    def risk(self, args):
        self.GetBaseUIControl('/root/accept/button_label').asLabel().SetText(u'仍然传送')
        self.GetBaseUIControl('/root/deny/button_label').asLabel().SetText(u'取消')
        self.pending = "__risk__"
        self.notice_until = time.time() + 30
        self.GetBaseUIControl("/root/notice").asLabel().SetText(args.get("message", u"目的地可能不安全"))
        self.show_request(True)

    def accept(self, args):
        if self.pending == "__risk__":
            system().send("confirm_risk")
        elif self.pending:
            system().send('accept', sender=self.pending)
        self.next_request()

    def deny(self, args):
        if self.pending == "__risk__":
            system().send("cancel_risk")
        elif self.pending:
            system().send('deny', sender=self.pending)
        self.next_request()

    def notify(self, text):
        self.GetBaseUIControl('/root/toast_bg').SetVisible(True)
        self.toast_until = time.time() + 5
        self.GetBaseUIControl('/root/toast').asLabel().SetText(messages.get(text, u'操作未完成'))

class Menu(ScreenNode):
    def __init__(self, namespace, name, param):
        ScreenNode.__init__(self, namespace, name, param)
        self.page = 'overview'
        self.items = []
        self.data = {}
        self.offset = 0
        self.selected = None
        self.here = False
        self.confirm_delete = False

    def Create(self):
        for name, callback in [('overview', self.overview), ('card_homes', self.homes), ('card_players', self.players), ('card_warps', self.warps), ('card_travel', self.travel), ('close', self.close), ('homes', self.homes), ('warps', self.warps), ('players', self.players), ('add', self.add), ('back', self.go_back), ('previous', self.previous), ('next', self.next_page), ('go', self.go), ('rename', self.rename), ('delete', self.delete), ('mode', self.mode), ('death', self.death), ('world_spawn', self.world_spawn), ('requests', self.toggle_requests), ('admin', self.admin), ('save_config', self.save_config), ('random', self.random)]:
            bind(self, '/root/' + name, callback)
        for i in range(6):
            bind(self, '/root/row%d' % i, self.make_row(i))
        self.render()
        system().send('list')

    def Destroy(self):
        system().menu = None

    def close(self, args):
        clientApi.PopScreen()

    def overview(self, args):
        self.page = 'overview'; self.reset_page()

    def travel(self, args):
        self.page = 'travel'; self.reset_page()

    def homes(self, args):
        self.page = 'homes'; self.reset_page()

    def warps(self, args):
        self.page = 'warps'; self.reset_page()

    def players(self, args):
        self.page = 'players'; self.reset_page()

    def add(self, args):
        name = self.GetBaseUIControl('/root/input').asTextEditBox().GetEditText()
        if self.page in ('homes', 'warps'):
            system().send('home_add' if self.page == 'homes' else 'warp_add', name=name)

    def random(self, args):
        system().send("random")

    def death(self, args):
        system().send("death")

    def world_spawn(self, args):
        system().send("world_spawn")

    def toggle_requests(self, args):
        system().send("allow_requests", value=not self.data.get("allow_requests", True))

    def go_back(self, args):
        system().send('back')

    def reset_page(self):
        self.offset = 0
        self.selected = None
        self.confirm_delete = False
        self.GetBaseUIControl('/root/selection').asLabel().SetText(u'选择列表中的一项')
        self.GetBaseUIControl('/root/status').asLabel().SetText(u'')
        self.GetBaseUIControl('/root/input').asTextEditBox().SetEditText(u'')
        self.render()

    def previous(self, args):
        self.offset = max(0, self.offset - 6)
        self.render()

    def next_page(self, args):
        if self.offset + 6 < len(self.items):
            self.offset += 6
        self.render()

    def mode(self, args):
        self.here = not self.here
        self.GetBaseUIControl('/root/mode/button_label').asLabel().SetText(u'邀请对方过来' if self.here else u'前往对方位置')

    def admin(self, args):
        if self.data.get('admin'):
            self.page = 'config'
            self.reset_page()

    def save_config(self, args):
        if self.page != 'config' or self.selected is None:
            return
        key = self.selected
        value = self.GetBaseUIControl('/root/input').asTextEditBox().GetEditText()
        if key == 'safety_check':
            value = not self.data.get('config', {}).get(key, True)
        system().send('config_set', key=key, value=value)

    def go(self, args):
        if self.selected is None or self.page == 'config':
            return
        if self.page == 'players':
            system().send('tpa', target=self.selected['id'], here=self.here)
        else:
            system().send('home_go' if self.page == 'homes' else 'warp_go', name=self.selected)

    def rename(self, args):
        if self.selected is not None and self.page in ('homes', 'warps'):
            name = self.GetBaseUIControl('/root/input').asTextEditBox().GetEditText()
            system().send('home_rename' if self.page == 'homes' else 'warp_rename', name=self.selected, new_name=name)

    def delete(self, args):
        if self.selected is None or self.page not in ('homes', 'warps'):
            return
        if not self.confirm_delete:
            self.confirm_delete = True
            self.GetBaseUIControl('/root/status').asLabel().SetText(u'再次点击删除，确认移除此位置')
            return
        system().send('home_delete' if self.page == 'homes' else 'warp_delete', name=self.selected)
        self.selected = None
        self.confirm_delete = False

    def make_row(self, index):
        def click(args):
            index_in_list = self.offset + index
            if index_in_list >= len(self.items):
                return
            self.selected = self.items[index_in_list]
            self.confirm_delete = False
            name = self.selected.get('name', '') if self.page == 'players' else self.selected
            if self.page == 'config':
                name = LABELS.get(name, name)
                value = self.data.get('config', {}).get(self.selected)
                self.GetBaseUIControl('/root/input').asTextEditBox().SetEditText(str(value))
                bounds = LIMITS.get(self.selected)
                if bounds:
                    name += u'（范围 %s–%s）' % bounds
            self.GetBaseUIControl('/root/selection').asLabel().SetText(name)
            self.GetBaseUIControl('/root/status').asLabel().SetText(u'已选择：' + name)
        return click

    def receive(self, args):
        if args.get('action') == 'list' and args.get('status') == 'ok':
            self.data = args; self.render()
        elif args.get('status') == 'ok':
            system().send('list')
        else:
            self.GetBaseUIControl('/root/status').asLabel().SetText(messages.get(args.get('status'), u'操作未完成'))

    def render(self):
        titles = {'overview': u'总菜单', 'homes': u'我的家园', 'warps': u'公共传送点', 'players': u'玩家传送', 'config': u'管理配置', 'travel': u'快捷出行'}
        hints = {'overview': u'选择目的地，开启下一段旅程。', 'homes': u'记录属于自己的落脚处。', 'warps': u'全体玩家共享，房主与管理员维护。', 'players': u'选中好友，发送前往或邀请请求。', 'config': u'修改后点击保存，仅影响当前世界。', 'travel': u'重返足迹，或探索新的地方。'}
        self.GetBaseUIControl('/root/page_title').asLabel().SetText(titles[self.page])
        self.GetBaseUIControl('/root/page_hint').asLabel().SetText(hints[self.page])
        is_list = self.page in ('homes', 'warps', 'players', 'config')
        is_config = self.page == 'config' and self.data.get('admin', False)
        can_edit = self.page == 'homes' or (self.page == 'warps' and self.data.get('admin', False))
        for name in ('card_homes', 'card_players', 'card_warps', 'card_travel', 'overview_note'):
            self.GetBaseUIControl('/root/' + name).SetVisible(self.page == 'overview')
        for name in ('back', 'death', 'world_spawn', 'random'):
            self.GetBaseUIControl('/root/' + name).SetVisible(self.page == 'travel')
        for name in ('add', 'rename', 'delete'):
            self.GetBaseUIControl('/root/' + name).SetVisible(can_edit)
        for name in ('input', 'input_hint'):
            self.GetBaseUIControl('/root/' + name).SetVisible(can_edit or is_config)
        for name in ('selection', 'previous', 'next', 'page_number'):
            self.GetBaseUIControl('/root/' + name).SetVisible(is_list)
        self.GetBaseUIControl('/root/admin').SetVisible(self.data.get('admin', False))
        self.GetBaseUIControl('/root/save_config').SetVisible(is_config)
        self.GetBaseUIControl('/root/go').SetVisible(is_list and not is_config and not can_edit)
        # For editable location lists, the selected row itself is not a teleport button.
        if can_edit:
            self.GetBaseUIControl('/root/go').SetVisible(True)
            self.GetBaseUIControl('/root/go').SetPosition((397, 280))
            self.GetBaseUIControl('/root/delete').SetPosition((466, 246))
            self.GetBaseUIControl('/root/delete').SetSize((64, 27))
            self.GetBaseUIControl('/root/rename').SetSize((64, 27))
        else:
            self.GetBaseUIControl('/root/go').SetPosition((397, 212))
        self.GetBaseUIControl('/root/go/button_label').asLabel().SetText(u'发送请求' if self.page == 'players' else u'传送')
        self.GetBaseUIControl('/root/mode').SetVisible(self.page == 'players')
        self.GetBaseUIControl('/root/requests/button_label').asLabel().SetText(u'接收请求：开' if self.data.get('allow_requests', True) else u'接收请求：关')
        value = self.data.get(self.page, {})
        self.items = value if self.page == 'players' else sorted(value.keys())
        self.offset = min(self.offset, max(0, (len(self.items) - 1) // 6 * 6))
        self.GetBaseUIControl('/root/empty').SetVisible(is_list and not self.items)
        self.GetBaseUIControl('/root/page_number').asLabel().SetText(u'%s / %s' % (self.offset // 6 + 1, max(1, (len(self.items) + 5) // 6)))
        for i in range(6):
            available = is_list and self.offset + i < len(self.items)
            self.GetBaseUIControl('/root/row%d' % i).SetVisible(available)
            if available:
                value = self.items[self.offset + i]
                text = value.get('name', '') if self.page == 'players' else value
                if is_config:
                    setting = self.data.get('config', {}).get(value)
                    shown = (u'开启' if setting else u'关闭') if isinstance(setting, bool) else str(setting)
                    text = LABELS.get(value, value) + u'：' + shown
                self.GetBaseUIControl('/root/row%d/button_label' % i).asLabel().SetText(text)
