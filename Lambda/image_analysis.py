import cv2
import numpy as np
from PIL import Image
import io
import logging

logger = logging.getLogger(__name__)

# MobileNet SSD class labels
CLASSES = ["background", "aeroplane", "bicycle", "bird", "boat",
           "bottle", "bus", "car", "cat", "chair", "cow", "diningtable",
           "dog", "horse", "motorbike", "person", "pottedplant", "sheep",
           "sofa", "train", "tvmonitor"]

def get_dominant_colors(image_bytes, top_n=3):
    """Extract dominant colors from image using improved color detection."""
    try:
        img = Image.open(io.BytesIO(image_bytes))
        img = img.convert('RGB')
        img_small = img.resize((150, 150))
        pixels = np.array(img_small).reshape(-1, 3)
        
        # Count color occurrences with relaxed thresholds
        color_counts = {}
        for pixel in pixels:
            r, g, b = int(pixel[0]), int(pixel[1]), int(pixel[2])
            color = None
            
            # Relaxed color detection - check red first
            if r > 120 and r > g * 1.5 and r > b * 1.5:  # Red (dominant red channel)
                color = 'red'
            elif r < 80 and g < 80 and b < 80:  # Black
                color = 'black'
            elif r > 200 and g > 200 and b > 200:  # White
                color = 'white'
            elif abs(r - g) < 30 and abs(r - b) < 30 and 100 < r < 200:  # Gray
                color = 'gray'
            elif r > 150 and g > 100 and g < r * 0.8 and b < 80:  # Orange
                color = 'orange'
            elif r > 180 and g > 180 and b < 120:  # Yellow
                color = 'yellow'
            elif g > 120 and g > r * 1.3 and g > b * 1.3:  # Green
                color = 'green'
            elif b > 120 and b > r * 1.3 and b > g * 1.3:  # Blue
                color = 'blue'
            elif r > 100 and g > 60 and g < r * 0.7 and b < 80:  # Brown
                color = 'brown'
            elif abs(r - g) < 40 and abs(r - b) < 40 and 140 < r < 220:  # Silver
                color = 'silver'
            
            if color:
                color_counts[color] = color_counts.get(color, 0) + 1
        
        # Sort by frequency and return top colors
        sorted_colors = sorted(color_counts.items(), key=lambda x: x[1], reverse=True)
        return [color for color, count in sorted_colors[:top_n]]
        
    except Exception as e:
        logger.warning(f"Color detection failed: {e}")
        return []

def detect_objects(image_bytes, model_path='/opt/models', confidence_threshold=0.3):
    """Detect objects in image using MobileNet SSD."""
    try:
        # Load image
        img = Image.open(io.BytesIO(image_bytes))
        img_array = np.array(img.convert('RGB'))
        
        # Load MobileNet SSD model
        prototxt = f"{model_path}/deploy.prototxt"
        model = f"{model_path}/mobilenet_iter_73000.caffemodel"
        net = cv2.dnn.readNetFromCaffe(prototxt, model)
        
        # Prepare image for detection
        (h, w) = img_array.shape[:2]
        blob = cv2.dnn.blobFromImage(cv2.resize(img_array, (300, 300)), 0.007843, (300, 300), 127.5)
        
        # Run detection
        net.setInput(blob)
        detections = net.forward()
        
        # Extract detected objects
        objects_found = []
        for i in range(detections.shape[2]):
            confidence = detections[0, 0, i, 2]
            if confidence > confidence_threshold:
                idx = int(detections[0, 0, i, 1])
                if idx < len(CLASSES):
                    label = CLASSES[idx]
                    if label != "background" and label not in objects_found:
                        objects_found.append(label)
        
        return objects_found
    except Exception as e:
        logger.warning(f"Object detection failed: {e}")
        return []

def detect_diagram_type(image_bytes, ocr_keywords=None):
    """Hybrid detection: rule-based filters + OpenCV analysis.
    
    Args:
        image_bytes: Raw image data
        ocr_keywords: List of OCR keywords found in image (for validation)
    """
    try:
        img = Image.open(io.BytesIO(image_bytes))
        width, height = img.size
        file_size = len(image_bytes)
        img_array = np.array(img.convert('RGB'))
        print(f"[DIAGRAM] Analyzing image: {width}x{height}px, {file_size} bytes")
        logger.info(f"Analyzing image: {width}x{height}px, {file_size} bytes")
        
        # RULE 1: Filter out tiny images (logos/icons) - STRICT
        min_dimension = min(width, height)
        if min_dimension < 300:
            print(f"[DIAGRAM] Too small ({min_dimension}px) - REJECTED (logo/icon)")
            return None
        
        # RULE 1B: Filter out small file sizes (compressed logos/icons)
        if file_size < 50000:  # 50KB minimum for diagrams
            print(f"[DIAGRAM] File too small ({file_size} bytes) - REJECTED (logo/icon)")
            return None
        
        # RULE 2: Filter out banners and letterheads (extreme aspect ratios)
        aspect_ratio = width / height
        if aspect_ratio > 3.5 or aspect_ratio < 0.3:
            print(f"[DIAGRAM] Aspect ratio: {aspect_ratio:.2f} - REJECTED (banner/letterhead)")
            return None
        
        # RULE 3: Filter out square logos (typical logo size)
        if 0.9 < aspect_ratio < 1.1 and min_dimension < 500:
            print(f"[DIAGRAM] Square and small ({width}x{height}) - REJECTED (logo)")
            return None
        
        print(f"[DIAGRAM] Size checks PASSED: {width}x{height}px, {file_size} bytes, ratio={aspect_ratio:.2f}")
        
        # OPENCV: Edge and shape analysis
        gray = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)
        edges = cv2.Canny(gray, 50, 150)
        edge_density = np.count_nonzero(edges) / edges.size
        
        # RULE 3: QR codes have very high edge density
        if edge_density > 0.20:
            print(f"[DIAGRAM] Edge density: {edge_density:.3f} - REJECTED (QR code)")
            return None
        
        # OPENCV: Count shapes (must be done before using contours)
        contours, _ = cv2.findContours(edges, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
        rectangles = sum(1 for cnt in contours if len(cv2.approxPolyDP(cnt, 0.04 * cv2.arcLength(cnt, True), True)) == 4)
        
        # Count small rectangles (QR codes have many tiny squares)
        small_rectangles = sum(1 for cnt in contours if len(cv2.approxPolyDP(cnt, 0.04 * cv2.arcLength(cnt, True), True)) == 4 and cv2.contourArea(cnt) < 500)
        if small_rectangles > 100 and edge_density > 0.10:
            print(f"[DIAGRAM] Many small rectangles ({small_rectangles}) + high edge density - REJECTED (QR code)")
            return None
        
        print(f"[DIAGRAM] Edge density: {edge_density:.3f} - PASSED")
        
        lines = cv2.HoughLinesP(edges, 1, np.pi/180, 50, minLineLength=30, maxLineGap=10)
        line_count = len(lines) if lines is not None else 0
        
        # Calculate complexity score
        total_pixels = width * height
        complexity_score = (rectangles * 10 + line_count * 5) / (total_pixels / 100000)
        
        print(f"[DIAGRAM] Shape analysis: rectangles={rectangles}, lines={line_count}, edge_density={edge_density:.3f}, complexity={complexity_score:.2f}")
        
        # Check if we have ARCHITECTURAL keywords (not just provider names)
        architectural_terms = ['vpc', 'subnet', 'gateway', 'load balancer', 'firewall', 'network', 
                               'architecture', 'landing zone', 'kubernetes', 'container', 'database',
                               'storage', 'compute', 'lambda', 'function', 'api', 'service', 'cluster',
                               'ec2', 's3', 'rds', 'eks', 'ecs', 'fargate', 'cloudfront', 'route53',
                               'gke', 'cloud run', 'cloud sql', 'bigquery', 'cloud storage',
                               'aks', 'blob storage', 'cosmos db', 'app service']
        
        has_architectural_keywords = any(term in ocr_keywords for term in architectural_terms) if ocr_keywords else False
        has_multiple_keywords = len(ocr_keywords) >= 2 if ocr_keywords else False
        
        # Valid if: has architectural terms OR has 2+ tech keywords
        has_tech_keywords = has_architectural_keywords or has_multiple_keywords
        
        if has_tech_keywords:
            print(f"[DIAGRAM] OCR validation: PASSED - Keywords: {ocr_keywords[:5]}")
        elif ocr_keywords:
            print(f"[DIAGRAM] OCR validation: FAILED - Only generic keywords: {ocr_keywords[:3]}")
        
        # IMPROVED DETECTION: More permissive thresholds
        # Architecture diagrams: High rectangle count OR high line count with cloud keywords
        if rectangles > 150 and line_count > 200:
            print("[DIAGRAM] DETECTED: architecture diagram (high complexity)")
            return "architecture diagram"
        elif rectangles > 100 and line_count > 100 and edge_density > 0.03:
            # Require architectural keywords for medium-complexity diagrams
            if has_tech_keywords or rectangles > 250:
                print("[DIAGRAM] DETECTED: architecture diagram")
                return "architecture diagram"
            else:
                print("[DIAGRAM] NOT DETECTED: No architectural keywords (generic diagram/logo)")
                return None
        elif rectangles > 50 and line_count > 300:
            # Line-heavy diagrams need keyword validation
            if has_tech_keywords:
                print("[DIAGRAM] DETECTED: architecture diagram (line-heavy)")
                return "architecture diagram"
            else:
                print("[DIAGRAM] NOT DETECTED: Line-heavy but no tech keywords")
                return None
        elif rectangles > 200 and line_count > 400:
            # Very high shape count = likely architecture diagram
            print("[DIAGRAM] DETECTED: architecture diagram (complex)")
            return "architecture diagram"
        elif rectangles > 6 and line_count > 10 and edge_density > 0.05:
            if rectangles > 12:
                print("[DIAGRAM] DETECTED: system diagram")
                return "system diagram"
            print("[DIAGRAM] DETECTED: technical diagram")
            return "technical diagram"
        elif edge_density > 0.08 and rectangles > 4 and line_count > 6:
            print("[DIAGRAM] DETECTED: flowchart")
            return "flowchart"
        
        print("[DIAGRAM] NOT DETECTED: No diagram pattern matched")
        return None
    except Exception as e:
        print(f"[DIAGRAM] ERROR: {e}")
        logger.error(f"Diagram detection error: {e}")
        return None

def analyze_image(image_bytes, model_path='/opt/models'):
    """Analyze image for colors, objects, and diagram type."""
    colors = get_dominant_colors(image_bytes)
    
    # Extract text FIRST for validation
    ocr_keywords = []
    try:
        import pytesseract
        img = Image.open(io.BytesIO(image_bytes))
        ocr_text = pytesseract.image_to_string(img, lang='eng', config='--psm 6 --oem 1')
        # AWS, GCP, Azure cloud service terms
        tech_terms = [
            # AWS
            'aws', 'vpc', 'ec2', 's3', 'lambda', 'cloudfront', 'route53', 'rds', 'dynamodb',
            'eks', 'ecs', 'fargate', 'api gateway', 'cognito', 'iam', 'kms', 'cloudwatch',
            'transit gateway', 'direct connect', 'vpn', 'nat gateway', 'load balancer',
            'security group', 'nacl', 'waf', 'shield', 'guardduty', 'config', 'cloudtrail',
            'landing zone', 'control tower', 'organizations', 'sso', 'service catalog',
            # GCP
            'gcp', 'google cloud', 'compute engine', 'cloud storage', 'cloud functions',
            'cloud run', 'gke', 'kubernetes engine', 'cloud sql', 'bigquery', 'dataflow',
            'cloud cdn', 'cloud dns', 'cloud armor', 'vpc network', 'cloud nat',
            'cloud load balancing', 'cloud iam', 'cloud kms', 'cloud monitoring',
            'cloud logging', 'security command center', 'organization policy',
            # Azure
            'azure', 'virtual machine', 'blob storage', 'azure functions', 'app service',
            'aks', 'kubernetes service', 'sql database', 'cosmos db', 'event hub',
            'azure cdn', 'traffic manager', 'application gateway', 'virtual network',
            'vpn gateway', 'expressroute', 'load balancer', 'azure ad', 'key vault',
            'azure monitor', 'log analytics', 'security center', 'azure policy',
            'management groups', 'landing zones'
        ]
        ocr_lower = ocr_text.lower()
        for term in tech_terms:
            if term in ocr_lower:
                ocr_keywords.append(term)
    except:
        pass
    
    # NOW detect diagram type with OCR validation
    diagram_type = detect_diagram_type(image_bytes, ocr_keywords)
    
    # Only run object detection if NOT a diagram (avoid false positives)
    objects = [] if diagram_type else detect_objects(image_bytes, model_path)
    
    # FILTER: If objects detected but no diagram, check if it's a logo/banner
    if objects and not diagram_type:
        img = Image.open(io.BytesIO(image_bytes))
        width, height = img.size
        if min(width, height) < 300 or (width / height > 3.5 or height / width > 3.5):
            description_parts = []
            if objects:
                description_parts.append(f"Objects: {', '.join(objects)}")
            if colors:
                description_parts.append(f"Colors: {', '.join(colors)}")
            result = {
                'colors': colors,
                'objects': objects,
                'diagram_type': None,
                'ocr_keywords': ocr_keywords,
                'description': '. '.join(description_parts) if description_parts else 'Image content',
                'is_logo_or_banner': True
            }
            return dict(result)
    
    description_parts = []
    if diagram_type:
        description_parts.append(f"Type: {diagram_type}")
        if 'architecture' in diagram_type:
            description_parts.append("Keywords: cloud architecture, AWS architecture, GCP architecture, Azure architecture, system design, infrastructure diagram, technical architecture, solution architecture, multi-cloud")
        elif 'system' in diagram_type:
            description_parts.append("Keywords: system diagram, architecture, infrastructure, technical design, cloud infrastructure")
        elif 'diagram' in diagram_type or 'flowchart' in diagram_type:
            description_parts.append("Keywords: technical diagram, architecture diagram, cloud diagram, flowchart")
    if ocr_keywords:
        description_parts.append(f"Contains: {', '.join(ocr_keywords[:10])}")
    if objects:
        description_parts.append(f"Objects: {', '.join(objects)}")
    if colors:
        description_parts.append(f"Colors: {', '.join(colors)}")
    
    result = {
        'colors': colors,
        'objects': objects,
        'diagram_type': diagram_type,
        'ocr_keywords': ocr_keywords,
        'description': '. '.join(description_parts) if description_parts else 'Image content'
    }
    return dict(result)
