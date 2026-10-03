"""Rolga qarab menyu va "+ Tez amal" ro'yxatlari (vazifa nomlari bilan)."""
from django.urls import NoReverseMatch, reverse


def role_of(user):
    if user.is_director:
        return 'director'
    if user.is_administrator_role:
        return 'administrator'
    return 'teacher'


# key: (yorliq, ikonka, url nomi, "faol" bo'lish prefikslari, aniq moslik)
ITEMS = {
    'home': ("Bugun", 'house', 'new:home', ('/new/',), True),
    'pay': ("To'lov", 'wallet', 'new:pay', ('/new/payments/',), False),
    'money': ("Pul", 'wallet', 'new:report', ('/new/payments/', '/new/reports/'), False),
    'attendance': ("Davomat", 'clipboard-check', 'new:attendance', ('/new/attendance/',), False),
    'students': ("O'quvchilar", 'user-graduate', 'new:students', ('/new/students/',), False),
    'groups': ("Guruhlar", 'people-group', 'new:groups', ('/new/groups/',), False),
    'schedule': ("Dars jadvali", 'calendar-days', 'new:schedule', ('/new/schedule/',), False),
    'messages': ("Ota-onalar xabarlari", 'envelope', 'new:messages', ('/new/messages/',), False),
    'staff': ("Xodimlar", 'chalkboard-user', 'new:staff', ('/new/staff/',), False),
    'settings': ("Sozlamalar", 'gear', 'new:settings', ('/new/settings/',), False),
    'grades': ("Baholash", 'star', 'new:grades', ('/new/grades/',), False),
    'mygroups': ("Guruhlarim", 'people-group', 'new:my_groups', ('/new/my-groups/',), False),
    'myschedule': ("Jadval", 'calendar-days', 'new:my_schedule', ('/new/my-schedule/',), False),
}

LAYOUT = {
    'administrator': {
        'side': ['home', 'pay', 'attendance', 'students', 'groups', 'schedule', 'messages'],
        'bottom': ['home', 'pay', 'attendance', 'students'],
    },
    'director': {
        'side': ['home', 'money', 'students', 'groups', 'staff', 'attendance', 'schedule', 'messages', 'settings'],
        'bottom': ['home', 'money', 'students', 'staff'],
    },
    'teacher': {
        'side': ['home', 'attendance', 'grades', 'mygroups', 'myschedule'],
        'bottom': ['home', 'attendance', 'grades', 'myschedule'],
    },
}

QUICK = {
    'administrator': [("Yangi o'quvchi", 'user-plus', 'new:student_new'), ("To'lov qabul qilish", 'wallet', 'new:pay'),
                      ("Davomat", 'clipboard-check', 'new:attendance'), ("Yangi guruh", 'people-group', 'new:group_new')],
    'director': [("Yangi o'quvchi", 'user-plus', 'new:student_new'), ("To'lov qabul qilish", 'wallet', 'new:pay'),
                 ("Davomat", 'clipboard-check', 'new:attendance'), ("Yangi guruh", 'people-group', 'new:group_new')],
    'teacher': [("Davomat belgilash", 'clipboard-check', 'new:attendance'), ("Baho qo'yish", 'star', 'new:grades')],
}


def _resolve(key, path):
    label, icon, name, prefixes, exact = ITEMS[key]
    try:
        url = reverse(name)
    except NoReverseMatch:
        return None
    if exact:
        active = path.rstrip('/') == url.rstrip('/')
    else:
        active = any(path.startswith(p) for p in prefixes)
    return {'key': key, 'label': label, 'icon': icon, 'url': url, 'active': active}


def menu_for(user, path):
    role = role_of(user)
    lay = LAYOUT[role]
    side = [i for i in (_resolve(k, path) for k in lay['side']) if i]
    bottom = [i for i in (_resolve(k, path) for k in lay['bottom']) if i]
    quick = []
    for label, icon, name in QUICK[role]:
        try:
            quick.append({'label': label, 'icon': icon, 'url': reverse(name)})
        except NoReverseMatch:
            continue
    return {'ux_role': role, 'ux_side': side, 'ux_bottom': bottom, 'ux_quick': quick}
