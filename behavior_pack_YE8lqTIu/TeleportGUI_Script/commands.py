# -*- coding: utf-8 -*-
# SPDX-FileCopyrightText: ZCT Studio
# SPDX-License-Identifier: GPL-3.0-only
import mod.server.extraServerApi as serverApi
from TeleportGUI_Script.settings import LABELS

SIMPLE = {'back': 'back', 'tpdeathpoint': 'death', 'tpdp': 'death', 'tpworldspawn': 'world_spawn',
          'tpws': 'world_spawn', 'tpspawnpoint': 'personal_spawn', 'tpsp': 'personal_spawn', 'tpforce': 'confirm_risk',
          'randomtp': 'random', 'rtp': 'random'}
KNOWN = set(SIMPLE) | set(
    ('home', 'warp', 'tpa', 'tpahere', 'tpaaccept', 'tpay', 'tpadeny', 'tpan', 'teleportgui', 'teleportgui_admin',
     'teleportgui_be'))


def execute(server, event):
    command = event.get('command', '').lstrip('/')
    if command not in KNOWN:
        return

    def fail(message):
        event['return_failed'] = True
        event['return_msg_key'] = message

    player = event.get('origin', {}).get('entityId')
    if player not in serverApi.GetPlayerList():
        fail(u'请由在线玩家执行此命令。');
        return
    uid = server.identity(player)
    if not uid:
        fail(u'暂时无法读取玩家身份。');
        return
    args = [x.get('value') for x in event.get('args', [])]
    args += [None] * (3 - len(args))
    a, b, c = args[:3]
    event['return_msg_key'] = u'已提交操作，请查看右侧提示。'

    def action(action_name, **data):
        data.update({'__id__': player, 'action': action_name})
        server.on_action(data)

    if command in SIMPLE:
        action(SIMPLE[command]);
        return
    data = server.store.data['players'].setdefault(uid, {'homes': {}, 'allow_requests': True})
    if command in ('home', 'warp') and not server.config['home_limit' if command == 'home' else 'warp_limit']:
        fail(u'此功能已禁用。');
        return
    if command in ('home', 'warp'):
        locations = data['homes'] if command == 'home' else server.store.data['warps']
        if not a:
            if command == 'home' and not a and data.get('default_home') in locations:
                action('home_go', name=data['default_home'])
            else:
                event['return_msg_key'] = u'位置列表：' + (u'、'.join(sorted(locations)) or u'暂无')
        elif a == 'list':
            event['return_msg_key'] = u'位置列表：' + (u'、'.join(sorted(locations)) or u'暂无')
        elif a == 'default' and command == 'home':
            if b not in locations:
                fail(u'家园不存在。');
                return
            data['default_home'] = b
            if not server.store.save():
                fail(u'保存失败。')
            else:
                event['return_msg_key'] = u'已设置默认家园。'
        elif a in ('create', 'add', 'go', 'del', 'delete', 'rename'):
            if not b or (a == 'rename' and not c):
                fail(u'用法：/%s %s 名称%s' % (command, a, u' 新名称' if a == 'rename' else u''));
                return
            suffix = \
            {'create': 'add', 'add': 'add', 'go': 'go', 'del': 'delete', 'delete': 'delete', 'rename': 'rename'}[a]
            action(command + '_' + suffix, name=b, new_name=c)
        else:
            fail(u'支持 create/add、go、del/delete、rename、list；家园还支持 default。')
        return
    if command in ('tpa', 'tpahere', 'tpaaccept', 'tpay', 'tpadeny', 'tpan'):
        target = None
        if a:
            factory = serverApi.GetEngineCompFactory()
            matches = [p for p in serverApi.GetPlayerList() if factory.CreateName(p).GetName() == a]
            if len(matches) != 1:
                fail(u'请输入唯一的在线玩家完整名称。');
                return
            target = matches[0]
        elif command not in ('tpa', 'tpahere'):
            server.requests.expire()
            pending = [key[0] for key in server.requests.items if key[1] == player]
            if len(pending) != 1:
                fail(u'请指定请求者的名字；没有请求或存在多个请求。');
                return
            target = pending[0]
        else:
            fail(u'用法：/%s 玩家名称' % command);
            return
        if command in ('tpa', 'tpahere'):
            action('tpa', target=target, here=command == 'tpahere')
        else:
            action('accept' if command in ('tpaaccept', 'tpay') else 'deny', sender=target)
        return
    if command == 'teleportgui_admin':
        if not server.is_admin(player, uid):
            fail(u'只有房主或管理员可以使用。');
            return
        if a == 'config' and b in server.config:
            if c is None:
                event['return_msg_key'] = LABELS.get(b, b) + u'：' + str(server.config[b]);
                return
            value = c
            if b == 'safety_check':
                if c not in ('true', 'false'):
                    fail(u'请输入 true 或 false。');
                    return
                value = c == 'true'
            action('config_set', key=b, value=value);
            return
        fail(u'用法：/teleportgui_admin config 配置项 [值]。');
        return
    if command == 'teleportgui':
        if a == 'allow_request':
            if b is None:
                event['return_msg_key'] = u'接收请求：' + (u'开启' if data.get('allow_requests', True) else u'关闭');
                return
            if b in ('true', 'false'):
                action('allow_requests', value=b == 'true');
                return
        fail(u'用法：/teleportgui allow_request [true|false]');
        return
    if command == 'teleportgui_be':
        if a == 'notif_gui':
            if b is None:
                event['return_msg_key'] = u'请求通知：' + (u'开启' if data.get('notifications', True) else u'关闭');
                return
            if b in ('true', 'false'):
                data['notifications'] = b == 'true'
                if not server.store.save(): fail(u'保存失败。')
                return
        fail(u'用法：/teleportgui_be notif_gui [true|false]；网易版不提供表情菜单。')
