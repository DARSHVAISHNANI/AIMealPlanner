import streamlit as st
import pandas as pd # Import pandas for the new UI
from pymongo import MongoClient
import os
import re
import json
from dotenv import load_dotenv
from PIL import Image
from io import BytesIO

# --- Agent and DB Imports ---
from agents import nutrition_agent, meal_agent, recipe_agent, shopping_agent, price_agent
from datetime import datetime, timezone
from database import (
    user_collection,
    nutrition_collection,
    meal_plan_collection,
    ingredient_collection,
    get_user_and_nutrition,
    save_image_to_gridfs,
    fs,
)
from utils import clean_mongo_doc, generate_dish_image_bytes
from upload_images import upload_images_and_get_urls # New import
from whatsapp_message import send_whatsapp_message # New import
from charts import generate_and_save_all_charts # New Import
import streamlit.components.v1 as components

load_dotenv()

st.set_page_config(layout="wide")
st.title("🍽️ AI Personalized Meal Planner")

# --- CSS STYLES ---
# --- CSS STYLES ---
st.markdown(
    """
    <style>
        div[data-testid="stImage"] { background: none !important; padding: 0 !important; margin: 0 !important; }
        div[data-testid="stImage"] img { border-radius: 12px; margin-bottom: 0 !important; }
        .st-emotion-cache-1r6slb0 { gap: 0rem !important; }
        /* --- FIX IS HERE --- */
        .dish-name { 
            font-weight: 800; 
            font-size: 1.4em; 
            margin-top: 8px; 
            margin-bottom: 6px; 
            text-align: center; 
            color: #FFFFFF; 
            min-height: 3.5em; /* Ensures space for up to 2 lines of text */
            display: flex;
            align-items: center;
            justify-content: center;
        }
        .metrics-row { display: flex; justify-content: center; gap: 20px; font-size: 1.2em; margin-bottom: 6px; font-weight: 600; color: #E0E0E0; }
        .vitamins { text-align: center; font-size: 1em; color: #E0E0E0; margin-bottom: 10px; }
        .daily-summary { text-align: center; font-size: 1.3em; color: #155724; background: #d4edda; padding: 15px; border-radius: 10px; margin-top: 25px; margin-bottom: 25px; box-shadow: 0px 2px 6px rgba(0,0,0,0.15); }
        .daily-summary .summary-label { font-weight: 700; font-size: 1.2em; color: #0c3c1e; }
        .daily-summary .summary-text { font-weight: 500; display: inline-block; margin-top: 8px; }
        .recipe-card { border: 1px solid #ddd; border-radius: 10px; padding: 15px; margin-bottom: 15px; }
        .price-col { text-align: right; font-weight: bold; }
    </style>
    """,
    unsafe_allow_html=True,
)

# --- Create Tabs ---
tabs = ["Profile", "Meal Plan", "Recipes", "Shopping List", "WhatsApp", "View Data", "Dashboard"]
tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs(tabs)

# --- TAB 1: User Profile & Nutrition Report ---
with tab1:
    st.header("Create or Update Your Nutrition Profile")
    phone_input = st.text_input("Enter your phone number to continue")
    if phone_input:
        existing_user = user_collection.find_one({"phone": phone_input})
        if existing_user: st.success(f"Welcome back {existing_user.get('name', '')}! Your details are pre-filled below.")
        else: st.info("New user detected. Please fill in your details.")
        with st.form("user_form"):
            name = st.text_input("Name", value=existing_user.get("name", "") if existing_user else "")
            goal = st.text_input("Goal", value=existing_user.get("goal", "") if existing_user else "")
            meals_per_day = st.slider("Meals per day", 2, 6, existing_user.get("meals_per_day", 3) if existing_user else 3)
            diet = st.radio("Diet preference", ["Vegetarian", "Vegan", "Non-veg"], index=["Vegetarian", "Vegan", "Non-veg"].index(existing_user.get("diet", "Vegetarian")) if existing_user else 0)
            allergies = st.text_area("Allergies / dislikes", value=existing_user.get("allergies", "") if existing_user else "")
            likes = st.text_area("Foods you like", value=existing_user.get("likes", "") if existing_user else "")
            cuisine = st.text_input("Preferred cuisine", value=existing_user.get("cuisine", "") if existing_user else "")
            budget = st.number_input("Budget per week (INR)", 500, 20000, existing_user.get("budget", 1000) if existing_user else 1000, 100)
            age = st.number_input("Age", 10, 100, existing_user.get("age", 25) if existing_user else 25)
            weight = st.number_input("Weight (kg)", 30.0, 200.0, float(existing_user.get("weight", 70.0)) if existing_user else 70.0)
            height = st.number_input("Height (cm)", 100.0, 250.0, float(existing_user.get("height", 170.0)) if existing_user else 170.0)
            gender = st.radio("Gender", ["Male", "Female"], index=["Male", "Female"].index(existing_user.get("gender", "Male")) if existing_user else 0)
            activity = st.selectbox("Activity Level", ["Sedentary", "Lightly active", "Moderately active", "Very active", "Extra active"], index=["Sedentary", "Lightly active", "Moderately active", "Very active", "Extra active"].index(existing_user.get("activity", "Moderately active")) if existing_user else 2)
            submit_nutrition = st.form_submit_button("Save and Generate Nutrition Report")
        if submit_nutrition:
            with st.spinner("Saving user data and running Nutrition Agent..."):
                user_data = { "name": name, "phone": phone_input, "goal": goal, "meals_per_day": meals_per_day, "diet": diet, "allergies": allergies, "likes": likes, "cuisine": cuisine, "budget": budget, "age": age, "weight": weight, "height": height, "gender": gender, "activity": activity }
                if existing_user: user_collection.update_one({"_id": existing_user["_id"]}, {"$set": user_data}); user_id = existing_user["_id"]
                else: result = user_collection.insert_one(user_data); user_id = result.inserted_id
                st.success("✅ User profile saved!")
                response = nutrition_agent.run(str(user_data))
                try:
                    match = re.search(r'(\{.*\})', response.content, re.DOTALL); report_json = json.loads(match.group(1))
                    nutrition_collection.update_one({"user_id": user_id}, {"$set": {"report": report_json, "generated_at": datetime.now(timezone.utc)}}, upsert=True)
                    st.success("✅ Nutrition report generated and saved!"); st.session_state.update(nutrition_report_generated=True, meal_plan_generated=False, recipes_generated=False, shopping_list_generated=False)
                    # --- UI ENHANCEMENT: Display the formatted summary ---
                    st.subheader("Your Personalized Nutrition Summary")

                    # Safely extract all the data from the JSON report
                    summary_data = report_json.get("nutrition_summary", {})
                    calories = summary_data.get("calories", "N/A")
                    protein = summary_data.get("protein_g", "N/A")
                    fat = summary_data.get("fat_g", "N/A")

                    preferences_data = report_json.get("preferences", {})
                    budget = preferences_data.get("budget_weekly_inr", "N/A")

                    meal_targets_data = report_json.get("meal_targets", {})
                    meals_per_day = meal_targets_data.get("meals_per_day", "N/A")

                    micronutrients_data = report_json.get("micronutrients", [])
                    vitamins = ", ".join([nutrient.get("name") for nutrient in micronutrients_data if nutrient.get("name")])
                    if not vitamins:
                        vitamins = "As per standard dietary guidelines"

                    # Use columns and metrics for a clean layout
                    col1, col2 = st.columns(2)
                    with col1:
                        st.metric(label="Calories Required", value=f"{calories} kcal / day")
                        st.metric(label="Protein Required", value=f"{protein} g / day")
                        st.metric(label="Meals per Day", value=meals_per_day)

                    with col2:
                        st.metric(label="Fat Required", value=f"{fat} g / day")
                        st.metric(label="Weekly Budget", value=f"₹ {budget}")

                    st.markdown("---")
                    st.markdown(f"**Key Vitamins & Minerals Focus:** {vitamins}")
                    
                    human_summary = report_json.get("human_summary", "No summary was generated by the agent.")
                    st.info(f"**Agent's Summary:** {human_summary}")
                except Exception as e: st.error(f"An error occurred: {e}"); st.code(response.content)


# --- TAB 2: Meal Plan ---
with tab2:
    st.header("Generate Your Meal Plan")
    if not phone_input or not st.session_state.get('nutrition_report_generated'):
        st.warning("Please complete your Nutrition Profile in Tab 1 first.")
    else:
        if st.button("✨ Generate Meal Plan Now"):
            with st.spinner("🧑‍🍳 Our AI chef is creating your meal plan..."):
                try:
                    user = user_collection.find_one({"phone": phone_input})
                    user_id = user["_id"]
                    _, nutrition_report = get_user_and_nutrition(str(user_id))
                    input_data = {"user": clean_mongo_doc(user), "nutrition_report": clean_mongo_doc(nutrition_report)}
                    response = meal_agent.run(json.dumps(input_data, indent=2))
                    match = re.search(r'(\{.*\})', response.content, re.DOTALL)
                    meal_plan_json = json.loads(match.group(1))
                    
                    image_ids = {}
                    for day, meals in meal_plan_json.items():
                        if isinstance(meals, dict):
                            for meal_details in meals.values():
                                if isinstance(meal_details, dict) and "dish_name" in meal_details:
                                    dish_name = meal_details["dish_name"]
                                    st.write(f"Generating image for {dish_name}...")
                                    img_bytes = generate_dish_image_bytes(dish_name)
                                    if img_bytes:
                                        filename = f"{day}_{dish_name.replace(' ', '_')}.png"
                                        file_id = save_image_to_gridfs(img_bytes, filename)
                                        image_ids[filename[:-4]] = file_id
                                        
                    record = {
                        "user_id": user_id,
                        "meal_plan": meal_plan_json,
                        "image_file_ids": image_ids,
                        "generated_at": datetime.now(timezone.utc)
                    }
                    
                    st.write("Uploading images for sharing...")
                    image_urls = upload_images_and_get_urls(record)
                    record["image_urls"] = image_urls
                    
                    meal_plan_collection.update_one({"user_id": user_id}, {"$set": record}, upsert=True)
                    st.success("🎉 Your meal plan has been generated and saved!")
                    st.session_state.update(meal_plan_generated=True, recipes_generated=False, shopping_list_generated=False)
                    
                except Exception as e:
                    st.error(f"An error occurred: {e}")

        if st.session_state.get('meal_plan_generated'):
            user = user_collection.find_one({"phone": phone_input})
            meal_plan_doc = meal_plan_collection.find_one({"user_id": user["_id"]})
            if meal_plan_doc:
                st.markdown(f"## Meal Plan for **{user.get('name', 'User')}**")
                meal_plan_json = meal_plan_doc.get("meal_plan", {})
                image_ids = meal_plan_doc.get("image_file_ids", {})
                
                for day in sorted(meal_plan_json.keys()):
                    day_data = meal_plan_json[day]
                    st.markdown(f"---\n\n### 📅 {day.replace('Day', 'Day ')}")
                    meals = {k: v for k, v in day_data.items() if k.lower() != "summary"}
                    cols = st.columns(len(meals) if meals else 1)
                    
                    i = 0 # Initialize a counter for columns
                    for meal_key, meal_val in day_data.items():
                        # --- FIX IS HERE ---
                        # Check if meal_val is a dictionary before processing
                        if isinstance(meal_val, dict):
                            with cols[i]:
                                dish = meal_val.get("dish_name", "N/A")
                                # --- FIX IS HERE ---
                                # Map generic meal keys to proper names
                                meal_name_mapping = {
                                    "Breakfast": "Breakfast",
                                    "Lunch": "Lunch",
                                    "Dinner": "Dinner",
                                    "Snack 1": "Snack 1",
                                    "Snack 2": "Snack 2",
                                    # Add fallbacks for the agent's current output
                                    "Meal 1": "Breakfast",
                                    "Meal 2": "Lunch",
                                    "Meal 3": "Dinner"
                                }
                                display_meal_name = meal_name_mapping.get(meal_key, meal_key)

                                st.markdown(f"<div class='dish-name'>{display_meal_name}: {dish}</div>", unsafe_allow_html=True)
                                # st.markdown(f"<div class='dish-name'>{meal_key}: {dish}</div>", unsafe_allow_html=True)
                                
                                image_key = f"{day}_{dish.replace(' ', '_')}"
                                fid = image_ids.get(image_key)
                                if fid:
                                    img_bytes = fs.get(fid).read()
                                    st.image(Image.open(BytesIO(img_bytes)), use_container_width=True)
                                    
                                st.markdown(f"<div class='metrics-row'><div>Calories: {meal_val.get('calories_percentage', 'N/A')}%</div><div>Protein: {meal_val.get('protein_percentage', 'N/A')}%</div></div>", unsafe_allow_html=True)
                                st.markdown(f"<div class='vitamins'>Vitamins: {meal_val.get('vitamin_mineral_highlights', '')}</div>", unsafe_allow_html=True)
                                i += 1 # Increment counter only when a meal is processed
                            
                    if "summary" in day_data:
                        st.markdown(f"<div class='daily-summary'><span class='summary-label'>📌 Daily Summary:</span><br><span class='summary-text'>{day_data['summary']}</span></div>", unsafe_allow_html=True)

# --- TAB 3: Recipes ---
with tab3:
    st.header("Get Your Meal Recipes")
    if not phone_input or not st.session_state.get('meal_plan_generated'): st.warning("Please generate a Meal Plan in Tab 2 to get recipes.")
    else:
        if st.button("🍳 Generate All Recipes"):
            with st.spinner("📜 Our AI chef is writing down your recipes..."):
                try:
                    user = user_collection.find_one({"phone": phone_input}); user_id = user["_id"]
                    meal_plan_doc = meal_plan_collection.find_one({"user_id": user_id}); meal_plan = meal_plan_doc.get("meal_plan", {})
                    for day, meals in meal_plan.items():
                        if isinstance(meals, dict):
                            for meal_key, meal_details in meals.items():
                                if isinstance(meal_details, dict) and "dish_name" in meal_details and "recipe" not in meal_details:
                                    dish_name = meal_details["dish_name"]; st.write(f"Generating recipe for {dish_name}...")
                                    response = recipe_agent.run(json.dumps({dish_name: meal_details}, indent=2))
                                    match = re.search(r'(\{.*\})', response.content.strip(), re.DOTALL); meal_plan[day][meal_key]["recipe"] = json.loads(match.group(1))
                    meal_plan_collection.update_one({"_id": meal_plan_doc["_id"]}, {"$set": {"meal_plan": meal_plan}})
                    st.success("✅ All recipes have been generated and saved!"); st.session_state['recipes_generated'] = True
                except Exception as e: st.error(f"An error occurred: {e}")
        if st.session_state.get('recipes_generated'):
            user = user_collection.find_one({"phone": phone_input}); meal_plan_doc = meal_plan_collection.find_one({"user_id": user["_id"]})
            if meal_plan_doc:
                full_meal_plan = meal_plan_doc.get("meal_plan", {});
                for day, meals in full_meal_plan.items():
                    if isinstance(meals, dict):
                        st.subheader(f"📅 {day.replace('Day', 'Day ')}")
                        for meal_details in meals.values():
                            if isinstance(meal_details, dict) and "recipe" in meal_details:
                                with st.expander(f"**Dish:** {meal_details.get('dish_name', 'N/A')}"):
                                    recipe = meal_details['recipe']
                                    st.write(f"**Prep Time:** {recipe.get('prep_time', 'N/A')} | **Cook Time:** {recipe.get('cook_time', 'N/A')}")
                                    for step, instruction in recipe.get("steps", {}).items(): st.write(f"**{step.replace('-', ' ').title()}:** {instruction}")

# --- TAB 4: Shopping List & Prices ---
with tab4:
    st.header("Create Your Shopping List")
    if not phone_input or not st.session_state.get('recipes_generated'):
        st.warning("Please generate Recipes in Tab 3 to create a shopping list.")
    else:
        if st.button("🛒 Generate Shopping List & Prices"):
            with st.spinner("🧠 Analyzing recipes and forecasting prices..."):
                try:
                    user = user_collection.find_one({"phone": phone_input})
                    user_id = user["_id"]
                    meal_plan_doc = meal_plan_collection.find_one({"user_id": user_id})
                    meal_plan_data = meal_plan_doc.get("meal_plan", {})
                    
                    response = shopping_agent.run(json.dumps(clean_mongo_doc(meal_plan_data), indent=2))
                    match = re.search(r'(\{.*\})', response.content.strip(), re.DOTALL)
                    shopping_list = json.loads(match.group(1))
                    
                    st.write("Forecasting prices for your list...")
                    price_response = price_agent.run(json.dumps(shopping_list))
                    price_match = re.search(r'(\{.*\})', price_response.content.strip(), re.DOTALL)
                    pricing_details = json.loads(price_match.group(1))

                    ingredient_doc = {
                        "user_id": user_id,
                        "source_meal_plan_id": meal_plan_doc["_id"],
                        "shopping_list": shopping_list,
                        "pricing_details": pricing_details,
                        "created_at": datetime.now(timezone.utc)
                    }
                    ingredient_collection.update_one({"source_meal_plan_id": meal_plan_doc["_id"]}, {"$set": ingredient_doc}, upsert=True)
                    st.success("✅ Shopping list and prices generated!")
                    st.session_state['shopping_list_generated'] = True
                except Exception as e:
                    st.error(f"An error occurred: {e}")

        if st.session_state.get('shopping_list_generated'):
            user = user_collection.find_one({"phone": phone_input})
            meal_plan_doc = meal_plan_collection.find_one({"user_id": user["_id"]})
            shopping_list_doc = ingredient_collection.find_one({"source_meal_plan_id": meal_plan_doc["_id"]})
            
            if shopping_list_doc:
                # --- NEW "SEXY" UI FOR SHOPPING LIST ---
                st.subheader("🛒 Your Interactive Shopping List")
                pricing_details = shopping_list_doc.get("pricing_details", {})
                
                # Use .get() to safely access Grand_Total without removing it yet
                grand_total = pricing_details.get("Grand_Total", 0)
                
                # --- Progress Bar Logic ---
                total_items = 0
                checked_items = 0
                all_categories_data = {}

                # Create a copy to iterate over, excluding Grand_Total
                categories_to_display = {k: v for k, v in pricing_details.items() if k != "Grand_Total"}

                for category, details in categories_to_display.items():
                    items_with_prices = details.get("items", [])
                    unique_items = []
                    seen_names = set()
                    for item in items_with_prices:
                        name = item.get("name")
                        if name and name not in seen_names:
                            unique_items.append(item)
                            seen_names.add(name)
                    
                    if not unique_items: continue
                    
                    data_for_df = [{"✅ Got it?": False, "Item": item['name'], "Price (₹)": item['price']} for item in unique_items]
                    all_categories_data[category] = data_for_df
                    total_items += len(data_for_df)

                # --- Display Progress Bar First ---
                progress_bar_placeholder = st.empty()

                # --- Display Interactive Tables ---
                for category, data in all_categories_data.items():
                    st.markdown(f"#### {category}")
                    df = pd.DataFrame(data)
                    edited_df = st.data_editor(
                        df, 
                        key=f"df_{category}", 
                        hide_index=True, 
                        use_container_width=True, 
                        disabled=["Item", "Price (₹)"]
                    )
                    checked_items += edited_df["✅ Got it?"].sum()

                # --- Update Progress Bar ---
                progress_percentage = 0 if total_items == 0 else int((checked_items / total_items) * 100)
                progress_bar_placeholder.progress(progress_percentage, text=f"Shopping Progress: {checked_items} of {total_items} items gathered")

                # --- FIX IS HERE: Display the Grand Total ---
                st.header(f"Estimated Grand Total: ₹{grand_total}")
                st.caption("💡 **Disclaimer:** The Grand Total is estimated based on standard package sizes (e.g., 500g, 1 liter). The actual cost per dish is often lower as ingredients are used across multiple meals.")
            
            else:
                st.warning("No Shopping List found. Please generate one.")

# --- TAB 5 (Now works correctly) ---
with tab5:
    st.header("Get Your Meal Plan on WhatsApp")
    if not phone_input or not st.session_state.get('meal_plan_generated'):
        st.warning("Please generate a Meal Plan in Tab 2 first.")
    else:
        st.info("Select a day and click the button below to receive messages for that day's meals on WhatsApp.")

        days_available = []
        try:
            user = user_collection.find_one({"phone": phone_input})
            meal_plan_doc = meal_plan_collection.find_one({"user_id": user["_id"]})
            if meal_plan_doc and "meal_plan" in meal_plan_doc:
                days_available = sorted([day for day in meal_plan_doc["meal_plan"].keys() if day.lower() != "summary"])
        except Exception:
            days_available = ["Day 1", "Day 2"]

        selected_day = st.radio(
            "Which day's meals would you like to receive?",
            options=days_available,
            horizontal=True,
            label_visibility="collapsed"
        )

        if st.button(f"📲 Send {selected_day}'s Meals to my WhatsApp"):
            with st.spinner("🚀 Sending messages..."):
                try:
                    if not meal_plan_doc or "image_urls" not in meal_plan_doc:
                        st.error("Image URLs not found. Please re-generate the meal plan in Tab 2 to ensure images are uploaded.")
                        st.stop()

                    day_plan = meal_plan_doc.get("meal_plan", {}).get(selected_day, {})
                    image_urls = meal_plan_doc.get("image_urls", {})

                    if not day_plan:
                        st.warning(f"No meal plan found for {selected_day}.")
                        st.stop()

                    messages_sent = 0
                    # --- FIX IS HERE: Loop directly through the meal plan's items ---
                    # This avoids case-sensitivity issues (e.g., "Breakfast" vs "breakfast")
                    for meal_name, meal_details in day_plan.items():
                        # Ensure we only process meals (which are dictionaries), skipping the summary string
                        if isinstance(meal_details, dict):
                            dish = meal_details.get("dish_name", "your delicious meal")
                            image_key = f"{selected_day}_{dish.replace(' ', '_')}"
                            image_url = image_urls.get(image_key)

                            status = send_whatsapp_message(user, meal_name.title(), dish, image_url)
                            st.write(status)
                            messages_sent += 1

                    if messages_sent > 0:
                        st.success(f"All messages for {selected_day} have been sent!")
                        st.balloons()
                    else:
                        st.warning(f"No meals were found to send for {selected_day}.")

                except Exception as e:
                    st.error(f"An error occurred while sending messages: {e}")

# --- TAB 6: View All User Data ---
with tab6:
    st.header("📜 Your Complete AI-Generated Health Plan")

    if not phone_input:
        st.warning("Please enter your phone number in Tab 1 to view your saved data.")
    else:
        with st.spinner("🔍 Fetching your complete data profile..."):
            try:
                user = user_collection.find_one({"phone": phone_input})

                if not user:
                    st.info("No profile found for this phone number. Please create one in Tab 1.")
                else:
                    user_id = user["_id"]
                    
                    # Fetch all related data documents
                    nutrition_report_doc = nutrition_collection.find_one({"user_id": user_id})
                    meal_plan_doc = meal_plan_collection.find_one({"user_id": user_id})
                    shopping_list_doc = None
                    if meal_plan_doc:
                        shopping_list_doc = ingredient_collection.find_one({"source_meal_plan_id": meal_plan_doc["_id"]})

                    # --- 1. Display Nutrition Report ---
                    st.subheader("🥗 Your Personalized Nutrition Summary")
                    if nutrition_report_doc and "report" in nutrition_report_doc:
                        report_json = nutrition_report_doc["report"]
                        summary_data = report_json.get("nutrition_summary", {})
                        calories = summary_data.get("calories", "N/A")
                        protein = summary_data.get("protein_g", "N/A")
                        fat = summary_data.get("fat_g", "N/A")
                        human_summary = report_json.get("human_summary", "No summary was generated.")

                        col1, col2, col3 = st.columns(3)
                        col1.metric("Calories", f"{calories} kcal")
                        col2.metric("Protein", f"{protein} g")
                        col3.metric("Fat", f"{fat} g")
                        st.info(f"**Agent's Summary:** {human_summary}")
                    else:
                        st.warning("No Nutrition Report found. Please generate one in Tab 1.")
                    
                    st.markdown("---")

                    # --- 2. Display Day-wise Meal Plan ---
                    st.subheader("📅 Your Meal Plan")
                    if meal_plan_doc:
                        meal_plan_json = meal_plan_doc.get("meal_plan", {})
                        image_ids = meal_plan_doc.get("image_file_ids", {})
                        for day in sorted(meal_plan_json.keys()):
                            day_data = meal_plan_json[day]
                            st.markdown(f"#### {day.replace('Day', 'Day ')}")
                            meals = {k: v for k, v in day_data.items() if isinstance(v, dict)}
                            cols = st.columns(len(meals) if meals else 1)
                            
                            for i, (meal_key, meal_val) in enumerate(meals.items()):
                                with cols[i]:
                                    dish = meal_val.get("dish_name", "N/A")
                                    # --- FIX IS HERE ---
                                    # Map generic meal keys to proper names
                                    meal_name_mapping = {
                                        "Breakfast": "Breakfast",
                                        "Lunch": "Lunch",
                                        "Dinner": "Dinner",
                                        "Snack 1": "Snack 1",
                                        "Snack 2": "Snack 2",
                                        # Add fallbacks for the agent's current output
                                        "Meal 1": "Breakfast",
                                        "Meal 2": "Lunch",
                                        "Meal 3": "Dinner"
                                    }
                                    display_meal_name = meal_name_mapping.get(meal_key, meal_key)

                                    st.markdown(f"<div class='dish-name'>{display_meal_name}: {dish}</div>", unsafe_allow_html=True)
                                    # st.markdown(f"<div class='dish-name'>{meal_key.title()}: {dish}</div>", unsafe_allow_html=True)
                                    image_key = f"{day}_{dish.replace(' ', '_')}"
                                    fid = image_ids.get(image_key)
                                    if fid:
                                        img_bytes = fs.get(fid).read()
                                        st.image(Image.open(BytesIO(img_bytes)), use_container_width=True)
                                    st.markdown(f"<div class='metrics-row'><div>Calories: {meal_val.get('calories_percentage', 'N/A')}%</div><div>Protein: {meal_val.get('protein_percentage', 'N/A')}%</div></div>", unsafe_allow_html=True)
                    else:
                        st.warning("No Meal Plan found. Please generate one in Tab 2.")

                    st.markdown("---")

                    # --- 3. Display Recipes ---
                    st.subheader("🍳 Your Recipes")
                    if meal_plan_doc and meal_plan_doc.get("meal_plan"):
                        full_meal_plan = meal_plan_doc.get("meal_plan", {})
                        for day, meals in full_meal_plan.items():
                            if isinstance(meals, dict):
                                for meal_details in meals.values():
                                    if isinstance(meal_details, dict) and "recipe" in meal_details:
                                        with st.expander(f"**{meal_details.get('dish_name', 'N/A')}** Recipe"):
                                            recipe = meal_details['recipe']
                                            st.write(f"**Prep Time:** {recipe.get('prep_time', 'N/A')} | **Cook Time:** {recipe.get('cook_time', 'N/A')}")
                                            for step, instruction in recipe.get("steps", {}).items():
                                                st.write(f"**{step.replace('-', ' ').title()}:** {instruction}")
                    else:
                        st.warning("No Recipes found. Please generate them in Tab 3.")

                    st.markdown("---")

                    # --- 4. Display Shopping List ---
                    st.subheader("🛒 Your Shopping List")
                    if shopping_list_doc:
                        pricing_details = shopping_list_doc.get("pricing_details", {})
                        grand_total = pricing_details.pop("Grand_Total", 0)
                        
                        for category, details in pricing_details.items():
                            st.markdown(f"##### {category}")
                            items = details.get("items", [])
                            if items:
                                for item in items:
                                    item_col, price_col = st.columns([4, 1])
                                    item_col.write(f"- {item.get('name')}")
                                    price_col.markdown(f"<div class='price-col'>₹{item.get('price')}</div>", unsafe_allow_html=True)
                            else:
                                st.write("No items in this category.")
                        
                        st.header(f"Estimated Grand Total: ₹{grand_total}")
                    else:
                        st.warning("No Shopping List found. Please generate one in Tab 4.")

            except Exception as e:
                st.error(f"An error occurred while fetching your data: {e}")

# --- MODIFIED TAB 7: Interactive Health Dashboard ---
with tab7:
    st.header("📊 Your Interactive Health Dashboard")

    if not phone_input:
        st.warning("Please enter your phone number to generate and view your dashboard.")
    else:
        user = user_collection.find_one({"phone": phone_input})
        if not user:
            st.info("No profile found for this phone number. Please create one in Tab 1.")
        else:
            user_id_str = str(user["_id"])

            st.info("Click the button below to generate a visual dashboard of your latest nutrition and shopping data.")
            if st.button("🚀 Generate My Interactive Dashboard"):
                with st.spinner("🎨 Creating your personalized interactive charts..."):
                    success = generate_and_save_all_charts(user_id_str)
                    if success:
                        st.success("✅ Your interactive dashboard has been generated!")
                        st.rerun()
                    else:
                        st.error("❌ Could not generate charts. Please ensure all previous steps are complete.")

            st.markdown("---")

            # --- Display Interactive Charts ---
            chart_filenames = {
                "Macro Distribution": f"user_{user['_id']}_macro_distribution.html",
                "Calories vs Target": f"user_{user['_id']}_calories_vs_target.html",
                "Shopping Breakdown": f"user_{user['_id']}_shopping_breakdown.html",
                "Grocery Items": f"user_{user['_id']}_grocery_items.html" # Added new chart
            }

            # Check if at least one chart exists
            if fs.exists({"filename": chart_filenames["Macro Distribution"]}):
                st.subheader("Nutrition Insights")
                col1, col2 = st.columns(2)
                
                with col1:
                    macro_chart_file = fs.find_one({"filename": chart_filenames["Macro Distribution"]})
                    if macro_chart_file: components.html(macro_chart_file.read().decode(), height=450)
                
                with col2:
                    calorie_chart_file = fs.find_one({"filename": chart_filenames["Calories vs Target"]})
                    if calorie_chart_file: components.html(calorie_chart_file.read().decode(), height=450)

                st.markdown("---")
                st.subheader("Shopping Insights")
                col3, col4 = st.columns(2)

                with col3:
                    shopping_chart_file = fs.find_one({"filename": chart_filenames["Shopping Breakdown"]})
                    if shopping_chart_file: components.html(shopping_chart_file.read().decode(), height=500)

                with col4:
                    # Display the new grocery items chart
                    grocery_chart_file = fs.find_one({"filename": chart_filenames["Grocery Items"]})
                    if grocery_chart_file: components.html(grocery_chart_file.read().decode(), height=500)
            
            else:
                st.write("Your dashboard is ready to be generated. Click the button above to see your charts!")