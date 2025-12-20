# app.py - Flask Backend with Phone Number as Primary Key
from flask import Flask, request, jsonify
from flask_cors import CORS
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime, timedelta
import os
from dotenv import load_dotenv
import traceback
import random
import string
import requests

load_dotenv()

app = Flask(__name__)
CORS(app)

# Database configuration
DATABASE_URL = "postgresql://vinayreddychetelli:WQ74scvC81kv9BnD5eXi3PM4G6F8qakC@dpg-d52udav5r7bs73deu0n0-a.virginia-postgres.render.com/ruchitara_db"

# Fast2SMS Configuration
FAST2SMS_API_KEY = "VRs0wZD9SnHxoeEGNLvYrakT6hy3bAFJ74tWCpPBuXjgcUKq8lHyp71M3euN9shI4cZrPG5AOKSnbJwj"
FAST2SMS_URL = "https://www.fast2sms.com/dev/bulkV2"

# For testing - set to False when you want to use real SMS
USE_TEST_OTP = True
TEST_OTP = "9999"

# In-memory storage for OTP sessions (use Redis in production)
otp_storage = {}

def get_db_connection():
    """Create database connection using DATABASE_URL"""
    try:
        conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
        return conn
    except Exception as e:
        print(f"Database connection error: {e}")
        raise

def init_database():
    """Initialize database with updated schema using phone_number as primary key"""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Drop existing tables to recreate with new schema
        print("🔄 Recreating database schema with phone_number as primary key...")
        
        
        # Create user_profiles table with phone_number as primary key
        cur.execute('''
            CREATE TABLE IF NOT EXISTS user_profiles (
                phone_number VARCHAR(10) PRIMARY KEY,
                name VARCHAR(100),
                email VARCHAR(100),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        print("✅ Created user_profiles table")
        
        # Create favorites table
        cur.execute('''
            CREATE TABLE IF NOT EXISTS favorites (
                id SERIAL PRIMARY KEY,
                phone_number VARCHAR(10) REFERENCES user_profiles(phone_number) ON DELETE CASCADE,
                product_id INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(phone_number, product_id)
            )
        ''')
        print("✅ Created favorites table")
        
        # Create cart_items table
        cur.execute('''
            CREATE TABLE IF NOT EXISTS cart_items (
                id SERIAL PRIMARY KEY,
                phone_number VARCHAR(10) REFERENCES user_profiles(phone_number) ON DELETE CASCADE,
                product_id INTEGER NOT NULL,
                quantity INTEGER NOT NULL DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(phone_number, product_id)
            )
        ''')
        print("✅ Created cart_items table")
        
        # Create orders table
        cur.execute('''
            CREATE TABLE IF NOT EXISTS orders (
                id SERIAL PRIMARY KEY,
                order_number VARCHAR(20) UNIQUE NOT NULL,
                phone_number VARCHAR(10) REFERENCES user_profiles(phone_number) ON DELETE CASCADE,
                status VARCHAR(20) DEFAULT 'Pending',
                total_amount DECIMAL(10, 2) NOT NULL,
                delivery_address TEXT NOT NULL,
                payment_method VARCHAR(50) DEFAULT 'Cash on Delivery',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        print("✅ Created orders table")
        
        # Create order_items table
        cur.execute('''
            CREATE TABLE IF NOT EXISTS order_items (
                id SERIAL PRIMARY KEY,
                order_id INTEGER REFERENCES orders(id) ON DELETE CASCADE,
                product_id INTEGER NOT NULL,
                product_name VARCHAR(200) NOT NULL,
                quantity INTEGER NOT NULL,
                unit_price DECIMAL(10, 2) NOT NULL,
                subtotal DECIMAL(10, 2) NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        print("✅ Created order_items table")
        
        conn.commit()
        cur.close()
        conn.close()
        print("✅ Database schema created successfully!")
        
    except Exception as e:
        print(f"❌ Error initializing database: {e}")
        traceback.print_exc()

def generate_otp():
    """Generate a random 4-digit OTP"""
    return ''.join(random.choices(string.digits, k=4))

def clean_phone_number(phone_number):
    """Clean and validate phone number"""
    cleaned = ''.join(filter(str.isdigit, phone_number))
    if cleaned.startswith('91') and len(cleaned) == 12:
        cleaned = cleaned[2:]
    return cleaned

def send_sms_otp(phone_number, otp):
    """Send OTP via Fast2SMS API"""
    try:
        message = f"Your Ruchitara verification code is {otp}. Valid for 5 minutes. Do not share this code with anyone."
        payload = {
            'route': 'q',
            'message': message,
            'language': 'english',
            'flash': 0,
            'numbers': phone_number
        }
        headers = {
            'authorization': FAST2SMS_API_KEY,
            'Content-Type': "application/x-www-form-urlencoded",
            'Cache-Control': "no-cache"
        }
        
        print(f"📤 Sending SMS to {phone_number} via Fast2SMS...")
        response = requests.post(FAST2SMS_URL, data=payload, headers=headers)
        response_data = response.json()
        print(f"Fast2SMS Response: {response_data}")
        
        if response_data.get('return') == True:
            print(f"✅ SMS sent successfully to {phone_number}")
            return True, "OTP sent successfully"
        else:
            error_msg = response_data.get('message', 'Failed to send SMS')
            print(f"❌ Fast2SMS Error: {error_msg}")
            return False, f"SMS sending failed: {error_msg}"
            
    except Exception as e:
        print(f"❌ Exception in send_sms_otp: {e}")
        traceback.print_exc()
        return False, f"Error sending SMS: {str(e)}"

# ============================================================================
# TEST ENDPOINT
# ============================================================================

@app.route('/api/test', methods=['GET'])
def test():
    """Test endpoint to verify server is running"""
    return jsonify({
        'success': True,
        'message': 'Server is running!',
        'timestamp': datetime.now().isoformat(),
        'sms_mode': 'TEST - ANY OTP ACCEPTED' if USE_TEST_OTP else 'PRODUCTION'
    })

# ============================================================================
# AUTHENTICATION ENDPOINTS
# ============================================================================

@app.route('/api/auth/send-otp', methods=['POST'])
def send_otp():
    """Send OTP - Creates user profile if doesn't exist"""
    try:
        data = request.json
        phone_number = data.get('phone_number')
        
        if not phone_number:
            return jsonify({'success': False, 'message': 'Phone number is required'}), 400
        
        phone_number = clean_phone_number(phone_number)
        
        if len(phone_number) != 10:
            return jsonify({'success': False, 'message': 'Please enter a valid 10-digit phone number'}), 400
        
        print(f"📱 OTP Request for: {phone_number}")
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Check if user exists
        cur.execute('SELECT phone_number, name, email FROM user_profiles WHERE phone_number = %s', (phone_number,))
        user = cur.fetchone()
        
        # If user doesn't exist, create profile with just phone number
        if not user:
            cur.execute('INSERT INTO user_profiles (phone_number) VALUES (%s)', (phone_number,))
            conn.commit()
            print(f"🆕 Created user profile for: {phone_number}")
        
        cur.close()
        conn.close()
        
        # Generate OTP
        if USE_TEST_OTP:
            otp = TEST_OTP
            print(f"🔑 TEST MODE: Any OTP will be accepted for login")
            sms_sent = True
        else:
            otp = generate_otp()
            print(f"🔑 Generated OTP: {otp}")
            sms_sent, sms_message = send_sms_otp(phone_number, otp)
            if not sms_sent:
                return jsonify({'success': False, 'message': sms_message}), 500
        
        # Store OTP with expiry time (5 minutes)
        otp_storage[phone_number] = {
            'otp': otp,
            'expires_at': datetime.now() + timedelta(minutes=5),
            'attempts': 0
        }
        
        response_data = {
            'success': True,
            'message': 'OTP sent successfully',
            'phone_number': phone_number,
        }
        
        if USE_TEST_OTP:
            response_data['otp'] = otp
            response_data['test_mode'] = True
            response_data['bypass_info'] = 'Any OTP will be accepted'
        
        if user:
            response_data['is_existing_user'] = True
            response_data['has_profile'] = bool(user['name'] and user['email'])
        else:
            response_data['is_existing_user'] = True  # We just created it
            response_data['has_profile'] = False
        
        return jsonify(response_data)
            
    except Exception as e:
        print(f"Error in send_otp: {e}")
        traceback.print_exc()
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/auth/verify-otp', methods=['POST'])
def verify_otp():
    """Verify OTP and log in user - ACCEPTS ANY OTP IN TEST MODE"""
    try:
        data = request.json
        phone_number = data.get('phone_number')
        otp = data.get('otp')
        
        if not phone_number or not otp:
            return jsonify({'success': False, 'message': 'Phone number and OTP are required'}), 400
        
        phone_number = clean_phone_number(phone_number)
        print(f"🔐 Verifying OTP for: {phone_number}")
        
        # ==========================================
        # BYPASS MODE - Accept any OTP in test mode
        # ==========================================
        if USE_TEST_OTP:
            print(f"⚠️ TEST MODE: Accepting any OTP (entered: {otp})")
            # Clean up OTP storage if exists
            if phone_number in otp_storage:
                del otp_storage[phone_number]
        else:
            # Normal OTP verification logic for production
            if phone_number not in otp_storage:
                return jsonify({'success': False, 'message': 'No OTP request found. Please request a new OTP.'}), 400
            
            stored_otp_data = otp_storage[phone_number]
            
            # Check if OTP has expired
            if datetime.now() > stored_otp_data['expires_at']:
                del otp_storage[phone_number]
                return jsonify({'success': False, 'message': 'OTP has expired. Please request a new one.'}), 400
            
            # Check attempts
            if stored_otp_data['attempts'] >= 5:
                del otp_storage[phone_number]
                return jsonify({'success': False, 'message': 'Too many failed attempts. Please request a new OTP.'}), 400
            
            # Verify OTP
            if otp != stored_otp_data['otp']:
                stored_otp_data['attempts'] += 1
                remaining = 5 - stored_otp_data['attempts']
                return jsonify({'success': False, 'message': f'Invalid OTP. {remaining} attempt{"s" if remaining != 1 else ""} remaining.'}), 400
            
            # Clean up on success
            del otp_storage[phone_number]
        
        print(f"✅ OTP verified successfully for: {phone_number}")
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Get or create user
        cur.execute('SELECT * FROM user_profiles WHERE phone_number = %s', (phone_number,))
        user = cur.fetchone()
        
        if not user:
            cur.execute('INSERT INTO user_profiles (phone_number) VALUES (%s) RETURNING *', (phone_number,))
            user = cur.fetchone()
            conn.commit()
            print(f"🆕 Created user profile during verification for: {phone_number}")
        
        cur.close()
        conn.close()
        
        profile_complete = bool(user['name'] and user['email'])
        
        response = {
            'success': True,
            'message': 'Login successful',
            'user': dict(user),
            'requires_profile_setup': not profile_complete
        }
        
        if USE_TEST_OTP:
            response['test_mode'] = True
            response['bypass_used'] = True
        
        return jsonify(response)
        
    except Exception as e:
        print(f"Error in verify_otp: {e}")
        traceback.print_exc()
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/auth/resend-otp', methods=['POST'])
def resend_otp():
    """Resend OTP"""
    try:
        data = request.json
        phone_number = data.get('phone_number')
        
        if not phone_number:
            return jsonify({'success': False, 'message': 'Phone number is required'}), 400
        
        phone_number = clean_phone_number(phone_number)
        print(f"🔄 Resending OTP for: {phone_number}")
        
        if USE_TEST_OTP:
            otp = TEST_OTP
            print(f"🔑 TEST MODE: Any OTP will be accepted")
            sms_sent = True
        else:
            otp = generate_otp()
            print(f"🔑 Generated new OTP: {otp}")
            sms_sent, sms_message = send_sms_otp(phone_number, otp)
            if not sms_sent:
                return jsonify({'success': False, 'message': sms_message}), 500
        
        otp_storage[phone_number] = {
            'otp': otp,
            'expires_at': datetime.now() + timedelta(minutes=5),
            'attempts': 0
        }
        
        response = {'success': True, 'message': 'OTP resent successfully'}
        if USE_TEST_OTP:
            response['otp'] = otp
            response['test_mode'] = True
            response['bypass_info'] = 'Any OTP will be accepted'
        
        return jsonify(response)
        
    except Exception as e:
        print(f"Error in resend_otp: {e}")
        traceback.print_exc()
        return jsonify({'success': False, 'message': str(e)}), 500

# ============================================================================
# DIRECT BYPASS ENDPOINT (Optional - for complete OTP skip)
# ============================================================================

@app.route('/api/auth/bypass-login', methods=['POST'])
def bypass_login():
    """Bypass OTP completely for testing - directly log in with phone number"""
    try:
        data = request.json
        phone_number = data.get('phone_number')
        
        if not phone_number:
            return jsonify({'success': False, 'message': 'Phone number is required'}), 400
        
        phone_number = clean_phone_number(phone_number)
        
        if len(phone_number) != 10:
            return jsonify({'success': False, 'message': 'Please enter a valid 10-digit phone number'}), 400
        
        print(f"🚀 BYPASS LOGIN for: {phone_number}")
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Check if user exists, if not create
        cur.execute('SELECT * FROM user_profiles WHERE phone_number = %s', (phone_number,))
        user = cur.fetchone()
        
        if not user:
            cur.execute('INSERT INTO user_profiles (phone_number) VALUES (%s) RETURNING *', (phone_number,))
            user = cur.fetchone()
            conn.commit()
            print(f"🆕 Created user profile for: {phone_number}")
        
        cur.close()
        conn.close()
        
        profile_complete = bool(user['name'] and user['email'])
        
        return jsonify({
            'success': True,
            'message': 'Login successful (bypassed)',
            'user': dict(user),
            'requires_profile_setup': not profile_complete,
            'bypassed': True
        })
        
    except Exception as e:
        print(f"Error in bypass_login: {e}")
        traceback.print_exc()
        return jsonify({'success': False, 'message': str(e)}), 500

# ============================================================================
# USER PROFILE ENDPOINTS
# ============================================================================

@app.route('/api/profile/<phone_number>', methods=['GET'])
def get_profile(phone_number):
    """Get user profile by phone number"""
    try:
        phone_number = clean_phone_number(phone_number)
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        cur.execute('SELECT * FROM user_profiles WHERE phone_number = %s', (phone_number,))
        user = cur.fetchone()
        
        cur.close()
        conn.close()
        
        if not user:
            return jsonify({'success': False, 'message': 'User not found'}), 404
        
        return jsonify({'success': True, 'user': dict(user)})
    except Exception as e:
        print(f"Error in get_profile: {e}")
        traceback.print_exc()
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/profile/<phone_number>', methods=['PUT'])
def update_profile(phone_number):
    """Update user profile (name, email)"""
    try:
        phone_number = clean_phone_number(phone_number)
        data = request.json
        name = data.get('name')
        email = data.get('email')
        
        if not name or not email:
            return jsonify({'success': False, 'message': 'Name and email are required'}), 400
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        cur.execute('SELECT phone_number FROM user_profiles WHERE phone_number = %s', (phone_number,))
        if not cur.fetchone():
            cur.close()
            conn.close()
            return jsonify({'success': False, 'message': 'User not found'}), 404
        
        cur.execute('''
            UPDATE user_profiles 
            SET name = %s, email = %s, updated_at = CURRENT_TIMESTAMP
            WHERE phone_number = %s
            RETURNING *
        ''', (name, email, phone_number))
        
        user = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()
        
        print(f"✏️ Profile updated for phone: {phone_number}")
        
        return jsonify({'success': True, 'user': dict(user), 'message': 'Profile updated successfully'})
    except Exception as e:
        print(f"Error in update_profile: {e}")
        traceback.print_exc()
        return jsonify({'success': False, 'message': str(e)}), 500

# ============================================================================
# FAVORITES ENDPOINTS
# ============================================================================

@app.route('/api/favorites/<phone_number>', methods=['GET'])
def get_favorites(phone_number):
    """Get user's favorite products"""
    try:
        phone_number = clean_phone_number(phone_number)
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        cur.execute('''
            SELECT f.*, p.name, p.unit_price, p.weight, p.image_url, p.category_id
            FROM favorites f
            JOIN products p ON f.product_id = p.id
            WHERE f.phone_number = %s
            ORDER BY f.created_at DESC
        ''', (phone_number,))
        
        favorites = cur.fetchall()
        cur.close()
        conn.close()
        
        return jsonify({'success': True, 'favorites': [dict(fav) for fav in favorites]})
    except Exception as e:
        print(f"Error in get_favorites: {e}")
        traceback.print_exc()
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/favorites', methods=['POST'])
def add_favorite():
    """Add product to favorites"""
    try:
        data = request.json
        phone_number = clean_phone_number(data.get('phone_number'))
        product_id = data.get('product_id')
        
        if not phone_number or not product_id:
            return jsonify({'success': False, 'message': 'Phone number and Product ID are required'}), 400
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Check if already in favorites
        cur.execute('SELECT id FROM favorites WHERE phone_number = %s AND product_id = %s', (phone_number, product_id))
        if cur.fetchone():
            cur.close()
            conn.close()
            return jsonify({'success': False, 'message': 'Product already in favorites'}), 400
        
        cur.execute('INSERT INTO favorites (phone_number, product_id) VALUES (%s, %s)', (phone_number, product_id))
        conn.commit()
        cur.close()
        conn.close()
        
        print(f"❤️ Added to favorites - Phone: {phone_number}, Product: {product_id}")
        return jsonify({'success': True, 'message': 'Added to favorites'})
    except Exception as e:
        print(f"Error in add_favorite: {e}")
        traceback.print_exc()
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/favorites/<int:favorite_id>', methods=['DELETE'])
def remove_favorite(favorite_id):
    """Remove product from favorites"""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        cur.execute('DELETE FROM favorites WHERE id = %s', (favorite_id,))
        conn.commit()
        cur.close()
        conn.close()
        
        print(f"💔 Removed from favorites: {favorite_id}")
        return jsonify({'success': True, 'message': 'Removed from favorites'})
    except Exception as e:
        print(f"Error in remove_favorite: {e}")
        traceback.print_exc()
        return jsonify({'success': False, 'message': str(e)}), 500

# ============================================================================
# CART ENDPOINTS
# ============================================================================

@app.route('/api/cart/<phone_number>', methods=['GET'])
def get_cart(phone_number):
    """Get user's cart items"""
    try:
        phone_number = clean_phone_number(phone_number)
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        cur.execute('''
            SELECT c.*, p.name, p.unit_price, p.weight, p.image_url,
                   (c.quantity * p.unit_price) as subtotal
            FROM cart_items c
            JOIN products p ON c.product_id = p.id
            WHERE c.phone_number = %s
        ''', (phone_number,))
        
        cart_items = cur.fetchall()
        cur.close()
        conn.close()
        
        return jsonify({'success': True, 'cart_items': [dict(item) for item in cart_items]})
    except Exception as e:
        print(f"Error in get_cart: {e}")
        traceback.print_exc()
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/cart', methods=['POST'])
def add_to_cart():
    """Add item to cart"""
    try:
        data = request.json
        phone_number = clean_phone_number(data.get('phone_number'))
        product_id = data.get('product_id')
        quantity = data.get('quantity', 1)
        
        if not phone_number or not product_id:
            return jsonify({'success': False, 'message': 'Phone number and Product ID are required'}), 400
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Check if product exists
        cur.execute('SELECT id, is_available FROM products WHERE id = %s', (product_id,))
        product = cur.fetchone()
        
        if not product:
            cur.close()
            conn.close()
            return jsonify({'success': False, 'message': 'Product not found'}), 404
        
        if not product['is_available']:
            cur.close()
            conn.close()
            return jsonify({'success': False, 'message': 'Product is not available'}), 400
        
        # Check if item already in cart
        cur.execute('SELECT * FROM cart_items WHERE phone_number = %s AND product_id = %s', (phone_number, product_id))
        existing = cur.fetchone()
        
        if existing:
            cur.execute('UPDATE cart_items SET quantity = quantity + %s, updated_at = CURRENT_TIMESTAMP WHERE phone_number = %s AND product_id = %s', (quantity, phone_number, product_id))
            print(f"🛒 Updated cart - Phone: {phone_number}, Product: {product_id}")
        else:
            cur.execute('INSERT INTO cart_items (phone_number, product_id, quantity) VALUES (%s, %s, %s)', (phone_number, product_id, quantity))
            print(f"🛒 Added to cart - Phone: {phone_number}, Product: {product_id}")
        
        conn.commit()
        cur.close()
        conn.close()
        
        return jsonify({'success': True, 'message': 'Added to cart successfully'})
    except Exception as e:
        print(f"Error in add_to_cart: {e}")
        traceback.print_exc()
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/cart/<int:cart_item_id>', methods=['PUT'])
def update_cart_quantity(cart_item_id):
    """Update cart item quantity"""
    try:
        data = request.json
        quantity = data.get('quantity')
        
        if quantity is None:
            return jsonify({'success': False, 'message': 'Quantity is required'}), 400
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        if quantity <= 0:
            cur.execute('DELETE FROM cart_items WHERE id = %s', (cart_item_id,))
            print(f"🗑️ Removed cart item: {cart_item_id}")
        else:
            cur.execute('UPDATE cart_items SET quantity = %s, updated_at = CURRENT_TIMESTAMP WHERE id = %s', (quantity, cart_item_id))
            print(f"✏️ Updated cart item {cart_item_id} quantity to {quantity}")
        
        conn.commit()
        cur.close()
        conn.close()
        
        return jsonify({'success': True, 'message': 'Cart updated successfully'})
    except Exception as e:
        print(f"Error in update_cart_quantity: {e}")
        traceback.print_exc()
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/cart/<int:cart_item_id>', methods=['DELETE'])
def remove_from_cart(cart_item_id):
    """Remove item from cart"""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        cur.execute('DELETE FROM cart_items WHERE id = %s', (cart_item_id,))
        conn.commit()
        cur.close()
        conn.close()
        
        print(f"🗑️ Removed cart item: {cart_item_id}")
        return jsonify({'success': True, 'message': 'Item removed from cart'})
    except Exception as e:
        print(f"Error in remove_from_cart: {e}")
        traceback.print_exc()
        return jsonify({'success': False, 'message': str(e)}), 500

# ============================================================================
# ORDER ENDPOINTS
# ============================================================================

@app.route('/api/orders/<phone_number>', methods=['GET'])
def get_user_orders(phone_number):
    """Get all orders for a user"""
    try:
        phone_number = clean_phone_number(phone_number)
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        cur.execute('SELECT * FROM orders WHERE phone_number = %s ORDER BY created_at DESC', (phone_number,))
        orders = cur.fetchall()
        
        orders_with_items = []
        for order in orders:
            cur.execute('SELECT * FROM order_items WHERE order_id = %s', (order['id'],))
            items = cur.fetchall()
            order_dict = dict(order)
            order_dict['items'] = [dict(item) for item in items]
            orders_with_items.append(order_dict)
        
        cur.close()
        conn.close()
        
        return jsonify({'success': True, 'orders': orders_with_items})
        
    except Exception as e:
        print(f"Error in get_user_orders: {e}")
        traceback.print_exc()
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/orders', methods=['POST'])
def create_order():
    """Create a new order"""
    try:
        data = request.json
        phone_number = clean_phone_number(data.get('phone_number'))
        items = data.get('items', [])
        delivery_address = data.get('delivery_address')
        payment_method = data.get('payment_method', 'Cash on Delivery')
        
        if not phone_number or not items:
            return jsonify({'success': False, 'message': 'Phone number and items are required'}), 400
        
        if not delivery_address:
            return jsonify({'success': False, 'message': 'Delivery address is required'}), 400
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        total_amount = sum(item['quantity'] * item['unit_price'] for item in items)
        order_number = f"ORD{random.randint(10000, 99999)}"
        
        cur.execute('''
            INSERT INTO orders (order_number, phone_number, status, total_amount, 
                              delivery_address, payment_method)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING *
        ''', (order_number, phone_number, 'Pending', total_amount, delivery_address, payment_method))
        
        order = cur.fetchone()
        
        for item in items:
            cur.execute('''
                INSERT INTO order_items (order_id, product_id, product_name, 
                                       quantity, unit_price, subtotal)
                VALUES (%s, %s, %s, %s, %s, %s)
            ''', (order['id'], item['product_id'], item['name'],
                  item['quantity'], item['unit_price'],
                  item['quantity'] * item['unit_price']))
        
        # Clear cart
        cur.execute('DELETE FROM cart_items WHERE phone_number = %s', (phone_number,))
        
        conn.commit()
        cur.close()
        conn.close()
        
        print(f"📦 Order created - Order ID: {order['id']}, Phone: {phone_number}")
        
        return jsonify({'success': True, 'order': dict(order), 'message': 'Order placed successfully'})
        
    except Exception as e:
        print(f"Error in create_order: {e}")
        traceback.print_exc()
        return jsonify({'success': False, 'message': str(e)}), 500

# ============================================================================
# PRODUCTS ENDPOINTS (unchanged)
# ============================================================================

@app.route('/api/products', methods=['GET'])
def get_products():
    """Get all products"""
    try:
        category = request.args.get('category')
        search = request.args.get('search')
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        query = '''
            SELECT p.*, c.name as category_name 
            FROM products p
            LEFT JOIN categories c ON p.category_id = c.id
            WHERE p.is_available = TRUE
        '''
        params = []
        
        if category:
            query += ' AND c.name = %s'
            params.append(category)
        
        if search:
            query += ' AND p.name ILIKE %s'
            params.append(f'%{search}%')
        
        query += ' ORDER BY p.name'
        
        cur.execute(query, params)
        products = cur.fetchall()
        
        cur.close()
        conn.close()
        
        return jsonify({'success': True, 'products': [dict(p) for p in products]})
    except Exception as e:
        print(f"Error in get_products: {e}")
        traceback.print_exc()
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/categories', methods=['GET'])
def get_categories():
    """Get all categories"""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        cur.execute('SELECT * FROM categories ORDER BY display_order')
        categories = cur.fetchall()
        
        cur.close()
        conn.close()
        
        return jsonify({'success': True, 'categories': [dict(c) for c in categories]})
    except Exception as e:
        print(f"Error in get_categories: {e}")
        traceback.print_exc()
        return jsonify({'success': False, 'message': str(e)}), 500

# ============================================================================
# ERROR HANDLERS
# ============================================================================

@app.errorhandler(404)
def not_found(error):
    return jsonify({'success': False, 'message': 'Endpoint not found'}), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({'success': False, 'message': 'Internal server error'}), 500

# ============================================================================
# RUN SERVER
# ============================================================================

if __name__ == '__main__':
    print("=" * 60)
    print("🚀 Starting Ruchitara Flask Server")
    print("=" * 60)
    print("Database: Render PostgreSQL")
    print("Primary Key: phone_number")
    print(f"SMS Mode: {'TEST (ANY OTP ACCEPTED)' if USE_TEST_OTP else 'PRODUCTION'}")
    print("Port: 8000")
    print("=" * 60)
    
    # Initialize database
    init_database()
    
    # Test database connection
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute('SELECT COUNT(*) as count FROM user_profiles')
        result = cur.fetchone()
        print(f"✅ Users in DB: {result['count']}")
        cur.close()
        conn.close()
    except Exception as e:
        print(f"❌ Database connection failed: {e}")
    
    print("=" * 60)
    app.run(debug=True, host='0.0.0.0', port=8000)
