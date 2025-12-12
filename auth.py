"""
Authentication Module
Handles user authentication and session management
"""

import streamlit as st
import json
import uuid
from datetime import datetime, timedelta
import os
from settings import USERS
from database import get_user

REMEMBER_FILE = "remember_tokens.json"


def _load_tokens():
    """Load remember tokens from file"""
    if not os.path.exists(REMEMBER_FILE):
        return {}
    try:
        with open(REMEMBER_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_tokens(tokens: dict):
    """Persist tokens to file"""
    try:
        with open(REMEMBER_FILE, "w", encoding="utf-8") as f:
            json.dump(tokens, f)
    except Exception:
        pass


def create_remember_token(username, days_valid=30):
    """Create and persist a remember token for username"""
    token = str(uuid.uuid4())
    expires_at = (datetime.utcnow() + timedelta(days=days_valid)).isoformat()
    tokens = _load_tokens()
    tokens[token] = {"username": username, "expires_at": expires_at}
    _save_tokens(tokens)
    return token


def get_username_from_token(token: str):
    """Return username if token is valid and not expired"""
    if not token:
        return None
    tokens = _load_tokens()
    info = tokens.get(token)
    if not info:
        return None
    try:
        expires_at = datetime.fromisoformat(info.get("expires_at", ""))
        if datetime.utcnow() > expires_at:
            # expired, remove
            tokens.pop(token, None)
            _save_tokens(tokens)
            return None
    except Exception:
        return None
    return info.get("username")


def remove_token(token: str):
    """Delete a remember token"""
    if not token:
        return
    tokens = _load_tokens()
    if token in tokens:
        tokens.pop(token, None)
        _save_tokens(tokens)


def check_login(username, password):
    """
    Check if username and password are valid
    
    Args:
        username: Username
        password: Password
        
    Returns:
        bool: True if valid, False otherwise
    """
    # First, try to fetch from database
    db_user = get_user(username)
    if db_user and db_user.get('password') == password:
        return True

    # Fallback to config (in case DB not initialized)
    return username in USERS and USERS[username] == password


def get_current_user():
    """
    Get current logged-in user from session state
    
    Returns:
        str: Username or None if not logged in
    """
    return st.session_state.get('username', None)


def is_logged_in():
    """
    Check if user is logged in
    
    Returns:
        bool: True if logged in, False otherwise
    """
    return 'username' in st.session_state and st.session_state['username'] is not None


def login(username, password):
    """
    Login user and set session state
    
    Args:
        username: Username
        password: Password
        
    Returns:
        bool: True if login successful, False otherwise
    """
    if check_login(username, password):
        st.session_state['username'] = username
        return True
    return False


def logout():
    """Logout user and clear session state + remember token"""
    # Clear remembered token in URL and file
    params = st.query_params
    token_val = params.get("remember_token")
    token = token_val[0] if isinstance(token_val, list) else token_val
    if token:
        remove_token(token)
        # Clear query params
        st.query_params.clear()

    # Clear session
    if 'username' in st.session_state:
        del st.session_state['username']


def is_admin():
    """
    Check if current user is admin
    
    Returns:
        bool: True if user is admin, False otherwise
    """
    username = get_current_user()
    return username == 'admin'


def is_store_user():
    """
    Check if current user is a store user.
    First checks database flag, then falls back to username pattern.
    
    Returns:
        bool: True if user is a store user, False otherwise
    """
    username = get_current_user()
    if not username:
        return False
    
    # Check database first
    try:
        from database import get_user
        user = get_user(username)
        if user and user.get('is_store'):
            return True
    except Exception as e:
        print(f"Error checking store user from database: {e}")
    
    # Fallback to username pattern (for backward compatibility)
    return username.startswith('cuahang')


def get_store_name_from_username(username):
    """
    Get store name from username.
    For store users, returns formatted store name.
    
    Args:
        username: Username string
        
    Returns:
        str: Store name or None if not a store user
    """
    if not username:
        return None
    
    # Check if it's a store user
    if not is_store_user():
        return None
    
    # Try DB first
    try:
        user = get_user(username)
        if user and user.get('store_name'):
            return user.get('store_name')
    except Exception:
        pass
    
    # Fallback to username pattern
    if username.startswith('cuahang'):
        try:
            store_num = username.replace('cuahang', '')
            return f"Cửa hàng {store_num}"
        except:
            return None
    
    # For other store users, use username as store name
    return username


def require_login():
    """
    Show login form if user is not logged in
    Returns True if user is logged in, False otherwise
    """
    # 1) Auto login if remember_token is valid
    if not is_logged_in():
        params = st.query_params
        token_val = params.get("remember_token")
        token = token_val[0] if isinstance(token_val, list) else token_val
        remembered_user = get_username_from_token(token) if token else None
        if remembered_user:
            st.session_state['username'] = remembered_user
            return True

    # 2) If still not logged in, show form
    if not is_logged_in():
        st.title("🔐 Đăng Nhập")
        
        with st.form("login_form"):
            username = st.text_input("Tên đăng nhập")
            password = st.text_input("Mật khẩu", type="password")
            submit = st.form_submit_button("Đăng nhập")
            
            if submit:
                if login(username, password):
                    # always remember login (no checkbox)
                    token = create_remember_token(username)
                    st.query_params.clear()
                    st.query_params["remember_token"] = token
                    st.success("Đăng nhập thành công!")
                    st.rerun()
                else:
                    st.error("Tên đăng nhập hoặc mật khẩu không đúng!")
        
        return False
    return True

