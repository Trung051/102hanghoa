from datetime import datetime
from database import update_telegram_message, get_shipment_by_id
from telegram_notify import send_text, send_photo


def _format_shipment_text(shipment, is_update_image=False):
    note = shipment.get('notes') or ''
    recv_time = shipment.get('received_time') or ''
    sent_time = shipment.get('sent_time') or ''
    header = "Cập nhật ảnh" if is_update_image else "Phiếu đã nhận"
    text = (
        f"<b>{header}</b>\n"
        f"QR: {shipment.get('qr_code','')}\n"
        f"IMEI: {shipment.get('imei','')}\n"
        f"Thiết bị: {shipment.get('device_name','')}\n"
        f"Dung lượng: {shipment.get('capacity','')}\n"
        f"NCC: {shipment.get('supplier','')}\n"
        f"Trạng thái: {shipment.get('status','')}\n"
        f"Thời gian gửi: {sent_time}\n"
        f"Thời gian nhận: {recv_time}\n"
        f"Ghi chú: {note}"
    )
    return text


def notify_shipment_if_received(shipment_id, force=False, is_update_image=False):
    """
    Send Telegram message if shipment status is 'Đã nhận'.
    - force: send even if already sent before
    - is_update_image: True when sending follow-up with image
    """
    shipment = get_shipment_by_id(shipment_id)
    if not shipment:
        return

    if shipment.get('status') != 'Đã nhận':
        return

    already_sent = shipment.get('telegram_message_id')
    image_url = shipment.get('image_url')

    # If not force and already sent and no new image, skip
    if already_sent and not (is_update_image and image_url):
        return

    message_text = _format_shipment_text(shipment, is_update_image=is_update_image)

    # Try photo first if available; fallback to text if photo fails or no image
    res = None
    if image_url:
        res = send_photo(image_url, message_text)
        if not res.get('success'):
            # Fallback: send text with link to image
            message_text = f"{message_text}\nẢnh: {image_url}"
            res = send_text(message_text)
    else:
        res = send_text(message_text)

    if res.get('success') and res.get('message_id'):
        update_telegram_message(shipment_id, res['message_id'])

    return res

