from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime, timedelta
import json

db = SQLAlchemy()

class User(UserMixin, db.Model):
    """User model for authentication and profile management"""
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(100), unique=True, nullable=False)
    name = db.Column(db.String(1000), nullable=False)
    child_name = db.Column(db.String(100), nullable=True)
    profile_picture = db.Column(db.String(200), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    conversations = db.relationship('Conversation', backref='user', lazy=True, cascade='all, delete-orphan')
    
    def to_dict(self):
        return {
            'id': self.id,
            'email': self.email,
            'name': self.name,
            'child_name': self.child_name,
            'profile_picture': self.profile_picture,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat()
        }

class Conversation(db.Model):
    """Conversation model to track user sessions and analytics"""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    session_id = db.Column(db.String(100), nullable=False, index=True)
    
    # Session metadata
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
        self.conversation_history = json.dumps(data)
    
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
        self.amber_responses = json.dumps(data)
    
    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'session_id': self.session_id,
            'sentences_count': self.sentences_count,
            'good_response_count': self.good_response_count,
            'reward_points': self.reward_points,
            'duration_minutes': round(self.duration_minutes, 1),
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat(),
            'ended_at': self.ended_at.isoformat() if self.ended_at else None
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