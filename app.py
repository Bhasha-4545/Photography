from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_mysqldb import MySQL
import os
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'super_secret_dev_key_change_this_in_prod')

# MySQL Configuration
app.config['MYSQL_HOST'] = os.environ.get('DB_HOST', 'localhost')
app.config['MYSQL_USER'] = os.environ.get('DB_USER', 'root')
app.config['MYSQL_PASSWORD'] = os.environ.get('DB_PASSWORD', '')
app.config['MYSQL_DB'] = os.environ.get('DB_NAME', 'capture_db')
app.config['MYSQL_CURSORCLASS'] = 'DictCursor'

# Set Flask environment
app.debug = os.environ.get('DEBUG', 'False').lower() == 'true'

# Initialize MySQL
mysql = MySQL(app)

import secrets
from datetime import datetime, timedelta
import re
from flask_mail import Mail, Message

# Mail configuration
app.config['MAIL_SERVER'] = os.environ.get('MAIL_SERVER', 'smtp.gmail.com')
app.config['MAIL_PORT'] = int(os.environ.get('MAIL_PORT', 587))
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD')
app.config['MAIL_DEFAULT_SENDER'] = os.environ.get('MAIL_DEFAULT_SENDER')

mail = Mail(app)

def generate_reset_token():
    return secrets.token_urlsafe(32)

def is_valid_password(password):
    # At least 8 characters long
    if len(password) < 8:
        return False
    # Contains at least one uppercase letter
    if not re.search(r'[A-Z]', password):
        return False
    # Contains at least one lowercase letter
    if not re.search(r'[a-z]', password):
        return False
    # Contains at least one number
    if not re.search(r'\d', password):
        return False
    # Contains at least one special character
    if not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
        return False
    return True

def send_reset_email(email, token):
    reset_url = url_for('reset_password', token=token, _external=True)
    msg = Message('Password Reset Request',
                 recipients=[email],
                 body=f'''To reset your password, visit the following link:
{reset_url}

If you did not make this request, simply ignore this email and no changes will be made.

The link will expire in 30 minutes.
''')
    mail.send(msg)

def init_db():
    try:
        # Test database connection
        print("Testing database connection...")
        cur = mysql.connection.cursor()
        cur.execute("SELECT 1")
        print("Database connection successful!")

        # Create users table if it doesn't exist
        print("Creating/verifying users table...")
        cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INT AUTO_INCREMENT PRIMARY KEY,
            username VARCHAR(100) UNIQUE NOT NULL,
            email VARCHAR(255) UNIQUE NOT NULL,
            password VARCHAR(255) NOT NULL,
            reset_token VARCHAR(100) DEFAULT NULL,
            reset_token_expires TIMESTAMP DEFAULT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)

        # Ensure full_name column exists (migrate existing table)
        cur.execute(
            "SELECT COUNT(*) AS cnt FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = %s AND TABLE_NAME = 'users' AND COLUMN_NAME = 'full_name'",
            [app.config['MYSQL_DB']]
        )
        col_info = cur.fetchone()
        if col_info and col_info.get('cnt', 0) == 0:
            print("Adding 'full_name' column to users table...")
            # Add column with a safe default to avoid issues for existing rows
            cur.execute("ALTER TABLE users ADD COLUMN full_name VARCHAR(100) NOT NULL DEFAULT ''")

        # Ensure email and reset token columns exist for password reset functionality
        for col, col_def in {
            'email': "VARCHAR(255) DEFAULT ''",
            'reset_token': "VARCHAR(100) DEFAULT NULL",
            'reset_token_expires': "TIMESTAMP DEFAULT NULL"
        }.items():
            cur.execute(
                "SELECT COUNT(*) AS cnt FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = %s AND TABLE_NAME = 'users' AND COLUMN_NAME = %s",
                [app.config['MYSQL_DB'], col]
            )
            col_info = cur.fetchone()
            if col_info and col_info.get('cnt', 0) == 0:
                print(f"Adding missing column '{col}' to users table...")
                cur.execute(f"ALTER TABLE users ADD COLUMN {col} {col_def}")

        # Create bookings table if it doesn't exist (includes basic contact and date-range fields)
        cur.execute("""
        CREATE TABLE IF NOT EXISTS bookings (
            id INT AUTO_INCREMENT PRIMARY KEY,
            user_id INT NOT NULL,
            photographer VARCHAR(100) NOT NULL,
            date DATE DEFAULT NULL,
            time TIME DEFAULT NULL,
            start_date DATE DEFAULT NULL,
            end_date DATE DEFAULT NULL,
            package VARCHAR(100) DEFAULT '',
            event_type VARCHAR(100) DEFAULT NULL,
            full_name VARCHAR(100) DEFAULT '',
            email VARCHAR(255) DEFAULT '',
            phone VARCHAR(50) DEFAULT '',
            special_requests TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
        """)

        # For existing installations: ensure important columns exist (safe migration)
        required_cols = {
            'start_date': "DATE DEFAULT NULL",
            'end_date': "DATE DEFAULT NULL",
            'full_name': "VARCHAR(100) DEFAULT ''",
            'email': "VARCHAR(255) DEFAULT ''",
            'phone': "VARCHAR(50) DEFAULT ''",
            'special_requests': "TEXT"
        }
        for col, col_def in required_cols.items():
            cur.execute(
                "SELECT COUNT(*) AS cnt FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = %s AND TABLE_NAME = 'bookings' AND COLUMN_NAME = %s",
                [app.config['MYSQL_DB'], col]
            )
            col_info = cur.fetchone()
            if col_info and col_info.get('cnt', 0) == 0:
                print(f"Adding missing column '{col}' to bookings table...")
                cur.execute(f"ALTER TABLE bookings ADD COLUMN {col} {col_def}")

        mysql.connection.commit()
        cur.close()
        print("Database tables created/updated successfully!")
    except Exception as e:
        print(f"Error initializing database: {str(e)}")

def get_user(username):
    cur = mysql.connection.cursor()
    cur.execute("SELECT * FROM users WHERE username = %s", [username])
    user = cur.fetchone()
    cur.close()
    return user

def create_user(username, password, full_name, email):
    cur = None
    try:
        cur = mysql.connection.cursor()
        hashed_password = generate_password_hash(password)
        print(f"Attempting to create user: username={username}, full_name={full_name}, email={email}")
        cur.execute("INSERT INTO users (username, password, full_name, email) VALUES (%s, %s, %s, %s)",
                    [username, hashed_password, full_name, email])
        mysql.connection.commit()
        print("User created successfully in database")
        return True
    except Exception as e:
        # Log and re-raise so caller can handle it; ensure cursor is closed safely
        print(f"Database error in create_user: {type(e).__name__}: {str(e)}")
        import traceback
        traceback.print_exc()
        raise
    finally:
        try:
            if cur is not None:
                cur.close()
        except Exception:
            pass

def get_bookings(user_id):
    """Get all bookings for a user."""
    cursor = mysql.connection.cursor()
    try:
        cursor.execute("""
            SELECT id, photographer, date, time, start_date, end_date, package, full_name, email, phone, special_requests
            FROM bookings 
            WHERE user_id = %s
            ORDER BY COALESCE(date, start_date, created_at) DESC
        """, [user_id])
        bookings = cursor.fetchall()
        return bookings
    finally:
        cursor.close()
def create_booking(user_id, photographer, date, time, package,
                   start_date=None, end_date=None, full_name='', email='', phone='', special_requests='', event_type=None):
    """Create a new booking in the database. Accepts optional contact and range fields."""
    cursor = mysql.connection.cursor()
    try:
        cursor.execute(
            "INSERT INTO bookings (user_id, photographer, date, time, start_date, end_date, package, event_type, full_name, email, phone, special_requests) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (
                user_id,
                photographer,
                date or None,
                time or None,
                start_date or None,
                end_date or None,
                package or '',
                event_type or None,
                full_name or '',
                email or '',
                phone or '',
                special_requests or ''
            )
        )
        mysql.connection.commit()
        return True
    except Exception as e:
        print(f"Error creating booking (create_booking): {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        raise
    finally:
        try:
            cursor.close()
        except Exception:
            pass

# Database initialization route
@app.route('/init-db')
def initialize_database():
    try:
        init_db()
        return 'Database initialized successfully!'
    except Exception as e:
        return f'Error initializing database: {str(e)}'

# --- Route for the Landing Page ---
@app.route('/')
def index():
    return render_template('index.html')

# --- Route for the Login Page ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = get_user(username)
        if user and check_password_hash(user['password'], password):
            session['user_id'] = user['id']
            session['username'] = username
            session['full_name'] = user['full_name']
            flash('Logged in successfully!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid username or password. Please try again.', 'danger')
            return render_template('login.html')
    return render_template('login.html')

# --- Route for the Register Page ---
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        full_name = request.form.get('full_name')
        
        # Validate required fields
        if not username or not email or not password or not full_name:
            flash('All fields are required.', 'danger')
            return render_template('register.html', 
                                username=username, 
                                email=email, 
                                full_name=full_name)
        
        # Check if user already exists
        existing_user = get_user(username)
        if existing_user:
            flash('Username already exists. Please choose another.', 'danger')
            return render_template('register.html',
                                email=email,
                                full_name=full_name)
        # Also ensure email isn't already registered
        cur = mysql.connection.cursor()
        cur.execute('SELECT id FROM users WHERE email = %s', [email])
        existing_email = cur.fetchone()
        cur.close()
        if existing_email:
            flash('An account with this email already exists. Please sign in or use a different email.', 'danger')
            return render_template('register.html',
                                username=username,
                                full_name=full_name)
            
        # Password validation
        if not password:
            flash('Password is required.', 'danger')
            return render_template('register.html',
                                username=username,
                                email=email,
                                full_name=full_name)
                                
        if len(password) < 8:
            flash('Password must be at least 8 characters long.', 'danger')
            return render_template('register.html',
                                username=username,
                                email=email,
                                full_name=full_name)
                                
        if not any(char.isdigit() for char in password):
            flash('Password must contain at least one number.', 'danger')
            return render_template('register.html',
                                username=username,
                                email=email,
                                full_name=full_name)

        try:
            print(f"Registration attempt - Username: {username}, Full Name: {full_name}, Email: {email}")
            
            # Additional password validation
            if ' ' in password:
                flash('Password cannot contain spaces.', 'danger')
                return render_template('register.html',
                                    username=username,
                                    email=email,
                                    full_name=full_name)
                                    
            # Create new user (include email)
            create_user(username, password, full_name, email)
            print("User creation successful")
            flash(f'Account created successfully! Please sign in.', 'success')
            return redirect(url_for('login'))
            
        except Exception as e:
            error_message = str(e)
            print(f"Registration error details: {type(e).__name__}: {error_message}")
            import traceback
            traceback.print_exc()

            # If MySQL reports a duplicate entry, most likely the username already exists
            if "Duplicate entry" in error_message:
                # Be forgiving: tell user username/email is already taken
                flash('This username (or email) is already registered. Please choose another.', 'danger')
            else:
                # Show the exception message in development so the user (developer) can see what's wrong
                # Keep the message short and safe
                safe_msg = error_message.split('\n')[0]
                flash(f'Registration failed: {safe_msg}', 'danger')

            return render_template('register.html',
                                username=username,
                                email=email,
                                full_name=full_name)

    return render_template('register.html')

# --- Dashboard Page ---
@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        flash('Please login first.', 'danger')
        return redirect(url_for('login'))
    user_id = session['user_id']
    full_name = session.get('full_name', session['username'])
    # Get user's bookings
    bookings = get_bookings(user_id)
    return render_template('dashboard.html', user_name=full_name, bookings=bookings)

@app.route('/about')
def about():
    if 'username' not in session:
        flash('Please login first.', 'danger')
        return redirect(url_for('login'))
    return render_template('about.html')

@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form.get('email')
        
        # Check if email exists in database
        cur = mysql.connection.cursor()
        cur.execute('SELECT id FROM users WHERE email = %s', [email])
        user = cur.fetchone()
        
        if user:
            # Generate token
            token = generate_reset_token()
            expires = datetime.now() + timedelta(minutes=30)
            
            # Save token to database
            cur.execute('UPDATE users SET reset_token = %s, reset_token_expires = %s WHERE email = %s',
                       [token, expires, email])
            mysql.connection.commit()
            
            try:
                # Send reset email
                send_reset_email(email, token)
                flash('Password reset instructions have been sent to your email.', 'success')
            except Exception as e:
                print(f"Error sending email: {e}")
                flash('Error sending reset email. Please try again later.', 'danger')
        else:
            # Don't reveal if email exists or not
            flash('If an account exists with that email, a password reset link has been sent.', 'info')
        
        return redirect(url_for('login'))
    
    return render_template('forgot_password.html')

@app.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    if request.method == 'POST':
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        
        if password != confirm_password:
            flash('Passwords do not match.', 'danger')
            return render_template('reset_password.html', token=token)
            
        if not is_valid_password(password):
            flash('Password does not meet requirements. Please try again.', 'danger')
            return render_template('reset_password.html', token=token)
        
        cur = mysql.connection.cursor()
        cur.execute('''SELECT id FROM users 
                      WHERE reset_token = %s 
                      AND reset_token_expires > NOW()''', [token])
        user = cur.fetchone()
        
        if user:
            # Update password and clear reset token
            hashed_password = generate_password_hash(password)
            cur.execute('''UPDATE users 
                          SET password = %s, reset_token = NULL, reset_token_expires = NULL 
                          WHERE id = %s''',
                       [hashed_password, user['id']])
            mysql.connection.commit()
            flash('Your password has been successfully reset. Please login with your new password.', 'success')
            return redirect(url_for('login'))
        else:
            flash('Invalid or expired reset token. Please try again.', 'danger')
            return redirect(url_for('forgot_password'))
            
    # GET request - verify token first
    cur = mysql.connection.cursor()
    cur.execute('''SELECT id FROM users 
                  WHERE reset_token = %s 
                  AND reset_token_expires > NOW()''', [token])
    user = cur.fetchone()
    
    if not user:
        flash('Invalid or expired reset token. Please try again.', 'danger')
        return redirect(url_for('forgot_password'))
        
    return render_template('reset_password.html', token=token)

@app.route('/logout')
def logout():
    # Clear the session
    session.clear()
    # Get and clear any existing flashed messages
    _ = session.pop('_flashes', None)
    # Add only the logout message
    flash('You have been logged out.', 'info')
    return redirect(url_for('login'))

@app.route('/services')
def services():
    if 'username' not in session:
        flash('Please login first.', 'danger')
        return redirect(url_for('login'))
    return render_template('services.html')

@app.route('/contact_page')
def contact_page():
    if 'username' not in session:
        flash('Please login first.', 'danger')
        return redirect(url_for('login'))
    return render_template('contact_page.html')

@app.route('/find_photographers')
def find_photographers():
    if 'username' not in session:
        flash('Please login first.', 'danger')
        return redirect(url_for('login'))
    return render_template('find_photographers.html')

@app.route('/booking', methods=['GET', 'POST'])
def booking():
    if 'username' not in session:
        flash('Please login first.', 'danger')
        return redirect(url_for('login'))

    if request.method == 'POST':
        # Extract booking details from form
        booking_data = {
            'username': session['username'],
            'event_type': request.form.get('eventType'),
            'start_date': request.form.get('startDate'),
            'end_date': request.form.get('endDate'),
            'full_name': request.form.get('fullName'),
            'email': request.form.get('email'),
            'phone': request.form.get('phone'),
            'package': request.form.get('package'),
            'photographer': request.form.get('photographer'),
            'payment_method': request.form.get('paymentMethod'),
            'special_requests': request.form.get('specialRequests')
        }

        # Create the booking in the database
        try:
            # Pass optional contact and range fields so they are saved and can be shown on dashboard
            create_booking(
                session['user_id'],
                booking_data.get('photographer', ''),
                booking_data.get('start_date'),  # primary date (may be None)
                '09:00',  # Default time for legacy forms
                booking_data.get('package', ''),
                start_date=booking_data.get('start_date'),
                end_date=booking_data.get('end_date'),
                full_name=booking_data.get('full_name', ''),
                email=booking_data.get('email', ''),
                phone=booking_data.get('phone', ''),
                special_requests=booking_data.get('special_requests', ''),
                event_type=booking_data.get('event_type', '')  # Added event_type
            )
            flash('Booking successful!', 'success')
            return redirect(url_for('success'))
        except Exception as e:
            print(f"Booking creation failed: {type(e).__name__}: {e}")
            flash('An error occurred while creating your booking. Please try again.', 'danger')
            return render_template('booking.html')

    return render_template('booking.html')

@app.route('/success')
def success():
    if 'username' not in session:
        return redirect(url_for('login'))
    return render_template('success.html')


if __name__ == '__main__':
    with app.app_context():
        init_db()  # Initialize database tables
    app.run(debug=True)