"""tg 0.26 layout, carrying message identity separately from visible text."""
from __future__ import annotations
from datetime import date
from tg.msg import MsgProxy
from tg.utils import string_len_dwc

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

