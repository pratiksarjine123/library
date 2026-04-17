import os
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from models import db, User, Book, BorrowRecord, BookRequest

app = Flask(__name__)
app.config['SECRET_KEY'] = 'pratik_library_secret_key_2026'
# Use an absolute path for local SQLite database
basedir = os.path.abspath(os.path.dirname(__name__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'library.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)

login_manager = LoginManager()
login_manager.login_view = 'login'
login_manager.init_app(app)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Initialize database with a default admin user
with app.app_context():
    db.create_all()
    if not User.query.filter_by(username='admin').first():
        admin = User(
            username='admin',
            password_hash=generate_password_hash('admin', method='pbkdf2:sha256'),
            role='admin',
            name='Administrator'
        )
        db.session.add(admin)
        db.session.commit()

# --- Helpers ---
def calculate_fine(due_date):
    if datetime.utcnow() > due_date:
        days_late = (datetime.utcnow() - due_date).days
        return days_late * 5.0  # 5 units penalty per day late
    return 0.0

def calculate_active_fines(borrows):
    # Dynamically update fines for active borrows to display in UI
    for b in borrows:
        if b.status == 'borrowed':
            b.fine_amount = calculate_fine(b.due_date)
    return borrows

# --- Routes ---

@app.route('/', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        if current_user.role == 'admin':
            return redirect(url_for('admin_dashboard'))
        else:
            return redirect(url_for('user_dashboard'))
            
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            if user.role == 'admin':
                return redirect(url_for('admin_dashboard'))
            else:
                return redirect(url_for('user_dashboard'))
        else:
            flash('Login Failed. Please check username and password.', 'error')
            
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/admin/add_fine/<int:borrow_id>', methods=['POST'])
@login_required
def add_manual_fine(borrow_id):
    if current_user.role != 'admin':
        return redirect(url_for('user_dashboard'))
    
    borrow_record = BorrowRecord.query.get_or_404(borrow_id)
    fine_val = float(request.form.get('fine_amount', 0))
    # We can either add to existing or set absolute. User said "how much to fine is on admin", so let's set it.
    borrow_record.fine_amount = fine_val
    db.session.commit()
    flash(f'Fine of ₹{fine_val} updated for {borrow_record.user.name}.', 'success')
    return redirect(url_for('admin_dashboard', user_filter=borrow_record.user_id))

@app.route('/admin_dashboard')
@login_required
def admin_dashboard():
    if current_user.role != 'admin':
        return redirect(url_for('user_dashboard'))
    
    users = User.query.filter_by(role='user').all()
    books = Book.query.all()
    
    # Check if we are filtering by a specific user for issued books
    user_filter_id = request.args.get('user_filter')
    if user_filter_id:
        all_borrows = BorrowRecord.query.filter_by(user_id=user_filter_id).order_by(BorrowRecord.borrow_date.desc()).all()
    else:
        all_borrows = BorrowRecord.query.order_by(BorrowRecord.borrow_date.desc()).all()
        
    calculate_active_fines(all_borrows)
    
    # Fetch pending book requests for admin
    pending_requests = BookRequest.query.filter_by(status='pending').order_by(BookRequest.request_date.desc()).all()
    
    return render_template('admin_dashboard.html', users=users, books=books, borrows=all_borrows, active_filter_id=user_filter_id, pending_requests=pending_requests)

@app.route('/user_dashboard')
@login_required
def user_dashboard():
    if current_user.role == 'admin':
        return redirect(url_for('admin_dashboard'))
        
    query = request.args.get('search', '')
    if query:
        books = Book.query.filter(Book.title.ilike(f'%{query}%') | Book.author.ilike(f'%{query}%')).all()
    else:
        books = Book.query.all()
        
    my_borrows = BorrowRecord.query.filter_by(user_id=current_user.id).all()
    calculate_active_fines(my_borrows)
    total_fine = sum(b.fine_amount for b in my_borrows if (b.status == 'borrowed' or (b.status == 'returned' and b.fine_amount > 0)))
    
    # Fetch this user's book requests
    my_requests = BookRequest.query.filter_by(user_id=current_user.id).order_by(BookRequest.request_date.desc()).all()
    
    return render_template('user_dashboard.html', books=books, borrows=my_borrows, search=query, total_fine=total_fine, my_requests=my_requests)

@app.route('/admin/add_book', methods=['POST'])
@login_required
def add_book():
    if current_user.role != 'admin':
        return redirect(url_for('user_dashboard'))
        
    title = request.form.get('title')
    author = request.form.get('author')
    category = request.form.get('category')
    copies = int(request.form.get('copies', 1))
    
    new_book = Book(title=title, author=author, category=category, total_copies=copies, available_copies=copies)
    db.session.add(new_book)
    db.session.commit()
    flash('Book added successfully!', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/edit_book/<int:book_id>', methods=['POST'])
@login_required
def edit_book(book_id):
    if current_user.role != 'admin':
        return redirect(url_for('user_dashboard'))
    
    book = Book.query.get_or_404(book_id)
    book.title = request.form.get('title')
    book.author = request.form.get('author')
    book.category = request.form.get('category')
    
    # Adjust available copies if total copies changed
    new_total = int(request.form.get('copies', book.total_copies))
    diff = new_total - book.total_copies
    book.total_copies = new_total
    book.available_copies += diff
    
    db.session.commit()
    flash('Book updated successfully!', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/delete_book/<int:book_id>', methods=['POST'])
@login_required
def delete_book(book_id):
    if current_user.role != 'admin':
        return redirect(url_for('user_dashboard'))
    
    book = Book.query.get_or_404(book_id)
    # Check if any copies are borrowed
    if book.available_copies < book.total_copies:
        flash('Cannot delete book while some copies are borrowed.', 'error')
    else:
        db.session.delete(book)
        db.session.commit()
        flash('Book deleted successfully!', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/add_user', methods=['POST'])
@login_required
def add_user():
    if current_user.role != 'admin':
        return redirect(url_for('user_dashboard'))
        
    username = request.form.get('username')
    password = request.form.get('password')
    name = request.form.get('name')
    
    if User.query.filter_by(username=username).first():
        flash('Username already exists.', 'error')
    else:
        new_user = User(
            username=username,
            name=name,
            password_hash=generate_password_hash(password, method='pbkdf2:sha256'),
            role='user'
        )
        db.session.add(new_user)
        db.session.commit()
        flash('User registered successfully!', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/edit_user/<int:user_id>', methods=['POST'])
@login_required
def edit_user(user_id):
    if current_user.role != 'admin':
        return redirect(url_for('user_dashboard'))
    
    user = User.query.get_or_404(user_id)
    user.name = request.form.get('name')
    user.username = request.form.get('username')
    
    password = request.form.get('password')
    if password:
        user.password_hash = generate_password_hash(password, method='pbkdf2:sha256')
        
    db.session.commit()
    flash('User profile updated!', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/delete_user/<int:user_id>', methods=['POST'])
@login_required
def delete_user(user_id):
    if current_user.role != 'admin':
        return redirect(url_for('user_dashboard'))
    
    user = User.query.get_or_404(user_id)
    # Delete any pending or existing book requests for this user
    BookRequest.query.filter_by(user_id=user.id).delete()
    # Check if user has active borrows
    active_borrows = BorrowRecord.query.filter_by(user_id=user.id, status='borrowed').first()
    if active_borrows:
        flash('Cannot delete user with active borrowed books.', 'error')
        return redirect(url_for('admin_dashboard'))
    
    db.session.delete(user)
    db.session.commit()
    flash('User and related requests deleted successfully!', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/assign_book', methods=['POST'])
@login_required
def assign_book():
    if current_user.role != 'admin':
        return redirect(url_for('user_dashboard'))
    
    user_id = request.form.get('user_id')
    book_id = request.form.get('book_id')
    days = int(request.form.get('days', 14))
    
    book = Book.query.get_or_404(book_id)
    if book.available_copies > 0:
        book.available_copies -= 1
        due_date = datetime.utcnow() + timedelta(days=days)
        borrow_record = BorrowRecord(user_id=user_id, book_id=book.id, due_date=due_date)
        db.session.add(borrow_record)
        db.session.commit()
        flash('Book assigned to user successfully!', 'success')
    else:
        flash('No copies available for assignment.', 'error')
        
    return redirect(url_for('admin_dashboard'))

@app.route('/return/<int:borrow_id>', methods=['POST'])
@login_required
def return_book(borrow_id):
    borrow_record = BorrowRecord.query.get_or_404(borrow_id)
    if borrow_record.user_id != current_user.id and current_user.role != 'admin':
        flash('Unauthorized action.', 'error')
        return redirect(url_for('user_dashboard'))
        
    if borrow_record.status == 'borrowed':
        borrow_record.status = 'returned'
        borrow_record.return_date = datetime.utcnow()
        borrow_record.fine_amount = calculate_fine(borrow_record.due_date)
        
        book = Book.query.get(borrow_record.book_id)
        if book:
            book.available_copies += 1
            
        db.session.commit()
        flash(f'Returned successfully. Fine incurred: ₹{borrow_record.fine_amount}', 'success')
        
    return redirect(request.referrer or url_for('user_dashboard'))

# --- Book Request Routes ---

@app.route('/user/request_book/<int:book_id>', methods=['POST'])
@login_required
def request_book(book_id):
    if current_user.role == 'admin':
        return redirect(url_for('admin_dashboard'))
    
    book = Book.query.get_or_404(book_id)
    
    # Check if user already has a pending request for this book
    existing = BookRequest.query.filter_by(user_id=current_user.id, book_id=book_id, status='pending').first()
    if existing:
        flash('You already have a pending request for this book.', 'error')
        return redirect(url_for('user_dashboard'))
    
    days = int(request.form.get('days', 14))
    new_request = BookRequest(user_id=current_user.id, book_id=book_id, days_requested=days)
    db.session.add(new_request)
    db.session.commit()
    flash(f'Request for "{book.title}" submitted! Waiting for admin approval.', 'success')
    return redirect(url_for('user_dashboard'))

@app.route('/admin/accept_request/<int:request_id>', methods=['POST'])
@login_required
def accept_request(request_id):
    if current_user.role != 'admin':
        return redirect(url_for('user_dashboard'))
    
    book_request = BookRequest.query.get_or_404(request_id)
    book = Book.query.get_or_404(book_request.book_id)
    
    if book.available_copies > 0:
        book_request.status = 'accepted'
        book.available_copies -= 1
        due_date = datetime.utcnow() + timedelta(days=book_request.days_requested)
        borrow_record = BorrowRecord(user_id=book_request.user_id, book_id=book.id, due_date=due_date)
        db.session.add(borrow_record)
        db.session.commit()
        flash(f'Request accepted! "{book.title}" assigned to {book_request.user.name}.', 'success')
    else:
        flash('No copies available. Cannot accept this request.', 'error')
    
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/delete_request/<int:request_id>', methods=['POST'])
@login_required
def delete_request(request_id):
    if current_user.role != 'admin':
        return redirect(url_for('user_dashboard'))
    
    req = BookRequest.query.get_or_404(request_id)
    db.session.delete(req)
    db.session.commit()
    flash('Book request removed.', 'success')
    return redirect(url_for('admin_dashboard'))

if __name__ == '__main__':
    # Initialize some default books if the database is empty
    with app.app_context():
        if Book.query.count() <= 5: # If only base books exist, add more
            more_books = [
                Book(title='Introduction to Algorithms', author='Cormen et al.', category='Computer Science', total_copies=5, available_copies=5),
                Book(title='Artificial Intelligence: A Modern Approach', author='Stuart Russell', category='Computer Science', total_copies=3, available_copies=3),
                Book(title='The Great Gatsby', author='F. Scott Fitzgerald', category='Classic Fiction', total_copies=10, available_copies=10),
                Book(title='Heads First Design Patterns', author='Eric Freeman', category='Programming', total_copies=4, available_copies=4),
                Book(title='Brief History of Time', author='Stephen Hawking', category='Science', total_copies=6, available_copies=6),
                Book(title='Thinking, Fast and Slow', author='Daniel Kahneman', category='Psychology', total_copies=2, available_copies=2),
                Book(title='Wings of Fire', author='A.P.J. Abdul Kalam', category='Autobiography', total_copies=8, available_copies=8),
                Book(title='Ikigai', author='Hector Garcia', category='Self-Help', total_copies=12, available_copies=12)
            ]
            db.session.bulk_save_objects(more_books)
            db.session.commit()
    app.run(debug=True)
