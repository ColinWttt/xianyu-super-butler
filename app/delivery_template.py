"""发货内容发送：把一条卡券内容作为闲鱼 IM 消息发给买家。"""

from loguru import logger

IMAGE_MARKER = "__IMAGE_SEND__"


async def send_payload(
    live_instance,
    websocket,
    chat_id: str,
    buyer_id: str,
    payload: str,
) -> int:
    """发送单条发货内容，返回发出的消息条数。

    标记格式必须与自动发货链路保持一致，见 ``XianyuAutoAsync.py`` 的
    ``_handle_auto_delivery`` 发送循环和 ``_auto_delivery`` 的图片卡券返回值。
    """
    if not payload.startswith(IMAGE_MARKER):
        await live_instance.send_msg(websocket, chat_id, buyer_id, payload)
        return 1

    image_data = payload[len(IMAGE_MARKER):]
    card_id = None
    if "|" in image_data:
        card_id_str, image_url = image_data.split("|", 1)
        try:
            card_id = int(card_id_str)
        except ValueError:
            logger.error(f"无效的卡券ID: {card_id_str}")
    else:
        image_url = image_data

    await live_instance.send_image_msg(websocket, chat_id, buyer_id, image_url, card_id=card_id)
    return 1
