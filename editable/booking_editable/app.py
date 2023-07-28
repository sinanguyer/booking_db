from flask import Flask, render_template, jsonify, request, Response
import sqlite3
from datetime import datetime, timedelta
import smtplib
from email.mime.text import MIMEText
import bcrypt
from flask_mail import Mail, Message  # Import the Message class
app = Flask(__name__)

def create_tables():
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()

    # Create the customers table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS customers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT
        )
    ''')

    # Create the hours table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS hours (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT
        )
    ''')

    # Create the equipment table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS equipment (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT
        )
    ''')

    # Create the selected_dates table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS selected_dates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id INTEGER,
            date DATE,
            hour_id INTEGER,
            inverter TEXT,
            equipment_id INTEGER,
            FOREIGN KEY (customer_id) REFERENCES customers (id),
            FOREIGN KEY (hour_id) REFERENCES hours (id),
            FOREIGN KEY (equipment_id) REFERENCES equipment (id)
        )
    ''')

    # Create the selected_equipments table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS selected_equipments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            selected_date_id INTEGER,
            equipment_id INTEGER,
            FOREIGN KEY (selected_date_id) REFERENCES selected_dates (id),
            FOREIGN KEY (equipment_id) REFERENCES equipment (id)
        )
    ''')

    equipment_names = [
        'SPS groß',
        'PVS 1',
        'PVS 2',
        'PVS 3',
        'Ametek',
        'SPS klein',
        'DC Bidi 1',
        'DC Bidi 2',
        'DC Bidi 3',
        'DC Bidi 4',
        'Klimakammer ES',
        'Holzkammer ES'
    ]
    for name in equipment_names:
        cursor.execute('INSERT INTO equipment (name) VALUES (?)', (name,))

    conn.commit()
    conn.close()

# Create the tables if they don't exist
create_tables()



@app.route('/')
def index():
    return render_template('index.html')

@app.route('/get_calendar_events', methods=['GET'])
def get_calendar_events():
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    today = datetime.now().date()
    start_date = today 
    end_date = start_date + timedelta(days=7)  # Next 5 days

    cursor.execute('''
        SELECT sd.date || 'T' || h.name AS start, c.name AS title, h.name AS hour, sd.inverter, sd.id, 1 as is_selected
        FROM selected_dates sd
        JOIN customers c ON c.id = sd.customer_id
        JOIN hours h ON h.id = sd.hour_id
        WHERE sd.date BETWEEN ? AND ?
    ''', (start_date, end_date))
    rows = cursor.fetchall()

    events = []
    for row in rows:
        cursor.execute('''
            SELECT e.name
            FROM selected_equipments se
            JOIN equipment e ON e.id = se.equipment_id
            WHERE se.selected_date_id = ?
        ''', (row[4],))
        equipment_names = [e[0] for e in cursor.fetchall()]
        event = {
            'start': row[0],
            'title': row[1],
            'hour': row[2],
            'inverter': row[3],
            'equipment': equipment_names,  # Return all equipment as a list
            'id': row[4],
            'isOccupied': True,
            'backgroundColor': 'red' if row[5] else ''  # Set background color to red for selected events
        }
        events.append(event)

    conn.close()

    # Retrieve newly selected slots from the request data
    selected_slots = request.args.getlist('selected_slots[]')
    for slot in selected_slots:
        slot_data = slot.split(',')
        event = {
            'start': slot_data[0],
            'title': slot_data[1],
            'hour': slot_data[2],
            'inverter': slot_data[3],
            'id': slot_data[4],
            'equipment': slot_data[5].split(','),
            'isOccupied': True,
            'backgroundColor': 'red'
        }
        events.append(event)

    return jsonify(events)

@app.route('/edit_event/<event_id>', methods=['POST'])
def edit_event(event_id):
    # Retrieve the event data from the request
    customer = request.form.get('customer')
    inverter = request.form.get('inverter')
    hours = request.form.get('hours')
    equipment_names = request.form.getlist('equipment[]')

    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()

    # Update the event data in the database
    cursor.execute('UPDATE selected_dates SET customer_id=?, hour_id=?, inverter=? WHERE id=?',
                   (customer, hours, inverter, event_id))

    # Remove old equipment selections for the event
    cursor.execute('DELETE FROM selected_equipments WHERE selected_date_id=?', (event_id,))

    # Add the new equipment selections for the event
    for equipment_name in equipment_names:
        cursor.execute('SELECT id FROM equipment WHERE name = ?', (equipment_name,))
        result = cursor.fetchone()
        if result is not None:
            equipment_id = result[0]
            cursor.execute('INSERT INTO selected_equipments (selected_date_id, equipment_id) VALUES (?, ?)',
                           (event_id, equipment_id))

    conn.commit()
    conn.close()

    return jsonify({'success': True, 'message': 'Event updated successfully.'})

@app.route('/remove_event/<event_id>', methods=['POST'])
def remove_event(event_id):
    print('Removing event:', event_id)
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()

    # Remove the event and its equipment selections from the database
    cursor.execute('DELETE FROM selected_dates WHERE id=?', (event_id,))
    cursor.execute('DELETE FROM selected_equipments WHERE selected_date_id=?', (event_id,))

    conn.commit()
    conn.close()

    return jsonify({'success': True, 'message': 'Event removed successfully.'})




@app.route('/get_equipment_list', methods=['GET'])
def get_equipment_list():
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()

    cursor.execute('SELECT id, name FROM equipment')
    rows = cursor.fetchall()

    equipment_list = [{'id': row[0], 'name': row[1]} for row in rows]

    conn.close()

    return jsonify(equipment_list)

@app.route('/get_customer_list', methods=['GET'])
def get_customer_list():
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()

    cursor.execute('SELECT id, name FROM customers')
    rows = cursor.fetchall()

    customer_list = [{'id': row[0], 'name': row[1]} for row in rows]

    conn.close()

    return jsonify(customer_list)


@app.route('/save_selection', methods=['POST'])
def save_selection():
    customer = request.form.get('customer')
    date = request.form.get('date')
    inverter = request.form.get('inverter')
    hours = request.form.get('hours')
    equipment_names = request.form.getlist('equipment[]')  # Get equipment names as a list
    email = request.form.get('email')  # Get the user's email address
    password = request.form.get('password')
    if not customer or not date or not inverter or not hours or not equipment_names:
        return 'Missing selection. Please fill in all fields.'

    selected_date = datetime.strptime(date, '%Y-%m-%d').date()
    if selected_date < datetime.now().date() or (selected_date == datetime.now().date() and hours < datetime.now().strftime('%H:%M:%S')):
        return 'Please choose a valid date and hour.'

    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()

    cursor.execute('''
        SELECT sd.id
        FROM selected_dates sd
        JOIN customers c ON c.id = sd.customer_id
        JOIN hours h ON h.id = sd.hour_id
        WHERE sd.date = ? AND h.name = ?
    ''', (date, hours))
    result = cursor.fetchone()
    if result is not None:
        conn.close()
        return 'Please choose another date and hour.'

    cursor.execute('SELECT id FROM customers WHERE name = ?', (customer,))
    result = cursor.fetchone()
    if result is None:
        cursor.execute('INSERT INTO customers (name) VALUES (?)', (customer,))
        customer_id = cursor.lastrowid
    else:
        customer_id = result[0]

    cursor.execute('SELECT id FROM hours WHERE name = ?', (hours,))
    result = cursor.fetchone()
    if result is None:
        cursor.execute('INSERT INTO hours (name) VALUES (?)', (hours,))
        hour_id = cursor.lastrowid
    else:
        hour_id = result[0]

    cursor.execute('''
        INSERT INTO selected_dates (customer_id, date, hour_id, inverter)
        VALUES (?, ?, ?, ?)
    ''', (customer_id, date, hour_id, inverter))
    selected_date_id = cursor.lastrowid

    for equipment_name in equipment_names:
        cursor.execute('SELECT id FROM equipment WHERE name = ?', (equipment_name,))
        result = cursor.fetchone()
        if result is not None:
            equipment_id = result[0]
            cursor.execute('''
                INSERT INTO selected_equipments (selected_date_id, equipment_id)
                VALUES (?, ?)
            ''', (selected_date_id, equipment_id))

    conn.commit()
    conn.close()
 
    return jsonify({'success': True})

@app.route('/daily_report', methods=['GET'])

def daily_report():


    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()

    # Fetch selected dates for the current day
    today = datetime.now().date()
    cursor.execute('''
        SELECT sd.date, c.name AS customer, h.name AS hour, sd.inverter, e.name AS equipment
        FROM selected_dates sd
        JOIN customers c ON c.id = sd.customer_id
        JOIN hours h ON h.id = sd.hour_id
        JOIN selected_equipments se ON se.selected_date_id = sd.id
        JOIN equipment e ON e.id = se.equipment_id
        WHERE sd.date = ?
    ''', (today,))
    rows = cursor.fetchall()

    # Group rows by date, hour, and inverter
    grouped_rows = {}
    for row in rows:
        key = (row[0], row[1], row[2], row[3])  # Use date, customer, hour, and inverter as the key
        if key not in grouped_rows:
            grouped_rows[key] = []
        grouped_rows[key].append(row[4])  # Add equipment to the list

    report = f"Daily Report - {today}\n\n"
    report += "Selected Slots:\n"
    for key, equipments in grouped_rows.items():
        date, customer, hour, inverter = key
        report += f"Date: {date}\n"
        report += f"Customer: {customer}\n"
        report += f"Hour: {hour}\n"
        report += f"Inverter: {inverter}\n"
        for equipment in equipments:
            report += f"Equipment: {equipment}\n"
        report += "\n"



    conn.close()

    # Create the response with the report content
    response = Response(report, mimetype='text/plain')
    response.headers.set('Content-Disposition', 'attachment', filename='daily_report.txt')

    return response

if __name__ == '__main__':
    app.run(debug=True)
