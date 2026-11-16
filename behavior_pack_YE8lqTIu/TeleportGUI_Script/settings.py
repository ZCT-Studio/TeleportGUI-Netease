# -*- coding: utf-8 -*-
DEFAULTS = {'home_limit': 10, 'warp_limit': 100, 'cooldown': 3, 'request_lifetime': 120, 'random_radius': 1000, 'safety_check': True}
LIMITS = {'home_limit': (1, 1000), 'warp_limit': (1, 10000), 'cooldown': (0, 3600), 'request_lifetime': (10, 600), 'random_radius': (16, 10000)}
LABELS = {'home_limit': u'每人家园上限', 'warp_limit': u'公共传送点上限', 'cooldown': u'传送冷却（秒）', 'request_lifetime': u'请求有效期（秒）', 'random_radius': u'随机传送范围（格）', 'safety_check': u'安全检查'}

def validate(key, value):
    if key == 'safety_check':
        return value if isinstance(value, bool) else None
    if key not in LIMITS or isinstance(value, bool):
        return None
    try:
        if not str(value).isdigit():
            return None
        value = int(value)
    except (ValueError, TypeError):
        return None
    low, high = LIMITS[key]
    return value if low <= value <= high else None
