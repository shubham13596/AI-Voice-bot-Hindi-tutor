from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime, timedelta
import json

db = SQLAlchemy()


class Educator(db.Model):
    """Educator/school that provides custom conversation topics"""
    id = db.Column(db.Integer, primary_key=True)
    short_code = db.Column(db.String(20), unique=True, nullable=False, index=True)
    name = db.Column(db.String(200), nullable=False)
    display_name_hindi = db.Column(db.String(200), nullable=True)
    logo_url = db.Column(db.String(500), nullable=True)
    brand_color = db.Column(db.String(7), default='#4F46E5')
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    topics = db.relationship('EducatorTopic', backref='educator', lazy=True, cascade='all, delete-orphan')

    def to_dict(self):
        return {
            'id': self.id,
            'short_code': self.short_code,
            'name': self.name,
            'display_name_hindi': self.display_name_hindi,
            'logo_url': self.logo_url,
            'brand_color': self.brand_color,
            'is_active': self.is_active,
        }


class EducatorTopic(db.Model):
    """Custom conversation topic created by an educator"""
    id = db.Column(db.Integer, primary_key=True)
    educator_id = db.Column(db.Integer, db.ForeignKey('educator.id'), nullable=False)
    topic_key = db.Column(db.String(100), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    name_hindi = db.Column(db.String(200), nullable=True)
    description = db.Column(db.String(500), nullable=False)
    icon = db.Column(db.String(10), default='📚')
    topic_focus = db.Column(db.Text, nullable=False)
    key_vocabulary = db.Column(db.Text, nullable=True)  # JSON array
    prompt_initial = db.Column(db.Text, nullable=True)  # Full initial prompt (like TOPIC_*_INITIAL_SPECIFIC)
    prompt_conversation = db.Column(db.Text, nullable=True)  # Full conversation prompt (like TOPIC_*_CONVERSATION_SPECIFIC)
    display_order = db.Column(db.Integer, default=0)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    @property
    def full_key(self):
        return f"edu_{self.educator_id}_{self.topic_key}"

    def to_dict(self):
        return {
            'id': self.id,
            'educator_id': self.educator_id,
            'topic_key': self.topic_key,
            'full_key': self.full_key,
            'name': self.name,
            'name_hindi': self.name_hindi,
            'description': self.description,
            'icon': self.icon,
            'topic_focus': self.topic_focus,
            'key_vocabulary': json.loads(self.key_vocabulary) if self.key_vocabulary else [],
            'display_order': self.display_order,
            'is_active': self.is_active,
        }

class User(UserMixin, db.Model):
    """User model for authentication and profile management"""
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(100), unique=True, nullable=False)
    name = db.Column(db.String(1000), nullable=False)
    child_name = db.Column(db.String(100), nullable=True)
    child_age = db.Column(db.Integer, nullable=True)
    child_gender = db.Column(db.String(10), nullable=True)
    profile_picture = db.Column(db.String(200), nullable=True)
    stars_spent = db.Column(db.Integer, default=0)
    transliteration_enabled = db.Column(db.Boolean, default=False)
    educator_code = db.Column(db.String(20), nullable=True, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    conversations = db.relationship('Conversation', backref='user', lazy=True, cascade='all, delete-orphan')
    stickers = db.relationship('UserSticker', backref='user', lazy=True)

    @property
    def reward_points(self):
        """Calculate total reward points from all conversations"""
        return sum(conv.reward_points for conv in self.conversations)

    @property
    def available_stars(self):
        """Spendable stars = total earned minus spent"""
        return self.reward_points - (self.stars_spent or 0)

    def to_dict(self):
        return {
            'id': self.id,
            'email': self.email,
            'name': self.name,
            'child_name': self.child_name,
            'child_age': self.child_age,
            'child_gender': self.child_gender,
            'profile_picture': self.profile_picture,
            'reward_points': self.reward_points,
            'available_stars': self.available_stars,
            'stars_spent': self.stars_spent or 0,
            'transliteration_enabled': self.transliteration_enabled or False,
            'educator_code': self.educator_code,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat()
        }

class UserSticker(db.Model):
    """Tracks which stickers a user has collected"""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    sticker_id = db.Column(db.String(50), nullable=False)
    tier = db.Column(db.String(20), nullable=False)
    unlocked_at = db.Column(db.DateTime, default=datetime.utcnow)


class Conversation(db.Model):
    """Conversation model to track user sessions and analytics"""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    session_id = db.Column(db.String(500), nullable=False, index=True)
    
    # Session metadata
    conversation_type = db.Column(db.String(100), default='everyday', nullable=False)
    sentences_count = db.Column(db.Integer, default=0)
    good_response_count = db.Column(db.Integer, default=0)
    reward_points = db.Column(db.Integer, default=0)
    
    # Conversation data
    conversation_history = db.Column(db.Text, nullable=True)  # JSON string
    amber_responses = db.Column(db.Text, nullable=True)  # JSON string
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    ended_at = db.Column(db.DateTime, nullable=True)
    
    # Computed properties
    @property
    def duration_minutes(self):
        """Calculate conversation duration in minutes"""
        if self.ended_at:
            return (self.ended_at - self.created_at).total_seconds() / 60
        return (datetime.utcnow() - self.created_at).total_seconds() / 60
    
    @property 
    def conversation_data(self):
        """Parse conversation history from JSON"""
        if self.conversation_history:
            try:
                return json.loads(self.conversation_history)
            except json.JSONDecodeError:
                return []
        return []
    
    @conversation_data.setter
    def conversation_data(self, data):
        """Set conversation history as JSON"""
        self.conversation_history = json.dumps(data, ensure_ascii=False)
    
    @property
    def amber_data(self):
        """Parse amber responses from JSON"""
        if self.amber_responses:
            try:
                return json.loads(self.amber_responses)
            except json.JSONDecodeError:
                return []
        return []
    
    @amber_data.setter
    def amber_data(self, data):
        """Set amber responses as JSON"""
        self.amber_responses = json.dumps(data, ensure_ascii=False)
    
    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'session_id': self.session_id,
            'conversation_type': self.conversation_type,
            'sentences_count': self.sentences_count,
            'good_response_count': self.good_response_count,
            'reward_points': self.reward_points,
            'duration_minutes': round(self.duration_minutes, 1),
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat(),
            'ended_at': self.ended_at.isoformat() if self.ended_at else None
        }

class ConversationAudio(db.Model):
    """Audio recordings linked to conversations (kid audio now, bot TTS in Phase 2)"""
    id = db.Column(db.Integer, primary_key=True)
    conversation_id = db.Column(db.Integer, db.ForeignKey('conversation.id'), nullable=False)
    turn_index = db.Column(db.Integer, nullable=False)
    role = db.Column(db.String(20), nullable=False)  # 'user' or 'assistant'
    s3_key = db.Column(db.String(500), nullable=False)
    audio_format = db.Column(db.String(20), default='webm')
    file_size_bytes = db.Column(db.Integer, nullable=True)
    upload_status = db.Column(db.String(20), default='pending')  # pending / uploaded / failed
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    conversation = db.relationship('Conversation', backref='audio_files')

    def to_dict(self):
        return {
            'id': self.id,
            'conversation_id': self.conversation_id,
            'turn_index': self.turn_index,
            'role': self.role,
            's3_key': self.s3_key,
            'audio_format': self.audio_format,
            'file_size_bytes': self.file_size_bytes,
            'upload_status': self.upload_status,
            'created_at': self.created_at.isoformat(),
        }


class AnalyticsHelper:
    """Helper class for generating user analytics"""
    
    @staticmethod
    def get_weekly_stats(user_id, weeks_ago=0):
        """
        Get conversation statistics for a specific week
        weeks_ago: 0 = this week, 1 = last week, etc.
        """
        # Calculate the start and end of the target week
        today = datetime.now().date()
        days_since_monday = today.weekday()
        current_week_start = today - timedelta(days=days_since_monday)
        
        target_week_start = current_week_start - timedelta(weeks=weeks_ago)
        target_week_end = target_week_start + timedelta(days=6)
        
        # Convert to datetime for database query
        week_start = datetime.combine(target_week_start, datetime.min.time())
        week_end = datetime.combine(target_week_end, datetime.max.time())
        
        # Query conversations in the target week
        conversations = Conversation.query.filter(
            Conversation.user_id == user_id,
            Conversation.created_at >= week_start,
            Conversation.created_at <= week_end
        ).all()
        
        # Calculate statistics
        total_sentences = sum(conv.sentences_count for conv in conversations)
        total_points = sum(conv.reward_points for conv in conversations)
        active_days = len(set(conv.created_at.date() for conv in conversations))
        total_conversations = len(conversations)
        
        return {
            'week_start': target_week_start.strftime('%Y-%m-%d'),
            'week_end': target_week_end.strftime('%Y-%m-%d'),
            'total_sentences': total_sentences,
            'total_points': total_points,
            'active_days': active_days,
            'total_conversations': total_conversations,
            'avg_sentences_per_day': round(total_sentences / max(active_days, 1), 1)
        }
    
    @staticmethod
    def get_comparison_stats(user_id):
        """Get this week vs last week comparison"""
        this_week = AnalyticsHelper.get_weekly_stats(user_id, 0)
        last_week = AnalyticsHelper.get_weekly_stats(user_id, 1)
        
        return {
            'this_week': this_week,
            'last_week': last_week,
            'improvements': {
                'sentences': this_week['total_sentences'] - last_week['total_sentences'],
                'points': this_week['total_points'] - last_week['total_points'],
                'active_days': this_week['active_days'] - last_week['active_days']
            }
        }

class PageView(db.Model):
    """Track page visits for analytics funnel analysis"""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)  # Nullable for anonymous users
    session_id = db.Column(db.String(500), nullable=False, index=True)  # Browser session ID
    page = db.Column(db.String(100), nullable=False, index=True)  # e.g., 'landing', 'conversation-select', 'conversation'
    url_path = db.Column(db.String(500), nullable=False)  # Full URL path
    referrer = db.Column(db.String(500), nullable=True)  # HTTP referrer
    user_agent = db.Column(db.String(500), nullable=True)  # Browser info
    ip_address = db.Column(db.String(45), nullable=True)  # User IP (IPv4/IPv6)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    
    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'session_id': self.session_id,
            'page': self.page,
            'url_path': self.url_path,
            'referrer': self.referrer,
            'created_at': self.created_at.isoformat()
        }

class UserAction(db.Model):
    """Track specific user actions for conversion analysis"""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)  # Nullable for anonymous users
    session_id = db.Column(db.String(500), nullable=False, index=True)
    action = db.Column(db.String(100), nullable=False, index=True)  # e.g., 'gmail_login_click', 'conversation_start'
    page = db.Column(db.String(100), nullable=False)  # Page where action occurred
    action_metadata = db.Column(db.Text, nullable=True)  # JSON for additional action data
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    
    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'session_id': self.session_id,
            'action': self.action,
            'page': self.page,
            'action_metadata': self.action_metadata,
            'created_at': self.created_at.isoformat()
        }

class FunnelAnalytics:
    """Helper class for user funnel analytics and admin dashboard"""
    
    @staticmethod
    def get_funnel_stats(start_date=None, end_date=None):
        """Get complete funnel conversion stats"""
        if not start_date:
            start_date = datetime.utcnow() - timedelta(days=30)
        if not end_date:
            end_date = datetime.utcnow()
        
        # Step 1: Landing page visits
        landing_visits = PageView.query.filter(
            PageView.page == 'landing',
            PageView.created_at >= start_date,
            PageView.created_at <= end_date
        ).count()
        
        # Step 2: Gmail login clicks
        gmail_clicks = UserAction.query.filter(
            UserAction.action == 'gmail_login_click',
            UserAction.created_at >= start_date,
            UserAction.created_at <= end_date
        ).count()
        
        # Step 3: Users reaching conversation-select
        conversation_select_visits = PageView.query.filter(
            PageView.page == 'conversation-select',
            PageView.created_at >= start_date,
            PageView.created_at <= end_date
        ).count()
        
        # Step 4: Users reaching conversation page
        conversation_visits = PageView.query.filter(
            PageView.page == 'conversation',
            PageView.created_at >= start_date,
            PageView.created_at <= end_date
        ).count()
        
        # Calculate conversion rates
        gmail_conversion = (gmail_clicks / max(landing_visits, 1)) * 100
        select_conversion = (conversation_select_visits / max(gmail_clicks, 1)) * 100
        conversation_conversion = (conversation_visits / max(conversation_select_visits, 1)) * 100
        overall_conversion = (conversation_visits / max(landing_visits, 1)) * 100
        
        return {
            'period': f"{start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}",
            'funnel': {
                'landing_visits': landing_visits,
                'gmail_clicks': gmail_clicks,
                'conversation_select_visits': conversation_select_visits,
                'conversation_visits': conversation_visits
            },
            'conversion_rates': {
                'landing_to_gmail': round(gmail_conversion, 2),
                'gmail_to_select': round(select_conversion, 2),
                'select_to_conversation': round(conversation_conversion, 2),
                'overall': round(overall_conversion, 2)
            }
        }
    
    @staticmethod
    def get_user_activity_stats(user_id):
        """Get detailed activity stats for a specific user"""
        user = User.query.get(user_id)
        if not user:
            return None
        
        # Get all conversations
        conversations = Conversation.query.filter(Conversation.user_id == user_id).all()
        
        # Get page views
        page_views = PageView.query.filter(PageView.user_id == user_id).count()
        
        # Get actions
        actions = UserAction.query.filter(UserAction.user_id == user_id).count()
        
        # Calculate conversation frequency
        if conversations:
            first_conversation = min(conv.created_at for conv in conversations)
            last_conversation = max(conv.created_at for conv in conversations)
            days_active = (last_conversation - first_conversation).days + 1
            conversation_frequency = len(conversations) / max(days_active, 1)
        else:
            conversation_frequency = 0
        
        # Get conversation types breakdown
        conversation_types = {}
        for conv in conversations:
            conv_type = conv.conversation_type
            if conv_type not in conversation_types:
                conversation_types[conv_type] = 0
            conversation_types[conv_type] += 1
        
        return {
            'user': user.to_dict(),
            'activity': {
                'total_conversations': len(conversations),
                'total_page_views': page_views,
                'total_actions': actions,
                'conversation_frequency_per_day': round(conversation_frequency, 2),
                'conversation_types': conversation_types,
                'total_sentences': sum(conv.sentences_count for conv in conversations),
                'total_points': sum(conv.reward_points for conv in conversations),
                'avg_conversation_duration': round(sum(conv.duration_minutes for conv in conversations) / max(len(conversations), 1), 1)
            }
        }