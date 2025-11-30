import pytest
from app import create_app, db, Category, Transaction
from datetime import date

@pytest.fixture
def app():
    app = create_app({
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"
    })
    with app.app_context():
        db.create_all()
    yield app
    with app.app_context():
        db.drop_all()

@pytest.fixture
def client(app):
    return app.test_client()

def test_create_category(app):
    with app.app_context():
        c = Category(name="Groceries")
        db.session.add(c)
        db.session.commit()
        assert Category.query.count() == 1
        assert Category.query.first().name == "Groceries"

def test_create_transaction(app):
    with app.app_context():
        t = Transaction(description="Coffee", amount=-5.0, date=date.today())
        db.session.add(t)
        db.session.commit()
        assert Transaction.query.count() == 1

def test_transaction_with_category(app):
    with app.app_context():
        c = Category(name="Food")
        db.session.add(c)
        db.session.commit()
        t = Transaction(description="Lunch", amount=-12.0, date=date.today(), category=c)
        db.session.add(t)
        db.session.commit()
        assert t.category.name == "Food"

def test_category_transactions_backref(app):
    with app.app_context():
        c = Category(name="Transport")
        db.session.add(c)
        db.session.commit()
        t1 = Transaction(description="Bus", amount=-2.0, date=date.today(), category=c)
        t2 = Transaction(description="Train", amount=-10.0, date=date.today(), category=c)
        db.session.add_all([t1, t2])
        db.session.commit()
        assert len(c.transactions) == 2

# --- Categories CRUD ---
def test_categories_view(client):
    rv = client.get('/categories')
    assert rv.status_code == 200

def test_add_category(app, client):
    rv = client.post('/categories/add', data={'name': 'Entertainment'}, follow_redirects=True)
    assert rv.status_code == 200
    with app.app_context():
        assert Category.query.filter_by(name='Entertainment').first() is not None

def test_add_category_empty_name(client):
    rv = client.post('/categories/add', data={'name': ''}, follow_redirects=True)
    assert rv.status_code == 200

def test_add_category_duplicate(app, client):
    with app.app_context():
        db.session.add(Category(name="Duplicate"))
        db.session.commit()
    rv = client.post('/categories/add', data={'name': 'duplicate'}, follow_redirects=True)
    assert rv.status_code == 200
    with app.app_context():
        assert Category.query.count() == 1

def test_delete_category(app, client):
    with app.app_context():
        c = Category(name="ToDelete")
        db.session.add(c)
        db.session.commit()
        cat_id = c.id
    rv = client.post(f'/categories/{cat_id}/delete', follow_redirects=True)
    assert rv.status_code == 200
    with app.app_context():
        assert Category.query.get(cat_id) is None

def test_delete_category_with_transactions(app, client):
    with app.app_context():
        c = Category(name="HasTx")
        db.session.add(c)
        db.session.commit()
        t = Transaction(description="Test", amount=-5.0, date=date.today(), category=c)
        db.session.add(t)
        db.session.commit()
        cat_id = c.id
        tx_id = t.id
    rv = client.post(f'/categories/{cat_id}/delete', follow_redirects=True)
    assert rv.status_code == 200
    with app.app_context():
        assert Category.query.get(cat_id) is None
        t = Transaction.query.get(tx_id)
        assert t is not None
        assert t.category is None

def test_delete_category_not_found(client):
    rv = client.post('/categories/9999/delete')
    assert rv.status_code == 404