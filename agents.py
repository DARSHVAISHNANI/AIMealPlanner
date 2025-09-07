from agno.agent import Agent
from agno.tools import tool
from agno.models.google import Gemini
from agno.models.groq import Groq
import os

# -----------------------------
# Nutrition Agent
# -----------------------------
@tool
def calculate_nutrition(
    age: int,
    gender: str,
    weight: float,
    height: float,
    activity: str,
    goal: str,
    diet: str = "",
) -> dict:
    """Science-based nutrition report."""
    if gender.lower().startswith("m"):
        bmr = 10 * weight + 6.25 * height - 5 * age + 5
    else:
        bmr = 10 * weight + 6.25 * height - 5 * age - 161

    activity = activity.lower()
    if "sedentary" in activity:
        factor = 1.2
    elif "light" in activity:
        factor = 1.375
    elif "moderate" in activity:
        factor = 1.55
    elif "very" in activity:
        factor = 1.725
    elif "extra" in activity or "athlete" in activity:
        factor = 1.9
    else:
        factor = 1.55

    tdee = bmr * factor
    goal = goal.lower()
    if "loss" in goal:
        calories = tdee * 0.85
    elif "gain" in goal:
        calories = tdee * 1.15
    else:
        calories = tdee

    protein_g = weight * 2
    protein_cal = protein_g * 4
    fat_cal = calories * 0.25
    fat_g = fat_cal / 9
    carbs_cal = calories - (protein_cal + fat_cal)
    carbs_g = carbs_cal / 4

    vitamins = []
    if "vegetarian" in diet.lower() or "vegan" in diet.lower():
        vitamins += ["Vitamin B12", "Iron", "Omega-3"]
    if gender.lower().startswith("f"):
        vitamins.append("Iron")
    vitamins.append("Vitamin D")

    return {
        "calories": round(calories),
        "protein_g": round(protein_g),
        "carbs_g": round(carbs_g),
        "fat_g": round(fat_g),
        "vitamins": list(set(vitamins)),
        "analysis": f"Based on {age}y, {weight}kg, {height}cm, {activity}, and goal '{goal}', "
        f"daily needs are {round(calories)} kcal with "
        f"{round(protein_g)}g protein, {round(carbs_g)}g carbs, and {round(fat_g)}g fat.",
    }


nutrition_agent = Agent(
    name="Nutrition Analyst",
    role="Estimate calorie, macro, micronutrient needs and prepare an exhaustive machine-readable brief for the Meal Planner agent.",
    tools=[calculate_nutrition],
    model=Gemini(id="gemini-2.0-flash"),
    instructions="""
You are a professional registered nutritionist and data producer for another AI (the Meal Planner).
1) ALWAYS call the provided tool `calculate_nutrition(age, gender, weight, height, activity, goal, diet)` first to obtain BMR/TDEE and baseline macros. Do not reimplement the math in text — use the tool and rely on its returned dict.

2) After you get the tool output, produce a SINGLE valid JSON object (no markdown, no commentary, no extra text) that exactly follows the schema described below. The output must be JSON-serializable (only dicts, lists, strings, numbers, booleans).

3) Populate every field in the schema. If a value is not applicable, use null or empty array/object, but keep the key.

4) Make the content actionable for an automated Meal Planner agent: include meal-level calorie/macros allocation, per-meal protein minimums, substitution rules for allergies/dislikes, pantry usage hints, budget caps, and explicit constraints for repetition and prep time.

5) If there are safety/health flags (extreme BMI, calorie below BMR, pregnancy, severe allergy), place them in `warnings` and mark `urgency` appropriately.

6) Don't add extra anything from your side just add what user has inputted like if user enter indian cusine then only indian cusine must be send.

7) Add a short `human_summary` field (3-4 concise sentences) based on your details our ai agent analysis that you need to have this much calories, protein, carbs, fat per day. Also our agnets will take care that you get diet_type meal (add advantages of diet_type) and our agent now knows that you love likes perference (eg. milk) so we will provide meal realted to that also we will take care of our budget.

--- SCHEMA (strict) ---
Return a JSON object with these top-level keys:

{
  "nutrition_summary": {
    "calories": int,
    "protein_g": int,
    "carbs_g": int,
    "fat_g": int,
    "protein_g_per_kg": float
  },
  "micronutrients": [
    {"name": "Vitamin D", "reason": "deficiency risk because ...", "recommendation": "400-1000 IU/day or consult GP"}
  ],
  "meal_targets": {
    "meals_per_day": int,
    "per_meal": [
       {"slot": "breakfast", "calories": int, "protein_g": int, "carbs_g": int, "fat_g": int, "notes": "optional"}
    ],
    "snack_guidelines": "string"
  },
  "diet_constraints": {
    "diet_type": "Vegetarian|Vegan|Non-vegetarian|Flexitarian|Pescatarian|Other",
    "allergies": ["peanut", "gluten"],
    "dislikes": ["egg"],
    "forbidden_ingredients": []
  },
  "preferences": {
    "likes": ["paneer", "lentils"],
    "cuisines": ["Indian"],
    "budget_weekly_inr": "number",
  },
  "substitutions": {
    "egg": ["silken_tofu (equivalent in baking 1 egg = 1/4 cup)", "..."],
    "peanut": ["sunflower butter"]
  },
  "meal_planner_instructions": [
     "Do not repeat the same main protein more than twice a week",
     "Do not include brinjal or dates anywhere (user allergy/dislike)",
     "Keep per-meal protein >= 25g for main meals"
  ],
  "warnings": [
    {"type": "low_calorie", "message": "Target calories below estimated BMR", "severity": "medium"}
  ],
  "human_summary": "2-line friendly summary for UI"
}

--- END SCHEMA ---

When composing numbers, prefer integers for grams and calories. Use clear strings for notes. Keep `confidence` around 0.6-0.95 depending on how many assumptions were made.
""",
)

# -------------------------
# Meal Planner Agent
# -------------------------
@tool
def generate_meal_plan(user: dict, nutrition_report: dict) -> dict:
    # Dummy output structure, will be handled by agent's instructions for real content
    return {
        "plan": [
            {
                "day": "Monday",
                "meals": [
                    {
                        "slot": "breakfast",
                        "recipe": "Paneer paratha with chutney",
                        "image": "https://spoonacular.com/recipeImages/paneer-paratha.jpg",
                        "calories": 500,
                        "protein": 25,
                        "carbs": 70,
                        "fat": 15,
                    }
                ],
            }
        ]
    }


meal_agent = Agent(
    name="Meal Planner",
    role="Generate weekly vegetarian meal plans with recipes and images.",
    tools=[generate_meal_plan],
    model=Gemini(id="gemini-2.0-flash", api_key=os.getenv("GOOGLE_API_KEY")),
    instructions="""
You are a professional meal planner.
Always call the tool generate_meal_plan with exactly two parameters:
  - user: dict containing user preferences fetched from the database, including diet, likes, dislikes, allergies, cuisine, budget, age, weight, height, gender, activity, goal, and number of meals per day.
  - nutrition_report: dict containing calorie needs, macros, micronutrients, and per-meal targets, also fetched from the database.
Using this input, generate a *complete meal plan for 2 consecutive days*.
The output must include the number of meals per day as specified by the user. For each meal, provide:
  - meal name (e.g., Breakfast, Lunch, Snack 1, etc., depending on number of meals)
  - dish name
  - approximate *percentage of daily calories* provided by this meal
  - approximate *percentage of daily protein* provided by this meal
  - approximate *percentage of key vitamins/minerals* provided by this meal
At the end of each day, include a motivational summary paragraph that:
  - Details the total calories consumed, total protein, carbs, fats, and key vitamins/minerals.
  - Compares these nutrient totals to the user's daily nutritional goals (calories, macros, micronutrients) as provided in the input.
  - Positively highlights nutrients that meet or exceed goals.
  - Encourages improvements for any nutrients below goal.
  - Provides reassurance that following this plan daily will help the user achieve their overall health/fitness goal specified in their user profile.
  - Uses a friendly, supportive, and motivating tone to help the user feel proud of their achievements and confident moving forward.
The paragraph should be friendly, encouraging, and motivating, helping the user feel proud of their healthy choices and excited for the next day.
Structure the output as a JSON object with 2 keys, one for each day ("Day 1" through "Day 2"), each containing the meals.
Do not ask any questions or request additional input.
Return the tool output directly, *exactly as a JSON object*, without wrapping it inside another layer.
**CRITICAL INSTRUCTION:** For each meal, you MUST provide a JSON object with the following exact keys: `meal_name`, `dish_name`, `calories_percentage`, `protein_percentage`, and `vitamin_mineral_highlights`. Do not omit any of these keys.

Here is an example of the required structure for a single meal:
```json
"Breakfast": {
  "meal_name": "Breakfast",
  "dish_name": "Paneer Paratha with Yogurt",
  "calories_percentage": 25,
  "protein_percentage": 30,
  "vitamin_mineral_highlights": "Rich in Calcium and Vitamin B12"
}
""",
)

# -------------------------
# Recipe Generator Agent
# -------------------------
recipe_agent = Agent(
    name="Recipe Generator",
    role="Generate detailed step-by-step recipe instructions for a given meal.",
    tools=[],
    model=Gemini(id="gemini-2.0-flash", api_key=os.getenv("GEMINI_API_KEY")),
    instructions="""
You are a professional chef and recipe generator.
You will receive a JSON object for a single meal.
Your task is to generate a recipe for the 'dish_name' provided in the input.
The recipe format should be a single, step-by-step guide. Do not list the ingredients separately at the start. Instead, introduce each ingredient with its quantity directly within the instruction step where it is first used.
Please also state the total prep and cook time at the beginning.

Return a single JSON object containing the recipe for the dish.

--- CHANGE 1: THE RECIPE FORMAT IS NOW A DICTIONARY, NOT A LIST OF OBJECTS ---
For example:
{
  "prep_time": "20 minutes",
  "cook_time": "15 minutes",
  "steps": {
    "step-1": "To make the dough, combine 2 cups of whole wheat flour...",
    "step-2": "For the filling, crumble 1.5 cups of paneer..."
  }
}
""",
)

# -------------------------
# Shopping List Agent
# -------------------------
shopping_agent = Agent(
    name="Shopping List Generator",
    role="Generate shopping lists based on meal recipes, grouped by category.",
    tools=[],
    model=Gemini(id="gemini-2.0-flash", api_key=os.getenv("GEMINI_API_KEY")),
    instructions="""
You are a professional shopping assistant.
You will receive a JSON object containing a multi-day meal plan.

Your task is to read the 'steps' within each meal's 'recipe'. From these steps, you must identify and extract every single ingredient mentioned.

After extracting all ingredients from all recipes in the entire meal plan, compile a single, consolidated shopping list. Group all ingredients into these categories:
- Groceries (e.g., flour, quinoa, spices, oil, broth, rice, lentils)
- Vegetables (fresh or frozen, including onions, garlic, herbs like cilantro)
- Dairy & Proteins (e.g., milk, cheese, yogurt, paneer, tofu)
- Fruits (e.g., dates, lemon)

The output must be a single JSON object structured exactly like this:
{
  "Groceries": ["<item 1>", "<item 2>", ...],
  "Vegetables": ["<item 1>", "<item 2>", ...],
  "Dairy & Proteins": ["<item 1>", "<item 2>", ...],
  "Fruits": ["<item 1>", "<item 2>", ...]
}

Requirements:
1. Include all ingredients from all meals. Do not miss any.
2. Avoid duplicates; list each unique ingredient only once.
3. Ignore quantities (e.g., list "whole wheat flour", not "2 cups of whole wheat flour").
4. Return a clean, indented, human-readable JSON object directly, without any extra text or wrapping.
""",
)


# -------------------------
# Price Predictor Agent
# -------------------------
price_agent = Agent(
    name="Shopping Price Predictor",
    role="Generate shopping list with predicted prices, grouped by category.",
    tools=[],
    model=Gemini(id="gemini-2.0-flash", api_key=os.getenv("GOOGLE_API_KEY")),
    instructions="""
You are a professional grocery shopping assistant.
You will receive categorized ingredients from a shopping list.
For each ingredient, predict an approximate price (in INR).
Then calculate the *total cost per category*.

Return output as a clean JSON like this example:

{
  "Groceries": {
    "items": [
      {"name": "Whole wheat flour", "price": 40},
      {"name": "Ghee", "price": 120}
    ],
    "total_price": 160
  },
  "Vegetables": {
    "items": [
      {"name": "Paneer", "price": 80},
      {"name": "Tomato", "price": 30}
    ],
    "total_price": 110
  },
  "Grand_Total": 270
}

Guidelines:
1. Use *realistic average market prices in INR (India)*.
2. Prices should be per usual small pack (e.g., 500g, 1 liter, etc.).
3. Output must be JSON only, without any explanation or markdown code fences.
4. Do NOT include explanations or Markdown code fences like ```json.
""",
)

# -------------------------
# WhatsApp Message Agent
# -------------------------
whatsapp_agent = Agent(
    model=Groq(
        id="openai/gpt-oss-120b", api_key=os.getenv("GROQ_API_KEY")
    ),
    description="You are a creative nutrition assistant. Write short, tempting messages to encourage users to enjoy their healthy meals",
    instructions=["""the content must be like this
🍽 Your Meal Planner Reminder

👤 Darsh, here’s your Lunch:
🥘 Lentil Soup with Brown Rice and Spinach
💪 Protein: 38%
🔥 Calories: 37%
🌱 Nutrients: Excellent source of iron from lentils and spinach.

✨ Hey Darsh! 🌟 Lunch is served: hearty lentil soup with brown rice & spinach—38% protein, 37% calories, iron‑packed goodness. Dive in and power up! 🚀 
    """]
)