from bson import ObjectId
from google import genai
from PIL import Image
from io import BytesIO
import os

# Replace with your actual API key
client = genai.Client(api_key="AIzaSyC3181Om2bXkBrHNVptE6UIGR_eO0r_4jE")

def clean_mongo_doc(doc):
    """Recursively convert MongoDB ObjectId to string for JSON serialization."""
    if isinstance(doc, dict):
        return {k: clean_mongo_doc(v) for k, v in doc.items()}
    elif isinstance(doc, list):
        return [clean_mongo_doc(i) for i in doc]
    elif isinstance(doc, ObjectId):
        return str(doc)
    else:
        return doc


def generate_dish_image_bytes(dish_name):
    """Generates an image for a given dish name using Google GenAI."""
    prompt = f"Create a picture of {dish_name}"
    response = client.models.generate_content(
    model="gemini-2.5-flash-image-preview",
    contents=[prompt],
    )
    for part in response.candidates[0].content.parts:
        if part.inline_data is not None:
            return part.inline_data.data  # raw bytes
    return None