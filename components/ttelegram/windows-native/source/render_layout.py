"""tg 0.26 layout, carrying message identity separately from visible text."""
from __future__ import annotations
import curses
import math
import time
from datetime import date
from tg.msg import MsgProxy
from tg.utils import string_len_dwc, truncate_to_len
from tg.colors import get_color, cyan, white, bold
from chat_transition import CHAT_TRANSITION_SECONDS, CHAT_TRANSITION_GLYPHS, chat_transition_state

class RenderElements(tuple):
    def __new__(cls,values,index,message_id):
        value=super().__new__(cls,values)
        value.message_index=index
        value.message_id=message_id
        return value

def collect(
    self,
    current_msg_idx: int,
    msgs: List[Tuple[int, Dict[str, Any]]],
    min_msg_padding: int,
) -> List[Tuple[Tuple[str, ...], bool, int]]:
    """
    Tries to collect list of messages that will satisfy `min_msg_padding`
    theshold. Long messages could prevent other messages from displaying on
    the screen. In order to prevent scenario when *selected* message moved
    out from the visible area of the screen by some long messages, this
    function will remove message one by one from the start until selected
    message could be visible on the screen.
    """
    selected_item_idx: Optional[int] = None
    collected_items: List[Tuple[Tuple[str, ...], bool, int]] = []
    screen_overflow = False
    today = date.today()
    for ignore_before in range(len(msgs)):
        if selected_item_idx is not None:
            break
        collected_items = []
        screen_overflow = False
        line_num = self.h
        newer_day: Optional[date] = None
        for msg_idx, msg_item in msgs[ignore_before:]:
            is_selected_msg = current_msg_idx == msg_idx
            msg_proxy = MsgProxy(msg_item)
            day = msg_proxy.date.date()
            if newer_day is not None and day != newer_day:
                line_num -= 1
                if line_num < 1:
                    screen_overflow = True
                    break
                collected_items.append(
                    (self._day_separator(newer_day, today), False, line_num)
                )
            newer_day = day
            dt = msg_proxy.date.strftime("%H:%M:%S")
            user_id_item = msg_proxy.sender_id

            user_id = self.model.users.get_user_label(user_id_item)
            flags = self._get_flags(msg_proxy)
            if user_id and flags:
                # if not channel add space between name and flags
                flags = f" {flags}"
            label_elements = f" {dt} ", user_id, flags
            label_len = sum(string_len_dwc(e) for e in label_elements)

            msg = self._format_msg(msg_proxy, width_limit=self.w - label_len - 1)
            elements = *label_elements, f" {msg}"
            needed_lines = 0
            for i, msg_line in enumerate(msg.split("\n")):
                # count wide character utf-8 symbols that take > 1 bytes to
                # print it causes invalid offset
                line_len = string_len_dwc(msg_line)

                # first line cotains msg lable, e.g user name, date
                if i == 0:
                    line_len += label_len

                needed_lines += (line_len // self.w) + 1

            line_num -= needed_lines
            if line_num < 0:
                screen_overflow = True
                tail_lines = needed_lines + line_num - 1
                # try preview long message that did fit in the screen
                if tail_lines > 0 and not is_selected_msg:
                    limit = self.w * tail_lines
                    tail_chatacters = len(msg) - limit - 3
                    elements = (
                        "",
                        "",
                        "",
                        f" ...{msg[tail_chatacters:]}",
                    )
                    collected_items.append((RenderElements(elements, msg_idx, msg_item["id"]), is_selected_msg, 0))
                break
            collected_items.append((RenderElements(elements, msg_idx, msg_item["id"]), is_selected_msg, line_num))
            if is_selected_msg:
                selected_item_idx = len(collected_items) - 1
        if newer_day is not None and not screen_overflow and line_num > 1:
            collected_items.append(
                (self._day_separator(newer_day, today), False, line_num - 1)
            )
        if (
            # ignore first and last msg
            selected_item_idx not in (0, len(msgs) - 1, None)
            and selected_item_idx is not None
            and len(collected_items) - 1 - selected_item_idx < min_msg_padding
            and screen_overflow
        ):
            selected_item_idx = None

    return collected_items


def _put(win, y, x, text, attr=0):
    raw = getattr(win, 'win', win)
    h, w = raw.getmaxyx()
    if not (0 <= y < h and 0 <= x < w - 1):
        return
    text = truncate_to_len(str(text), max(0, w - x - 1))
    if not text:
        return
    try:
        raw.addstr(y, x, text, attr)
    except curses.error:
        # Curses can reject a wide character at the lower right corner.
        cursor = x
        for char in text:
            width = string_len_dwc(char)
            if cursor + width >= w:
                break
            try:
                raw.addstr(y, cursor, char, attr)
            except curses.error:
                break
            cursor += width


def _wrap(text, limit):
    limit = max(1, limit)
    result = []
    for paragraph in str(text).split('\n'):
        if not paragraph:
            result.append('')
            continue
        while string_len_dwc(paragraph) > limit:
            used = cut = last_space = 0
            for index, char in enumerate(paragraph):
                width = string_len_dwc(char)
                if used + width > limit:
                    break
                used += width
                cut = index + 1
                if char.isspace():
                    last_space = cut
            if not cut:
                cut = 1
            if last_space:
                cut = last_space
            result.append(paragraph[:cut].rstrip())
            paragraph = paragraph[cut:].lstrip()
            if not paragraph:
                break
        if paragraph:
            result.append(paragraph)
    return result or ['']


def chat_preview(view, chat):
    try:
        sender, preview = view._get_last_msg_data(chat)
    except (AttributeError, KeyError, TypeError, ValueError):
        sender, preview = '', ''
    try:
        content = (chat.get('last_message') or {}).get('content') or {}
        kind = content.get('@type')
        label = {
            'messagePhoto': 'Фото', 'messageVideo': 'Видео',
            'messageAnimation': 'GIF', 'messageSticker': 'Стикер',
            'messageVoiceNote': 'Голосовое', 'messageAudio': 'Аудио',
            'messageVideoNote': 'Видеосообщение', 'messageDocument': 'Файл',
        }.get(kind)
        caption = content.get('caption') or {}
        caption = caption.get('text', '') if isinstance(caption, dict) else ''
        if label:
            preview = label + ((' · ' + caption) if caption else '')
    except (AttributeError, KeyError, TypeError, ValueError):
        pass
    return ' · '.join(str(part).strip() for part in (sender, preview) if part)


def draw_shell(controller):
    screen = controller.view.stdscr
    rows, cols = screen.getmaxyx()
    if rows < 1 or cols < 4:
        return
    engine = getattr(controller, 'engine', None)
    title = 'Диалоги' if controller.view_mode == 'chats' else 'Переписка'
    if controller.view_mode == 'messages':
        try:
            title += ' / ' + controller.model.chats.chats[controller.model.current_chat].get('title', '')
        except (IndexError, KeyError, TypeError):
            pass
    accent = get_color(cyan, -1) | bold
    muted = get_color(white, -1) | curses.A_DIM
    _put(screen, 0, 0, ' ' * (cols - 1))
    _put(screen, 0, 1, 'ttelegram', accent)
    _put(screen, 0, 13, truncate_to_len(title, max(0, cols - 35)), muted)
    if cols >= 58:
        _put(screen, 0, max(1, cols - 31), 'Ctrl+L чаты  ·  Ctrl+Q выход', muted)
    panel_rect = getattr(controller.view.chats, 'panel_rect', None)
    chat_width = panel_rect[3] if panel_rect else getattr(controller.view.chats, 'w', 0)
    if chat_width and controller.view.msgs.w and chat_width < cols - 36:
        panel_rows = panel_rect[2] if panel_rect else rows
        for y in range(1, min(rows, panel_rows + 1)):
            try:
                screen.addstr(y, chat_width, '│', muted)
            except curses.error:
                break
    screen.refresh()


def draw_chats(view, current, chats, title=''):
    view.win.erase()
    h, w = view.win.getmaxyx()
    engine = getattr(view, 'engine', None)
    accent = get_color(cyan, -1)
    primary = get_color(white, -1)
    muted = primary | curses.A_DIM
    _put(view.win, 0, 0, 'ДИАЛОГИ', accent | bold)
    count_label = str(getattr(engine, 'chat_count', len(chats)))
    if w > 14:
        _put(view.win, 0, max(1, w - len(count_label) - 2), count_label, muted)
    query = getattr(engine, 'query', '')
    if h > 1:
        _put(view.win, 1, 0, '⌕ ' + (query or 'Поиск по диалогам'), muted)
    _put(view.win, 2, 0, '─' * max(1, w - 1), muted)
    origin_y, origin_x = view.win.getbegyx()
    view.mouse_chats = list(chats)
    view.mouse_rows = []
    if not chats and h > 4:
        hint = 'Нет совпадений' if query else 'Диалогов пока нет'
        _put(view.win, 4, 1, hint, muted)
    now = time.monotonic()
    unread_previous = getattr(view, '_unread_counts', {})
    unread_current = {}
    if engine is not None:
        engine.unread_animation = getattr(engine, 'unread_animation', {})
    for index, chat in enumerate(chats):
        top = 3 + index * 2
        if top >= h:
            break
        selected = index == current
        chat_id = chat.get('id')
        unread = max(0, int(chat.get('unread_count') or 0))
        marked = bool(chat.get('is_marked_as_unread'))
        unread_current[chat_id] = unread
        if engine is not None and unread > unread_previous.get(chat_id, unread):
            engine.unread_animation[chat_id] = now
        badge = str(unread) if unread else ('•' if marked else '')
        marker = '▌' if selected else ' '
        selection = getattr(engine, 'selection_animation', None) if engine else None
        if selected and selection:
            phase = min(1.0, max(0.0, (now - selection[0]) / .10))
            marker = ('·', '◦', '▌')[min(2, int(phase * 3))]
        if engine is not None and engine.unread_animation:
            started = engine.unread_animation.get(chat_id)
            if started is not None and now - started < .24:
                phase = min(2, int((now - started) / .08))
                badge = ('·', '◦', '●')[phase] if unread or marked else badge
        marker_attr = accent | (bold if selected else curses.A_DIM)
        title_attr = primary | (bold if selected else 0)
        if top + 1 < h:
            name = str(chat.get('title') or 'Без названия')
            reserve = string_len_dwc(badge) + 1 if badge else 0
            title_limit = max(1, w - 3 - reserve)
            _put(view.win, top, 0, marker, marker_attr)
            _put(view.win, top, 2, truncate_to_len(name, title_limit), title_attr)
            if badge:
                _put(view.win, top, max(2, w - string_len_dwc(badge) - 1), badge, accent | bold)
            preview = chat_preview(view, chat) or 'Сообщений пока нет'
            preview = ' '.join(str(preview).split())
            _put(view.win, top + 1, 2, truncate_to_len(preview, max(0, w - 4)), muted)
            view.mouse_rows.append((origin_y + top, origin_y + top + 2, index))
    view._unread_counts = unread_current
    if getattr(view, '_refresh', None):
        view._refresh()


def controller_chat(view):
    engine = getattr(view, 'engine', None)
    if engine is None:
        return None
    try:
        cid = engine.c.model.current_chat_id
        return next((chat for chat in engine.c.model.chats.chats if chat.get('id') == cid), None)
    except (AttributeError, IndexError, KeyError, TypeError):
        return None


def draw_empty(view, chat_list_available=True):
    view.win.erase()
    h, w = view.win.getmaxyx()
    accent = get_color(cyan, -1)
    muted = get_color(white, -1) | curses.A_DIM
    _put(view.win, 0, 0, 'ПЕРЕПИСКА', accent | bold)
    _put(view.win, 2, 0, '─' * max(1, w - 1), muted)
    if h >= 7 and w >= 32:
        center = max(3, h // 2 - 1)
        ornament = '·  T / TELEGRAM  ·'
        _put(view.win, center, max(0, (w - string_len_dwc(ornament)) // 2), ornament, accent | curses.A_DIM)
        hint = 'Выберите диалог слева' if chat_list_available else 'Загружаю список диалогов…'
        _put(view.win, center + 2, max(0, (w - string_len_dwc(hint)) // 2), hint, get_color(white, -1) | bold)
        if chat_list_available:
            sub = 'Enter откроет переписку  ·  / поиск'
            _put(view.win, center + 3, max(0, (w - string_len_dwc(sub)) // 2), sub, muted)
    elif h > 3:
        _put(view.win, 3, 1, 'Выберите диалог слева', muted)
    if getattr(view, '_refresh', None):
        view._refresh()


def _message_block(view, index, message, current, selected_ids, now):
    proxy = MsgProxy(message)
    body_width = max(10, min(72, int(max(12, view.w - 4) * .74)))
    try:
        outgoing = bool(view.model.is_me(proxy.sender_id))
    except (AttributeError, KeyError, TypeError):
        outgoing = False
    try:
        sender = 'Вы' if outgoing else view.model.users.get_user_label(proxy.sender_id)
    except (AttributeError, KeyError, TypeError):
        sender = 'Сообщение'
    sender = str(sender or 'Сообщение')
    try:
        when = proxy.date
        clock = when.strftime('%H:%M')
        day = when.date()
    except (AttributeError, KeyError, TypeError, ValueError):
        clock = ''
        day = date.today()
    status = []
    send_state = (message.get('sending_state') or {}).get('@type')
    if send_state == 'messageSendingStatePending':
        status.append('отправляется')
    elif send_state == 'messageSendingStateFailed':
        status.append('ошибка отправки')
    if message.get('edit_date'):
        status.append('изменено')
    meta = '  '.join(part for part in (sender, clock, ' · '.join(status)) if part)
    try:
        formatted = view._format_msg(proxy, width_limit=body_width)
    except Exception:
        formatted = 'Не удалось отобразить сообщение'
    try:
        reply_id = proxy.reply_msg_id
        if reply_id:
            replied = view.model.msgs.get_message(proxy.chat_id, reply_id)
            if replied:
                reply_proxy = MsgProxy(replied)
                reply_text = ' '.join(str(view._parse_msg(reply_proxy)).split())
                reply_sender = view.model.users.get_user_label(reply_proxy.sender_id)
                reply_line = '> ' + ((str(reply_sender) + ': ') if reply_sender else '') + reply_text
                content_lines = str(formatted).split('\n')
                if content_lines and content_lines[0].startswith('>'):
                    content_lines = content_lines[1:]
                formatted = reply_line + ('\n' + '\n'.join(content_lines) if content_lines else '')
    except (AttributeError, KeyError, TypeError, ValueError):
        pass
    raw_lines = str(formatted).split('\n')
    lines = []
    media_marker = None
    for raw in raw_lines:
        if raw.startswith(('Фото / ', 'Стикер / ', 'GIF / ')):
            media_marker = len(lines)
            lines.extend(_wrap(raw, body_width))
        else:
            lines.extend(_wrap(raw, body_width))
    if media_marker is not None:
        while lines and not lines[-1].strip():
            lines.pop()
    if not lines:
        lines = ['']
    path = None
    media_size = None
    kind = proxy.content_type
    if kind in ('photo', 'sticker', 'animation'):
        try:
            from media import dimensions, media_path
            path = media_path(proxy)
            if path:
                if media_marker is None:
                    media_marker = len(lines)
                    label = {'photo': 'Фото', 'sticker': 'Стикер', 'animation': 'GIF'}[kind]
                    lines.append(label + ' / изображение')
                cols, rows = dimensions(path, min(48, max(8, body_width - 2)), max(2, min(16, view.h // 2)))
                media_size = (cols, rows)
                lines.extend([''] * rows)
            elif media_marker is None:
                media_marker = len(lines)
                label = {'photo': 'Фото', 'sticker': 'Стикер', 'animation': 'GIF'}[kind]
                file_id = getattr(proxy, 'file_id', None)
                downloading = bool(file_id)
                lines.append(label + ' / ' + ('загрузка…' if downloading else 'медиа'))
        except (OSError, ValueError, KeyError, TypeError):
            path = None
    content_width = max(string_len_dwc(meta), *(string_len_dwc(line) for line in lines))
    if media_size:content_width=max(content_width,media_size[0])
    block_width = min(body_width, content_width)
    selected = index == current or message.get('id') in selected_ids
    engine = getattr(view, 'engine', None)
    incoming_start = None
    if engine is not None:
        chat_id = message.get('chat_id')
        known = engine.known_message_ids.setdefault(chat_id, set())
        history_loading = chat_id in getattr(view.model.msgs, '_history_loading', set())
        opened = getattr(engine, 'chat_opened_wall', 0)
        if message.get('id') not in known:
            if (not outgoing and not history_loading and now >= engine.chat_grace_until
                    and message.get('date', 0) > int(opened)):
                incoming_start = now
                engine.incoming_animation[(chat_id, message['id'])] = now
            known.add(message.get('id'))
        incoming_start = engine.incoming_animation.get((chat_id, message.get('id')), incoming_start)
    return {
        'index': index, 'message': message, 'id': message.get('id'), 'day': day,
        'meta': meta, 'lines': lines, 'media_marker': media_marker,
        'media_path': path, 'media_size': media_size, 'width': block_width,
        'outgoing': outgoing, 'selected': selected, 'incoming_start': incoming_start,
        'height': 1 + len(lines),
    }


def draw_messages(view, current, msgs, min_msg_padding, chat):
    from native_image import begin_frame
    begin_frame(view.win)
    view.win.erase()
    h, w = view.win.getmaxyx()
    accent = get_color(cyan, -1)
    primary = get_color(white, -1)
    muted = primary | curses.A_DIM
    try:
        title = str(chat.get('title') or 'Переписка')
    except AttributeError:
        title = 'Переписка'
    engine = getattr(view, 'engine', None)
    transition = getattr(engine, 'transition_started', 0) if engine else 0
    now = time.monotonic()
    transition_age = now - transition if transition else CHAT_TRANSITION_SECONDS
    transition_active = bool(transition and 0 <= transition_age < CHAT_TRANSITION_SECONDS)
    progress = min(1.0, max(0.0, transition_age / CHAT_TRANSITION_SECONDS))
    glyph = CHAT_TRANSITION_GLYPHS[chat_transition_state(transition_age)]
    _put(view.win, 0, 0, 'ПЕРЕПИСКА  /  ' + truncate_to_len(title, max(0, w - 20)), accent | bold)
    _put(view.win, 0, max(1, w - 3), glyph, accent | curses.A_DIM)
    _put(view.win, 1, 0, '─' * max(1, w - 1), muted)
    view._mouse_rows = []
    view._media_hitboxes = []
    view._editorial_media = []
    view._draw_layout = []
    view._incoming_marks = []
    selected_ids = set()
    try:
        selected_ids = set(view.model.selected[chat['id']])
    except (AttributeError, KeyError, TypeError):
        pass
    radius = max(10, min(32, h // 2 + 8))
    nearby = [(index, message) for index, message in msgs if current - radius <= index <= current + radius]
    blocks = [_message_block(view, index, message, current, selected_ids, now) for index, message in nearby]
    blocks.sort(key=lambda block: block['index'])
    if not blocks or h < 3:
        if h > 2:
            hint = 'История пока пуста' if not blocks else 'Увеличьте окно терминала'
            _put(view.win, 2, 1, hint, muted)
        if getattr(view, '_refresh', None):
            view._refresh()
        return
    anchor = next((position for position, block in enumerate(blocks) if block['index'] == current), 0)
    max_height = max(1, h - 3)
    target = blocks[anchor]
    if target['height'] > max_height:
        body_limit = max(1, max_height - 2)
        old_lines = target['lines']
        keep = max(0, body_limit - 1)
        target['lines'] = (['…'] + old_lines[-keep:]) if keep else ['…']
        target['media_marker'] = None
        target['media_path'] = None
        target['media_size'] = None
        target['height'] = 1 + len(target['lines'])
        target['width'] = min(target['width'], max(string_len_dwc(line) for line in target['lines']))
    target_top = h - target['height'] - 1 if anchor == 0 else max(2, min(h - target['height'] - 1, h // 2 - target['height'] // 2))
    placed = [(anchor, target_top)]
    cursor = target_top - 2
    for position in range(anchor + 1, len(blocks)):
        block = blocks[position]
        top = cursor - block['height'] + 1
        if top < 2:
            break
        placed.append((position, top))
        cursor = top - 2
    cursor = target_top + target['height'] - 1
    for position in range(anchor - 1, -1, -1):
        block = blocks[position]
        top = cursor + 2
        if top + block['height'] > h:
            break
        placed.append((position, top))
        cursor = top + block['height'] - 1
    placed.sort(key=lambda item: item[1])
    if transition_active and len(placed) > 1:
        eased = 1.0 - (1.0 - progress) ** 2
        reveal_count = max(1, min(len(placed), math.ceil(eased * len(placed))))
        reveal_order = sorted(placed, key=lambda item: (abs(item[0] - anchor), -item[1]))
        visible_positions = {position for position, _ in reveal_order[:reveal_count]}
        placed = [item for item in placed if item[0] in visible_positions]
    origin_y, origin_x = view.win.getbegyx()
    for previous, following in zip(placed, placed[1:]):
        older = blocks[previous[0]]
        newer = blocks[following[0]]
        gap_y = previous[1] + older['height']
        if older['day'] != newer['day'] and gap_y < following[1]:
            try:
                from tg.views import day_label
                label = '· ' + day_label(older['day'], date.today()) + ' ·'
            except (ImportError, AttributeError, TypeError):
                label = '· ' + older['day'].isoformat() + ' ·'
            _put(view.win, gap_y, max(0, (w - string_len_dwc(label)) // 2), label, muted)
    for position, top in placed:
        block = blocks[position]
        max_x = max(1, w - block['width'] - 1)
        x = min(2, max_x) if not block['outgoing'] else max(1, w - 2 - block['width'])
        meta = truncate_to_len(block['meta'], block['width'])
        meta_x = x if not block['outgoing'] else max(1, x + block['width'] - string_len_dwc(meta))
        meta_attr = accent | curses.A_DIM
        if block['selected']:
            meta_attr |= bold
        _put(view.win, top, meta_x, meta, meta_attr)
        view._mouse_rows.append((origin_y + top, block['index']))
        media_marker = block['media_marker']
        for line_index, line in enumerate(block['lines']):
            row = top + 1 + line_index
            if row >= h:
                break
            line_width = min(block['width'], string_len_dwc(line))
            line_x = x if not block['outgoing'] else max(1, x + block['width'] - line_width)
            if block['outgoing']:
                line_attr = accent | (bold if block['selected'] else 0)
            else:
                line_attr = primary | (bold if block['selected'] else 0)
            if line.lstrip().startswith('>'):
                line_attr = muted
            if media_marker == line_index:
                line_attr = accent | curses.A_DIM
            if block['selected']:
                _put(view.win, row, max(0, x - 1), '▏', accent | bold)
            if block['incoming_start'] is not None and line_index == 0:
                age = now - block['incoming_start']
                if age < .18:
                    marker = ('·', '◦', '▏')[min(2, int(age / .06))]
                    _put(view.win, row, max(0, x - 1), marker, accent | curses.A_DIM)
                    view._incoming_marks.append((row, max(0, x - 1), block['incoming_start']))
            if line:
                _put(view.win, row, line_x, line, line_attr)
            view._mouse_rows.append((origin_y + row, block['index']))
        if not transition_active and media_marker is not None and block['media_path'] and block['media_size']:
            cols, rows = block['media_size']
            image_y = top + 1 + media_marker + 1
            image_x = x if not block['outgoing'] else max(1, x + block['width'] - cols)
            if image_y >= 0 and image_y + rows <= h:
                screen_top, screen_left = origin_y + image_y, origin_x + image_x
                view._editorial_media.append((image_y, image_x, cols, rows, block['index'], block['media_path']))
                view._media_hitboxes.append((screen_top, screen_left, rows, cols, block['index']))
        elements = RenderElements((block['meta'], block['meta'], '', '\n'.join(block['lines'])), block['index'], block['id'])
        view._draw_layout.append((elements, block['index'] == current, top))
    if getattr(view, '_refresh', None):
        view._refresh()


def animate_messages(controller, now=None):
    """Update small markers after chat-open history has settled."""
    view = controller.view.msgs
    if not getattr(view, 'w', 0):
        return
    now = time.monotonic() if now is None else now
    engine = getattr(controller, 'engine', None)
    accent = get_color(cyan, -1) | curses.A_DIM
    transition = getattr(engine, 'transition_started', 0) if engine else 0
    glyph = CHAT_TRANSITION_GLYPHS[-1]
    if transition and now - transition < CHAT_TRANSITION_SECONDS:
        glyph = CHAT_TRANSITION_GLYPHS[chat_transition_state(now - transition)]
    _put(view.win, 0, max(1, view.w - 3), glyph, accent)
    for row, column, started in getattr(view, '_incoming_marks', []):
        age = now - started
        if age < .18:
            phase = min(2, int(age / .06))
            _put(view.win, row, column, ('·', '◦', '▏')[phase], accent)
    if getattr(view, '_refresh', None):
        view._refresh()

