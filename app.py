from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import or_
from datetime import datetime
import os

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///gundatabase.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY') or 'your-secret-key-here'
db = SQLAlchemy(app)

# Моделі даних
class Department(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    records = db.relationship('Record', backref='department', lazy=True)

class Record(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    department_id = db.Column(db.Integer, db.ForeignKey('department.id'), nullable=False)
    last_name = db.Column(db.String(50), nullable=False)
    first_name = db.Column(db.String(50), nullable=False)
    middle_name = db.Column(db.String(50))
    ip_address = db.Column(db.String(15), nullable=False)
    mac_address = db.Column(db.String(17), nullable=False)
    service = db.Column(db.String(100), nullable=False)
    office = db.Column(db.String(10), nullable=False)
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
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    department = db.relationship('Department', backref='support_requests')

# Список підрозділів
DEPARTMENTS = [
    "ГУНП",
    "Голосіївське УП",
    "Дарницьке УП",
    "Деснянське УП",
    "Дніпровське УП",
    "Оболонське УП",
    "Печерське УП",
    "Подільське УП",
    "Святошинське УП",
    "Солом'янське УП",
    "Шевченківське УП",
    "ППОП№1",
    "ППОП№2",
    "УП в метрополітені",
    "ВП в р/п Київ",
    "ВПнаСЗТ",
    "Стрілецький полк",  # Тільки один раз
    "БКСП",  # Окремий підрозділ
    "ІТТ",
    "Тренінговий Центр",
    "Кінологічний Центр",
    "ЦЗ№2"
]

# Ініціалізація бази даних
with app.app_context():
    db.create_all()
    for dept in DEPARTMENTS:
        if not Department.query.filter_by(name=dept).first():
            db.session.add(Department(name=dept))
    db.session.commit()

# Маршрути
@app.route('/')
def index():
    departments = Department.query.order_by(Department.name).all()
    return render_template('index.html', departments=departments)

@app.route('/department/<int:dept_id>')
def show_department(dept_id):
    department = Department.query.get_or_404(dept_id)
    records = Record.query.filter_by(department_id=dept_id).order_by(Record.last_name).all()
    return render_template('department.html', department=department, records=records)

@app.route('/add_record/<int:dept_id>', methods=['GET', 'POST'])
def add_record(dept_id):
    department = Department.query.get_or_404(dept_id)
    if request.method == 'POST':
        try:
            record = Record(
                department_id=dept_id,
                last_name=request.form['last_name'].strip(),
                first_name=request.form['first_name'].strip(),
                middle_name=request.form.get('middle_name', '').strip(),
                ip_address=request.form['ip_address'].strip(),
                mac_address=request.form['mac_address'].strip(),
                service=request.form['service'].strip(),
                office=request.form['office'].strip()
            )
            db.session.add(record)
            db.session.commit()
            flash('Запис успішно додано!', 'success')
            return redirect(url_for('show_department', dept_id=dept_id))
        except Exception as e:
            db.session.rollback()
            flash(f'Помилка при додаванні запису: {str(e)}', 'danger')
    return render_template('add_record.html', department=department)

@app.route('/search', methods=['GET', 'POST'])
def search():
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
                    Department.name.ilike(f'%{search_term}%')
                )
            ).order_by(Record.last_name).all()
            return render_template('search.html', results=results, search_term=search_term)
        flash('Будь ласка, введіть пошуковий запит', 'warning')
    return render_template('search.html')

@app.route('/delete_record/<int:record_id>', methods=['POST'])
def delete_record(record_id):
    record = Record.query.get_or_404(record_id)
    dept_id = record.department_id
    try:
        db.session.delete(record)
        db.session.commit()
        flash('Запис успішно видалено', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Помилка при видаленні запису: {str(e)}', 'danger')
    return redirect(url_for('show_department', dept_id=dept_id))

@app.route('/tech_support')
def tech_support():
    departments = Department.query.all()
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
    except Exception as e:
        db.session.rollback()
        flash(f'Сталася помилка при відправці запиту: {str(e)}', 'danger')
    return redirect(url_for('tech_support'))

@app.route('/about')
def about():
    return render_template('about.html')

@app.route('/ip-calculator')
def ip_calculator():
    return render_template('ip_calculator.html')
# Чат-бот для техпідтримки
@app.route('/chatbot', methods=['POST'])
def chatbot():
    user_message = request.json.get('message', '').lower()
    response = generate_chatbot_response(user_message)
    return jsonify({'response': response})

@app.route('/get_my_ip')
def get_my_ip():
    client_ip = request.remote_addr
    return jsonify({'ip': client_ip})

def generate_chatbot_response(message):
    # Перевірка на IP-адресу
    if 'ip' in message or 'айпі' in message or 'айпи' in message:
        ip_pattern = r'\b(?:\d{1,3}\.){3}\d{1,3}\b'
        ip_match = re.search(ip_pattern, message)
        if ip_match:
            ip = ip_match.group()
            return f"Ваша IP-адреса: {ip}. Для перевірки підключення спробуйте команду 'ping {ip}'"
        return "Я можу допомогти з IP-адресою. Напишіть 'Моя IP' або введіть вашу IP у форматі XXX.XXX.XXX.XXX"

    # Перевірка на MAC-адресу
    elif 'mac' in message or 'мак' in message or 'фізична адреса' in message:
        mac_pattern = r'([0-9A-Fa-f]{2}[:-]){5}([0-9A-Fa-f]{2})'
        mac_match = re.search(mac_pattern, message)
        if mac_match:
            mac = mac_match.group()
            return f"Ваша MAC-адреса: {mac}. Для зміни MAC-адреси зверніться до адміністратора."
        return "Вкажіть вашу MAC-адресу у форматі XX:XX:XX:XX:XX:XX або напишіть 'Де знайти MAC?'"

    # Типові запитання
    elif 'привіт' in message or 'вітаю' in message:
        return "Вітаю! Я чат-бот техпідтримки ГУНП. Чим можу допомогти?"
    elif 'проблема' in message or 'не працює' in message or 'не можу' in message:
        return """Опишіть проблему детальніше. Наприклад:
        - Не працює інтернет
        - Не відкривається внутрішній сайт
        - Проблеми з принтером
        Також вкажіть вашу IP та MAC-адресу"""
    elif 'допомога' in message or 'можеш' in message:
        return """Я можу допомогти з:
        - Визначенням IP/MAC адреси
        - Основними проблемами з підключенням
        - Поясненням як вирішити прості технічні проблеми
        Напишіть конкретний запит, наприклад 'Не працює інтернет'"""
    elif 'дякую' in message or 'спасибі' in message:
        return "Було приємно допомогти! Звертайтеся ще 😊"
    else:
        return """Не розпізнав ваш запит. Ось що я можу:
        - Допомогти з IP/MAC адресами
        - Пояснити як вирішити прості технічні проблеми
        - Направити до фахівця при складних питаннях
        Спробуйте сформулювати запит інакше"""

# Обробка помилок
@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_server_error(e):
    return render_template('500.html'), 500

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(port=5000, debug=True)
    from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
    from flask_sqlalchemy import SQLAlchemy
    from sqlalchemy import or_
    from datetime import datetime
    import os
    import re  # Додаємо для перевірки IP/MAC