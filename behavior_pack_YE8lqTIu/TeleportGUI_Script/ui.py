# -*- coding: utf-8 -*-
# SPDX-FileCopyrightText: ZCT Studio
# SPDX-License-Identifier: GPL-3.0-only
import mod.client.extraClientApi as clientApi
import time
from TeleportGUI_Script.settings import LABELS, LIMITS, POPUP_POSITIONS, POPUP_LABELS

ScreenNode = clientApi.GetScreenNodeCls()
ViewBinder = clientApi.GetViewBinderCls()
CONFIG_KEYS = ('home_limit', 'warp_limit', 'cooldown', 'request_lifetime', 'random_radius', 'safety_check')
from TeleportGUI_Script.messages import messages, result_message


def system():
    return clientApi.GetSystem('TeleportGUI', 'client')


def bind(node, path, callback):
    control = node.GetBaseUIControl(path).asButton()
    control.AddTouchEventParams({'isSwallow': True})
    control.SetButtonTouchUpCallback(callback)


def update_banner(node):
    client = system()
    control = node.GetBaseUIControl('/overlay/banner')
    visible = time.time() < client.banner_until
    overlay = node.GetBaseUIControl('/overlay')
    width, height = overlay.GetSize()
    if width > 0 and height > 0:
        x = max(0, (width - 300) / 2.0)
        y = max(0, height - 70) if client.popup_position == 'top_middle' else 48
        control.SetPosition((x, y))
    control.SetVisible(visible)
    if visible:
        control.asLabel().SetText(client.banner_text)


class Invitation(object):
    """Transient invitation card; the inbox remains the source for bulk handling."""

    def __init__(self, node):
        self.node = node
        self.queue = []
        self.current = None
        self.input_check_at = 0
        self.keyboard = False
        self.anchor = None
        bind(node, '/overlay/invite/accept', self.accept)
        bind(node, '/overlay/invite/deny', self.deny)

    def text(self, name, text):
        self.node.GetBaseUIControl('/overlay/invite/' + name).asLabel().SetText(text)

    def request(self, args):
        entry = dict(args)
        entry['expires'] = args.get('expires', time.time() + args.get('remaining', 120))
        self.queue = [x for x in self.queue if x.get('sender') != entry.get('sender')]
        if self.current and self.current.get('sender') == entry.get('sender'):
            self.current = entry
        else:
            self.queue.append(entry)
        self.update()

    def update(self):
        now = time.time()
        if now >= self.input_check_at:
            self.keyboard = system().keyboard_mouse()
            self.input_check_at = now + 0.5
            self.text('accept_label', u'同意 Ctrl+Y' if self.keyboard else u'同意')
            self.text('deny_label', u'拒绝 Ctrl+N' if self.keyboard else u'拒绝')
        self.place()
        if self.current and self.current['expires'] <= now:
            self.current = None
        self.queue = [x for x in self.queue if x['expires'] > now]
        if not self.current and self.queue:
            self.current = self.queue.pop(0)
        self.node.GetBaseUIControl('/overlay/invite').SetVisible(self.current is not None)
        if self.current:
            self.text('player', self.current.get('name', u'玩家') + (
                u' 邀请你过去' if self.current.get('here') else u' 想传送到你这里'))
            self.text('timer', u'%s秒' % max(0, int(self.current['expires'] - now)))

    def place(self):
        anchor = system().popup_position
        if anchor not in POPUP_POSITIONS:
            anchor = 'left_middle'
        overlay = self.node.GetBaseUIControl('/overlay')
        width, height = overlay.GetSize()
        if width <= 0 or height <= 0:
            return
        key = (anchor, width, height)
        if key == self.anchor:
            return
        self.anchor = key
        card_width, card_height = 160, 56
        x = width - card_width - 8 if 'right' in anchor else (8 if 'left' in anchor else (width - card_width) / 2.0)
        y = (36 if anchor == 'top_middle' else 8) if 'top' in anchor else (
            height - card_height - 8 if 'bottom' in anchor else (height - card_height) / 2.0)
        control = self.node.GetBaseUIControl('/overlay/invite')
        control.SetPosition((max(0, x), max(0, y)))

    def remove(self, sender):
        self.queue = [x for x in self.queue if x.get('sender') != sender]
        if self.current and self.current.get('sender') == sender:
            self.current = None
        self.update()

    def handle(self, accepted):
        entry = self.current
        if not entry:
            return
        self.remove(entry['sender'])
        if entry['expires'] <= time.time():
            return
        system().send('accept' if accepted else 'deny', sender=entry['sender'])

    def accept(self, args):
        self.handle(True)

    def deny(self, args):
        self.handle(False)


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
        self.invite = Invitation(self)
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
        update_banner(self)
        self.invite.update()
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

    def notify(self, text, payload=None):
        system().tip(result_message(text, payload))


class Menu(ScreenNode):
    def __init__(self, namespace, name, param):
        ScreenNode.__init__(self, namespace, name, param)
        self.page = 'overview'
        self.items = []
        self.data = {}
        self.offset = 0
        self.selected = None
        self.here = False
        self.edit_action = None
        self.risk_visible = False
        self.confirm_delete = False
        self.config_loaded = False

    def Create(self):
        self.invite = Invitation(self)
        for name, callback in [('popup_position', self.cycle_popup_position), ('risk_yes', self.risk_yes),
                               ('risk_no', self.risk_no), ('inbox', self.inbox), ('inbox_accept', self.accept_selected),
                               ('inbox_deny', self.deny_selected), ('edit_confirm', self.confirm_edit),
                               ('edit_cancel', self.cancel_edit), ('overview', self.overview),
                               ('card_homes', self.homes), ('card_players', self.players), ('card_warps', self.warps),
                               ('card_travel', self.travel), ('close', self.close), ('homes', self.homes),
                               ('warps', self.warps), ('players', self.players), ('add', self.add),
                               ('back', self.go_back), ('previous', self.previous), ('next', self.next_page),
                               ('go', self.go), ('rename', self.rename), ('delete', self.delete), ('mode', self.mode),
                               ('death', self.death), ('world_spawn', self.world_spawn),
                               ('requests', self.toggle_requests), ('admin', self.admin),
                               ('save_config', self.save_config), ('random', self.random)]:
            bind(self, '/root/' + name, callback)
        for i in range(6):
            bind(self, '/root/row%d' % i, self.make_row(i))
        bind(self, '/root/config_toggle', self.toggle_config)
        self.render()
        system().send('list')

    def Update(self):
        update_banner(self)
        self.invite.update()
        if self.risk_visible or self.edit_action:
            self.GetBaseUIControl('/overlay/invite').SetVisible(False)

    def Destroy(self):
        self.flush_config()
        if system().hud:
            for entry in ([self.invite.current] if self.invite.current else []) + self.invite.queue:
                system().hud.invite.request(entry)
        system().menu = None

    @ViewBinder.binding(ViewBinder.BF_ButtonClickUp, '#tpgui_close')
    def close(self, args):
        if self.risk_visible:
            self.risk_no(args)
        elif self.edit_action:
            self.cancel_edit(args)
        else:
            clientApi.PopScreen()

    def message(self, text):
        self.GetBaseUIControl('/root/status').asLabel().SetText(text)

    def cycle_popup_position(self, args):
        index = POPUP_POSITIONS.index(system().popup_position)
        system().send('popup_position', value=POPUP_POSITIONS[(index + 1) % len(POPUP_POSITIONS)])

    def risk(self, args):
        self.risk_visible = True
        for name in ('risk_shade', 'risk_panel', 'risk_text', 'risk_yes', 'risk_no'):
            self.GetBaseUIControl('/root/' + name).SetVisible(True)
        self.GetBaseUIControl('/root/risk_text').asLabel().SetText(args.get('message', u'目的地可能不安全，是否继续？'))

    def hide_risk(self):
        self.risk_visible = False
        for name in ('risk_shade', 'risk_panel', 'risk_text', 'risk_yes', 'risk_no'):
            self.GetBaseUIControl('/root/' + name).SetVisible(False)

    def risk_yes(self, args):
        self.hide_risk()
        system().send('confirm_risk')

    def risk_no(self, args):
        self.hide_risk()
        system().send('cancel_risk')

    def overview(self, args):
        self.flush_config()
        self.page = 'overview';
        self.reset_page()

    def travel(self, args):
        self.flush_config()
        self.page = 'travel';
        self.reset_page()

    def homes(self, args):
        self.flush_config()
        self.page = 'homes';
        self.reset_page()

    def warps(self, args):
        self.flush_config()
        self.page = 'warps';
        self.reset_page()

    def inbox(self, args):
        self.flush_config()
        self.page = 'inbox';
        self.reset_page();
        system().send('list')

    def accept_selected(self, args):
        if self.page == 'inbox' and self.selected:
            system().clear_invitation(self.selected['id'])
            system().send('accept', sender=self.selected['id'])
            self.selected = None
            self.render()

    def deny_selected(self, args):
        if self.page == 'inbox' and self.selected:
            system().clear_invitation(self.selected['id'])
            system().send('deny', sender=self.selected['id'])
            self.selected = None
            self.render()

    def players(self, args):
        self.flush_config()
        self.page = 'players';
        self.reset_page()

    def edit(self, action, title, initial=u''):
        self.edit_action = action
        for name in ('edit_shade', 'edit_panel', 'edit_title', 'edit_confirm', 'edit_cancel'):
            self.GetBaseUIControl('/root/' + name).SetVisible(True)
        self.GetBaseUIControl('/root/edit_title').asLabel().SetText(title)
        box = self.GetBaseUIControl('/root/input')
        box.SetPosition((105.5, 112))
        box.SetSize((185, 22))
        box.SetLayer(46)
        box.SetVisible(True)
        box.asTextEditBox().SetEditText(initial)

    def confirm_edit(self, args):
        text = self.GetBaseUIControl('/root/input').asTextEditBox().GetEditText()
        if not text or not text.strip():
            self.GetBaseUIControl('/root/edit_title').asLabel().SetText(u'请输入名称')
            return
        if self.edit_action == 'add':
            system().send('home_add' if self.page == 'homes' else 'warp_add', name=text)
        elif self.edit_action == 'rename':
            system().send('home_rename' if self.page == 'homes' else 'warp_rename', name=self.selected, new_name=text)
        self.cancel_edit(args)

    def cancel_edit(self, args):
        self.edit_action = None
        for name in ('edit_shade', 'edit_panel', 'edit_title', 'edit_confirm', 'edit_cancel'):
            self.GetBaseUIControl('/root/' + name).SetVisible(False)
        box = self.GetBaseUIControl('/root/input')
        box.SetPosition((286, 127))
        box.SetSize((96, 19))
        box.SetLayer(5)
        self.render()

    def add(self, args):
        if self.page in ('homes', 'warps'):
            self.edit('add', u'给新家园起个名字' if self.page == 'homes' else u'给传送点起个名字')

    def random(self, args):
        system().send("random")

    def death(self, args):
        system().send("death")

    def world_spawn(self, args):
        system().send("personal_spawn")

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
        if self.page == 'players' and self.selected:
            system().send('tpa', target=self.selected['id'], here=True)

    def admin(self, args):
        if self.data.get('admin'):
            self.page = 'config'
            self.reset_page()
            self.load_config_controls()

    def toggle_config(self, args):
        if self.page == 'config' and self.config_loaded:
            self.config_draft['safety_check'] = not self.config_draft['safety_check']
            self.update_config_labels()

    def update_config_labels(self):
        for i, key in enumerate(CONFIG_KEYS):
            self.GetBaseUIControl('/root/config_label%d' % i).asLabel().SetText(LABELS[key])
        self.GetBaseUIControl('/root/config_toggle/button_label').asLabel().SetText(
            u'开' if self.config_draft['safety_check'] else u'关')

    def load_config_controls(self):
        config = self.data.get('config', {})
        if not all(key in config for key in CONFIG_KEYS):
            return
        self.config_draft = dict(config)
        for i, key in enumerate(CONFIG_KEYS[:5]):
            self.GetBaseUIControl('/root/config_input%d' % i).asTextEditBox().SetEditText(str(config[key]))
        self.config_loaded = True
        self.update_config_labels()

    def flush_config(self):
        if not self.config_loaded:
            return
        values = dict(self.config_draft)
        for i, key in enumerate(CONFIG_KEYS[:5]):
            values[key] = self.GetBaseUIControl('/root/config_input%d' % i).asTextEditBox().GetEditText()
        self.config_loaded = False
        system().send('config_batch', values=values)

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
            system().send('tpa', target=self.selected['id'], here=False)
        else:
            system().send('home_go' if self.page == 'homes' else 'warp_go', name=self.selected)

    def rename(self, args):
        if self.selected is not None and self.page in ('homes', 'warps'):
            self.edit('rename', u'修改名称', self.selected)

    def delete(self, args):
        if self.selected is None or self.page not in ('homes', 'warps'):
            return
        if not self.confirm_delete:
            self.confirm_delete = True
            self.message(u'再次点击删除，确认移除此位置')
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
            name = self.selected.get('name', '') if self.page in ('players', 'inbox') else self.selected
            if self.page == 'config':
                name = LABELS.get(name, name)
                value = self.data.get('config', {}).get(self.selected)
                self.GetBaseUIControl('/root/input').asTextEditBox().SetEditText(
                    (u'开启' if value else u'关闭') if isinstance(value, bool) else str(value))
                bounds = LIMITS.get(self.selected)
                if bounds:
                    name += u'（范围 %s–%s）' % bounds
            self.GetBaseUIControl('/root/selection').asLabel().SetText(name)
            self.GetBaseUIControl('/root/status').asLabel().SetText(u'')
            self.render()

        return click

    def receive(self, args):
        if args.get('action') == 'list' and args.get('status') == 'ok':
            was_loaded = self.config_loaded
            self.data = args;
            self.render()
            if self.page == 'config' and not was_loaded: self.load_config_controls()
        elif args.get('status') == 'risk':
            return
        elif args.get('status') == 'ok':
            if args.get('action') in ('home_go', 'warp_go', 'back', 'death', 'world_spawn', 'personal_spawn', 'random',
                                      'confirm_risk', 'tpa'):
                clientApi.PopScreen()
            else:
                self.message(messages.get('ok'))
                system().send('list')
        else:
            self.message(result_message(args.get('status'), args))

    def render(self):
        self.GetBaseUIControl('/root/popup_position/button_label').asLabel().SetText(
            u'通知：' + POPUP_LABELS.get(system().popup_position, u'左居中'))
        titles = {'overview': u'主页', 'homes': u'家园', 'warps': u'传送点', 'players': u'好友传送',
                  'config': u'管理配置', 'travel': u'快捷出行', 'inbox': u'请求'}
        hints = {'overview': u'选择传送方式', 'homes': u'记录属于自己的落脚处。',
                 'warps': u'全体玩家共享，房主与管理员维护。', 'players': u'选中好友，发送前往或邀请请求。',
                 'config': u'修改数值和开关，离开时自动保存。', 'travel': u'重返足迹，或探索新的地方。',
                 'inbox': u'查看并处理收到的传送请求。'}
        self.GetBaseUIControl('/root/page_title').asLabel().SetText(titles[self.page])
        self.GetBaseUIControl('/root/page_hint').asLabel().SetText(hints[self.page])
        is_list = self.page in ('homes', 'warps', 'players', 'inbox')
        is_config = self.page == 'config' and self.data.get('admin', False)
        can_edit = self.page == 'homes' or (self.page == 'warps' and self.data.get('admin', False))
        for name in ('card_homes', 'card_players', 'card_warps', 'card_travel', 'overview_note'):
            self.GetBaseUIControl('/root/' + name).SetVisible(False)
        for name in ('overview', 'homes', 'players', 'warps', 'inbox', 'admin'):
            self.GetBaseUIControl('/root/selected_' + name).SetVisible(
                (name == 'overview' and self.page == 'overview') or (name == 'players' and self.page == 'players') or (
                            name in ('homes', 'warps', 'inbox') and self.page == name))
        self.GetBaseUIControl('/root/players').SetVisible(True)
        self.GetBaseUIControl('/root/card_players').SetVisible(False)
        features = self.data.get('features', {})
        self.GetBaseUIControl('/root/homes').SetVisible(features.get('home', True))
        self.GetBaseUIControl('/root/warps').SetVisible(features.get('warp', True))
        for name in ('back', 'death', 'world_spawn', 'random'):
            self.GetBaseUIControl('/root/' + name).SetVisible(
                self.page == 'overview' and (name != 'random' or features.get('random', False)))
        for name in ('add', 'rename', 'delete'):
            self.GetBaseUIControl('/root/' + name).SetVisible(can_edit)
        for name in ('input', 'input_hint'):
            self.GetBaseUIControl('/root/' + name).SetVisible(False)
        for name in ('selection', 'previous', 'next', 'page_number'):
            self.GetBaseUIControl('/root/' + name).SetVisible(is_list)
        self.GetBaseUIControl('/root/admin').SetVisible(self.data.get('admin', False))
        self.GetBaseUIControl('/root/save_config').SetVisible(False)
        for i in range(6):
            for control in ('config_label%d' % i, 'config_input%d' % i if i < 5 else 'config_toggle'):
                self.GetBaseUIControl('/root/' + control).SetVisible(is_config)
        self.GetBaseUIControl('/root/go').SetVisible(
            is_list and not is_config and not can_edit and self.page != 'inbox')
        for name in ('inbox_accept', 'inbox_deny'):
            self.GetBaseUIControl('/root/' + name).SetVisible(self.page == 'inbox')
        # For editable location lists, the selected row itself is not a teleport button.
        if can_edit:
            self.GetBaseUIControl('/root/go').SetVisible(True)
            self.GetBaseUIControl('/root/go').SetPosition((286, 194))
            self.GetBaseUIControl('/root/delete').SetPosition((286, 166))
            self.GetBaseUIControl('/root/delete').SetSize((96, 20))
            self.GetBaseUIControl('/root/rename').SetPosition((286, 140))
            self.GetBaseUIControl('/root/rename').SetSize((96, 20))
        else:
            self.GetBaseUIControl('/root/go').SetPosition((286, 114))
        self.GetBaseUIControl('/root/add/button_label').asLabel().SetText(
            u'创建新家园' if self.page == 'homes' else u'创建传送点')
        self.GetBaseUIControl('/root/go/button_label').asLabel().SetText(
            u'传送到对方' if self.page == 'players' else u'前往此处')
        self.GetBaseUIControl('/root/mode').SetVisible(self.page == 'players')
        self.GetBaseUIControl('/root/requests/button_label').asLabel().SetText(
            u'接收请求：开' if self.data.get('allow_requests', True) else u'接收请求：关')
        value = self.data.get('incoming', []) if self.page == 'inbox' else self.data.get(self.page, {})
        self.items = value if self.page in ('players', 'inbox') else sorted(value.keys())
        self.offset = min(self.offset, max(0, (len(self.items) - 1) // 6 * 6))
        self.GetBaseUIControl('/root/empty').SetVisible(is_list and not self.items)
        self.GetBaseUIControl('/root/page_number').asLabel().SetText(
            u'%s / %s' % (self.offset // 6 + 1, max(1, (len(self.items) + 5) // 6)))
        for i in range(6):
            available = is_list and self.offset + i < len(self.items)
            self.GetBaseUIControl('/root/row%d' % i).SetVisible(available)
            if available:
                value = self.items[self.offset + i]
                text = value.get('name', '') if self.page in ('players', 'inbox') else value
                if self.page == 'inbox':
                    text += (u' · 邀请你过去' if value.get('here') else u' · 请求过来') + u' (%s秒)' % value.get(
                        'remaining', 0)
                if is_config:
                    setting = self.data.get('config', {}).get(value)
                    shown = (u'开启' if setting else u'关闭') if isinstance(setting, bool) else str(setting)
                    text = LABELS.get(value, value) + u'：' + shown
                self.GetBaseUIControl('/root/row%d/button_label' % i).asLabel().SetText(text)

        selected = self.selected is not None
        for name in ('rename', 'delete'):
            self.GetBaseUIControl('/root/' + name).SetVisible(can_edit and selected)
        self.GetBaseUIControl('/root/go').SetVisible(selected and self.page in ('homes', 'warps', 'players'))
        self.GetBaseUIControl('/root/mode').SetVisible(selected and self.page == 'players')
        for name in ('inbox_accept', 'inbox_deny'):
            self.GetBaseUIControl('/root/' + name).SetVisible(selected and self.page == 'inbox')
        if not selected:
            self.GetBaseUIControl('/root/selection').asLabel().SetText(
                u'点击左侧条目\n查看可用操作' if self.items else u'暂无可选内容')
