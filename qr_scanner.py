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
    Optimized for iPhone cameras (works well from distance, handles close-up blur)
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
        
        # Store original for fallback
        original_array = image_array.copy() if CV2_AVAILABLE else image_array
        
        # Multiple upscale strategies for distant QR codes (iPhone camera issue)
        upscaled_variants = []
        if len(image_array.shape) >= 2 and CV2_AVAILABLE:
            try:
                h, w = image_array.shape[:2]
                if h > 0 and w > 0:
                    # Strategy 1: Moderate upscale (4x) - good balance
                    scale1 = 4
                    upscaled1 = cv2.resize(image_array, (w * scale1, h * scale1), 
                                          interpolation=cv2.INTER_CUBIC)
                    upscaled_variants.append(('moderate', upscaled1))
                    
                    # Strategy 2: Large upscale (5x) - for very distant QR
                    scale2 = 5
                    upscaled2 = cv2.resize(image_array, (w * scale2, h * scale2), 
                                          interpolation=cv2.INTER_LANCZOS4)
                    upscaled_variants.append(('large', upscaled2))
                    
                    # Strategy 3: Extreme upscale (6x) - last resort
                    if h * 6 < 5000 and w * 6 < 5000:  # Limit to avoid memory issues
                        scale3 = 6
                        upscaled3 = cv2.resize(image_array, (w * scale3, h * scale3), 
                                              interpolation=cv2.INTER_LANCZOS4)
                        upscaled_variants.append(('extreme', upscaled3))
            except Exception as e:
                print(f"Upscale error: {e}")
        
        # Use original if no upscaling worked
        if not upscaled_variants:
            upscaled_variants = [('original', image_array)]
        
        # Try each upscaled variant with multiple preprocessing methods
        for variant_name, variant_img in upscaled_variants:
            # Method 1: Strong sharpening
            try:
                sharp_variant = sharpen_image_strong(variant_img)
            except:
                sharp_variant = variant_img
            
            # Method 2: CLAHE (Contrast Limited Adaptive Histogram Equalization)
            try:
                clahe_variant = apply_clahe(variant_img)
            except:
                clahe_variant = variant_img
            
            # Method 3: Bilateral filter (denoise while preserving edges)
            try:
                bilateral_variant = apply_bilateral_filter(variant_img)
            except:
                bilateral_variant = variant_img
            
            # Method 4: Combined preprocessing
            try:
                combined_variant = apply_combined_preprocessing(variant_img)
            except:
                combined_variant = variant_img
            
            # Try OpenCV detection on all variants
            variants_to_try = [
                ('original', variant_img),
                ('sharp', sharp_variant),
                ('clahe', clahe_variant),
                ('bilateral', bilateral_variant),
                ('combined', combined_variant)
            ]
            
            for proc_name, proc_img in variants_to_try:
                result = try_opencv_decode(proc_img)
                if result:
                    print(f"QR decoded: {variant_name} upscale + {proc_name} preprocessing")
                    return result
                
                # Also try pyzbar on processed image
                if PYZBAR_AVAILABLE:
                    try:
                        decoded_objects = pyzbar_decode(proc_img)
                        if decoded_objects:
                            result = decoded_objects[0].data.decode('utf-8')
                            print(f"QR decoded (pyzbar): {variant_name} upscale + {proc_name} preprocessing")
                            return result
                    except:
                        pass
        
        # Fallback: Try original image with all methods
        return try_all_methods_on_image(original_array)

    except Exception as e:
        print(f"Error decoding QR code: {e}")
        import traceback
        traceback.print_exc()
        return None


def try_opencv_decode(image_array):
    """Try OpenCV QRCodeDetector on image"""
    if not CV2_AVAILABLE:
        return None
    try:
        # Convert to grayscale if needed
        if len(image_array.shape) == 3:
            gray = cv2.cvtColor(image_array, cv2.COLOR_RGB2GRAY)
        else:
            gray = image_array
        
        detector = cv2.QRCodeDetector()
        
        # Try multi decode first
        retval, decoded_info, points, straight_qrcode = detector.detectAndDecodeMulti(gray)
        if retval and decoded_info:
            result = decoded_info[0] if isinstance(decoded_info, (list, tuple)) else decoded_info
            if result:
                return result
        
        # Try single decode
        data, bbox, rectified = detector.detectAndDecode(gray)
        if data:
            return data
        
        return None
    except Exception as e:
        return None


def try_all_methods_on_image(image_array):
    """Try all decoding methods on original image as fallback"""
    if not CV2_AVAILABLE:
        return None
    
    # Try OpenCV first
    result = try_opencv_decode(image_array)
    if result:
        return result
    
    # Try with various preprocessing
    methods = [
        lambda img: decode_grayscale_opencv(img),
        lambda img: decode_resized_opencv(img),
        lambda img: decode_binarized_opencv(img),
        lambda img: try_opencv_decode(sharpen_image_strong(img)),
        lambda img: try_opencv_decode(apply_clahe(img)),
        lambda img: try_opencv_decode(apply_bilateral_filter(img)),
    ]
    
    for i, method in enumerate(methods):
        try:
            result = method(image_array)
            if result:
                print(f"QR decoded using fallback method {i+1}")
                return result
        except Exception as e:
            continue
    
    # Try pyzbar as last resort
    if PYZBAR_AVAILABLE:
        try:
            decoded_objects = pyzbar_decode(image_array)
            if decoded_objects:
                return decoded_objects[0].data.decode('utf-8')
        except:
            pass
    
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
    """Decode QR with OpenCV after resizing (optimized for distant QR codes)"""
    if not CV2_AVAILABLE:
        return None
    try:
        if len(image_array.shape) == 3:
            height, width = image_array.shape[:2]
        else:
            height, width = image_array.shape
        
        # Try multiple scale factors for better detection
        scales = [4, 5, 6]  # Increased from 3x to handle distant QR better
        
        for scale in scales:
            try:
                if height * scale > 5000 or width * scale > 5000:
                    continue  # Skip if too large
                
                resized = cv2.resize(image_array, (width * scale, height * scale), 
                                    interpolation=cv2.INTER_LANCZOS4)
                
                detector = cv2.QRCodeDetector()
                data, bbox, rectified = detector.detectAndDecode(resized)
                if data:
                    return data
            except:
                continue
        
        return None
    except:
        return None


def decode_binarized_opencv(image_array):
    """Decode QR with OpenCV after binarization (multiple threshold methods)"""
    if not CV2_AVAILABLE:
        return None
    try:
        if len(image_array.shape) == 3:
            gray = cv2.cvtColor(image_array, cv2.COLOR_RGB2GRAY)
        else:
            gray = image_array
        
        detector = cv2.QRCodeDetector()
        
        # Method 1: Simple binary threshold (multiple thresholds)
        thresholds = [127, 100, 150, 80, 180]
        for thresh_val in thresholds:
            try:
                _, binary = cv2.threshold(gray, thresh_val, 255, cv2.THRESH_BINARY)
                data, bbox, rectified = detector.detectAndDecode(binary)
                if data:
                    return data
            except:
                continue
        
        # Method 2: Otsu's threshold (automatic)
        try:
            _, otsu = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            data, bbox, rectified = detector.detectAndDecode(otsu)
            if data:
                return data
        except:
            pass
        
        # Method 3: Adaptive threshold (multiple block sizes)
        block_sizes = [11, 15, 21, 25]
        for block_size in block_sizes:
            try:
                adaptive = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
                                                 cv2.THRESH_BINARY, block_size, 2)
                data, bbox, rectified = detector.detectAndDecode(adaptive)
                if data:
                    return data
            except:
                continue
        
        # Method 4: Adaptive mean threshold
        for block_size in block_sizes:
            try:
                adaptive_mean = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_MEAN_C, 
                                                      cv2.THRESH_BINARY, block_size, 2)
                data, bbox, rectified = detector.detectAndDecode(adaptive_mean)
                if data:
                    return data
            except:
                continue
        
        return None
    except:
        return None


def sharpen_image_opencv(img):
    """Unsharp mask to enhance edges for QR detection."""
    if not CV2_AVAILABLE:
        return img
    try:
        # Work in RGB/gray as-is; use mild blur and strong sharpening
        blur = cv2.GaussianBlur(img, (0, 0), sigmaX=1.2)
        sharp = cv2.addWeighted(img, 1.8, blur, -0.8, 0)
        sharp = np.clip(sharp, 0, 255).astype(np.uint8)
        return sharp
    except Exception:
        return img


def sharpen_image_strong(img):
    """Strong sharpening for distant/blurry QR codes (iPhone camera optimization)"""
    if not CV2_AVAILABLE:
        return img
    try:
        # Convert to grayscale if needed for processing
        is_color = len(img.shape) == 3
        if is_color:
            gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
        else:
            gray = img
        
        # Strong unsharp mask - more aggressive for distant QR
        blur = cv2.GaussianBlur(gray, (0, 0), sigmaX=2.0)
        sharp = cv2.addWeighted(gray, 2.5, blur, -1.5, 0)
        sharp = np.clip(sharp, 0, 255).astype(np.uint8)
        
        # Apply Laplacian sharpening for edge enhancement
        laplacian = cv2.Laplacian(sharp, cv2.CV_64F)
        laplacian_abs = np.absolute(laplacian)
        laplacian_8u = np.uint8(laplacian_abs)
        enhanced = cv2.addWeighted(sharp, 1.0, laplacian_8u, 0.3, 0)
        enhanced = np.clip(enhanced, 0, 255).astype(np.uint8)
        
        # Convert back to color if original was color
        if is_color:
            enhanced = cv2.cvtColor(enhanced, cv2.COLOR_GRAY2RGB)
        
        return enhanced
    except Exception:
        return img


def apply_clahe(img):
    """Apply CLAHE (Contrast Limited Adaptive Histogram Equalization) for better contrast"""
    if not CV2_AVAILABLE:
        return img
    try:
        # Convert to grayscale if needed
        is_color = len(img.shape) == 3
        if is_color:
            gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
        else:
            gray = img
        
        # Create CLAHE object
        clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
        enhanced = clahe.apply(gray)
        
        # Convert back to color if original was color
        if is_color:
            enhanced = cv2.cvtColor(enhanced, cv2.COLOR_GRAY2RGB)
        
        return enhanced
    except Exception:
        return img


def apply_bilateral_filter(img):
    """Apply bilateral filter to reduce noise while preserving edges"""
    if not CV2_AVAILABLE:
        return img
    try:
        # Bilateral filter works on color images
        if len(img.shape) == 3:
            filtered = cv2.bilateralFilter(img, d=9, sigmaColor=75, sigmaSpace=75)
        else:
            # Convert grayscale to 3-channel for bilateral filter
            gray_3ch = cv2.cvtColor(img, cv2.COLOR_GRAY2RGB)
            filtered = cv2.bilateralFilter(gray_3ch, d=9, sigmaColor=75, sigmaSpace=75)
            # Convert back to grayscale
            filtered = cv2.cvtColor(filtered, cv2.COLOR_RGB2GRAY)
        return filtered
    except Exception:
        return img


def apply_combined_preprocessing(img):
    """Apply multiple preprocessing techniques in sequence for maximum enhancement"""
    if not CV2_AVAILABLE:
        return img
    try:
        # Step 1: Bilateral filter to reduce noise
        denoised = apply_bilateral_filter(img)
        
        # Step 2: CLAHE for contrast
        contrasted = apply_clahe(denoised)
        
        # Step 3: Strong sharpening
        sharpened = sharpen_image_strong(contrasted)
        
        return sharpened
    except Exception:
        return img


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

