"""JSON tanasini xavfsiz o'qish: faqat dict qabul qilinadi, qiymatlar kutilgan turda bo'ladi."""
import json


def loads_dict(raw, stringify=True):
    """JSON obyektini (dict) qaytaradi. Aks holda ValueError (chaqiruvchi 400 qaytaradi).

    stringify=True: skalyar qiymatlar (son, bool, None) matnga aylantiriladi — shunda `.strip()` kabi
    matn amallari 500 bermaydi. Ichma-ich ro'yxat/obyekt rad etiladi.
    """
    if isinstance(raw, (bytes, bytearray)):
        raw = raw.decode('utf-8')
    data = json.loads(raw or '{}')
    if not isinstance(data, dict):
        raise ValueError('JSON obyekt (dict) bo\'lishi kerak')
    out = {}
    for key, value in data.items():
        if isinstance(value, (dict, list)):
            if stringify:
                raise ValueError(f"'{key}' maydoni oddiy qiymat bo'lishi kerak")
            out[key] = value
        elif stringify:
            out[key] = '' if value is None else str(value)
        else:
            out[key] = value
    return out


def to_id(value):
    """Matn/son -> musbat 31-bitli butun id yoki None (500 o'rniga 400/404 qaytarish uchun)."""
    try:
        number = int(str(value).strip())
    except (TypeError, ValueError):
        return None
    return number if 0 < number < 2 ** 31 else None
