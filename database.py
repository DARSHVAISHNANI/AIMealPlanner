from pymongo import MongoClient
from bson import ObjectId
import gridfs
import os
from dotenv import load_dotenv

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI")
DB_NAME = os.getenv("MONGO_DB", "UserDB")

client = MongoClient(MONGO_URI)
db = client[DB_NAME]

user_collection = db["UserCo"]
nutrition_collection = db["Nutrition_Reports"]
meal_plan_collection = db["Weekly_Meal_Plans"]
ingredient_collection = db["IngredientsCol"]
fs = gridfs.GridFS(db)


def get_user_and_nutrition(user_id: str):
    """Fetches user and nutrition report from the database."""
    user = user_collection.find_one({"_id": ObjectId(user_id)})
    nutrition = nutrition_collection.find_one({"user_id": ObjectId(user_id)})
    if not user:
        raise ValueError("User not found in UserCo")
    if not nutrition:
        raise ValueError("Nutrition report not found in Nutrition_Reports")
    return user, nutrition["report"]


def save_image_to_gridfs(image_bytes, filename):
    """Saves an image to GridFS and returns the file ID."""
    file_id = fs.put(image_bytes, filename=filename)
    return file_id


def get_ingredients_collection():
    """Returns the ingredients collection object."""
    return ingredient_collection