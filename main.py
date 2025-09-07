import json
import re
from datetime import datetime
from agents import meal_agent, recipe_agent, shopping_agent, price_agent
from database import (
    get_user_and_nutrition,
    save_image_to_gridfs,
    meal_plan_collection,
    ingredient_collection,
    user_collection,
)
from utils import clean_mongo_doc, generate_dish_image_bytes
from upload_images import upload_images
from whatsapp_message import send_meal_notifications
import schedule
import time


def generate_meal_plan_pipeline(user_id):
    """
    Runs the entire pipeline to generate and upsert a meal plan for a given user.
    """
    print(f"\nProcessing user: {user_id}")
    try:
        user, nutrition_report = get_user_and_nutrition(str(user_id))
        user_clean = clean_mongo_doc(user)
        report_clean = clean_mongo_doc(nutrition_report)
        input_data = {"user": user_clean, "nutrition_report": report_clean}

        response = meal_agent.run(json.dumps(input_data, indent=2))
        raw = response.content
        if not raw: raise RuntimeError("Agent returned empty response")

        match = re.search(r"(\{.*\})", raw, re.DOTALL)
        if not match:
            print("Invalid agent output. Expected JSON object.")
            print(raw)
            raise RuntimeError("Failed to find JSON in agent response")

        json_str = match.group(1)
        meal_plan_json = json.loads(json_str)

        image_ids = {}
        for day in ["Day 1", "Day 2"]:
            day_content = meal_plan_json.get(day)
            if not day_content: continue
            for meal_key, meal_val in day_content.items():
                if meal_key.lower() == "summary": continue
                dish_name = meal_val.get("dish_name")
                if dish_name:
                    print(f"Generating image for {dish_name}...")
                    img_bytes = generate_dish_image_bytes(dish_name)
                    if img_bytes:
                        file_id = save_image_to_gridfs(img_bytes, f"{day}_{dish_name.replace(' ', '_')}.png")
                        image_ids[f"{day}_{dish_name.replace(' ', '_')}"] = file_id

        record = {
            "user_id": user_id,
            "meal_plan": meal_plan_json,
            "image_file_ids": image_ids,
            "generated_at": datetime.utcnow(),
        }

        # Using update_one with upsert ensures no duplicates
        meal_plan_collection.update_one({"user_id": user_id}, {"$set": record}, upsert=True)
        print(f"Upserted meal plan with images for user {user_id} in MongoDB.")

        return meal_plan_collection.find_one({"user_id": user_id})

    except Exception as e:
        print(f"Error processing user {user_id}: {e}")
        return None


def generate_recipes_pipeline(meal_plan_doc):
    """
    Generates recipes for the given meal plan.
    """
    if not meal_plan_doc:
        print("❌ No meal plan found in the database.")
        return

    print(f"📄 Found a meal plan for user: {meal_plan_doc.get('user_id')}")
    meal_plan = meal_plan_doc.get("meal_plan", {})

    for day, meals in meal_plan.items():
        if not isinstance(meals, dict): continue
        for meal_name, meal_details in meals.items():
            if not isinstance(meal_details, dict): continue
            dish_name = meal_details.get("dish_name")
            if not dish_name: continue
            if "recipe" in meal_details:
                print(f"⏭️ Skipping {dish_name}, recipe already exists.")
                continue

            print(f"\n🍳 Generating recipe for: {day} - {dish_name}...")
            cleaned_meal_details = clean_mongo_doc({dish_name: meal_details})
            response = recipe_agent.run(json.dumps(cleaned_meal_details, indent=2))

            try:
                raw_content = response.content.strip()
                if raw_content.startswith("```json"): raw_content = raw_content[7:]
                if raw_content.endswith("```"): raw_content = raw_content[:-3]
                recipe_content = json.loads(raw_content.strip())
                meal_details["recipe"] = recipe_content
                print(f"👍 Recipe generated for {dish_name}.")
            except json.JSONDecodeError:
                print(f"⚠️ Could not parse the recipe for {dish_name}. Response was: {raw_content}")
                meal_details["recipe"] = {"error": "Failed to generate recipe."}

    print("\n💾 Saving updated meal plan back to the database...")
    try:
        filter_query = {"_id": meal_plan_doc["_id"]}
        update_operation = {"$set": {"meal_plan": meal_plan}}
        result = meal_plan_collection.update_one(filter_query, update_operation)
        if result.modified_count > 0:
            print("✅ Database updated successfully!")
        else:
            print("ℹ️ No changes were needed in the database.")
    except Exception as e:
        print(f"❌ Failed to update database. Error: {e}")


def generate_shopping_list_pipeline(meal_plan_doc):
    """
    Generates and upserts a shopping list for the given meal plan.
    """
    if not meal_plan_doc:
        print("❌ No meal plan found in the database.")
        return

    user_id = meal_plan_doc.get("user_id")
    meal_plan_id = meal_plan_doc.get("_id")
    print(f"📄 Found meal plan for user: {user_id}")

    meal_plan_data = meal_plan_doc.get("meal_plan", {})
    input_data = clean_mongo_doc(meal_plan_data)

    print("🛒 Running the shopping list generator agent...")
    response = shopping_agent.run(json.dumps(input_data, indent=2))

    shopping_list = None
    try:
        raw_content = response.content.strip()
        if raw_content.startswith("```json"): raw_content = raw_content[7:]
        if raw_content.endswith("```"): raw_content = raw_content[:-3]
        shopping_list = json.loads(raw_content)
        print("\n\n--- 🛍️ Generated Shopping List ---")
        print(json.dumps(shopping_list, indent=2))
    except json.JSONDecodeError:
        print(f"⚠️ Could not parse the agent's response. Raw output:\n{raw_content}")

    if shopping_list:
        print(f"\n💾 Upserting shopping list to 'IngredientsCol' collection...")
        try:
            ingredient_doc = {
                "user_id": user_id,
                "source_meal_plan_id": meal_plan_id,
                "shopping_list": shopping_list,
                "created_at": datetime.utcnow(),
            }
            result = ingredient_collection.update_one(
                {"source_meal_plan_id": meal_plan_id},
                {"$set": ingredient_doc},
                upsert=True
            )
            if result.upserted_id:
                print(f"✅ Successfully inserted new shopping list with document ID: {result.upserted_id}")
            elif result.modified_count > 0:
                print(f"✅ Successfully updated existing shopping list for meal plan ID: {meal_plan_id}")
            else:
                print("ℹ️ No changes were needed for the shopping list in the database.")
        except Exception as e:
            print(f"❌ Failed to save ingredients to the database. Error: {e}")


def price_prediction_pipeline():
    """
    Predicts prices for all shopping lists in the database.
    """
    all_documents_cursor = ingredient_collection.find({})
    print(f"\nFound documents to process. Starting loop...")
    print("-" * 40)

    for document in all_documents_cursor:
        doc_id = document.get("_id")
        print(f"Processing document with ID: {doc_id}")
        if "shopping_list" in document and isinstance(document["shopping_list"], dict):
            ingredients_to_price = document["shopping_list"]
            input_data = clean_mongo_doc(ingredients_to_price)
            response = price_agent.run(json.dumps(input_data, indent=2))
            try:
                cleaned_response = response.content.strip()
                if cleaned_response.startswith("```json"): cleaned_response = cleaned_response[7:]
                if cleaned_response.endswith("```"): cleaned_response = cleaned_response[:-3]
                pricing_details = json.loads(cleaned_response)
                result = ingredient_collection.update_one(
                    {"_id": doc_id}, {"$set": {"pricing_details": pricing_details}}
                )
                if result.modified_count > 0:
                    print(f"✅ Successfully updated document ID: {doc_id}\n")
                else:
                    print(f"⚠️ Document {doc_id} was not updated.\n")
            except json.JSONDecodeError:
                print(f"❌ Error parsing AI response for doc {doc_id}. Skipping.")
                print("   Raw response:", response.content, "\n")
            except Exception as e:
                print(f"❌ An unexpected error occurred while updating doc {doc_id}: {e}\n")
        else:
            print(f"⚠️ Document {doc_id} does not have a 'shopping_list' field. Skipping.\n")
    print("-" * 40)
    print("🎉 All documents processed.")


if __name__ == "__main__":
    # 1. Generate meal plans for all users
    all_users = list(user_collection.find({}))
    for user in all_users:
        meal_plan_doc = generate_meal_plan_pipeline(user["_id"])
        if meal_plan_doc:
            # 2. Generate recipes for the meal plan
            generate_recipes_pipeline(meal_plan_doc)
            # 3. Generate shopping list
            generate_shopping_list_pipeline(meal_plan_doc)

    # 4. Predict prices for all shopping lists
    price_prediction_pipeline()

    # 5. Upload images to Cloudinary
    upload_images()

    # 6. Schedule WhatsApp notifications
    schedule.every().day.at("07:00").do(send_meal_notifications)
    schedule.every().day.at("12:00").do(send_meal_notifications)
    schedule.every().day.at("20:00").do(send_meal_notifications)

    print("✅ WhatsApp notification system started...")

    while True:
        schedule.run_pending()
        time.sleep(30)