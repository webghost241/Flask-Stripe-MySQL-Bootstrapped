import json
import os
from datetime import timedelta

from flask import Flask, render_template, redirect, request, escape, jsonify, flash, current_app
from flask_login import LoginManager, UserMixin, login_required, login_user, logout_user, current_user
from flask_bcrypt import generate_password_hash, check_password_hash
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import exc
import stripe

# Upon importing, run backend/setup/__init__.py
from backend.setup import app, db, User, login_manager
stripe.api_key = app.config['STRIPE_SECRET_KEY']

@login_manager.user_loader
def load_user(id):
    return User.query.get(int(id))

@app.route("/")
def home():
    variables = dict(is_authenticated=current_user.is_authenticated)
    return render_template('index.html', **variables)

@app.route("/signup", methods=["POST"])
def signup():
    try:
        data = request.get_json(force=True)
        email = data['email']
        password = data['password']

        pw_hash = generate_password_hash(password, 10)

        new_user = User(email=email, password_hash=pw_hash)
        db.session.add(new_user)
        db.session.commit()

        return json.dumps({'message':'/login_page'}), 200
    except exc.IntegrityError as ex:
        db.session.rollback()
        return json.dumps({'message':'Email already in use, tried logging in?'}), 403
    except Exception as ex:
        return json.dumps({'message':'Something went wrong'}), 401
    
@app.route("/login_page")
def login_page():
    if current_user.is_authenticated:
        return redirect('/dashboard', code=302)
    return render_template('login_page.html')

@app.route("/login", methods=["POST"])
def login():
    data = request.get_json(force=True)
    email = data['email']
    password = data['password']
    user = User.query.filter_by(email=email).first()

    if user != None:
        check_pw = check_password_hash(user.password_hash, password)

        if user.email == email and check_pw:
            login_user(user, remember=True)
            return json.dumps({'message':'/dashboard'}), 200
    else:
        return json.dumps({'message':'User data incorrect'}), 401

@app.route("/dashboard")
@login_required
def dashboard():
    trial_period = timedelta(days=7)

    variables = dict(email=current_user.email,
                     expire_date=current_user.created_date + trial_period,
                     STRIPE_PUBLIC_KEY=app.config['STRIPE_PUBLIC_KEY'])

    return render_template('dashboard.html', **variables)

@app.route("/paynow", methods=["POST"])
#@login_required
def paynow():
    session = stripe.checkout.Session.create(
        customer_email=current_user.email,
        payment_method_types=['card'],
        subscription_data={
            'items': [{
                'plan': app.config['STRIPE_PLAN'],
            }],
        },
        success_url=app.config['BASE_URL'] + '/billing?session_id={CHECKOUT_SESSION_ID}',
        cancel_url=app.config['BASE_URL'] + '/billing',
    )

    print(session)

    variables = dict(CHECKOUT_SESSION_ID=session.id,
                     STRIPE_PUBLIC_KEY=app.config['STRIPE_PUBLIC_KEY'])

    return render_template('dashboard.html', **variables)

@app.route("/billing")
@login_required
def billing():
    variables = dict(subscription_active=current_user.is_subscribed,
                     email=current_user.email)
    return render_template('billing.html', **variables)

@app.route("/tos")
def terms_of_service():
    variables = dict(is_authenticated=current_user.is_authenticated)
    return render_template('terms_of_service.html', **variables)

@app.route("/logout")
def logout():
    current_user.is_authenticated = False
    logout_user()
    return redirect('/', code=302)
    
@app.errorhandler(401)
def not_logged_in(e):
    variables = dict(message='Please login first')
    
    return render_template('login_page.html', **variables)

@app.errorhandler(404)
def not_found(e):
    variables = dict(is_authenticated=current_user.is_authenticated,
                     message = '404 Page Not Found',
                     stacktrace = str(e))
    
    return render_template('error.html', **variables)

if __name__ == '__main__':
    app.run(host='0.0.0.0')