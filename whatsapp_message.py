import os
import schedule
import time
from datetime import datetime
from pymongo import MongoClient
from twilio.rest import Client
from agents import whatsapp_agent
from dotenv import load_dotenv

load_dotenv()

# --- CONFIG ---
MONGO_URI = os.getenv("MONGO_URI")
DB_NAME = os.getenv("MONGO_DB", "UserDBB")
TWILIO_SID = os.getenv("TWILIO_SID")
TWILIO_AUTH = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_WHATSAPP = os.getenv("TWILIO_WHATSAPP_NUMBER")

# --- DB CONNECTION ---
client = MongoClient(MONGO_URI)
db = client[DB_NAME]
user_collection = db["UserCo"]
meal_plan_collection = db["Weekly_Meal_Plans"]

# --- HELPER FUNCTIONS (can be imported) ---
def generate_tempting_message(user_name, meal_name, dish):
    prompt = f"Write a very short, exciting, and tempting (<25 words) WhatsApp notification for {user_name} about their upcoming {meal_name}, which is {dish}. Make them look forward to eating it."
    response = whatsapp_agent.run(prompt)
    return response.content if hasattr(response, "content") else str(response)

def send_whatsapp_message(user, meal_name, dish, image_url):
    client_twilio = Client(TWILIO_SID, TWILIO_AUTH)
    user_name = user.get("name", "Friend")
    user_phone = user.get("phone")
    if not user_phone: return

    if not user_phone.startswith("+91"):
        user_phone = f"+91{user_phone.lstrip('0')}"

    tempting_text = generate_tempting_message(user_name, meal_name, dish)

    body = f"Hey {user_name}! 👋\n\nYour *{meal_name}* is ready: *{dish}*.\n\n_{tempting_text}_"

    try:
        msg = client_twilio.messages.create(
            from_=TWILIO_WHATSAPP,
            body=body,
            to=f"whatsapp:{user_phone}",
            media_url=[image_url] if image_url else None
        )
        print(f"✅ Sent {meal_name} to {user_name} ({user_phone})")
        return f"Message for {meal_name} sent successfully to {user_name}!"
    except Exception as e:
        print(f"❌ Failed to send to {user_phone}: {e}")
        return f"Failed to send message for {meal_name}. Error: {e}"

# --- MAIN SCHEDULER (only runs if script is executed directly) ---
if __name__ == "__main__":
    def scheduled_job():
        # This function can be expanded with logic to determine the current day/meal
        print("Running scheduled job... (Logic to send notifications would go here)")

    schedule.every().day.at("07:00").do(scheduled_job)
    schedule.every().day.at("12:00").do(scheduled_job)
    schedule.every().day.at("20:00").do(scheduled_job)

    print("✅ WhatsApp notification scheduler started...")
    while True:
        schedule.run_pending()
        time.sleep(60)