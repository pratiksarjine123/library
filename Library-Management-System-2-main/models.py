from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime

db = SQLAlchemy()

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(20), nullable=False, default='user') # 'admin' or 'user'
    name = db.Column(db.String(100))
    email = db.Column(db.String(100))
    borrows = db.relationship('BorrowRecord', backref='user', lazy=True, cascade="all, delete-orphan")

class Book(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(250), nullable=False)
    author = db.Column(db.String(200), nullable=False)
    category = db.Column(db.String(100), nullable=False)
    isbn = db.Column(db.String(50))
    total_copies = db.Column(db.Integer, default=1)
    available_copies = db.Column(db.Integer, default=1)
    added_date = db.Column(db.DateTime, default=datetime.utcnow)
    borrows = db.relationship('BorrowRecord', backref='book', lazy=True)

class BorrowRecord(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    book_id = db.Column(db.Integer, db.ForeignKey('book.id'), nullable=False)
    borrow_date = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    due_date = db.Column(db.DateTime, nullable=False)
    return_date = db.Column(db.DateTime, nullable=True)
    status = db.Column(db.String(20), default='borrowed') # 'borrowed', 'returned'
    fine_amount = db.Column(db.Float, default=0.0)

class BookRequest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    book_id = db.Column(db.Integer, db.ForeignKey('book.id'), nullable=False)
    request_date = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(20), default='pending')  # 'pending', 'accepted', 'rejected'
    admin_note = db.Column(db.String(300), nullable=True)
    days_requested = db.Column(db.Integer, default=14)
    user = db.relationship('User', backref=db.backref('book_requests', lazy=True, cascade="all, delete-orphan"))
    book = db.relationship('Book', backref=db.backref('book_requests', lazy=True, cascade="all, delete-orphan"))
