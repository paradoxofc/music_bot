import re
from urllib.parse import urlparse

TRACK_ID_RE = re.compile(r'^\d{1,20}$')


def is_valid_track_id(track_id: str) -> bool:
    return bool(track_id and TRACK_ID_RE.fullmatch(track_id))


def is_safe_http_url(url: str) -> bool:
    try:
        parsed = urlparse(url.strip())
    except ValueError:
        return False
    return parsed.scheme in ('http', 'https') and bool(parsed.netloc)


def parse_op_channel_line(line: str) -> dict[str, str] | None:
    """Парсит строку канала ОП: «Текст кнопки — @channel» или «Текст — https://t.me/...»."""
    if '—' in line:
        left, right = line.split('—', 1)
    elif '-' in line:
        left, right = line.split('-', 1)
    else:
        return None

    button_text = left.strip()
    target = right.strip()
    if not button_text or not target:
        return None

    invite_url = None
    channel_ref = target

    if target.startswith('http://') or target.startswith('https://'):
        if not is_safe_http_url(target):
            return None
        invite_url = target.strip()
        parsed = urlparse(invite_url)
        path = (parsed.path or '').strip('/')
        if path.startswith('+'):
            return None
        if path:
            channel_ref = f'@{path.split("/")[0]}'
        else:
            return None
    elif target.startswith('@'):
        channel_ref = target
        invite_url = f'https://t.me/{target.lstrip("@")}'
    elif target.lstrip('-').isdigit():
        channel_ref = target
    else:
        channel_ref = f'@{target.lstrip("@")}'
        invite_url = f'https://t.me/{target.lstrip("@")}'

    return {
        'button_text': button_text,
        'channel_ref': channel_ref,
        'invite_url': invite_url,
    }
