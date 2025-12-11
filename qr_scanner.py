"""
QR Code Scanner and Parser Module
Handles QR code decoding from images and parsing QR string data
Uses OpenCV QRCodeDetector as primary method, with pyzbar as fallback
"""

from PIL import Image, ImageEnhance, ImageFilter
import numpy as np

# Try to import cv2 (OpenCV) - primary method
try:
    import cv2
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False
    print("Warning: opencv-python not available")

# Try to import pyzbar, with fallback if not available
try:
    from pyzbar.pyzbar import decode as pyzbar_decode
    PYZBAR_AVAILABLE = True
except ImportError as e:
    PYZBAR_AVAILABLE = False
    print(f"Warning: pyzbar not available: {e}")
    # Create a dummy decode function
    def pyzbar_decode(image):
        return []


def decode_qr_from_image(image):
    """
    Decode QR code from image with multiple preprocessing methods
    Uses OpenCV QRCodeDetector as primary method, pyzbar as fallback
    
    Args:
        image: PIL Image or numpy array
        
    Returns:
        str: Decoded QR code text, or None if not found
    """
    try:
        # Convert PIL Image to numpy array if needed
        if isinstance(image, Image.Image):
            image_array = np.array(image)
        else:
            image_array = image
        
        # Optional: upscale image to help weak/blurred captures
        if len(image_array.shape) >= 2:
            try:
                h, w = image_array.shape[:2]
                scale = 2  # upscale 2x
                if h > 0 and w > 0:
                    if len(image_array.shape) == 3:
                        image_array = cv2.resize(image_array, (w * scale, h * scale), interpolation=cv2.INTER_CUBIC)
                    else:
                        image_array = cv2.resize(image_array, (w * scale, h * scale), interpolation=cv2.INTER_CUBIC)
            except Exception:
                pass

        # Method 1: Try OpenCV QRCodeDetector first (best for Windows, no DLL needed)
        if CV2_AVAILABLE:
            try:
                # Convert to grayscale if needed
                if len(image_array.shape) == 3:
                    gray = cv2.cvtColor(image_array, cv2.COLOR_RGB2GRAY)
                else:
                    gray = image_array
                
                # Use OpenCV QRCodeDetector
                detector = cv2.QRCodeDetector()
                retval, decoded_info, points, straight_qrcode = detector.detectAndDecodeMulti(gray)
                
                if retval and decoded_info:
                    # Return first decoded QR code
                    result = decoded_info[0] if isinstance(decoded_info, (list, tuple)) else decoded_info
                    if result:
                        print("QR decoded successfully using OpenCV")
                        return result
                
                # Try single decode if multi failed
                data, bbox, rectified = detector.detectAndDecode(gray)
                if data:
                    print("QR decoded successfully using OpenCV (single)")
                    return data
            except Exception as e:
                print(f"OpenCV decode failed: {e}")
        
        # Method 2: Try pyzbar as fallback
        if PYZBAR_AVAILABLE:
            try:
                decoded_objects = pyzbar_decode(image_array)
                if decoded_objects:
                    result = decoded_objects[0].data.decode('utf-8')
                    print("QR decoded successfully using pyzbar")
                    return result
            except Exception as e:
                print(f"pyzbar decode failed: {e}")
        
        # Method 3: Try with preprocessing (if CV2 available)
        if CV2_AVAILABLE:
            methods = [
                lambda img: decode_grayscale_opencv(img),
                lambda img: decode_resized_opencv(img),
                lambda img: decode_binarized_opencv(img),
            ]
            
            for i, method in enumerate(methods):
                try:
                    result = method(image_array)
                    if result:
                        print(f"QR decoded successfully using preprocessing method {i+1}")
                        return result
                except Exception as e:
                    print(f"Preprocessing method {i+1} failed: {e}")
                    continue
        
        # If all methods fail, return None
        return None
        
    except Exception as e:
        print(f"Error decoding QR code: {e}")
        import traceback
        traceback.print_exc()
        return None


def decode_grayscale_opencv(image_array):
    """Decode QR with OpenCV after grayscale conversion"""
    if not CV2_AVAILABLE:
        return None
    try:
        if len(image_array.shape) == 3:
            gray = cv2.cvtColor(image_array, cv2.COLOR_RGB2GRAY)
        else:
            gray = image_array
        
        detector = cv2.QRCodeDetector()
        data, bbox, rectified = detector.detectAndDecode(gray)
        if data:
            return data
        return None
    except:
        return None


def decode_resized_opencv(image_array):
    """Decode QR with OpenCV after resizing"""
    if not CV2_AVAILABLE:
        return None
    try:
        if len(image_array.shape) == 3:
            height, width = image_array.shape[:2]
            resized = cv2.resize(image_array, (width * 3, height * 3), interpolation=cv2.INTER_CUBIC)
        else:
            height, width = image_array.shape
            resized = cv2.resize(image_array, (width * 3, height * 3), interpolation=cv2.INTER_CUBIC)
        
        detector = cv2.QRCodeDetector()
        data, bbox, rectified = detector.detectAndDecode(resized)
        if data:
            return data
        return None
    except:
        return None


def decode_binarized_opencv(image_array):
    """Decode QR with OpenCV after binarization"""
    if not CV2_AVAILABLE:
        return None
    try:
        if len(image_array.shape) == 3:
            gray = cv2.cvtColor(image_array, cv2.COLOR_RGB2GRAY)
        else:
            gray = image_array
        
        # Apply threshold
        _, binary = cv2.threshold(gray, 127, 255, cv2.THRESH_BINARY)
        adaptive = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2)
        
        detector = cv2.QRCodeDetector()
        
        # Try binary
        data, bbox, rectified = detector.detectAndDecode(binary)
        if data:
            return data
        
        # Try adaptive
        data2, bbox2, rectified2 = detector.detectAndDecode(adaptive)
        if data2:
            return data2
        
        return None
    except:
        return None


def decode_grayscale(image_array):
    """Decode QR with grayscale conversion (pyzbar method)"""
    if not CV2_AVAILABLE or not PYZBAR_AVAILABLE:
        return []
    try:
        if len(image_array.shape) == 3:
            gray = cv2.cvtColor(image_array, cv2.COLOR_RGB2GRAY)
            return pyzbar_decode(gray)
        else:
            return pyzbar_decode(image_array)
    except:
        return []


def decode_resized(image_array):
    """Decode QR with resized image (pyzbar method)"""
    if not CV2_AVAILABLE or not PYZBAR_AVAILABLE:
        return []
    try:
        if len(image_array.shape) == 3:
            height, width = image_array.shape[:2]
            resized = cv2.resize(image_array, (width * 2, height * 2), interpolation=cv2.INTER_CUBIC)
        else:
            height, width = image_array.shape
            resized = cv2.resize(image_array, (width * 2, height * 2), interpolation=cv2.INTER_CUBIC)
        return pyzbar_decode(resized)
    except:
        return []


def decode_enhanced_contrast(image_array):
    """Decode QR with enhanced contrast (pyzbar method)"""
    if not PYZBAR_AVAILABLE:
        return []
    try:
        # Convert to PIL Image for enhancement
        if isinstance(image_array, np.ndarray):
            if len(image_array.shape) == 3:
                pil_image = Image.fromarray(image_array)
            else:
                pil_image = Image.fromarray(image_array, mode='L')
        else:
            pil_image = image_array
        
        # Enhance contrast
        enhancer = ImageEnhance.Contrast(pil_image)
        enhanced = enhancer.enhance(2.0)
        
        # Convert back to numpy array
        enhanced_array = np.array(enhanced)
        
        return pyzbar_decode(enhanced_array)
    except:
        return []


def decode_binarized(image_array):
    """Decode QR with binarization (pyzbar method)"""
    if not CV2_AVAILABLE or not PYZBAR_AVAILABLE:
        return []
    try:
        # Convert to grayscale if needed
        if len(image_array.shape) == 3:
            gray = cv2.cvtColor(image_array, cv2.COLOR_RGB2GRAY)
        else:
            gray = image_array
        
        # Apply threshold to create binary image
        _, binary = cv2.threshold(gray, 127, 255, cv2.THRESH_BINARY)
        
        # Also try adaptive threshold
        adaptive = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2)
        
        # Try both
        result1 = pyzbar_decode(binary)
        if result1:
            return result1
        
        result2 = pyzbar_decode(adaptive)
        if result2:
            return result2
        
        return []
    except:
        return []


def parse_qr_code(qr_string):
    """
    Parse QR code string into dictionary (flexible format)
    
    Format: "qr_code,imei,device_name,capacity" or more values
    Accepts 1-4+ values, takes first 4, missing values will be empty strings
    
    Args:
        qr_string: QR code string with comma-separated values
        
    Returns:
        dict: Parsed QR data with keys: qr_code, imei, device_name, capacity
        None: If qr_string is empty
    """
    if not qr_string:
        return None
    
    try:
        # Split by comma
        parts = qr_string.split(',')
        
        # Strip whitespace from each part
        parts = [part.strip() for part in parts]
        
        # Take first 4 values, pad with empty strings if less than 4
        while len(parts) < 4:
            parts.append('')
        
        # Return first 4 values (ignore extra values if more than 4)
        return {
            'qr_code': parts[0] if len(parts) > 0 else '',
            'imei': parts[1] if len(parts) > 1 else '',
            'device_name': parts[2] if len(parts) > 2 else '',
            'capacity': parts[3] if len(parts) > 3 else ''
        }
    except Exception as e:
        print(f"Error parsing QR code: {e}")
        return None

