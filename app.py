import logging
import traceback
import os
import re
import csv
from io import StringIO
import subprocess
import speedtest
import time
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, Response, Blueprint, send_from_directory, abort
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from flask_socketio import SocketIO, emit, join_room
from markupsafe import escape
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from sqlalchemy import or_
from datetime import datetime, timezone
from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, SubmitField, SelectField, DateField, PasswordField
from wtforms.validators import DataRequired, Optional, Regexp, Length, Email, EqualTo, ValidationError
from apscheduler.schedulers.background import BackgroundScheduler
from concurrent.futures import ThreadPoolExecutor
from functools import wraps

# Налаштування логування
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('app.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)

# Ініціалізація додатку
app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///gundatabase.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY') or 'your-secret-key-here'
app.config['TEMPLATES_AUTO_RELOAD'] = True
app.config['UPLOAD_FOLDER'] = os.path.join(app.static_folder, 'Uploads')
db = SQLAlchemy(app)

socketio = SocketIO(app)

# Ініціалізація Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# Store online users
online_users = {}  # {socket_id: {'id': user_id, 'name': username, 'is_admin': bool}}

# Декоратор для перевірки адмін-прав
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not getattr(current_user, 'is_admin', False):
            flash('Доступ до адмін-панелі дозволено лише адміністраторам', 'danger')
            logging.warning(f"User {current_user.username if current_user.is_authenticated else 'anonymous'} attempted to access admin route")
            abort(403)  # Forbidden
        return f(*args, **kwargs)
    return decorated_function

# Форми Flask-WTF
class RecordForm(FlaskForm):
    department_id = SelectField('Підрозділ', coerce=int, validators=[DataRequired()])
    last_name = StringField('Прізвище', validators=[DataRequired()])
    first_name = StringField('Ім’я', validators=[DataRequired()])
    middle_name = StringField('По батькові')
    ip_address = StringField('IP-адреса', validators=[
        DataRequired(),
        Regexp(r'^(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$',
               message='Невірний формат IP-адреси')
    ])
    mac_address = StringField('MAC-адреса', validators=[
        DataRequired(),
        Regexp(r'^([0-9A-Fa-f]{2}[:-]){5}([0-9A-Fa-f]{2})$',
               message='Невірний формат MAC-адреси')
    ])
    service = StringField('Служба', validators=[DataRequired()])
    office = StringField('Кабінет', validators=[DataRequired()])
    work_phone = StringField('Робочий телефон')
    mobile_phone = StringField('Мобільний телефон')
    submit = SubmitField('Зберегти')

class DepartmentForm(FlaskForm):
    name = StringField('Назва підрозділу', validators=[DataRequired()])
    ip_address = StringField('IP-адреса', validators=[
        Optional(),
        Regexp(r'^(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$',
               message='Невірний формат IP-адреси')
    ])
    submit = SubmitField('Зберегти')

class SupportRequestForm(FlaskForm):
    status = SelectField('Статус', choices=[
        ('new', 'Новий'),
        ('in_progress', 'В процесі'),
        ('resolved', 'Виконано')
    ], validators=[DataRequired()])
    description = TextAreaField('Опис', validators=[DataRequired()])
    admin_response = TextAreaField('Відповідь адміністратора', validators=[Optional()])
    submit = SubmitField('Зберегти')

class KnowledgeBaseForm(FlaskForm):
    title = StringField('Заголовок', validators=[DataRequired()])
    category = StringField('Категорія', validators=[DataRequired()])
    content = TextAreaField('Вміст', validators=[DataRequired()])
    submit = SubmitField('Додати статтю')

class ReportForm(FlaskForm):
    start_date = DateField('Дата початку', validators=[DataRequired()], format='%Y-%m-%d')
    end_date = DateField('Дата закінчення', validators=[DataRequired()], format='%Y-%m-%d')
    submit = SubmitField('Сформувати звіт')

class UserForm(FlaskForm):
    username = StringField('Ім\'я користувача', validators=[DataRequired(), Length(min=3, max=80)])
    password = PasswordField('Пароль', validators=[DataRequired(), Length(min=6)])
    department = StringField('Підрозділ')
    submit = SubmitField('Зберегти')

class RegistrationForm(FlaskForm):
    username = StringField('Ім\'я користувача', validators=[DataRequired(), Length(min=3, max=80)])
    password = PasswordField('Пароль', validators=[DataRequired(), Length(min=6)])
    confirm_password = PasswordField('Підтвердити пароль', validators=[DataRequired(), EqualTo('password')])
    submit = SubmitField('Зареєструватися')

    def validate_username(self, username):
        user = User.query.filter_by(username=username.data).first()
        if user:
            raise ValidationError('Це ім\'я користувача вже зайнято.')

class LoginForm(FlaskForm):
    username = StringField('Ім\'я користувача', validators=[DataRequired()])
    password = PasswordField('Пароль', validators=[DataRequired()])
    submit = SubmitField('Увійти')

# Моделі даних
class Department(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    ip_address = db.Column(db.String(15), nullable=True)
    last_status = db.Column(db.Boolean, default=False)
    last_latency = db.Column(db.Float, nullable=True)
    last_checked = db.Column(db.DateTime, nullable=True)
    records = db.relationship('Record', backref='department', lazy=True)
    support_requests = db.relationship('SupportRequest', backref='department', lazy=True)

class Record(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    department_id = db.Column(db.Integer, db.ForeignKey('department.id'), nullable=False)
    last_name = db.Column(db.String(50), nullable=False)
    first_name = db.Column(db.String(50), nullable=False)
    middle_name = db.Column(db.String(50))
    ip_address = db.Column(db.String(15), nullable=False, unique=True)
    mac_address = db.Column(db.String(17), nullable=False, unique=True)
    service = db.Column(db.String(100), nullable=False)
    office = db.Column(db.String(10), nullable=False)
    work_phone = db.Column(db.String(20))
    mobile_phone = db.Column(db.String(20))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class SupportRequest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    department_id = db.Column(db.Integer, db.ForeignKey('department.id'))
    email = db.Column(db.String(100), nullable=False)
    issue_type = db.Column(db.String(50), nullable=False)
    description = db.Column(db.Text, nullable=False)
    urgency = db.Column(db.String(20), nullable=False)
    status = db.Column(db.String(20), default='new')
    admin_response = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class KnowledgeBaseArticle(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, nullable=False)
    category = db.Column(db.String(50), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, onupdate=datetime.utcnow)
    __table_args__ = (
        db.Index('idx_title', 'title'),
        db.Index('idx_category', 'category'),
    )

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    @property
    def is_admin(self):
        return False  # Звичайні користувачі не є адміністраторами

class AdminUser(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    is_admin = db.Column(db.Boolean, default=True)  # Додаємо поле is_admin

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class PrivateChatMessage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey('admin_user.id'), nullable=True)
    user_id = db.Column(db.String(50), nullable=True)
    guest_id = db.Column(db.String(50), nullable=True)
    message = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_admin = db.Column(db.Boolean, default=False)
    is_read = db.Column(db.Boolean, default=False)

class PublicChatMessage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey('admin_user.id'), nullable=True)
    sender_name = db.Column(db.String(100), nullable=False)
    message = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class DownloadLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('admin_user.id'), nullable=True)
    filename = db.Column(db.String(100), nullable=False)
    downloaded_at = db.Column(db.DateTime, default=datetime.utcnow)

@login_manager.user_loader
def load_user(user_id):
    admin_user = AdminUser.query.get(int(user_id))
    if admin_user:
        return admin_user
    return User.query.get(int(user_id))

# Список підрозділів
DEPARTMENTS = [
    "ГУНП", "Голосіївське УП", "Дарницьке УП", "Деснянське УП", "Дніпровське УП",
    "Оболонське УП", "Печерське УП", "Подільське УП", "Святошинське УП", "Солом'янське УП",
    "Шевченківське УП", "ППОП№1", "ППОП№2", "УП в метрополітені", "ВП в р/п Київ",
    "ВПнаСЗТ", "Стрілецький полк", "БКС", "ІТТ", "Тренінговий Центр", "Кінологічний Центр",
    "ЦЗ№2", "УКР Антоновича", "УБН", "УКОРД"
]

# Ініціалізація бази даних
with app.app_context():
    try:
        if os.path.exists('gundatabase.db'):
            os.remove('gundatabase.db')
            logging.info("Old database removed")
        db.create_all()
        for dept in DEPARTMENTS:
            if not Department.query.filter_by(name=dept).first():
                db.session.add(Department(name=dept))
        if not AdminUser.query.first():
            admin = AdminUser(username='admin', is_admin=True)
            admin.set_password('admin123')
            db.session.add(admin)
            db.session.commit()  # Фіксуємо admin, щоб отримати id
        if not User.query.first():
            user = User(username='user1')
            user.set_password('password123')
            db.session.add(user)
        db.session.commit()
        logging.info("Database initialized with departments, default admin, and default user")
    except Exception as e:
        db.session.rollback()
        logging.error(f"Database initialization failed: {str(e)}")
        raise

# Створення папки uploads
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Функція пінгу
def check_ping(ip_address):
    if not ip_address:
        return {'status': False, 'latency': None}
    try:
        param = '-n' if os.name == 'nt' else '-c'
        start_time = time.time()
        result = subprocess.run(['ping', param, '1', ip_address],
                                capture_output=True, text=True, timeout=2)
        latency = (time.time() - start_time) * 1000
        status = result.returncode == 0
        return {'status': status, 'latency': latency if status else None}
    except Exception as e:
        logging.error(f"Ping failed for {ip_address}: {str(e)}")
        return {'status': False, 'latency': None}

# Функція паралельного пінгу
def update_department_statuses():
    with app.app_context():
        departments = Department.query.filter(Department.ip_address != None).all()
        with ThreadPoolExecutor(max_workers=10) as executor:
            results = list(executor.map(lambda dept: (dept, check_ping(dept.ip_address)), departments))
        for dept, result in results:
            dept.last_status = result['status']
            dept.last_latency = result['latency']
            dept.last_checked = datetime.utcnow()
        db.session.commit()
        logging.info(f"Updated statuses for {len(departments)} departments")

# Очистка старих повідомлень
def cleanup_old_messages():
    with app.app_context():
        cutoff = datetime.utcnow() - timedelta(days=7)
        old_messages = PublicChatMessage.query.filter(PublicChatMessage.created_at < cutoff).all()
        for msg in old_messages:
            db.session.delete(msg)
        db.session.commit()
        logging.info(f"Deleted {len(old_messages)} old public chat messages")

# Налаштування планувальника
scheduler = BackgroundScheduler(daemon=True)
scheduler.remove_all_jobs()
scheduler.add_job(update_department_statuses, 'interval', minutes=5)
scheduler.start()

# Blueprint для адмінки
admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

# Маршрути адмінки
@admin_bp.route('/')
@admin_required
@login_required
def admin_index():
    department_count = Department.query.count()
    record_count = Record.query.count()
    support_request_count = SupportRequest.query.count()
    departments = Department.query.order_by(Department.name).all()
    logging.info(
        f"Admin accessed dashboard: departments={department_count}, records={record_count}, support_requests={support_request_count}")
    logging.debug("Rendering admin/index.html")
    return render_template('admin/index.html',
                           department_count=department_count,
                           record_count=record_count,
                           support_request_count=support_request_count,
                           departments=departments,
                           show_statistics=True)

@admin_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        if getattr(current_user, 'is_admin', False):
            logging.info("Admin already logged in, redirecting to admin dashboard")
            return redirect(url_for('admin.admin_index'))
        return redirect(url_for('index'))
    form = LoginForm()
    if form.validate_on_submit():
        user = AdminUser.query.filter_by(username=form.username.data).first()
        if user and user.check_password(form.password.data):
            login_user(user)
            logging.info(f"Admin {user.username} logged in successfully")
            return redirect(url_for('admin.admin_index'))
        flash('Невірне ім\'я користувача або пароль для адміністратора.', 'danger')
        logging.warning(f"Failed admin login attempt for {form.username.data}")
    logging.debug("Rendering admin/login.html")
    return render_template('admin/login.html', form=form)

@admin_bp.route('/logout')
@admin_required
@login_required
def logout():
    if current_user.is_authenticated:
        logging.info(f"Admin {current_user.username} logged out")
    else:
        logging.info("Unauthenticated user attempted logout")
    logout_user()
    return redirect(url_for('admin.login'))

@admin_bp.route('/change-password', methods=['GET', 'POST'])
@admin_required
@login_required
def change_password():
    if request.method == 'POST':
        current_password = request.form['current_password']
        new_password = request.form['new_password']
        if current_user.check_password(current_password):
            current_user.set_password(new_password)
            db.session.commit()
            flash('Пароль успішно змінено!', 'success')
            logging.info(f"Admin {current_user.username} changed password")
            return redirect(url_for('admin.admin_index'))
        flash('Невірний поточний пароль', 'danger')
        logging.warning(f"Failed password change attempt for {current_user.username}")
    logging.info("Rendering change password form")
    logging.debug("Rendering admin/change_password.html")
    return render_template('admin/change_password.html')

@admin_bp.route('/users', methods=['GET', 'POST'])
@admin_required
@login_required
def manage_users():
    action = request.args.get('action')
    user_id = request.args.get('id', type=int)
    if action == 'add':
        form = UserForm()
        if form.validate_on_submit():
            try:
                if AdminUser.query.filter_by(username=form.username.data).first():
                    flash('Користувач з таким логіном уже існує', 'danger')
                    logging.warning(f"Attempted to add duplicate user: {form.username.data}")
                else:
                    new_user = AdminUser(
                        username=form.username.data,
                        is_admin=True
                    )
                    new_user.set_password(form.password.data)
                    db.session.add(new_user)
                    db.session.commit()
                    flash('Користувача успішно додано', 'success')
                    logging.info(f"New admin user added: {form.username.data}")
                    return redirect(url_for('admin.manage_users'))
            except Exception as e:
                db.session.rollback()
                flash(f'Помилка при додаванні користувача: {str(e)}', 'danger')
                logging.error(f"Error adding user: {str(e)}")
        logging.debug("Rendering admin/add_user.html")
        return render_template('admin/add_user.html', form=form)
    elif action == 'edit' and user_id:
        user = AdminUser.query.get_or_404(user_id)
        form = UserForm(obj=user)
        if form.validate_on_submit():
            try:
                existing_user = AdminUser.query.filter_by(username=form.username.data).first()
                if existing_user and existing_user.id != user_id:
                    flash('Користувач з таким логіном уже існує', 'danger')
                    logging.warning(f"Duplicate username: {form.username.data}")
                else:
                    user.username = form.username.data
                    if form.password.data:
                        user.set_password(form.password.data)
                    db.session.commit()
                    flash('Користувача успішно оновлено', 'success')
                    logging.info(f"User updated: {user_id}")
                    return redirect(url_for('admin.manage_users'))
            except Exception as e:
                db.session.rollback()
                flash(f'Помилка при оновленні користувача: {str(e)}', 'danger')
                logging.error(f"Error updating user {user_id}: {str(e)}")
        logging.debug("Rendering admin/edit_user.html")
        return render_template('admin/edit_user.html', form=form, user=user)
    elif action == 'delete' and user_id:
        if user_id == current_user.id:
            flash('Ви не можете видалити власний обліковий запис', 'danger')
            logging.warning(f"User {current_user.username} attempted to delete their own account")
        else:
            user = AdminUser.query.get_or_404(user_id)
            try:
                db.session.delete(user)
                db.session.commit()
                flash('Користувача успішно видалено', 'success')
                logging.info(f"User deleted: {user_id}")
            except Exception as e:
                db.session.rollback()
                flash(f'Помилка при видаленні користувача: {str(e)}', 'danger')
                logging.error(f"Error deleting user {user_id}: {str(e)}")
        return redirect(url_for('admin.manage_users'))
    users = AdminUser.query.order_by(AdminUser.username).all()
    logging.info(f"Admin accessed user management: {len(users)} users found")
    logging.debug("Rendering admin/users.html")
    return render_template('admin/users.html', users=users)

@admin_bp.route('/departments')
@admin_required
@login_required
def manage_departments():
    departments = Department.query.order_by(Department.name).all()
    logging.info(f"Admin accessed departments list: {len(departments)} departments found")
    logging.debug("Rendering admin/departments.html")
    return render_template('admin/departments.html', departments=departments)

@admin_bp.route('/add_department', methods=['GET', 'POST'])
@admin_required
@login_required
def add_department():
    form = DepartmentForm()
    if request.method == 'POST' and form.validate_on_submit():
        name = form.name.data.strip()
        ip_address = form.ip_address.data.strip() if form.ip_address.data else None
        if Department.query.filter_by(name=name).first():
            flash('Підрозділ з такою назвою вже існує', 'danger')
            logging.warning(f"Attempted to add duplicate department: {name}")
        else:
            try:
                new_dept = Department(name=name, ip_address=ip_address)
                db.session.add(new_dept)
                db.session.commit()
                flash(f'Підрозділ "{name}" успішно додано', 'success')
                logging.info(f"New department added: {name}")
                return redirect(url_for('admin.manage_departments'))
            except Exception as e:
                db.session.rollback()
                flash(f'Помилка при додаванні підрозділу: {str(e)}', 'danger')
                logging.error(f"Error adding department {name}: {str(e)}")
    logging.debug("Rendering admin/add_department.html")
    return render_template('admin/add_department.html', form=form)

@admin_bp.route('/edit_department/<int:dept_id>', methods=['GET', 'POST'])
@admin_required
@login_required
def edit_department(dept_id):
    department = Department.query.get_or_404(dept_id)
    form = DepartmentForm(obj=department)
    if request.method == 'POST' and form.validate_on_submit():
        try:
            department.name = form.name.data.strip()
            department.ip_address = form.ip_address.data.strip() if form.ip_address.data else None
            db.session.commit()
            flash(f'Підрозділ "{department.name}" успішно оновлено', 'success')
            logging.info(f"Department updated: {dept_id}")
            return redirect(url_for('admin.manage_departments'))
        except Exception as e:
            db.session.rollback()
            flash(f'Помилка при оновленні підрозділу: {str(e)}', 'danger')
            logging.error(f"Error updating department {dept_id}: {str(e)}")
    logging.debug("Rendering admin/edit_department.html")
    return render_template('admin/edit_department.html', form=form, department=department)

@admin_bp.route('/delete_department/<int:dept_id>', methods=['POST'])
@admin_required
@login_required
def delete_department(dept_id):
    department = Department.query.get_or_404(dept_id)
    try:
        db.session.delete(department)
        db.session.commit()
        flash(f'Підрозділ "{department.name}" успішно видалено', 'success')
        logging.info(f"Department deleted: {dept_id}")
    except Exception as e:
        db.session.rollback()
        flash(f'Помилка при видаленні підрозділу: {str(e)}', 'danger')
        logging.error(f"Error deleting department {dept_id}: {str(e)}")
    return redirect(url_for('admin.manage_departments'))

@admin_bp.route('/records', methods=['GET', 'POST'])
@admin_required
@login_required
def manage_records():
    if request.method == 'POST':
        logging.debug("Received POST request for records import")
        if 'csv_file' not in request.files:
            flash('Файл не вибрано', 'danger')
            logging.warning("No CSV file selected for import")
        else:
            file = request.files['csv_file']
            if file.filename == '':
                flash('Файл не вибрано', 'danger')
                logging.warning("Empty filename for CSV import")
            elif file and file.filename.endswith('.csv'):
                try:
                    stream = StringIO(file.stream.read().decode("UTF8"), newline=None)
                    csv_reader = csv.DictReader(stream)
                    for row in csv_reader:
                        if not all(key in row for key in ['ПІБ', 'IP-адреса', 'MAC-адреса', 'Служба', 'Кабінет']):
                            flash('CSV файл має неправильний формат', 'danger')
                            logging.warning("Invalid CSV format during import")
                            return redirect(url_for('admin.manage_records'))
                        name_parts = row['ПІБ'].split()
                        last_name = name_parts[0] if len(name_parts) > 0 else ''
                        first_name = name_parts[1] if len(name_parts) > 1 else ''
                        middle_name = name_parts[2] if len(name_parts) > 2 else ''
                        dept_name = row.get('Підраздел', '')
                        department = Department.query.filter_by(name=dept_name).first()
                        if not department:
                            flash(f'Підраздел "{dept_name}" не знайдено', 'danger')
                            logging.warning(f"Department not found: {dept_name}")
                            return redirect(url_for('admin.manage_records'))
                        if Record.query.filter_by(ip_address=row['IP-адреса']).first():
                            flash(f'IP-адреса {row["IP-адреса"]} вже існує', 'danger')
                            logging.warning(f"Duplicate IP address: {row['IP-адреса']}")
                            return redirect(url_for('admin.manage_records'))
                        if Record.query.filter_by(mac_address=row['MAC-адреса']).first():
                            flash(f'MAC-адреса {row["MAC-адреса"]} вже існує', 'danger')
                            logging.warning(f"Duplicate MAC address: {row['MAC-адреса']}")
                            return redirect(url_for('admin.manage_records'))
                        record = Record(
                            department_id=department.id,
                            last_name=last_name,
                            first_name=first_name,
                            middle_name=middle_name,
                            ip_address=row['IP-адреса'],
                            mac_address=row['MAC-адреса'],
                            service=row['Служба'],
                            office=row['Кабінет'],
                            work_phone=row.get('Робочий телефон', ''),
                            mobile_phone=row.get('Мобільний телефон', '')
                        )
                        db.session.add(record)
                    db.session.commit()
                    flash('Дані успішно імпортовано!', 'success')
                    logging.info("Imported CSV for records")
                except Exception as e:
                    db.session.rollback()
                    flash(f'Помилка при імпорті даних: {str(e)}', 'danger')
                    logging.error(f"Error importing CSV: {str(e)}")
            else:
                flash('Непідтримуваний формат файлу. Використовуйте .csv', 'danger')
                logging.warning("Unsupported file format for CSV import")
        return redirect(url_for('admin.manage_records'))
    records = Record.query.join(Department).order_by(Department.name, Record.last_name).all()
    logging.info(f"Admin accessed records list: {len(records)} records found")
    logging.debug("Rendering admin/records.html")
    return render_template('admin/records.html', records=records)

@admin_bp.route('/add_record', methods=['GET', 'POST'])
@admin_required
@login_required
def add_record():
    form = RecordForm()
    form.department_id.choices = [(dept.id, dept.name) for dept in Department.query.order_by(Department.name).all()]
    if request.method == 'POST':
        logging.debug(f"Received POST request for add_record: {request.form}")
    if form.validate_on_submit():
        try:
            if Record.query.filter_by(ip_address=form.ip_address.data).first():
                flash(f'IP-адреса {form.ip_address.data} вже існує', 'danger')
                logging.warning(f"Duplicate IP address: {form.ip_address.data}")
                return render_template('admin/add_record.html', form=form)
            if Record.query.filter_by(mac_address=form.mac_address.data).first():
                flash(f'MAC-адреса {form.mac_address.data} вже існує', 'danger')
                logging.warning(f"Duplicate MAC address: {form.mac_address.data}")
                return render_template('admin/add_record.html', form=form)
            new_record = Record(
                department_id=form.department_id.data,
                last_name=form.last_name.data,
                first_name=form.first_name.data,
                middle_name=form.middle_name.data or None,
                ip_address=form.ip_address.data,
                mac_address=form.mac_address.data,
                service=form.service.data,
                office=form.office.data,
                work_phone=form.work_phone.data or None,
                mobile_phone=form.mobile_phone.data or None
            )
            db.session.add(new_record)
            db.session.commit()
            flash('Запис успішно додано', 'success')
            logging.info(f"New record added: {form.last_name.data} {form.first_name.data}")
            return redirect(url_for('admin.manage_records'))
        except Exception as e:
            db.session.rollback()
            flash(f'Помилка при додаванні запису: {str(e)}', 'danger')
            logging.error(f"Error adding record: {str(e)}")
    logging.debug("Rendering admin/add_record.html")
    return render_template('admin/add_record.html', form=form)

@admin_bp.route('/edit_record/<int:record_id>', methods=['GET', 'POST'])
@admin_required
@login_required
def edit_record(record_id):
    record = Record.query.get_or_404(record_id)
    form = RecordForm(obj=record)
    form.department_id.choices = [(dept.id, dept.name) for dept in Department.query.order_by(Department.name).all()]
    if request.method == 'POST':
        logging.debug(f"Received POST request for edit_record: {request.form}")
    if form.validate_on_submit():
        try:
            existing_ip = Record.query.filter_by(ip_address=form.ip_address.data).first()
            if existing_ip and existing_ip.id != record_id:
                flash(f'IP-адреса {form.ip_address.data} вже існує', 'danger')
                logging.warning(f"Duplicate IP address: {form.ip_address.data}")
                return render_template('admin/edit_record.html', form=form, record=record)
            existing_mac = Record.query.filter_by(mac_address=form.mac_address.data).first()
            if existing_mac and existing_mac.id != record_id:
                flash(f'MAC-адреса {form.mac_address.data} вже існує', 'danger')
                logging.warning(f"Duplicate MAC address: {form.mac_address.data}")
                return render_template('admin/edit_record.html', form=form, record=record)
            record.department_id = form.department_id.data
            record.last_name = form.last_name.data
            record.first_name = form.first_name.data
            record.middle_name = form.middle_name.data or None
            record.ip_address = form.ip_address.data
            record.mac_address = form.mac_address.data
            record.service = form.service.data
            record.office = form.office.data
            record.work_phone = form.work_phone.data or None
            record.mobile_phone = form.mobile_phone.data or None
            db.session.commit()
            flash('Запис успішно оновлено', 'success')
            logging.info(f"Record updated: {record_id}")
            return redirect(url_for('admin.manage_records'))
        except Exception as e:
            db.session.rollback()
            flash(f'Помилка при оновленні запису: {str(e)}', 'danger')
            logging.error(f"Error updating record {record_id}: {str(e)}")
    logging.debug("Rendering admin/edit_record.html")
    return render_template('admin/edit_record.html', form=form, record=record)

@admin_bp.route('/delete_record/<int:record_id>', methods=['POST'])
@admin_required
@login_required
def delete_record(record_id):
    record = Record.query.get_or_404(record_id)
    try:
        db.session.delete(record)
        db.session.commit()
        flash('Запис успішно видалено', 'success')
        logging.info(f"Record deleted: {record_id}")
    except Exception as e:
        db.session.rollback()
        flash(f'Помилка при видаленні запису: {str(e)}', 'danger')
        logging.error(f"Error deleting record {record_id}: {str(e)}")
    return redirect(url_for('admin.manage_records'))

@admin_bp.route('/export_records')
@admin_required
@login_required
def export_records():
    records = Record.query.join(Department).order_by(Department.name, Record.last_name).all()
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(
        ['Підраздел', 'ПІБ', 'IP-адреса', 'MAC-адреса', 'Служба', 'Кабінет', 'Робочий телефон', 'Мобільний телефон'])
    for record in records:
        writer.writerow([
            record.department.name,
            f"{record.last_name} {record.first_name} {record.middle_name or ''}",
            record.ip_address,
            record.mac_address,
            record.service,
            record.office,
            record.work_phone or '',
            record.mobile_phone or ''
        ])
    output.seek(0)
    logging.info("Exported all records to CSV")
    return Response(
        output,
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment;filename=records.csv"}
    )

@admin_bp.route('/support-requests')
@admin_required
@login_required
def manage_support_requests():
    requests = SupportRequest.query.join(Department).order_by(SupportRequest.status,
                                                              SupportRequest.created_at.desc()).all()
    logging.info(f"Admin accessed support requests list: {len(requests)} requests found")
    logging.debug("Rendering admin/support_requests.html")
    return render_template('admin/support_requests.html', requests=requests)

@admin_bp.route('/support-request/<int:request_id>', methods=['GET'])
@admin_required
@login_required
def view_support_request(request_id):
    support_request = SupportRequest.query.get_or_404(request_id)
    logging.info(f"Admin viewed support request: {request_id}")
    logging.debug("Rendering admin/support_request_view.html")
    return render_template('admin/support_request_view.html', support_request=support_request)

@admin_bp.route('/support-request/<int:request_id>/edit', methods=['GET', 'POST'])
@admin_required
@login_required
def edit_support_request(request_id):
    support_request = SupportRequest.query.get_or_404(request_id)
    form = SupportRequestForm(obj=support_request)
    if form.validate_on_submit():
        try:
            support_request.status = form.status.data
            support_request.description = form.description.data
            support_request.admin_response = form.admin_response.data or None
            db.session.commit()
            flash('Заявку успішно оновлено', 'success')
            logging.info(f"Support request updated: {request_id}")
            return redirect(url_for('admin.manage_support_requests'))
        except Exception as e:
            db.session.rollback()
            flash(f'Помилка при оновленні заявки: {str(e)}', 'danger')
            logging.error(f"Error updating support request {request_id}: {str(e)}")
    logging.debug("Rendering admin/support_request_edit.html")
    return render_template('admin/support_request_edit.html', form=form, support_request=support_request)

@admin_bp.route('/support-request/<int:request_id>/delete', methods=['POST'])
@admin_required
@login_required
def delete_support_request(request_id):
    support_request = SupportRequest.query.get_or_404(request_id)
    try:
        db.session.delete(support_request)
        db.session.commit()
        flash('Заявку успішно видалено', 'success')
        logging.info(f"Support request deleted: {request_id}")
    except Exception as e:
        db.session.rollback()
        flash(f'Помилка при видаленні заявки: {str(e)}', 'danger')
        logging.error(f"Error deleting support request {request_id}: {str(e)}")
    return redirect(url_for('admin.manage_support_requests'))

@admin_bp.route('/new-support-requests-count')
@admin_required
@login_required
def new_support_requests_count():
    count = SupportRequest.query.filter_by(status='new').count()
    logging.info(f"Checked new support requests count: {count}")
    return jsonify({'count': count})

@admin_bp.route('/knowledge-base', methods=['GET', 'POST'])
@admin_required
@login_required
def manage_knowledge_base():
    form = KnowledgeBaseForm()
    if form.validate_on_submit():
        try:
            article = KnowledgeBaseArticle(
                title=form.title.data.strip(),
                content=form.content.data.strip(),
                category=form.category.data.strip()
            )
            db.session.add(article)
            db.session.commit()
            flash('Статтю успішно додано!', 'success')
            logging.info(f"New knowledge base article added: {form.title.data}")
        except Exception as e:
            db.session.rollback()
            flash(f'Помилка при додаванні статті: {str(e)}', 'danger')
            logging.error(f"Error adding knowledge base article: {str(e)}")
        return redirect(url_for('admin.manage_knowledge_base'))
    articles = KnowledgeBaseArticle.query.order_by(KnowledgeBaseArticle.category, KnowledgeBaseArticle.title).all()
    logging.info(f"Admin accessed knowledge base: {len(articles)} articles found")
    logging.debug("Rendering admin/knowledge_base.html")
    return render_template('admin/knowledge_base.html', articles=articles, form=form)

@admin_bp.route('/edit-article/<int:article_id>', methods=['GET', 'POST'])
@admin_required
@login_required
def edit_article(article_id):
    article = KnowledgeBaseArticle.query.get_or_404(article_id)
    form = KnowledgeBaseForm(obj=article)
    if form.validate_on_submit():
        try:
            article.title = form.title.data.strip()
            article.content = form.content.data.strip()
            article.category = form.category.data.strip()
            db.session.commit()
            flash('Статтю успішно оновлено!', 'success')
            logging.info(f"Knowledge base article updated: {article_id}")
        except Exception as e:
            db.session.rollback()
            flash(f'Помилка при оновленні статті: {str(e)}', 'danger')
            logging.error(f"Error updating knowledge base article {article_id}: {str(e)}")
        return redirect(url_for('admin.manage_knowledge_base'))
    logging.debug("Rendering admin/edit_article.html")
    return render_template('admin/edit_article.html', article=article, form=form)

@admin_bp.route('/delete-article/<int:article_id>', methods=['POST'])
@admin_required
@login_required
def delete_article(article_id):
    article = KnowledgeBaseArticle.query.get_or_404(article_id)
    try:
        db.session.delete(article)
        db.session.commit()
        flash('Статтю успішно видалено!', 'success')
        logging.info(f"Knowledge base article deleted: {article_id}")
    except Exception as e:
        db.session.rollback()
        flash(f'Помилка при видаленні статті: {str(e)}', 'danger')
        logging.error(f"Error deleting knowledge base article {article_id}: {str(e)}")
    return redirect(url_for('admin.manage_knowledge_base'))

@admin_bp.route('/upload-form', methods=['GET', 'POST'])
@admin_required
@login_required
def upload_form():
    if request.method == 'POST':
        if 'file' not in request.files:
            flash('Файл не вибрано', 'danger')
            logging.warning("No file selected for upload")
            return redirect(url_for('admin.upload_form'))
        file = request.files['file']
        if file.filename == '':
            flash('Файл не вибрано', 'danger')
            logging.warning("Empty filename for upload")
            return redirect(url_for('admin.upload_form'))
        if file and file.filename.endswith(('.doc', '.docx')):
            filename = secure_filename(file.filename)
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], 'application_form.doc'))
            flash('Файл успішно завантажено!', 'success')
            logging.info(f"Uploaded file: application_form.doc")
            return redirect(url_for('admin.upload_form'))
        flash('Дозволено лише файли .doc або .docx', 'danger')
        logging.warning("Unsupported file format for upload")
    logging.debug("Rendering admin/upload_form.html")
    return render_template('admin/upload_form.html')

@admin_bp.route('/chats', methods=['GET', 'POST'])
@admin_required
@login_required
def admin_chats():
    if request.method == 'POST':
        chat_type = request.form.get('chat_type')
        message_text = request.form.get('message')
        target_id = request.form.get('target_id')
        if not message_text or not chat_type:
            flash('Повідомлення або тип чату не вказано', 'danger')
            logging.warning("Missing message or chat type in POST request")
            return redirect(url_for('admin.admin_chats'))

        if chat_type == 'public':
            message = PublicChatMessage(
                sender_id=current_user.id,
                sender_name=current_user.username,
                message=message_text.strip(),
                created_at=datetime.utcnow()
            )
            db.session.add(message)
            db.session.commit()
            socketio.emit('receive_message', {
                'message': message_text,
                'sender_name': current_user.username,
                'created_at': message.created_at.isoformat(),
                'is_admin': True,
                'type': 'public'
            }, room='public_chat')
            logging.info(f"Admin {current_user.username} sent public message: {message_text}")
        elif chat_type == 'private' and target_id:
            message = PrivateChatMessage(
                sender_id=current_user.id,
                user_id=target_id,
                message=message_text.strip(),
                is_admin=True,
                created_at=datetime.utcnow(),
                is_read=True
            )
            db.session.add(message)
            db.session.commit()
            socketio.emit('receive_message', {
                'message': message_text,
                'sender_name': current_user.username,
                'created_at': message.created_at.isoformat(),
                'is_admin': True,
                'type': 'private',
                'userId': target_id
            }, room=f'private_{target_id}')
            logging.info(f"Admin {current_user.username} sent private message to user {target_id}")
        elif chat_type == 'stats' and target_id:
            message = PrivateChatMessage(
                sender_id=current_user.id,
                user_id=f'dept_{target_id}',
                message=message_text.strip(),
                is_admin=True,
                created_at=datetime.utcnow(),
                is_read=True
            )
            db.session.add(message)
            db.session.commit()
            socketio.emit('receive_message', {
                'message': message_text,
                'sender_name': current_user.username,
                'created_at': message.created_at.isoformat(),
                'is_admin': True,
                'type': 'stats',
                'userId': f'dept_{target_id}'
            }, room=f'stats_{target_id}')
            logging.info(f"Admin {current_user.username} sent stats message to dept {target_id}")
        flash('Повідомлення надіслано!', 'success')
        return redirect(url_for('admin.admin_chats'))

    # Fetch public messages
    public_messages = PublicChatMessage.query.order_by(PublicChatMessage.created_at.asc()).limit(100).all()

    # Fetch private conversations
    private_messages = PrivateChatMessage.query.filter_by(is_admin=False).order_by(PrivateChatMessage.created_at.asc()).all()
    conversations = {}
    for msg in private_messages:
        conv_id = msg.user_id or msg.guest_id
        if conv_id and not conv_id.startswith('dept_'):
            if conv_id not in conversations:
                sender = User.query.filter_by(id=msg.sender_id).first() if msg.sender_id else None
                conversations[conv_id] = {
                    'user_id': conv_id,
                    'sender_name': sender.username if sender else 'Гість',
                    'department': sender.department if sender and hasattr(sender, 'department') else 'Невідомий',
                    'messages': []
                }
            conversations[conv_id]['messages'].append({
                'message': msg.message,
                'created_at': msg.created_at,
                'is_admin': msg.is_admin,
                'sender_name': sender.username if sender else 'Гість'
            })
    admin_responses = PrivateChatMessage.query.filter_by(is_admin=True).all()
    for msg in admin_responses:
        conv_id = msg.user_id or msg.guest_id
        if conv_id in conversations:
            conversations[conv_id]['messages'].append({
                'message': msg.message,
                'created_at': msg.created_at,
                'is_admin': True,
                'sender_name': 'Адміністратор'
            })

    # Fetch stats conversations
    stats_conversations = {}
    stats_messages = PrivateChatMessage.query.filter(PrivateChatMessage.user_id.like('dept_%')).all()
    for msg in stats_messages:
        dept_id = msg.user_id.replace('dept_', '')
        dept = Department.query.get(dept_id)
        if dept_id not in stats_conversations:
            stats_conversations[dept_id] = {
                'dept_id': dept_id,
                'dept_name': dept.name if dept else 'Невідомий',
                'messages': []
            }
        stats_conversations[dept_id]['messages'].append({
            'message': msg.message,
            'created_at': msg.created_at,
            'is_admin': msg.is_admin,
            'sender_name': 'Адміністратор' if msg.is_admin else 'Відділ'
        })

    logging.info(f"Admin accessed chats: {len(public_messages)} public, {len(conversations)} private, {len(stats_conversations)} stats")
    return render_template('admin/chats.html',
                           public_messages=public_messages,
                           private_conversations=conversations.values(),
                           stats_conversations=stats_conversations.values())
@app.route('/chat', methods=['GET', 'POST'])
@login_required
def user_chat():
    if request.method == 'POST':
        chat_type = request.form.get('chat_type')
        message_text = request.form.get('message')
        target_id = request.form.get('target_id')
        if not message_text or not chat_type:
            flash('Повідомлення або тип чату не вказано', 'danger')
            logging.warning("Missing message or chat type in user chat POST")
            return redirect(url_for('user_chat'))

        if chat_type == 'public':
            message = PublicChatMessage(
                sender_id=current_user.id,
                sender_name=current_user.username,
                message=message_text.strip(),
                created_at=datetime.utcnow()
            )
            db.session.add(message)
            db.session.commit()
            socketio.emit('receive_message', {
                'message': message_text,
                'sender_name': current_user.username,
                'created_at': message.created_at.isoformat(),
                'is_admin': False,
                'type': 'public'
            }, room='public_chat')
            logging.info(f"User {current_user.username} sent public message: {message_text}")
        elif chat_type == 'private' and target_id:
            message = PrivateChatMessage(
                sender_id=current_user.id,
                user_id=target_id,
                message=message_text.strip(),
                is_admin=False,
                created_at=datetime.utcnow(),
                is_read=False
            )
            db.session.add(message)
            db.session.commit()
            socketio.emit('receive_message', {
                'message': message_text,
                'sender_name': current_user.username,
                'created_at': message.created_at.isoformat(),
                'is_admin': False,
                'type': 'private',
                'userId': target_id
            }, room=f'private_{target_id}')
            socketio.emit('receive_message', {
                'message': message_text,
                'sender_name': current_user.username,
                'created_at': message.created_at.isoformat(),
                'is_admin': False,
                'type': 'private',
                'userId': target_id
            }, room='private_admin')
            logging.info(f"User {current_user.username} sent private message to admin")
        elif chat_type == 'stats' and target_id:
            message = PrivateChatMessage(
                sender_id=current_user.id,
                user_id=f'dept_{target_id}',
                message=message_text.strip(),
                is_admin=False,
                created_at=datetime.utcnow(),
                is_read=False
            )
            db.session.add(message)
            db.session.commit()
            socketio.emit('receive_message', {
                'message': message_text,
                'sender_name': current_user.username,
                'created_at': message.created_at.isoformat(),
                'is_admin': False,
                'type': 'stats',
                'userId': f'dept_{target_id}'
            }, room=f'stats_{target_id}')
            socketio.emit('receive_message', {
                'message': message_text,
                'sender_name': current_user.username,
                'created_at': message.created_at.isoformat(),
                'is_admin': False,
                'type': 'stats',
                'userId': f'dept_{target_id}'
            }, room='stats_admin')
            logging.info(f"User {current_user.username} sent stats message to dept {target_id}")
        flash('Повідомлення надіслано!', 'success')
        return redirect(url_for('user_chat'))

    public_messages = PublicChatMessage.query.order_by(PublicChatMessage.created_at.asc()).limit(100).all()
    departments = Department.query.order_by(Department.name).all()
    private_messages = PrivateChatMessage.query.filter(
        or_(PrivateChatMessage.sender_id == current_user.id, PrivateChatMessage.user_id == str(current_user.id))
    ).order_by(PrivateChatMessage.created_at.asc()).all()
    conversations = {
        'admin': {
            'user_id': 'admin',
            'sender_name': 'Адміністратор',
            'department': 'Адмін',
            'messages': []
        }
    }
    for msg in private_messages:
        if not msg.user_id.startswith('dept_'):
            conversations['admin']['messages'].append({
                'message': msg.message,
                'created_at': msg.created_at,
                'is_admin': msg.is_admin,
                'sender_name': 'Адміністратор' if msg.is_admin else current_user.username
            })

    stats_conversations = {}
    for dept in departments:
        stats_messages = PrivateChatMessage.query.filter(
            PrivateChatMessage.user_id == f'dept_{dept.id}'
        ).order_by(PrivateChatMessage.created_at.asc()).all()
        if stats_messages:
            stats_conversations[dept.id] = {
                'dept_id': dept.id,
                'dept_name': dept.name,
                'messages': [{
                    'message': msg.message,
                    'created_at': msg.created_at,
                    'is_admin': msg.is_admin,
                    'sender_name': 'Адміністратор' if msg.is_admin else current_user.username
                } for msg in stats_messages]
            }

    logging.info(f"User {current_user.username} accessed chat: {len(public_messages)} public, {len(conversations)} private, {len(stats_conversations)} stats")
    return render_template('chat.html',
                           public_messages=public_messages,
                           private_conversations=[conversations['admin']],
                           stats_conversations=stats_conversations.values())

@admin_bp.route('/unread-messages-count')
@admin_required
@login_required
def unread_messages_count():
    count = PrivateChatMessage.query.filter_by(is_admin=False, is_read=False).count()
    logging.info(f"Checked unread messages count: {count}")
    return jsonify({'count': count})

@admin_bp.route('/statistics')
@admin_required
@login_required
def get_statistics():
    total_records = Record.query.count()
    total_support_requests = SupportRequest.query.count()
    new_requests = SupportRequest.query.filter_by(status='new').count()
    in_progress_requests = SupportRequest.query.filter_by(status='in_progress').count()
    resolved_requests = SupportRequest.query.filter_by(status='resolved').count()
    logging.info(
        f"Fetched statistics: records={total_records}, support_requests={total_support_requests}, new={new_requests}")
    return jsonify({
        'total_records': total_records,
        'total_support_requests': total_support_requests,
        'new_requests': new_requests,
        'in_progress_requests': in_progress_requests,
        'resolved_requests': resolved_requests
    })

@admin_bp.route('/department-statuses')
@admin_required
@login_required
def get_department_statuses():
    departments = Department.query.filter(Department.ip_address != None).all()
    with ThreadPoolExecutor(max_workers=10) as executor:
        results = list(executor.map(lambda dept: (dept, check_ping(dept.ip_address)), departments))
    statuses = []
    for dept, result in results:
        status = 'online' if result['status'] else 'offline'
        latency = result['latency']
        color = 'green' if result['status'] else 'red'
        if result['status'] and latency and latency > 1000:
            color = 'yellow'
        statuses.append({
            'id': dept.id,
            'name': dept.name,
            'ip_address': dept.ip_address,
            'status': status,
            'color': color,
            'latency': round(latency, 2) if latency else None,
            'last_checked': dept.last_checked.strftime('%Y-%m-%d %H:%M:%S') if dept.last_checked else None
        })
    logging.info(f"Returned statuses for {len(statuses)} departments")
    return jsonify(statuses)

@admin_bp.route('/reports', methods=['GET', 'POST'])
@admin_required
@login_required
def reports():
    form = ReportForm()
    report_data = None
    start_date = None
    end_date = None
    if form.validate_on_submit():
        start_date = form.start_date.data
        end_date = form.end_date.data
        if start_date > end_date:
            flash('Дата початку не може бути пізніше дати закінчення', 'danger')
            logging.warning("Invalid date range for report")
            return render_template('admin/report.html', form=form)
        total_requests = SupportRequest.query.filter(
            SupportRequest.created_at.between(start_date, end_date)
        ).count()
        new_requests = SupportRequest.query.filter(
            SupportRequest.created_at.between(start_date, end_date),
            SupportRequest.status == 'new'
        ).count()
        in_progress_requests = SupportRequest.query.filter(
            SupportRequest.created_at.between(start_date, end_date),
            SupportRequest.status == 'in_progress'
        ).count()
        resolved_requests = SupportRequest.query.filter(
            SupportRequest.created_at.between(start_date, end_date),
            SupportRequest.status == 'resolved'
        ).count()
        department_stats = db.session.query(
            Department.name,
            db.func.count(Record.id).label('record_count')
        ).join(Record).filter(
            Record.created_at.between(start_date, end_date)
        ).group_by(Department.id).all()
        report_data = {
            'support_requests': {
                'total': total_requests,
                'new': new_requests,
                'in_progress': in_progress_requests,
                'resolved': resolved_requests
            },
            'department_stats': [
                {'name': name, 'record_count': count}
                for name, count in department_stats
            ]
        }
        logging.info(f"Generated report for period {start_date} to {end_date}")
    logging.debug("Rendering admin/report.html")
    return render_template('admin/report.html', form=form, report_data=report_data, start_date=start_date,
                           end_date=end_date)

@admin_bp.route('/export_report', methods=['POST'])
@admin_required
@login_required
def export_report():
    start_date = request.form.get('start_date')
    end_date = request.form.get('end_date')
    start_date = datetime.strptime(start_date, '%Y-%m-%d')
    end_date = datetime.strptime(end_date, '%Y-%m-%d')
    total_requests = SupportRequest.query.filter(
        SupportRequest.created_at.between(start_date, end_date)
    ).count()
    new_requests = SupportRequest.query.filter(
        SupportRequest.created_at.between(start_date, end_date),
        SupportRequest.status == 'new'
    ).count()
    in_progress_requests = SupportRequest.query.filter(
        SupportRequest.created_at.between(start_date, end_date),
        SupportRequest.status == 'in_progress'
    ).count()
    resolved_requests = SupportRequest.query.filter(
        SupportRequest.created_at.between(start_date, end_date),
        SupportRequest.status == 'resolved'
    ).count()
    department_stats = db.session.query(
        Department.name,
        db.func.count(Record.id).label('record_count')
    ).join(Record).filter(
        Record.created_at.between(start_date, end_date)
    ).group_by(Department.id).all()
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(['Звіт за період', f'{start_date.strftime("%d.%m.%Y")} - {end_date.strftime("%d.%m.%Y")}'])
    writer.writerow([])
    writer.writerow(['Запити на підтримку'])
    writer.writerow(['Загальна кількість', total_requests])
    writer.writerow(['Нові', new_requests])
    writer.writerow(['В процесі', in_progress_requests])
    writer.writerow(['Виконані', resolved_requests])
    writer.writerow([])
    writer.writerow(['Записи по підрозділах'])
    writer.writerow(['Підрозділ', 'Кількість записів'])
    for name, count in department_stats:
        writer.writerow([name, count])
    output.seek(0)
    logging.info(f"Exported report CSV for period {start_date} to {end_date}")
    return Response(
        output,
        mimetype="text/csv",
        headers={
            "Content-Disposition": f"attachment;filename=report_{start_date.strftime('%Y%m%d')}_{end_date.strftime('%Y%m%d')}.csv"}
    )

# Основні маршрути
@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    form = RegistrationForm()
    if form.validate_on_submit():
        user = User(username=form.username.data)
        user.set_password(form.password.data)
        db.session.add(user)
        try:
            db.session.commit()
            flash('Реєстрація успішна! Увійдіть, щоб продовжити.', 'success')
            logging.info(f"User registered: {user.username}")
            return redirect(url_for('login'))
        except Exception as e:
            db.session.rollback()
            flash('Помилка реєстрації. Спробуйте ще раз.', 'danger')
            logging.error(f"Registration failed for {form.username.data}: {str(e)}")
    return render_template('register.html', form=form)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        if getattr(current_user, 'is_admin', False):
            return redirect(url_for('admin.admin_index'))
        return redirect(url_for('index'))
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()
        if user and user.check_password(form.password.data):
            login_user(user)
            logging.info(f"User {user.username} logged in successfully")
            return redirect(url_for('index'))
        flash('Невірне ім\'я користувача або пароль.', 'danger')
        logging.warning(f"Failed login attempt for {form.username.data}")
    return render_template('login.html', form=form)

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

@app.route('/')
def index():
    try:
        departments = Department.query.order_by(Department.name).all()
        logging.info(f"Loaded {len(departments)} departments for index page")
        for dept in departments:
            logging.debug(f"Department: id={dept.id}, name={dept.name}, status={dept.last_status}")
        logging.debug("Rendering index.html")
        return render_template('index.html', departments=departments)
    except Exception as e:
        logging.error(f"Error in index route: {str(e)}")
        return render_template('500.html'), 500

@app.route('/department/<int:dept_id>')
def show_department(dept_id):
    try:
        logging.info(f"Accessing department with ID: {dept_id}")
        department = Department.query.get_or_404(dept_id)
        if not current_user.is_authenticated:
            logging.info(f"Unauthorized access to department {dept_id}, redirecting to index")
            flash('Доступ до записів дозволено лише адміністраторам', 'danger')
            return redirect(url_for('index'))
        records = Record.query.filter_by(department_id=dept_id).order_by(Record.last_name).all()
        logging.info(f"Loaded department {dept_id} with {len(records)} records")
        logging.debug(
            f"Rendering department.html with context: department={department.name}, records_count={len(records)}")
        return render_template('department.html', department=department, records=records)
    except Exception as e:
        logging.error(f"Error in show_department route for dept_id={dept_id}: {str(e)}\n{traceback.format_exc()}")
        return render_template('500.html'), 500

@app.route('/add-record/<int:dept_id>', methods=['GET', 'POST'])
def add_record_public(dept_id):
    try:
        department = Department.query.get_or_404(dept_id)
        logging.info(f"User accessed add-record form for department ID: {dept_id}")
        if request.method == 'POST':
            last_name = request.form.get('last_name', '').strip()
            first_name = request.form.get('first_name', '').strip()
            middle_name = request.form.get('middle_name', '').strip()
            ip_address = request.form.get('ip_address', '').strip()
            mac_address = request.form.get('mac_address', '').strip()
            service = request.form.get('service', '').strip()
            office = request.form.get('office', '').strip()
            work_phone = request.form.get('work_phone', '').strip()
            mobile_phone = request.form.get('mobile_phone', '').strip()
            if not all([last_name, first_name, ip_address, mac_address, service, office]):
                flash('Усі обов’язкові поля мають бути заповнені', 'danger')
                logging.warning("Validation failed: Missing required fields")
            else:
                ip_pattern = r'^(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$'
                mac_pattern = r'^([0-9A-Fa-f]{2}[:-]){5}([0-9A-Fa-f]{2})$'
                if not re.match(ip_pattern, ip_address):
                    flash('Невірний формат IP-адреси', 'danger')
                    logging.warning(f"Invalid IP address format: {ip_address}")
                elif not re.match(mac_pattern, mac_address):
                    flash('Невірний формат MAC-адреси', 'danger')
                    logging.warning(f"Invalid MAC address format: {mac_address}")
                else:
                    try:
                        if Record.query.filter_by(ip_address=ip_address).first():
                            flash(f'IP-адреса {ip_address} вже існує', 'danger')
                            logging.warning(f"Duplicate IP address: {ip_address}")
                        elif Record.query.filter_by(mac_address=mac_address).first():
                            flash(f'MAC-адреса {mac_address} вже існує', 'danger')
                            logging.warning(f"Duplicate MAC address: {mac_address}")
                        else:
                            new_record = Record(
                                last_name=last_name,
                                first_name=first_name,
                                middle_name=middle_name,
                                department_id=dept_id,
                                ip_address=ip_address,
                                mac_address=mac_address,
                                service=service,
                                office=office,
                                work_phone=work_phone,
                                mobile_phone=mobile_phone
                            )
                            db.session.add(new_record)
                            db.session.commit()
                            flash('Запис успішно додано', 'success')
                            logging.info(f"New record added: {last_name} {first_name}, department_id={dept_id}")
                            return redirect(url_for('index'))
                    except Exception as e:
                        db.session.rollback()
                        flash(f'Помилка при додаванні запису: {str(e)}', 'danger')
                        logging.error(f"Error adding record: {str(e)}")
        logging.debug("Rendering public_add_record.html")
        return render_template('public_add_record.html', department=department, dept_id=dept_id)
    except Exception as e:
        logging.error(f"Error in add_record_public route: {str(e)}")
        return render_template('500.html'), 500

@app.route('/search', methods=['GET', 'POST'])
def search():
    if not current_user.is_authenticated:
        logging.info("Unauthorized access to search, redirecting to index")
        flash('Пошук доступний лише для адміністраторів', 'danger')
        return redirect(url_for('index'))
    if request.method == 'POST':
        search_term = request.form.get('search_term', '').strip()
        if search_term:
            results = Record.query.join(Department).filter(
                or_(
                    Record.last_name.ilike(f'%{search_term}%'),
                    Record.first_name.ilike(f'%{search_term}%'),
                    Record.ip_address.ilike(f'%{search_term}%'),
                    Record.mac_address.ilike(f'%{search_term}%'),
                    Record.service.ilike(f'%{search_term}%'),
                    Record.work_phone.ilike(f'%{search_term}%'),
                    Record.mobile_phone.ilike(f'%{search_term}%'),
                    Department.name.ilike(f'%{search_term}%')
                )
            ).order_by(Record.last_name).all()
            logging.info(f"Search performed with term '{search_term}', found {len(results)} results")
            logging.debug("Rendering search.html")
            return render_template('search.html', results=results, search_term=search_term)
        flash('Будь ласка, введіть пошуковий запит', 'warning')
        logging.warning("Search attempted with empty search term")
    logging.debug("Rendering search.html")
    return render_template('search.html')

@app.route('/tech_support')
def tech_support():
    departments = Department.query.all()
    logging.info(f"Loaded {len(departments)} departments for tech support page")
    logging.debug("Rendering tech_support.html")
    return render_template('tech_support.html', departments=departments)

@app.route('/submit_support_request', methods=['POST'])
def submit_support_request():
    try:
        request_data = SupportRequest(
            name=request.form['name'],
            department_id=request.form['department'],
            email=request.form['email'],
            issue_type=request.form['issue_type'],
            description=request.form['description'],
            urgency=request.form['urgency']
        )
        db.session.add(request_data)
        db.session.commit()
        flash(f'Ваш запит успішно відправлено! Номер запиту: #{request_data.id}', 'success')
        logging.info(f"Support request submitted: #{request_data.id}")
    except Exception as e:
        db.session.rollback()
        flash(f'Сталася помилка при відправці запиту: {str(e)}', 'danger')
        logging.error(f"Error submitting support request: {str(e)}")
    return redirect(url_for('tech_support'))

@app.route('/check_support_request', methods=['GET', 'POST'])
def check_support_request():
    request_id = None
    support_request = None
    if request.method == 'POST':
        request_id = request.form.get('request_id', '').strip()
        if request_id.isdigit():
            support_request = SupportRequest.query.get(int(request_id))
            if not support_request:
                flash(f'Заявку з номером #{request_id} не знайдено', 'danger')
                logging.warning(f"Support request not found: #{request_id}")
        else:
            flash('Введіть коректний номер заявки', 'danger')
            logging.warning(f"Invalid support request ID: {request_id}")
    logging.debug("Rendering check_support_request.html")
    return render_template('check_support_request.html', support_request=support_request, request_id=request_id)

@app.route('/about')
def about():
    logging.info("User accessed about page")
    logging.debug("Rendering about.html")
    return render_template('about.html')

@app.route('/network-tools', methods=['GET', 'POST'])
def network_tools():
    ping_result = None
    traceroute_result = None
    if request.method == 'POST':
        target = request.form.get('target', '').strip()
        if 'ping' in request.form and target:
            try:
                result = subprocess.run(['ping', '-n', '4', target],
                                        capture_output=True,
                                        text=True,
                                        timeout=10)
                ping_result = result.stdout if result.returncode == 0 else result.stderr
                logging.info(f"Ping executed for target {target}: {ping_result}")
            except subprocess.TimeoutExpired:
                ping_result = "Ping timed out after 10 seconds"
                logging.warning(f"Ping timed out for target {target}")
            except Exception as e:
                ping_result = f"Error: {str(e)}"
                logging.error(f"Error during ping for target {target}: {str(e)}")
        elif 'traceroute' in request.form and target:
            try:
                result = subprocess.run(['tracert', target],
                                        capture_output=True,
                                        text=True,
                                        timeout=30)
                traceroute_result = result.stdout if result.returncode == 0 else result.stderr
                logging.info(f"Traceroute executed for target {target}: {traceroute_result}")
            except subprocess.TimeoutExpired:
                traceroute_result = "Traceroute timed out after 30 seconds"
                logging.warning(f"Traceroute timed out for target {target}")
            except Exception as e:
                traceroute_result = f"Error: {str(e)}"
                logging.error(f"Error during traceroute for target {target}: {str(e)}")
    logging.debug("Rendering network_tools.html")
    return render_template('network_tools.html',
                           ping_result=ping_result,
                           traceroute_result=traceroute_result)

@app.route('/ip-calculator')
def ip_calculator():
    logging.info("User accessed IP calculator page")
    logging.debug("Rendering ip_calculator.html")
    return render_template('ip_calculator.html')

@app.route('/export_csv/<int:dept_id>')
@admin_required
@login_required
def export_csv(dept_id):
    department = Department.query.get_or_404(dept_id)
    records = Record.query.filter_by(department_id=dept_id).all()
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(['ПІБ', 'IP-адреса', 'MAC-адреса', 'Служба', 'Кабінет', 'Робочий телефон', 'Мобільний телефон'])
    for record in records:
        writer.writerow([
            f"{record.last_name} {record.first_name} {record.middle_name or ''}",
            record.ip_address,
            record.mac_address,
            record.service,
            record.office,
            record.work_phone or '',
            record.mobile_phone or ''
        ])
    output.seek(0)
    logging.info(f"Exported CSV for department {dept_id}")
    return Response(
        output,
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment;filename={department.name}_records.csv"}
    )

@app.route('/import_csv/<int:dept_id>', methods=['POST'])
@admin_required
@login_required
def import_csv(dept_id):
    logging.debug(f"Received POST request for import_csv: dept_id={dept_id}")
    if 'csv_file' not in request.files:
        flash('Файл не вибрано', 'danger')
        logging.warning("No CSV file selected for import")
        return redirect(url_for('show_department', dept_id=dept_id))
    file = request.files['csv_file']
    if file.filename == '':
        flash('Файл не вибрано', 'danger')
        logging.warning("Empty filename for CSV import")
        return redirect(url_for('show_department', dept_id=dept_id))
    if file and file.filename.endswith('.csv'):
        try:
            stream = StringIO(file.stream.read().decode("UTF8"), newline=None)
            csv_reader = csv.DictReader(stream)
            for row in csv_reader:
                if not all(key in row for key in ['ПІБ', 'IP-адреса', 'MAC-адреса', 'Служба', 'Кабінет']):
                    flash('CSV файл має неправильний формат', 'danger')
                    logging.warning("Invalid CSV format during import")
                    return redirect(url_for('show_department', dept_id=dept_id))
                name_parts = row['ПІБ'].split()
                last_name = name_parts[0] if len(name_parts) > 0 else ''
                first_name = name_parts[1] if len(name_parts) > 1 else ''
                middle_name = name_parts[2] if len(name_parts) > 2 else ''
                if Record.query.filter_by(ip_address=row['IP-адреса']).first():
                    flash(f'IP-адреса {row["IP-адреса"]} вже існує', 'danger')
                    logging.warning(f"Duplicate IP address: {row['IP-адреса']}")
                    return redirect(url_for('show_department', dept_id=dept_id))
                if Record.query.filter_by(mac_address=row['MAC-адреса']).first():
                    flash(f'MAC-адреса {row["MAC-адреса"]} вже існує', 'danger')
                    logging.warning(f"Duplicate MAC address: {row['MAC-адреса']}")
                    return redirect(url_for('show_department', dept_id=dept_id))
                record = Record(
                    department_id=dept_id,
                    last_name=last_name,
                    first_name=first_name,
                    middle_name=middle_name,
                    ip_address=row['IP-адреса'],
                    mac_address=row['MAC-адреса'],
                    service=row['Служба'],
                    office=row['Кабінет'],
                    work_phone=row.get('Робочий телефон', ''),
                    mobile_phone=row.get('Мобільний телефон', '')
                )
                db.session.add(record)
            db.session.commit()
            flash('Дані успішно імпортовано!', 'success')
            logging.info(f"Imported CSV for department {dept_id}")
        except Exception as e:
            db.session.rollback()
            flash(f'Помилка при імпорті даних: {str(e)}', 'danger')
            logging.error(f"Error importing CSV for department {dept_id}: {str(e)}")
    return redirect(url_for('show_department', dept_id=dept_id))

@app.route('/chatbot', methods=['POST'])
def chatbot():
    user_message = request.json.get('message', '').lower()
    response = generate_chatbot_response(user_message)
    logging.info(f"Chatbot received message: {user_message}, responded with: {response}")
    return jsonify({'response': response})

@app.route('/get_my_ip')
def get_my_ip():
    client_ip = request.remote_addr
    logging.info(f"Returning IP address: {client_ip}")
    return jsonify({'ip': client_ip})

@app.route('/speedtest')
def run_speedtest():
    try:
        st = speedtest.Speedtest()
        st.get_best_server()
        download_speed = st.download() / 1_000_000
        upload_speed = st.upload() / 1_000_000
        ping = st.results.ping
        logging.info(f"Speedtest results: download={download_speed}, upload={upload_speed}, ping={ping}")
        return jsonify({
            'download': round(download_speed, 2),
            'upload': round(upload_speed, 2),
            'ping': round(ping, 2),
            'server': st.results.server['name']
        })
    except Exception as e:
        logging.error(f"Error during speedtest: {str(e)}")
        return jsonify({'error': str(e)}), 200

@app.route('/resources')
def resources():
    categories = db.session.query(KnowledgeBaseArticle.category).distinct().all()
    categories = [cat[0] for cat in categories]
    articles = KnowledgeBaseArticle.query.order_by(KnowledgeBaseArticle.category, KnowledgeBaseArticle.title).all()
    search_term = request.args.get('search', '')
    if search_term:
        articles = KnowledgeBaseArticle.query.filter(
            or_(
                KnowledgeBaseArticle.title.ilike(f'%{search_term}%'),
                KnowledgeBaseArticle.content.ilike(f'%{search_term}%')
            )
        ).order_by(KnowledgeBaseArticle.category, KnowledgeBaseArticle.title).all()
    logging.info(f"Accessed resources page, found {len(articles)} articles")
    logging.debug("Rendering resources.html")
    return render_template('resources.html', categories=categories, articles=articles, search_term=search_term)

@app.route('/download-form')
def download_form():
    filename = 'application_form.doc'
    try:
        if current_user.is_authenticated:
            log = DownloadLog(user_id=current_user.id, filename=filename)
            db.session.add(log)
            db.session.commit()
            logging.info(f"Download logged for user {current_user.id}: {filename}")
        return send_from_directory(app.config['UPLOAD_FOLDER'], filename, as_attachment=True)
    except Exception as e:
        flash(f'Помилка при завантаженні файлу: {str(e)}', 'danger')
        logging.error(f"Error downloading file {filename}: {str(e)}")
        return redirect(url_for('resources'))


def generate_chatbot_response(message):
    message = message.lower().strip()
    # Перевірка на неопрацьовані заявки
    if 'не опрацьовані заявки' in message or 'показати не опрацьовані' in message:
        requests = SupportRequest.query.filter_by(status='new').order_by(SupportRequest.created_at.desc()).limit(
            5).all()
        if requests:
            response = "Не опрацьовані заявки:\n"
            for req in requests:
                response += f"- #{req.id}: {req.issue_type}, Дата: {req.created_at.strftime('%d.%m.%Y %H:%M')}\n"
            response += "Напишіть 'Заявка #номер' для деталей."
        else:
            response = "Наразі немає не опрацьованих заявок."
        logging.info("Chatbot provided list of unprocessed support requests")
        return response
    # Перевірка на заявки або запити
    if 'заявка' in message or 'запит' in message:
        number_match = re.search(r'#(\d+)', message) or re.search(r'номер (\d+)', message)
        if number_match:
            request_id = int(number_match.group(1))
            support_request = SupportRequest.query.get(request_id)
            if support_request:
                status_text = {
                    'new': 'Новий',
                    'in_progress': 'В процесі',
                    'resolved': 'Виконано'
                }.get(support_request.status, 'Невідомий')
                response = (
                    f"Заявка #{support_request.id}:\n"
                    f"- Статус: {status_text}\n"
                    f"- Тип проблеми: {support_request.issue_type}\n"
                    f"- Дата створення: {support_request.created_at.strftime('%d.%m.%Y %H:%M')}\n"
                    f"Для деталей зверніться до техпідтримки."
                )
                logging.info(f"Chatbot provided info for support request #{request_id}")
                return response
            else:
                return f"Заявку з номером #{request_id} не знайдено. Перевірте номер або створіть нову заявку."
        if 'мої заявки' in message or 'список заявок' in message:
            requests = SupportRequest.query.order_by(SupportRequest.created_at.desc()).limit(5).all()
            if requests:
                response = "Останні заявки:\n"
                for req in requests:
                    status_text = {
                        'new': 'Новий',
                        'in_progress': 'В процесі',
                        'resolved': 'Виконано'
                    }.get(req.status, 'Невідомий')
                    response += f"- #{req.id}: {req.issue_type}, Статус: {status_text}\n"
                response += "Напишіть 'Заявка #номер' для деталей."
            else:
                response = "Заявки відсутні. Створіть нову на сторінці техпідтримки."
            logging.info("Chatbot provided list of recent support requests")
            return response
        return (
            "Напишіть 'Заявка #номер' для перевірки статусу, 'Мої заявки' для списку останніх заявок або 'Показати не опрацьовані заявки' для перегляду нових заявок.\n"
            "Також можете створити нову заявку на сторінці техпідтримки."
        )
    if 'ip' in message or 'айпі' in message or 'айпи' in message:
        ip_pattern = r'\b(?:\d{1,3}\.){3}\d{1,3}\b'
        ip_match = re.search(ip_pattern, message)
        if ip_match:
            ip = ip_match.group()
            return f"Ваша IP-адреса: {ip}. Для перевірки підключення спробуйте команду 'ping {ip}'"
        return "Я можу допомогти з IP-адресою. Напишіть 'Моя IP' або введіть вашу IP у форматі XXX.XXX.XXX.XXX"
    elif 'mac' in message or 'мак' in message or 'фізична адреса' in message:
        mac_pattern = r'([0-9A-Fa-f]{2}[:-]){5}([0-9A-Fa-f]{2})'
        mac_match = re.search(mac_pattern, message)
        if mac_match:
            mac = mac_match.group()
            return f"Ваша MAC-адреса: {mac}. Для зміни MAC-адреси зверніться до адміністратора."
        return "Вкажіть вашу MAC-адресу у форматі XX:XX:XX:XX:XX:XX або напишіть 'Де знайти MAC?'"
    elif 'привіт' in message or 'вітаю' in message:
        return "Вітаю! Я чат-бот техпідтримки ГУНП. Чим можу допомогти? Напишіть 'Заявка #номер' для перевірки статусу."
    elif 'проблема' in message or 'не працює' in message or 'не можу' in message:
        return (
            "Опишіть проблему детальніше або створіть заявку на сторінці техпідтримки.\n"
            "Наприклад:\n"
            "- Не працює інтернет\n"
            "- Не відкривається внутрішній сайт\n"
            "- Проблеми з принтером\n"
            "Вкажіть вашу IP та MAC-адресу або напишіть 'Мої заявки' для перегляду статусу."
        )
    elif 'допомога' in message or 'можеш' in message:
        return (
            "Я можу допомогти з:\n"
            "- Перевіркою статусу заявок ('Заявка #номер' або 'Мої заявки')\n"
            "- Переглядом не опрацьованих заявок ('Показати не опрацьовані заявки')\n"
            "- Визначенням IP/MAC адреси\n"
            "- Основними проблемами з підключенням\n"
            "Напишіть конкретний запит, наприклад 'Не працює інтернет' або 'Заявка #123'."
        )
    elif 'дякую' in message or 'спасибі' in message:
        return "Було приємно допомогти! Звертайтеся ще 😊"
    else:
        return (
            "Не розпізнав ваш запит. Ось що я можу:\n"
            "- Перевірити статус заявки ('Заявка #номер')\n"
            "- Показати останні заявки ('Мої заявки')\n"
            "- Показати не опрацьовані заявки ('Показати не опрацьовані заявки')\n"
            "- Допомогти з IP/MAC адресами\n"
            "- Пояснити, як вирішити прості технічні проблеми\n"
            "Спробуйте сформулювати запит інакше."
        )

# SocketIO Handlers
@socketio.on('connect')
def handle_connect():
    if not current_user.is_authenticated:
        logging.warning("Unauthenticated user attempted to connect to SocketIO")
        return False
    socket_id = request.sid
    is_admin = isinstance(current_user, AdminUser)
    join_room(f'user_{current_user.id}')
    join_room('public_chat')
    if is_admin:
        join_room('private_admin')
        join_room('stats_admin')
        departments = Department.query.all()
        for dept in departments:
            join_room(f'stats_{dept.id}')
    else:
        user_dept = Department.query.filter_by(name=current_user.department).first() if hasattr(current_user, 'department') else None
        if user_dept:
            join_room(f'stats_{user_dept.id}')
    online_users[socket_id] = {
        'id': current_user.id,
        'name': current_user.username,
        'is_admin': is_admin
    }
    logging.info(f"User {current_user.username} connected to SocketIO, socket_id={socket_id}")
    emit('online_users', {
        'users': [
            {'name': user['name'], 'is_admin': user['is_admin']}
            for user in online_users.values()
        ]
    }, room='public_chat')

@socketio.on('disconnect')
def handle_disconnect():
    socket_id = request.sid
    if socket_id in online_users:
        user = online_users.pop(socket_id)
        logging.info(f"User {user['name']} disconnected, socket_id={socket_id}")
        emit('online_users', {
            'users': [
                {'name': user['name'], 'is_admin': user['is_admin']}
                for user in online_users.values()
            ]
        }, room='public_chat')
    else:
        logging.warning(f"Disconnect event for unknown socket_id={socket_id}")

@socketio.on('send_message')
def handle_send_message(data):
    message_text = data.get('message')
    chat_type = data.get('type')
    target_id = data.get('userId')
    if not message_text or not chat_type:
        logging.warning("Missing message or chat type in SocketIO message")
        return

    message_text = escape(message_text.strip())  # Use escape
    if chat_type == 'public':
        message = PublicChatMessage(
            sender_id=current_user.id,
            sender_name=current_user.username,
            message=message_text,
            created_at=datetime.now(timezone.utc)
        )
        db.session.add(message)
        db.session.commit()
        emit('receive_message', {
            'message': message_text,
            'sender_name': current_user.username,
            'created_at': message.created_at.isoformat(),
            'is_admin': isinstance(current_user, AdminUser),
            'type': 'public'
        }, room='public_chat')
    elif chat_type == 'private' and target_id:
        message = PrivateChatMessage(
            sender_id=current_user.id,
            user_id=target_id,
            message=message_text,
            is_admin=isinstance(current_user, AdminUser),
            created_at=datetime.now(timezone.utc),
            is_read=isinstance(current_user, AdminUser)
        )
        db.session.add(message)
        db.session.commit()
        emit('receive_message', {
            'message': message_text,
            'sender_name': current_user.username,
            'created_at': message.created_at.isoformat(),
            'is_admin': isinstance(current_user, AdminUser),
            'type': 'private',
            'userId': target_id
        }, room=f'private_{target_id}')
        if not isinstance(current_user, AdminUser):
            emit('receive_message', {
                'message': message_text,
                'sender_name': current_user.username,
                'created_at': message.created_at.isoformat(),
                'is_admin': False,
                'type': 'private',
                'userId': target_id
            }, room='private_admin')
    elif chat_type == 'stats' and target_id:
        message = PrivateChatMessage(
            sender_id=current_user.id,
            user_id=f'dept_{target_id}',
            message=message_text,
            is_admin=isinstance(current_user, AdminUser),
            created_at=datetime.now(timezone.utc),
            is_read=isinstance(current_user, AdminUser)
        )
        db.session.add(message)
        db.session.commit()
        emit('receive_message', {
            'message': message_text,
            'sender_name': current_user.username,
            'created_at': message.created_at.isoformat(),
            'is_admin': isinstance(current_user, AdminUser),
            'type': 'stats',
            'userId': f'dept_{target_id}'
        }, room=f'stats_{target_id}')
        if not isinstance(current_user, AdminUser):
            emit('receive_message', {
                'message': message_text,
                'sender_name': current_user.username,
                'created_at': message.created_at.isoformat(),
                'is_admin': False,
                'type': 'stats',
                'userId': f'dept_{target_id}'
            }, room='stats_admin')
    logging.info(f"User {current_user.username} sent {chat_type} message: {message_text}")

@socketio.on('join_public_chat')
def handle_join_public_chat(data=None):
    join_room('public_chat')
    logging.info(f"User {current_user.username} joined public chat")

@socketio.on('join_private_chat')
def handle_join_private_chat(data=None):
    if data and 'userId' in data:
        join_room(f'private_{data["userId"]}')
        logging.info(f"User {current_user.username} joined private chat with {data['userId']}")
    else:
        join_room('private_admin')
        logging.info(f"Admin {current_user.username} joined private admin room")

@socketio.on('join_stats_chat')
def handle_join_stats_chat(data=None):
    if data and 'userId' in data:
        join_room(f'stats_{data["userId"]}')
        logging.info(f"User {current_user.username} joined stats chat with dept {data['userId']}")
    else:
        join_room('stats_admin')
        logging.info(f"Admin {current_user.username} joined stats admin room")

# Chat History Route
@app.route('/chat_history')
@login_required
def chat_history():
    chat_type = request.args.get('type')
    user_id = request.args.get('user_id')
    if chat_type == 'public':
        messages = PublicChatMessage.query.order_by(PublicChatMessage.created_at.asc()).limit(100).all()
        return jsonify({
            'messages': [{
                'message': msg.message,
                'sender_name': msg.sender_name,
                'created_at': msg.created_at.isoformat(),
                'is_admin': isinstance(User.query.get(msg.sender_id), AdminUser)
            } for msg in messages]
        })
    elif chat_type == 'private':
        messages = PrivateChatMessage.query.filter(
            or_(PrivateChatMessage.user_id == user_id, PrivateChatMessage.sender_id == current_user.id)
        ).order_by(PrivateChatMessage.created_at.asc()).all()
        return jsonify({
            'messages': [{
                'message': msg.message,
                'sender_name': 'Адміністратор' if msg.is_admin else User.query.get(msg.sender_id).username,
                'created_at': msg.created_at.isoformat(),
                'is_admin': msg.is_admin
            } for msg in messages]
        })
    elif chat_type == 'stats':
        messages = PrivateChatMessage.query.filter(
            or_(PrivateChatMessage.user_id == user_id, PrivateChatMessage.sender_id == current_user.id)
        ).order_by(PrivateChatMessage.created_at.asc()).all()
        return jsonify({
            'messages': [{
                'message': msg.message,
                'sender_name': 'Адміністратор' if msg.is_admin else User.query.get(msg.sender_id).username,
                'created_at': msg.created_at.isoformat(),
                'is_admin': msg.is_admin
            } for msg in messages]
        })
    return jsonify({'messages': []})

# Обробники помилок
@app.errorhandler(404)
def page_not_found(e):
    logging.error(f"404 error: {str(e)}")
    logging.debug(f"Rendering 404.html")
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_server_error(e):
    logging.error(f"500 error: {str(e)}\n{traceback.format_exc()}")
    logging.debug(f"Rendering 500.html")
    return render_template('500.html'), 500

# Реєстрація Blueprint
app.register_blueprint(admin_bp)

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    socketio.run(app, host='0.0.0.0', port=5000, debug=True, allow_unsafe_werkzeug=True)