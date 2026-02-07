import os
import json
from flask import Blueprint, request, redirect, url_for, session, flash, jsonify
from flask_login import login_user, logout_user, login_required, current_user
from authlib.integrations.flask_client import OAuth
from models import User, db
import secrets

auth_bp = Blueprint('auth', __name__)

def init_oauth(app):
    """Initialize OAuth with the Flask app"""
    oauth = OAuth(app)
    
    google = oauth.register(
        name='google',
        client_id=os.getenv('GOOGLE_CLIENT_ID'),
        client_secret=os.getenv('GOOGLE_CLIENT_SECRET'),
        server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
        client_kwargs={
            'scope': 'openid email profile'
        }
    )
    
    return oauth, google

# These will be set by the main app
oauth = None
google = None

@auth_bp.route('/login')
def login():
    """Initiate Google OAuth login"""
    if not google:
        return jsonify({'error': 'OAuth not configured'}), 500
    
    # Generate a random nonce for security
    nonce = secrets.token_urlsafe()
    session['oauth_nonce'] = nonce
    
    redirect_uri = url_for('auth.callback', _external=True)
    # Force HTTPS for ngrok (required by Google OAuth for non-localhost)
    if 'ngrok' in request.host:
        redirect_uri = redirect_uri.replace('http://', 'https://')
    return google.authorize_redirect(redirect_uri, nonce=nonce)

@auth_bp.route('/callback')
def callback():
    """Handle OAuth callback"""
    if not google:
        return jsonify({'error': 'OAuth not configured'}), 500
    
    try:
        # Get the access token
        token = google.authorize_access_token()
        
        # Verify nonce for security
        if 'oauth_nonce' in session:
            nonce = session.pop('oauth_nonce')
            user_info = token.get('userinfo')
            if user_info and user_info.get('nonce') != nonce:
                flash('Authentication failed. Please try again.', 'error')
                return redirect(url_for('home'))
        
        # Get user information
        user_info = token.get('userinfo')
        if not user_info:
            flash('Failed to get user information from Google.', 'error')
            return redirect(url_for('home'))
        
        # Find or create user
        user = User.query.filter_by(email=user_info['email']).first()
        
        if not user:
            # Create new user
            user = User(
                email=user_info['email'],
                name=user_info.get('name', ''),
                profile_picture=user_info.get('picture', '')
            )
            db.session.add(user)
            db.session.commit()
            
            # New user - redirect to profile setup
            login_user(user, remember=True)
            return redirect(url_for('profile_setup'))
        else:
            # Existing user - update profile picture if changed
            if user_info.get('picture') and user.profile_picture != user_info.get('picture'):
                user.profile_picture = user_info.get('picture')
                db.session.commit()
            
            # Login existing user
            login_user(user, remember=True)
            
            # Check if they need to set child name
            if not user.child_name:
                return redirect(url_for('profile_setup'))
            else:
                return redirect(url_for('conversation_select'))
    
    except Exception as e:
        print(f"OAuth callback error: {e}")
        flash('Authentication failed. Please try again.', 'error')
        return redirect(url_for('home'))

@auth_bp.route('/logout')
@login_required
def logout():
    """Logout the current user"""
    logout_user()
    flash('You have been logged out successfully.', 'success')
    return redirect(url_for('home'))

@auth_bp.route('/api/user')
@login_required
def get_user_info():
    """API endpoint to get current user information"""
    from models import Conversation
    user_dict = current_user.to_dict()
    # Check if user has started any conversations
    user_dict['has_conversations'] = Conversation.query.filter_by(
        user_id=current_user.id
    ).first() is not None
    user_dict['available_stars'] = current_user.available_stars
    user_dict['stars_spent'] = current_user.stars_spent or 0
    return jsonify(user_dict)

@auth_bp.route('/api/user/child-name', methods=['POST'])
@login_required
def update_child_name():
    """API endpoint to update child profile (name, age, gender)"""
    try:
        data = request.get_json()
        child_name = data.get('child_name', '').strip()
        child_age = data.get('child_age')
        child_gender = data.get('child_gender', '').strip()

        # Validate child name
        if not child_name:
            return jsonify({'error': 'Child name is required'}), 400

        if len(child_name) > 100:
            return jsonify({'error': 'Child name is too long'}), 400

        # Validate child age
        if not child_age:
            return jsonify({'error': 'Child age is required'}), 400

        try:
            child_age = int(child_age)
            if child_age < 1 or child_age > 18:
                return jsonify({'error': 'Child age must be between 1 and 18'}), 400
        except (ValueError, TypeError):
            return jsonify({'error': 'Invalid age format'}), 400

        # Validate child gender
        if not child_gender:
            return jsonify({'error': 'Child gender is required'}), 400

        if child_gender.lower() not in ['male', 'female']:
            return jsonify({'error': 'Invalid gender selection'}), 400

        # Store name as-is (Hindi names don't need English capitalization)
        formatted_name = child_name.strip()
        formatted_gender = child_gender.lower()

        # Update user profile
        current_user.child_name = formatted_name
        current_user.child_age = child_age
        current_user.child_gender = formatted_gender
        db.session.commit()

        return jsonify({
            'success': True,
            'child_name': formatted_name,
            'child_age': child_age,
            'child_gender': formatted_gender
        })

    except Exception as e:
        print(f"Error updating child profile: {e}")
        return jsonify({'error': 'Failed to update child profile'}), 500