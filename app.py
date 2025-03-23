# Import requirements FIRST
import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime, timedelta
from sklearn.ensemble import RandomForestRegressor
import hashlib

# Set page config IMMEDIATELY AFTER IMPORTS
st.set_page_config(
    page_title="Smart Fitness Tracker",
    layout="wide",
    page_icon="🏋️"
)

# --- Database Setup ---
conn = sqlite3.connect('fitness_tracker.db', check_same_thread=False)
c = conn.cursor()

# Create users table
c.execute('''
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE,
        password TEXT,
        dob DATE,
        height FLOAT,
        weight FLOAT,
        is_admin BOOLEAN DEFAULT 0
    )
''')

# Create workouts table (FIXED: Added missing closing parenthesis)
c.execute('''
    CREATE TABLE IF NOT EXISTS workouts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        date TIMESTAMP,
        duration INTEGER,
        heart_rate INTEGER,
        body_temp FLOAT,
        calories FLOAT,
        FOREIGN KEY(user_id) REFERENCES users(id)
    )
''')  # <-- Added missing closing parenthesis here

# Create admin user if not exists
admin_exists = c.execute('SELECT 1 FROM users WHERE username = "admin"').fetchone()
if not admin_exists:
    hashed_admin_pw = hashlib.sha256("admin".encode()).hexdigest()
    c.execute('''
        INSERT INTO users (username, password, dob, height, weight, is_admin)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', ("admin", hashed_admin_pw, "2000-01-01", 170, 70, 1))
    conn.commit()

# --- Authentication Functions ---
def make_hashed_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def create_user(username, password, dob, height, weight):
    c.execute('''
        INSERT INTO users (username, password, dob, height, weight)
        VALUES (?, ?, ?, ?, ?)
    ''', (username, make_hashed_password(password), dob, height, weight))
    conn.commit()

def get_user(username):
    c.execute('SELECT * FROM users WHERE username = ?', (username,))
    return c.fetchone()

# --- ML Model Loading ---
@st.cache_resource
def load_model():
    # Load your dataset
    calories = pd.read_csv("calories.csv")
    exercise = pd.read_csv("exercise.csv")

    # Merge datasets
    df = exercise.merge(calories, on="User_ID")

    # Feature engineering
    df["BMI"] = df["Weight"] / ((df["Height"] / 100) ** 2)
    df = df[["Gender", "Age", "BMI", "Duration", "Heart_Rate", "Body_Temp", "Calories"]]

    # Convert categorical variables (Gender) to numerical
    df = pd.get_dummies(df, drop_first=True)  # Male: 1, Female: 0

    # Separate features (X) and target (y)
    X = df.drop("Calories", axis=1)
    y = df["Calories"]

    # Train the model
    model = RandomForestRegressor(n_estimators=100, random_state=42)
    model.fit(X, y)

    return model

model = load_model()

# --- Session State Management ---
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.user_info = None
if 'goal' not in st.session_state:
    st.session_state.goal = None

# --- Main App Title ---
st.title("Smart Fitness Tracker 🏋️")

# --- Authentication Flow ---
if not st.session_state.logged_in:
    menu = st.radio("Select Action", ["Login", "Register"], horizontal=True)
    
    with st.form("auth_form"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        
        if menu == "Register":
            # Calculate minimum and maximum DOB
            min_dob = datetime(1950, 1, 1)  # Start from January 1, 1950
            max_dob = datetime.now() - timedelta(days=365 * 8)  # Ensure users are at least 8 years old
            
            # Use these in st.date_input
            dob = st.date_input("Date of Birth", min_value=min_dob, max_value=max_dob)
            
            height = st.number_input("Height (cm)", 100, 250)
            weight = st.number_input("Weight (kg)", 30, 200)
        
        if st.form_submit_button(f"{menu}"):
            user = get_user(username)
            
            if menu == "Register":
                if user:
                    st.error("Username already exists!")
                else:
                    create_user(username, password, dob, height, weight)
                    st.success("Account created! Please login.")
            
            elif menu == "Login":
                if user and user[2] == make_hashed_password(password):
                    st.session_state.logged_in = True
                    st.session_state.user_info = {
                        'id': user[0],
                        'username': user[1],
                        'is_admin': user[6],
                        'dob': user[3],
                        'height': user[4],
                        'weight': user[5]
                    }
                    st.rerun()
                else:
                    st.error("Invalid credentials!")

# --- Main Application ---
else:
    user = st.session_state.user_info
    
    # Admin Dashboard
    if user['is_admin']:
        st.sidebar.header(f"Admin Dashboard 👨💼")
        
        # Admin Statistics
        total_users = c.execute('SELECT COUNT(*) FROM users WHERE is_admin = 0').fetchone()[0]
        total_workouts = c.execute('SELECT COUNT(*) FROM workouts').fetchone()[0]
        avg_calories = c.execute('SELECT AVG(calories) FROM workouts').fetchone()[0]
        
        col1, col2, col3 = st.columns(3)
        col1.metric("Total Users", total_users)
        col2.metric("Total Workouts", total_workouts)
        col3.metric("Avg Calories", f"{avg_calories:.2f}" if avg_calories else "0")
        
        # User Management
        st.subheader("User Management")
        users = c.execute('SELECT id, username, dob, height, weight FROM users WHERE is_admin = 0').fetchall()
        selected_user = st.selectbox("Select User", ["All Users"] + [f"{u[1]} (ID: {u[0]})" for u in users])
        
        if selected_user != "All Users":
            user_id = int(selected_user.split("ID: ")[1][:-1])
            workouts = pd.read_sql('''
                SELECT date, duration, heart_rate, body_temp, calories 
                FROM workouts 
                WHERE user_id = ?
            ''', conn, params=(user_id,))
            
            if not workouts.empty:
                st.line_chart(workouts.set_index('date')['calories'])
                st.dataframe(workouts)
            else:
                st.warning("No workouts found for this user")
        else:
            st.dataframe(pd.DataFrame(users, columns=['ID', 'Username', 'DOB', 'Height', 'Weight']))
    
    # Regular User Interface
    else:
        age = datetime.now().year - datetime.strptime(user['dob'], '%Y-%m-%d').year
        
        # Sidebar
        st.sidebar.header(f"Welcome, {user['username']}!")
        st.sidebar.metric("Age", age)
        st.sidebar.metric("BMI", f"{(user['weight'] / ((user['height']/100)**2)):.1f}")
        
        # --- Today's Goal Feature ---
        st.subheader("Set Your Daily Goal 🎯")
        goal = st.number_input("Set your daily calorie burn goal (kcal)", min_value=100, max_value=5000, step=50,
                                value=st.session_state.goal if st.session_state.goal is not None else 500)
        if st.button("Save Goal"):
            st.session_state.goal = goal
            st.success(f"Goal set to {goal} kcal for today!")
        
        # Fetch today's calories burned
        today = datetime.now().strftime('%Y-%m-%d')
        c.execute('''
            SELECT SUM(calories) FROM workouts 
            WHERE user_id = ? AND DATE(date) = ?
        ''', (user['id'], today))
        calories_burned_today = c.fetchone()[0] or 0
        
        # Calculate remaining calories to reach goal if goal is set
        calories_left = st.session_state.goal - calories_burned_today if st.session_state.goal is not None else None
        
        # Display progress in sidebar
        st.sidebar.header("Today's Progress 🔥")
        st.sidebar.metric("Daily Goal", f"{st.session_state.goal} kcal" if st.session_state.goal is not None else "Not Set")
        st.sidebar.metric("Calories Burned Today", f"{calories_burned_today:.2f} kcal")
        st.sidebar.metric("Calories Left to Goal", f"{calories_left:.2f} kcal" if st.session_state.goal is not None else "Set a Goal")
        
        # Congratulations message and badge if daily goal is met
        if st.session_state.goal is not None and calories_burned_today >= st.session_state.goal:
            st.success("Congratulations! You've reached your daily goal and earned a badge 🏆!")
        
        # Workout Input Form
        with st.form("workout_form"):
            col1, col2 = st.columns(2)
            with col1:
                new_height = st.number_input("Height (cm)", value=user['height'])
                new_weight = st.number_input("Weight (kg)", value=user['weight'])
            with col2:
                duration = st.slider("Duration (min)", 1, 180, 30)
                heart_rate = st.slider("Heart Rate (bpm)", 60, 200, 120)
                body_temp = st.slider("Body Temp (°C)", 36.0, 40.0, 37.0)
            
            if st.form_submit_button("Save Workout"):
                # Update profile if height or weight changed
                if new_height != user['height'] or new_weight != user['weight']:
                    c.execute('''
                        UPDATE users 
                        SET height = ?, weight = ?
                        WHERE id = ?
                    ''', (new_height, new_weight, user['id']))
                    conn.commit()
                
                # Define feature names (must match the model's training data structure)
                feature_names = ["Age", "BMI", "Duration", "Heart_Rate", "Body_Temp", "Gender_male"]
                
                # Prepare input data for prediction
                input_data = pd.DataFrame([[ 
                    age,
                    new_weight / ((new_height / 100) ** 2),  # BMI
                    duration,
                    heart_rate,
                    body_temp,
                    1  # Gender_male: 1 for male, 0 for female
                ]], columns=feature_names)
                
                # Make prediction
                calories = model.predict(input_data)[0]
                
                # Save workout
                c.execute('''
                    INSERT INTO workouts 
                    (user_id, date, duration, heart_rate, body_temp, calories)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (user['id'], datetime.now(), duration, heart_rate, body_temp, calories))
                conn.commit()
                st.success(f"Saved workout! {calories:.2f} calories burned")
        
        # Workout History
        st.subheader("Workout History")
        workouts = pd.read_sql('''
            SELECT date, duration, heart_rate, body_temp, calories 
            FROM workouts 
            WHERE user_id = ?
        ''', conn, params=(user['id'],))
        
        if not workouts.empty:
            tab1, tab2 = st.tabs(["Chart", "Data"])
            with tab1:
                st.line_chart(workouts.set_index('date')['calories'])
            with tab2:
                st.dataframe(workouts.style.highlight_max(color='#90EE90'), use_container_width=True)
        else:
            st.info("No workouts recorded yet")
    
    # Logout Button
    if st.sidebar.button("Logout"):
        st.session_state.logged_in = False
        st.session_state.user_info = None
        st.rerun()

conn.close()
