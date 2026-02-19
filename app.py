import streamlit as st
import pandas as pd
import numpy as np

st.title("SeasonFinder (Prototype v1)")
unit = st.radio("Temperature unit", ["°F", "°C"], horizontal=True)

def c_to_f(c): 
    return c * 9/5 + 32

def f_to_c(f): 
    return (f - 32) * 5/9

def season_label_for_month(temp_c, winter_c, summer_c):
    if temp_c <= winter_c:
        return "Winter"
    if temp_c >= summer_c:
        return "Summer"
    return "Transition"

SEASON_COLORS = {
    "Winter": "#2b6cb0",      # blue
    "Spring": "#2f855a",      # green
    "Summer": "#c05621",      # orange
    "Autumn": "#b7791f",      # amber
    "Transition": "#4a5568"   # gray (should rarely show after we split)
}

def color_season_cell(val):
    color = SEASON_COLORS.get(val, "#4a5568")
    # background + white text for readability
    return f"background-color: {color}; color: white; font-weight: 600;"


st.write("Upload a CSV of cities with monthly average temps (T1..T12).")

uploaded = st.file_uploader("Upload your own CSV (optional)", type=["csv"])

if uploaded is not None:
    df = pd.read_csv(uploaded)
    st.success("Using uploaded dataset.")
else:
    df = pd.read_csv("cities_sample.csv")
    st.info("Using built-in city dataset.")


temp_cols = [f"T{i}" for i in range(1, 13)]
missing = [c for c in temp_cols if c not in df.columns]
if missing:
    st.error(f"Missing columns in CSV: {missing}")
    st.stop()

st.subheader("Season rules (simple v1)")

if unit == "°F":
    winter_thresh_f = st.slider("Winter month if temp ≤", -20.0, 70.0, 41.0, 1.0)
    summer_thresh_f = st.slider("Summer month if temp ≥", 40.0, 110.0, 68.0, 1.0)
    winter_thresh = f_to_c(winter_thresh_f)
    summer_thresh = f_to_c(summer_thresh_f)
else:
    winter_thresh = st.slider("Winter month if temp ≤ (°C)", -30.0, 20.0, 5.0, 0.5)
    summer_thresh = st.slider("Summer month if temp ≥ (°C)", 0.0, 40.0, 20.0, 0.5)

st.subheader("Your preferred season lengths (auto-fills the last one)")

w_pref = st.slider("Winter months", 0, 12, 5)
sp_pref = st.slider("Spring months", 0, 12, 2)

max_summer = 12 - (w_pref + sp_pref)
max_summer = max(0, max_summer)

su_pref = st.slider("Summer months", 0, max_summer, min(3, max_summer))

fa_pref = 12 - (w_pref + sp_pref + su_pref)
st.write(f"**Autumn months:** {fa_pref}")

T = df[temp_cols].to_numpy()

T_c = T  # assume the CSV temps are in °C for now

# For display only
if unit == "°F":
    T_display = c_to_f(T_c)
else:
    T_display = T_c

is_winter = T_c <= winter_thresh
is_summer = T_c >= summer_thresh

winter_len = is_winter.sum(axis=1)
summer_len = is_summer.sum(axis=1)

# Transition months are neither winter nor summer
is_transition = (~is_winter) & (~is_summer)

# month-to-month temperature change (wrap around Dec->Jan)
delta = np.roll(T_c, -1, axis=1) - T_c  # next_month - this_month

# Spring-like if warming, Autumn-like if cooling (only for transition months)
is_spring = is_transition & (delta > 0)
is_fall   = is_transition & (delta < 0)

# If delta == 0, split them later (rare with real data, but possible)
is_flat = is_transition & (delta == 0)

spring_len = is_spring.sum(axis=1)
fall_len = is_fall.sum(axis=1)

# Split flat months evenly between spring/fall (keeps totals consistent)
flat_len = is_flat.sum(axis=1)
spring_len = spring_len + (flat_len // 2)
fall_len = fall_len + (flat_len - (flat_len // 2))


score = (
    np.abs(winter_len - w_pref)
    + np.abs(spring_len - sp_pref)
    + np.abs(summer_len - su_pref)
    + np.abs(fall_len - fa_pref)
)

out = df.copy()
out["Winter"] = winter_len
out["Spring"] = spring_len
out["Summer"] = summer_len
out["Autumn"] = fall_len
out["Score"] = score

st.subheader("Top matches")

max_score = 48  # 4 seasons × 12 months max difference

# Start from the raw "distance" score (lower is better)
out2 = out.copy()

# Convert to "higher is better"
out2["Score"] = max_score - out2["Score"]

# Sort best-first (highest score)
out_sorted = out2.sort_values("Score", ascending=False).reset_index(drop=True)

# Rank AFTER sorting
out_sorted["Rank"] = np.arange(1, len(out_sorted) + 1)

# Match %
out_sorted["Match %"] = (out_sorted["Score"] / max_score * 100).clip(0, 100).round(1)

top = out_sorted.head(20)

st.dataframe(
    top[["Rank", "City", "Country", "Score", "Match %", "Winter", "Spring", "Summer", "Autumn"]],
    hide_index=True,
    use_container_width=True
)

st.subheader("City details")

# Use only the top results for the dropdown (keeps it clean)
top_for_pick = out_sorted.head(20).copy()

# Make a nice label like: "1. Chicago, USA (91.7%)"
top_for_pick["Label"] = (
    top_for_pick["Rank"].astype(str) + ". "
    + top_for_pick["City"].astype(str) + ", "
    + top_for_pick["Country"].astype(str)
    + " (" + top_for_pick["Match %"].astype(str) + "%)"
)

picked_label = st.selectbox("Select a city to inspect", top_for_pick["Label"].tolist())

picked_row = top_for_pick[top_for_pick["Label"] == picked_label].iloc[0]
picked_city = picked_row["City"]

st.write(
    f"**Selected:** {picked_row['Rank']}. {picked_row['City']}, {picked_row['Country']} — "
    f"**Match:** {picked_row['Match %']}%  |  "
    f"Winter {picked_row['Winter']} • Spring {picked_row['Spring']} • "
    f"Summer {picked_row['Summer']} • Autumn {picked_row['Autumn']}"
)

# Grab that city's temps from the original dataframe
city_row = df[df["City"] == picked_city].iloc[0]
temps_c = city_row[temp_cols].to_numpy(dtype=float)

# Convert for display
if unit == "°F":
    temps_display = c_to_f(temps_c)
else:
    temps_display = temps_c

months = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]

chart_df = pd.DataFrame({"Month": months, f"Temp ({unit})": temps_display})
chart_df = chart_df.set_index("Month")

st.line_chart(chart_df)

st.markdown("### What your settings mean (plain English)")

if unit == "°F":
    st.write(
        f"- A month counts as **Winter** if the city's monthly average is **≤ {winter_thresh_f:.0f}°F**\n"
        f"- A month counts as **Summer** if the city's monthly average is **≥ {summer_thresh_f:.0f}°F**\n"
        f"- Anything in between is a **transition month** (Spring or Autumn depending on warming/cooling)"
    )
else:
    st.write(
        f"- A month counts as **Winter** if the city's monthly average is **≤ {winter_thresh:.1f}°C**\n"
        f"- A month counts as **Summer** if the city's monthly average is **≥ {summer_thresh:.1f}°C**\n"
        f"- Anything in between is a **transition month** (Spring or Autumn depending on warming/cooling)"
    )

st.markdown("### Month-by-month breakdown")

# classify each month for THIS city
labels = [season_label_for_month(t, winter_thresh, summer_thresh) for t in temps_c]

# turn Transition into Spring/Autumn based on warming/cooling (same logic as earlier)
deltas = np.roll(temps_c, -1) - temps_c  # next - current (wraps)
for i in range(12):
    if labels[i] == "Transition":
        if deltas[i] > 0:
            labels[i] = "Spring"
        elif deltas[i] < 0:
            labels[i] = "Autumn"
        else:
            labels[i] = "Spring"  # tie-breaker

detail_df = pd.DataFrame({
    "Month": months,
    f"Temp ({unit})": np.round(temps_display, 1),
    "Season": labels
})

# Make Month the index so it displays nicely
detail_df2 = detail_df.set_index("Month")

styled = (
    detail_df2.style
    .applymap(color_season_cell, subset=["Season"])
)

st.dataframe(styled, use_container_width=True)

st.markdown("### Why this matched (or didn’t)")

st.write(
    f"Your preference: Winter **{w_pref}**, Spring **{sp_pref}**, Summer **{su_pref}**, Autumn **{fa_pref}** months."
)
st.write(
    f"This city: Winter **{int(picked_row['Winter'])}**, Spring **{int(picked_row['Spring'])}**, "
    f"Summer **{int(picked_row['Summer'])}**, Autumn **{int(picked_row['Autumn'])}** months."
)

diff_w = int(picked_row["Winter"]) - w_pref
diff_sp = int(picked_row["Spring"]) - sp_pref
diff_su = int(picked_row["Summer"]) - su_pref
diff_fa = int(picked_row["Autumn"]) - fa_pref

st.write(
    f"Difference: Winter {diff_w:+d}, Spring {diff_sp:+d}, Summer {diff_su:+d}, Autumn {diff_fa:+d}."
)

