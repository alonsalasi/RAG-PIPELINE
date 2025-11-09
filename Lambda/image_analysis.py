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

def analyze_image(image_bytes, model_path='/opt/models'):
    """Analyze image for colors and objects."""
    colors = get_dominant_colors(image_bytes)
    objects = detect_objects(image_bytes, model_path)
    
    description_parts = []
    if objects:
        description_parts.append(f"Objects: {', '.join(objects)}")
    if colors:
        description_parts.append(f"Colors: {', '.join(colors)}")
    
    return {
        'colors': colors,
        'objects': objects,
        'description': '. '.join(description_parts) if description_parts else 'Image content'
    }
