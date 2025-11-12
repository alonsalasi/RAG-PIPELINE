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

def detect_diagram_type(image_bytes):
    """Detect if image is a diagram/architecture and what type."""
    try:
        img = Image.open(io.BytesIO(image_bytes))
        img_array = np.array(img.convert('RGB'))
        gray = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)
        
        # Detect edges and shapes
        edges = cv2.Canny(gray, 50, 150)
        edge_density = np.count_nonzero(edges) / edges.size
        
        # Detect rectangles (boxes in diagrams)
        contours, _ = cv2.findContours(edges, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
        rectangles = sum(1 for cnt in contours if len(cv2.approxPolyDP(cnt, 0.04 * cv2.arcLength(cnt, True), True)) == 4)
        
        # Detect lines (connections in diagrams)
        lines = cv2.HoughLinesP(edges, 1, np.pi/180, 50, minLineLength=30, maxLineGap=10)
        line_count = len(lines) if lines is not None else 0
        
        # LOWERED THRESHOLDS for better detection
        # Classify diagram type
        if rectangles > 3 and line_count > 5:  # Was: rectangles > 5 and line_count > 10
            if rectangles > 10:  # Was: > 15
                return "architecture diagram"
            return "system diagram"
        elif edge_density > 0.10 and rectangles > 2:  # Was: > 0.15 and > 3
            return "flowchart"
        elif line_count > 10:  # Was: > 20
            return "network diagram"
        elif rectangles > 2 or line_count > 3:  # NEW: catch any technical diagram
            return "technical diagram"
        
        return None
    except:
        return None

def analyze_image(image_bytes, model_path='/opt/models'):
    """Analyze image for colors, objects, and diagram type."""
    colors = get_dominant_colors(image_bytes)
    diagram_type = detect_diagram_type(image_bytes)
    
    # Only run object detection if NOT a diagram (avoid false positives)
    objects = [] if diagram_type else detect_objects(image_bytes, model_path)
    
    description_parts = []
    if diagram_type:
        description_parts.append(f"Type: {diagram_type}")
        # Add searchable keywords for all diagrams
        if 'architecture' in diagram_type or 'system' in diagram_type or 'diagram' in diagram_type:
            description_parts.append("Keywords: architecture, system design, cloud architecture, infrastructure")
    if objects:
        description_parts.append(f"Objects: {', '.join(objects)}")
    if colors:
        description_parts.append(f"Colors: {', '.join(colors)}")
    
    return {
        'colors': colors,
        'objects': objects,
        'diagram_type': diagram_type,
        'description': '. '.join(description_parts) if description_parts else 'Image content'
    }
