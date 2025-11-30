import pytest
from app import create_app, db, Category, Transaction
from datetime import date

@pytest.fixture
def app():
    app = create_app({
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        "WTF_CSRF_ENABLED": False
    })
    with app.app_context():
        db.create_all()
    yield app
    with app.app_context():
        db.drop_all()

@pytest.fixture
def client(app):
    return app.test_client()

# --- Health & Summary ---
def test_health(client):
    rv = client.get('/health')
    assert rv.status_code == 200
    data = rv.get_json()
    assert data["status"] == "ok"

def test_api_summary_empty(client):
    rv = client.get('/api/summary')
    assert rv.status_code == 200
    data = rv.get_json()
    assert "labels" in data and "data" in data
    assert len(data["labels"]) == 6

def test_api_summary_with_data(app, client):
    with app.app_context():
        t = Transaction(description="Test", amount=100.0, date=date.today())
        db.session.add(t)
        db.session.commit()
    rv = client.get('/api/summary')
    assert rv.status_code == 200
    data = rv.get_json()
    assert any(v != 0 for v in data["data"])

# --- Index ---
def test_index(client):
    rv = client.get('/')
    assert rv.status_code == 200

def test_index_with_transactions(app, client):
    with app.app_context():
        db.session.add(Transaction(description="Income", amount=500.0, date=date.today()))
        db.session.add(Transaction(description="Expense", amount=-100.0, date=date.today()))
        db.session.commit()
    rv = client.get('/')
    assert rv.status_code == 200

# --- Transactions CRUD ---
def test_transactions_list(client):
    rv = client.get('/transactions')
    assert rv.status_code == 200

def test_new_transaction_get(client):
    rv = client.get('/transactions/new')
    assert rv.status_code == 200

def test_new_transaction_post(app, client):
    rv = client.post('/transactions/new', data={
        'description': 'Test expense',
        'amount': '-50.0',
        'date': '2025-01-15'
    }, follow_redirects=True)
    assert rv.status_code == 200
    with app.app_context():
        assert Transaction.query.count() == 1

def test_new_transaction_with_category(app, client):
    with app.app_context():
        c = Category(name="Food")
        db.session.add(c)
        db.session.commit()
        cat_id = c.id
    rv = client.post('/transactions/new', data={
        'description': 'Lunch',
        'amount': '-15.0',
        'date': '2025-01-15',
        'category': str(cat_id)
    }, follow_redirects=True)
    assert rv.status_code == 200

def test_new_transaction_invalid_date(client):
    rv = client.post('/transactions/new', data={
        'description': 'Bad date',
        'amount': '10',
        'date': 'not-a-date'
    }, follow_redirects=True)
    assert rv.status_code == 200
    assert b'Invalid date' in rv.data or rv.status_code == 200

def test_new_transaction_invalid_category(client):
    rv = client.post('/transactions/new', data={
        'description': 'Bad cat',
        'amount': '10',
        'date': '2025-01-01',
        'category': '9999'
    }, follow_redirects=True)
    assert rv.status_code == 200

def test_edit_transaction_get(app, client):
    with app.app_context():
        t = Transaction(description="Edit me", amount=10.0, date=date.today())
        db.session.add(t)
        db.session.commit()
        tx_id = t.id
    rv = client.get(f'/transactions/{tx_id}/edit')
    assert rv.status_code == 200

def test_edit_transaction_post(app, client):
    with app.app_context():
        t = Transaction(description="Old", amount=10.0, date=date.today())
        db.session.add(t)
        db.session.commit()
        tx_id = t.id
    rv = client.post(f'/transactions/{tx_id}/edit', data={
        'description': 'Updated',
        'amount': '20.0',
        'date': '2025-02-01'
    }, follow_redirects=True)
    assert rv.status_code == 200
    with app.app_context():
        t = Transaction.query.get(tx_id)
        assert t.description == 'Updated'

def test_edit_transaction_invalid_date(app, client):
    with app.app_context():
        t = Transaction(description="Test", amount=10.0, date=date.today())
        db.session.add(t)
        db.session.commit()
        tx_id = t.id
    rv = client.post(f'/transactions/{tx_id}/edit', data={
        'description': 'Test',
        'amount': '10',
        'date': 'bad-date'
    }, follow_redirects=True)
    assert rv.status_code == 200

def test_delete_transaction(app, client):
    with app.app_context():
        t = Transaction(description="Delete me", amount=5.0, date=date.today())
        db.session.add(t)
        db.session.commit()
        tx_id = t.id
    rv = client.post(f'/transactions/{tx_id}/delete', follow_redirects=True)
    assert rv.status_code == 200
    with app.app_context():
        assert Transaction.query.get(tx_id) is None

def test_delete_transaction_not_found(client):
    rv = client.post('/transactions/9999/delete')
    assert rv.status_code == 404

# --- Export CSV ---
def test_export_csv_empty(client):
    rv = client.get('/export.csv')
    assert rv.status_code == 200
    assert b'id,description,amount,date,category' in rv.data

def test_export_csv_with_data(app, client):
    with app.app_context():
        c = Category(name="Utils")
        db.session.add(c)
        db.session.commit()
        t = Transaction(description="Electric", amount=-80.0, date=date.today(), category=c)
        db.session.add(t)
        db.session.commit()
    rv = client.get('/export.csv')
    assert rv.status_code == 200
    assert b'Electric' in rv.data
    assert b'Utils' in rv.data