from flask import Flask, render_template, request, redirect, url_for, jsonify, flash, Response
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, date
import os
import logging
import csv
from io import StringIO

# keep DB as extension for factory pattern
db = SQLAlchemy()
logger = logging.getLogger(__name__)


# ---------- Models (defined OUTSIDE create_app to avoid re-registration) ----------
class Category(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), unique=True, nullable=False)


class Transaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    description = db.Column(db.String(200))
    amount = db.Column(db.Float, nullable=False)
    date = db.Column(db.Date, nullable=False, default=date.today)
    category_id = db.Column(db.Integer, db.ForeignKey('category.id'), nullable=True)
    category = db.relationship('Category', backref=db.backref('transactions', lazy=True))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


# ---------- Helpers ----------
def parse_float(value, default=0.0):
    try:
        if value is None:
            return default
        return float(str(value).strip())
    except (ValueError, TypeError):
        return default


def create_app(test_config=None):
    """Application factory."""
    app = Flask(__name__, instance_relative_config=False)

    # default config
    base_dir = os.path.abspath(os.path.dirname(__file__))
    app.config.from_mapping(
        SECRET_KEY=os.environ.get('SECRET_KEY', 'devkey'),
        SQLALCHEMY_DATABASE_URI='sqlite:///' + os.path.join(base_dir, 'budget.db'),
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
    )

    if test_config:
        app.config.update(test_config)

    # init logging
    logging.basicConfig(level=logging.INFO)

    # initialize extensions
    db.init_app(app)

    # optional metrics
    try:
        from prometheus_flask_exporter import PrometheusMetrics
        metrics = PrometheusMetrics(app)
        try:
            metrics.info('budget_tracker_app', 'Budget tracker app', version=os.environ.get('APP_VERSION', '1.0'))
        except Exception:
            pass
    except Exception:
        logger.info("PrometheusMetrics not available; continuing without metrics.")

    # ---------- Routes ----------
    @app.route('/health')
    def health():
        return jsonify(status="ok", message="running"), 200

    @app.route('/')
    def index():
        income = db.session.query(db.func.sum(Transaction.amount)).filter(Transaction.amount > 0).scalar() or 0.0
        expenses = db.session.query(db.func.sum(Transaction.amount)).filter(Transaction.amount < 0).scalar() or 0.0
        recent = Transaction.query.order_by(Transaction.date.desc()).limit(10).all()
        return render_template('index.html', income=income, expenses=expenses, recent=recent)

    @app.route('/api/summary')
    def api_summary():
        results = db.session.query(
            db.func.strftime('%Y-%m', Transaction.date).label('month'),
            db.func.sum(Transaction.amount).label('total')
        ).group_by('month').order_by('month').all()
        totals = {r.month: float(r.total or 0.0) for r in results}
        today = date.today()

        def month_pair(offset):
            y = today.year + (today.month - 1 + offset) // 12
            m = (today.month - 1 + offset) % 12 + 1
            return f"{y}-{m:02d}"

        labels = [month_pair(i) for i in range(-5, 1)]
        data = [totals.get(label, 0.0) for label in labels]
        return jsonify({"labels": labels, "data": data})

    @app.route('/export.csv')
    def export_csv():
        si = StringIO()
        cw = csv.writer(si, lineterminator='\n')
        cw.writerow(['id', 'description', 'amount', 'date', 'category'])
        for tx in Transaction.query.order_by(Transaction.date.desc()).all():
            cw.writerow([tx.id, tx.description or "", tx.amount, tx.date.isoformat(), tx.category.name if tx.category else ""])
        output = si.getvalue()
        headers = {
            "Content-Disposition": "attachment; filename=transactions.csv",
            "Content-Type": "text/csv; charset=utf-8"
        }
        return Response(output, headers=headers)

    # CRUD endpoints
    @app.route('/transactions', methods=['GET'])
    def transactions():
        txs = Transaction.query.order_by(Transaction.date.desc()).all()
        categories = Category.query.order_by(Category.name).all()
        return render_template('transactions.html', transactions=txs, categories=categories)

    @app.route('/transactions/new', methods=['GET', 'POST'])
    def new_transaction():
        if request.method == 'POST':
            desc = (request.form.get('description') or '').strip()
            amount = parse_float(request.form.get('amount'))
            date_str = request.form.get('date') or datetime.today().strftime('%Y-%m-%d')
            try:
                dt = datetime.strptime(date_str, '%Y-%m-%d').date()
            except ValueError:
                flash('Invalid date format. Use YYYY-MM-DD.')
                return redirect(url_for('new_transaction'))
            cat_id = request.form.get('category') or None
            category = None
            if cat_id:
                category = Category.query.get(cat_id)
                if category is None:
                    flash('Selected category not found.')
                    return redirect(url_for('new_transaction'))
            t = Transaction(description=desc, amount=amount, date=dt, category=category)
            try:
                db.session.add(t)
                db.session.commit()
                flash('Transaction added.')
            except Exception:
                db.session.rollback()
                logger.exception("Failed to add transaction")
                flash('Failed to add transaction.')
            return redirect(url_for('transactions'))
        categories = Category.query.order_by(Category.name).all()
        return render_template('transaction_form.html', categories=categories, tx=None)

    @app.route('/transactions/<int:tx_id>/edit', methods=['GET', 'POST'])
    def edit_transaction(tx_id):
        tx = Transaction.query.get_or_404(tx_id)
        if request.method == 'POST':
            tx.description = (request.form.get('description') or '').strip()
            tx.amount = parse_float(request.form.get('amount'), default=tx.amount)
            date_str = request.form.get('date') or tx.date.isoformat()
            try:
                tx.date = datetime.strptime(date_str, '%Y-%m-%d').date()
            except ValueError:
                flash('Invalid date format. Use YYYY-MM-DD.')
                return redirect(url_for('edit_transaction', tx_id=tx_id))
            cat_id = request.form.get('category') or None
            tx.category = Category.query.get(cat_id) if cat_id else None
            try:
                db.session.commit()
                flash('Transaction updated.')
            except Exception:
                db.session.rollback()
                logger.exception("Failed to update transaction")
                flash('Failed to update transaction.')
            return redirect(url_for('transactions'))
        categories = Category.query.order_by(Category.name).all()
        return render_template('transaction_form.html', tx=tx, categories=categories)

    @app.route('/transactions/<int:tx_id>/delete', methods=['POST'])
    def delete_transaction(tx_id):
        tx = Transaction.query.get_or_404(tx_id)
        try:
            db.session.delete(tx)
            db.session.commit()
            flash('Transaction deleted.')
        except Exception:
            db.session.rollback()
            logger.exception("Failed to delete transaction")
            flash('Failed to delete transaction.')
        return redirect(url_for('transactions'))

    @app.route('/categories', methods=['GET'])
    def categories_view():
        cats = Category.query.order_by(Category.name).all()
        return render_template('categories.html', categories=cats)

    @app.route('/categories/add', methods=['POST'])
    def add_category():
        name = (request.form.get('name') or '').strip()
        if name:
            existing = Category.query.filter(db.func.lower(Category.name) == name.lower()).first()
            if not existing:
                try:
                    db.session.add(Category(name=name))
                    db.session.commit()
                    flash('Category added.')
                except Exception:
                    db.session.rollback()
                    logger.exception("Failed to add category")
                    flash('Failed to add category.')
            else:
                flash('Category already exists.')
        else:
            flash('Category name cannot be empty.')
        return redirect(url_for('categories_view'))

    @app.route('/categories/<int:cat_id>/delete', methods=['POST'])
    def delete_category(cat_id):
        cat = Category.query.get_or_404(cat_id)
        try:
            for t in list(cat.transactions):
                t.category = None
            db.session.delete(cat)
            db.session.commit()
            flash('Category deleted.')
        except Exception:
            db.session.rollback()
            logger.exception("Failed to delete category")
            flash('Failed to delete category.')
        return redirect(url_for('categories_view'))

    # CLI helper
    @app.cli.command("init-db")
    def init_db():
        db.create_all()
        print("DB created")

    return app


# only create app when running directly
if __name__ == '__main__':
    app = create_app()
    with app.app_context():
        db.create_all()
    app.run(debug=True)