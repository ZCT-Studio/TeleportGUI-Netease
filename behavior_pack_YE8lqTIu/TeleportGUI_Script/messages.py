# -*- coding: utf-8 -*-
# SPDX-FileCopyrightText: ZCT Studio
# SPDX-License-Identifier: GPL-3.0-only
messages = {'no_spawn': u'尚未设置个人重生点', 'disabled': u'此功能已禁用',
            'random_no_safe': u'未找到安全的随机传送位置，请再试一次', 'random_timeout': u'随机传送搜索超时，请再试一次',
            'request_accepted': u'已同意传送请求', 'request_accepted_other': u'对方已同意传送请求',
            'request_denied': u'已拒绝传送请求', 'no_death': u'暂无死亡记录，无法返回死亡点',
            'no_back': u'暂无传送前位置，无法返回', 'busy': u'正在寻找传送位置，请稍候',
            'invalid': u'数值无效，请检查输入范围', 'ok': u'操作成功', 'forbidden': u'没有权限或对方拒收请求',
            'exists': u'名称或请求已存在', 'limit': u'已达到数量上限', 'invalid_name': u'请输入 1 至 32 字的名称',
            'missing': u'位置不存在', 'offline': u'玩家已离线', 'expired': u'请求已过期', 'denied': u'对方拒绝了请求',
            'unavailable': u'当前位置无法传送', 'save_failed': u'数据保存失败',
            'identity_unavailable': u'暂时无法读取玩家身份', 'self': u'不能向自己发送请求'}


def result_message(status, payload=None):
    if status == 'cooldown':
        payload = payload or {}
        seconds = max(1, int(payload.get('remaining', 1)))
        return (
            u'对方传送冷却中，还需等待 %s 秒' if payload.get('other_player') else u'传送冷却中，还需等待 %s 秒') % seconds
    return messages.get(status, u'操作未完成')
