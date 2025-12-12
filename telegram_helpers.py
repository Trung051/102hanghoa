from datetime import datetime
from database import update_telegram_message, get_shipment_by_id, get_transfer_slip, get_transfer_slip_items
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
        f"Lỗi / Tình trạng: {shipment.get('capacity','')}\n"
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
        # Handle multiple images (separated by ;)
        image_urls = [url.strip() for url in image_url.split(';') if url.strip()]
        print(f"📸 Sending {len(image_urls)} images to Telegram")
        if image_urls:
            success_count = 0
            failed_count = 0
            
            # Send first image with caption
            print(f"📤 Sending first image (1/{len(image_urls)}): {image_urls[0]}")
            res = send_photo(image_urls[0], message_text)
            print(f"📤 First image result: {res}")
            
            if res.get('success'):
                success_count += 1
                # Send remaining images without caption
                for idx, img_url in enumerate(image_urls[1:], 2):
                    print(f"📤 Sending image {idx}/{len(image_urls)}: {img_url}")
                    send_res = send_photo(img_url, "")
                    print(f"📤 Image {idx} result: {send_res}")
                    if send_res.get('success'):
                        success_count += 1
                    else:
                        failed_count += 1
                        print(f"❌ Failed to send image {idx}: {send_res.get('error', 'Unknown error')}")
                
                # Summary
                if success_count == len(image_urls):
                    print(f"✅ Successfully sent all {success_count} images to Telegram")
                else:
                    print(f"⚠️ Sent {success_count}/{len(image_urls)} images. {failed_count} failed.")
            else:
                # First image failed, fallback to text with links
                print(f"⚠️ First photo send failed, falling back to text")
                failed_count = 1
                images_text = "\n".join([f"Ảnh {i+1}: {url}" for i, url in enumerate(image_urls)])
                message_text = f"{message_text}\n\n{images_text}"
                res = send_text(message_text)
                print(f"📤 Text fallback result: {res}")
        else:
            res = send_text(message_text)
    else:
        print(f"📤 No image URL, sending text only")
        res = send_text(message_text)

    if res and res.get('success') and res.get('message_id'):
        update_telegram_message(shipment_id, res['message_id'])
        print(f"✅ Telegram message ID saved: {res['message_id']}")

    return res


def send_transfer_slip_notification(transfer_slip_id):
    """
    Send Telegram notification for completed transfer slip.
    Includes: transfer code, IMEIs (masked), transfer time, transfer person, image.
    """
    slip = get_transfer_slip(transfer_slip_id)
    if not slip:
        return {'success': False, 'error': 'Không tìm thấy phiếu chuyển'}
    
    items_df = get_transfer_slip_items(transfer_slip_id)
    if items_df.empty:
        return {'success': False, 'error': 'Phiếu chuyển không có máy nào'}
    
    # Format IMEIs (masked - tô đen)
    imeis = []
    for idx, row in items_df.iterrows():
        imei = str(row['imei'])
        # Mask IMEI: show first 2 and last 2 digits, mask middle
        if len(imei) > 4:
            masked = imei[:2] + '█' * (len(imei) - 4) + imei[-2:]
        else:
            masked = '█' * len(imei)
        imeis.append(f"{row['qr_code']}: {masked}")
    
    imeis_text = "\n".join(imeis)
    
    # Format message
    transfer_time = slip.get('completed_at') or slip.get('created_at') or datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    transfer_person = slip.get('completed_by') or slip.get('created_by', 'N/A')
    
    message_text = (
        f"<b>Phiếu Chuyển Hoàn Thành</b>\n"
        f"Mã phiếu chuyển: <code>{slip['transfer_code']}</code>\n"
        f"Giờ chuyển: {transfer_time}\n"
        f"Người chuyển: {transfer_person}\n"
        f"Số lượng máy: {len(items_df)}\n\n"
        f"<b>IMEI các máy:</b>\n{imeis_text}"
    )
    
    if slip.get('notes'):
        message_text += f"\n\nGhi chú: {slip['notes']}"
    
    image_url = slip.get('image_url')
    
    # Send with photo if available, otherwise text only
    if image_url:
        res = send_photo(image_url, message_text)
    else:
        res = send_text(message_text)
    
    return res

