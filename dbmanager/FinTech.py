import sqlite3
from discord.ext import tasks
from datetime import datetime, timedelta
from settings import ErrorHandler


def create_connection(db_path="data/finance.db"):
    return sqlite3.connect(db_path)


def create_money_table(user_id=None):
    with create_connection() as conn:
        cursor = conn.cursor()
        if user_id:
            cursor.execute(
            f"""
    CREATE TABLE IF NOT EXISTS "{user_id}_fintech" (  
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        category TEXT,
        amount REAL NOT NULL,
        status TEXT CHECK( status IN ('active', 'paid', 'overdue') ) NOT NULL DEFAULT 'active',
        frequency TEXT NOT NULL,
        due_date TEXT NOT NULL,
        last_paid_date TEXT
    )"""
        )
        cursor.execute(
            f"""
    CREATE TABLE IF NOT EXISTS user_payments (  
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER  NOT NULL
    )"""
        )
        conn.commit()


def calculate_next_due_date(
    due_date: str, frequency: str, last_paid_date: str = None
) -> str:
    """Calculates the next due date based on frequency and last paid date"""
    try:
        date_obj = datetime.strptime(due_date, "%Y-%m-%d")
        # If last_paid_date exists, make sure we aren't updating early
        if last_paid_date:
            last_paid_obj = datetime.strptime(last_paid_date, "%Y-%m-%d")
            if last_paid_obj >= date_obj:
                return due_date  # No update needed

        if frequency == "Monthly":
            next_due = date_obj + timedelta(days=30)
        elif frequency == "Bi-Weekly":
            next_due = date_obj + timedelta(days=14)
        elif frequency == "Weekly":
            next_due = date_obj + timedelta(days=7)
        else:
            return due_date  # One-time payments stay the same

        return next_due.strftime("%Y-%m-%d")
    except ValueError:
        return due_date  # Return as-is if date format is incorrect


def update_user_ids(user_id):
    with create_connection() as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM user_payments WHERE user_id = ?", (user_id,))
        existing = c.fetchone()
        if not existing:
            c.execute(
                f""" INSERT INTO user_payments (user_id) VALUES (?) """, (user_id,)
            )


def fintech_list(user_id):
    """Retrieves all series from the user's database."""
    table_name = f'"{user_id}_fintech"'
    create_money_table(user_id)
    with create_connection() as conn:
        c = conn.cursor()
        c.execute(f"SELECT * FROM {table_name}")
        return c.fetchall()


def update_table(
    user_id, name, category, amount, due_date, status, frequency="One-Time"
):
    table_name = f'"{user_id}_fintech"'
    create_money_table(user_id)
    update_user_ids(user_id)
    new_due_date = calculate_next_due_date(due_date, frequency)

    with create_connection() as conn:
        c = conn.cursor()
        c.execute(f"SELECT * FROM {table_name} WHERE name = ?", (name,))
        existing = c.fetchone()
        if existing:
            print(existing)
            existing_due_date = existing[6]
            existing_last_paid = existing[7]
            new_due_date = calculate_next_due_date(
                existing_due_date, frequency, existing_last_paid
            )

            # Check if the payment is overdue
            today = datetime.today().strftime("%Y-%m-%d")
            if existing_due_date < today and status != "paid":
                status = "Overdue"
            last_paid_date = None
            if status == "paid":
                last_paid_date = today

            # Update existing record
            c.execute(
                f"""
                    UPDATE {table_name}
                    SET category = COALESCE(?, category),
                        amount = COALESCE(amount + ?, amount),
                        due_date = COALESCE(?, due_date),
                        last_paid_date = COALESCE(?, last_paid_date),
                        status = COALESCE(?, status)
                    WHERE name = ?
                """,
                (category, amount, new_due_date, last_paid_date, status, name),
            )
        else:
            # Insert new record
            c.execute(
                f"""
                INSERT INTO {table_name} 
                (name, category, amount,  due_date, frequency,status)
                VALUES (?, ?, ?, ?, ?, ?)
            """,
                (name, category, amount, due_date, frequency, status),
            )
        conn.commit()


def update_payment_status(user_id, payment_name, status):
    with create_connection() as conn:
        c = conn.cursor()
        c.execute(
            f"""
            UPDATE {user_id}_fintech 
            SET status = ? 
            WHERE name = ?
        """,
            (status, payment_name),
        )
        conn.commit()



def check_due_dates():
    today = datetime.today().strftime("%Y-%m-%d")
    upcoming_date = (datetime.today() + timedelta(days=7)).strftime("%Y-%m-%d")
    reminders = []
    create_money_table()
    with create_connection() as conn:
        c = conn.cursor()
        c.execute("SELECT DISTINCT user_id FROM user_payments")
        user_ids = [row[0] for row in c.fetchall()]
        for user_id in user_ids:
            table_name = f'"{user_id}_fintech"'
           
            try:

                c.execute(
                    f"""
                SELECT name, category, amount, due_date, status
                FROM {table_name} 
                WHERE status != 'paid' 
                AND due_date IS NOT NULL 
                AND due_date BETWEEN ? AND ? 
                ORDER BY due_date ASC
            """,
                    (today, upcoming_date),
                )

                user_reminders = c.fetchall()
                
                for name, category, amount, due_date, status in user_reminders:
                    reminders.append(
                        {
                            "user_id": user_id,
                            "name": name,
                            "category": category,
                            "amount": amount,
                            "due_date": due_date,
                            "status": status,
                        }
                    )

            except sqlite3.OperationalError as e:
                ErrorHandler.handle_exception(e)
            

    
    return reminders
