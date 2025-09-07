# AIMealPlanner/charts.py

import plotly.express as px
import plotly.io as pio
import pandas as pd
from database import fs, user_collection, nutrition_collection, ingredient_collection
from bson import ObjectId

# Set default theme for plotly charts
pio.templates.default = "plotly_dark"

def save_chart_to_gridfs(user_id, chart_name, fig):
    """Saves a Plotly figure as HTML to GridFS."""
    try:
        html_str = fig.to_html(full_html=False, include_plotlyjs='cdn')
        filename = f"user_{user_id}_{chart_name}.html"

        existing_chart = fs.find_one({"filename": filename})
        if existing_chart:
            fs.delete(existing_chart._id)
            
        fs.put(
            html_str.encode('utf-8'), 
            filename=filename, 
            user_id=user_id, 
            content_type="text/html"
        )
        print(f"✅ Saved interactive chart to GridFS: {filename}")
    except Exception as e:
        print(f"❌ Failed to save chart {chart_name} to GridFS: {e}")

def shopping_cost_breakdown(pricing_details, username, user_id):
    if not pricing_details: return
    data = []
    for key, value in pricing_details.items():
        if key != "Grand_Total" and isinstance(value, dict):
            data.append({"Category": key, "Cost": value.get("total_price", 0)})
    if not data: return
    df = pd.DataFrame(data)
    fig = px.pie(df, values='Cost', names='Category', hole=.3, color_discrete_sequence=px.colors.sequential.RdBu)
    fig.update_traces(textposition='inside', textinfo='percent+label')
    fig.update_layout(
        title_text=f"<b>Shopping Cost Breakdown</b><br><span style='font-size: 13px;'>This chart shows the percentage of your budget spent on each food category.</span>",
        title_x=0.5, title_font_size=20, margin=dict(t=100)
    )
    save_chart_to_gridfs(user_id, "shopping_breakdown", fig)

def macro_distribution(summary, username, user_id):
    if not summary: return
    macros = {"Protein": summary.get("protein_g", 0), "Carbs": summary.get("carbs_g", 0), "Fat": summary.get("fat_g", 0)}
    df = pd.DataFrame(list(macros.items()), columns=['Macro', 'Grams'])
    fig = px.bar(df, x='Macro', y='Grams', color='Macro', text='Grams')
    fig.update_layout(
        title_text=f"<b>Daily Macro Distribution</b><br><span style='font-size: 13px;'>This chart displays your daily intake of Protein, Carbs, and Fats in grams.</span>",
        title_x=0.5, title_font_size=20, showlegend=False, margin=dict(t=100)
    )
    save_chart_to_gridfs(user_id, "macro_distribution", fig)

def calorie_vs_target(summary, username, user_id):
    if not summary: return
    calories = summary.get("calories", 0)
    target = 2000
    df = pd.DataFrame([{"Category": "Actual Intake", "Calories": calories}, {"Category": "Target Goal", "Calories": target}])
    fig = px.bar(df, x='Category', y='Calories', color='Category', color_discrete_map={"Actual Intake": "dodgerblue", "Target Goal": "lightgray"}, text='Calories')
    fig.update_layout(
        title_text=f"<b>Calories: Actual vs. Target</b><br><span style='font-size: 13px;'>This chart compares your actual daily calorie intake against your target goal.</span>",
        title_x=0.5, title_font_size=20, showlegend=False, margin=dict(t=100)
    )
    save_chart_to_gridfs(user_id, "calories_vs_target", fig)

# --- NEW GRAPH FUNCTION ---
def grocery_items_chart(pricing_details, username, user_id):
    """Creates a horizontal bar chart for individual grocery item prices."""
    if not pricing_details: return
    
    items_data = []
    # Collect items from all categories for a comprehensive list
    for category, details in pricing_details.items():
        if isinstance(details, dict) and "items" in details:
            for item in details.get("items", []):
                items_data.append({"Item": item.get("name"), "Price": item.get("price")})
    
    if not items_data: return
    
    df = pd.DataFrame(items_data).sort_values(by="Price", ascending=True)
    
    fig = px.bar(
        df,
        y='Item',
        x='Price',
        orientation='h',
        text='Price'
    )
    
    fig.update_layout(
        title_text=f"<b>Individual Item Prices (in ₹)</b><br><span style='font-size: 13px;'>This chart breaks down the estimated cost for each item on your shopping list.</span>",
        title_x=0.5,
        title_font_size=20,
        xaxis_title="Price (₹)",
        yaxis_title="Grocery Item",
        margin=dict(t=100, l=150) # Add left margin for long item names
    )
    save_chart_to_gridfs(user_id, "grocery_items", fig)


def generate_and_save_all_charts(user_id_str):
    """Main function to generate all interactive charts for a specific user."""
    user_id = ObjectId(user_id_str)
    user = user_collection.find_one({"_id": user_id})
    if not user:
        print(f"No user found for ID: {user_id}")
        return False

    username = user.get("name", "User")
    
    ingredients_doc = ingredient_collection.find_one({"user_id": user_id})
    pricing_details = ingredients_doc.get("pricing_details", {}) if ingredients_doc else {}
    
    nutrition_doc = nutrition_collection.find_one({"user_id": user_id})
    nutrition_summary = nutrition_doc.get("report", {}).get("nutrition_summary", {}) if nutrition_doc else {}

    print(f"📊 Generating interactive charts for {username}...")
    shopping_cost_breakdown(pricing_details, username, user_id)
    macro_distribution(nutrition_summary, username, user_id)
    calorie_vs_target(nutrition_summary, username, user_id)
    grocery_items_chart(pricing_details, username, user_id) # Call the new function
    print("✅ All interactive charts generated.")
    return True