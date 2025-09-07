import os
from pymongo import MongoClient
import gridfs
import cloudinary
import cloudinary.uploader
from dotenv import load_dotenv

load_dotenv()

# --- CONFIG ---
MONGO_URI = os.getenv("MONGO_URI")
DB_NAME = os.getenv("MONGO_DB", "UserDBB")
cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET"),
)
client = MongoClient(MONGO_URI)
db = client[DB_NAME]
fs = gridfs.GridFS(db)

def upload_images_and_get_urls(plan_doc):
    """
    Uploads images from GridFS to Cloudinary for a given meal plan
    and returns a dictionary of public URLs.
    """
    updated_urls = plan_doc.get("image_urls", {})
    file_ids = plan_doc.get("image_file_ids", {})
    
    # --- THIS IS THE FIX ---
    # Use the user_id as a fallback if the database _id doesn't exist yet
    plan_id = plan_doc.get("_id") or plan_doc.get("user_id")
    # --- END OF FIX ---

    for dish_key, oid in file_ids.items():
        if dish_key in updated_urls:
            continue
        try:
            file_obj = fs.get(oid)
            print(f"⬆️ Uploading {dish_key}...")
            upload_result = cloudinary.uploader.upload(
                file_obj,
                public_id=f"meal_plans/{plan_id}/{dish_key}",
                overwrite=True,
                resource_type="image"
            )
            updated_urls[dish_key] = upload_result["secure_url"]
        except Exception as e:
            print(f"❌ Failed to upload {dish_key}: {e}")
    
    return updated_urls