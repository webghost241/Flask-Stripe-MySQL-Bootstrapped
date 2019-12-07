import json
from datetime import datetime

from flask import Flask, Blueprint, request
from flask_login import login_required, current_user
import stripe

from backend.setup import app, db, User, login_manager, csrf

# Every route from here will be imported to app.py through the stripe_api Blueprint
stripe_api = Blueprint('stripe_api', __name__)
stripe.api_key = app.config['STRIPE_SECRET_KEY']

@stripe_api.route("/setup_payment", methods=["POST"])
@login_required
def setup_payment():
    try:
        # Get the data from AJAX request
        data = request.get_json(force=True)
        plan = app.config['STRIPE_PLAN_' + data['plan']]

        # Setup a Stripe session, completed with a webhook
        session = stripe.checkout.Session.create(
            customer_email=current_user.email,
            payment_method_types=['card'],
            subscription_data={
                'items': [{
                    'plan': plan,
                }],
            },
            success_url=app.config['BASE_URL'] + '/billing',
            cancel_url=app.config['BASE_URL'] +'/dashboard',
        )

        variables = dict(stripe_public_key=app.config['STRIPE_PUBLIC_KEY'],
                         session_id=session.id)

        return json.dumps(variables), 200
    except Exception as ex:
        return json.dumps({'message':'Something went wrong'}), 401
    
    
@stripe_api.route("/webhook_pay_success", methods=["POST"])
@csrf.exempt
def succesful_payment():
    # Upon successful payment, Stripe sends data. Capture payload.
    payload = request.data.decode("utf-8")
    received_sig = request.headers.get("Stripe-Signature", None)

    # Verify received data
    try:
        with app.app_context():
            event = stripe.Webhook.construct_event(
                payload, received_sig, app.config['ENDPOINT_SECRET']
            )
    except ValueError:
        print("Error while decoding event!")
        return "Bad payload", 400
    except stripe.error.SignatureVerificationError:
        print("Invalid signature!")
        return "Bad signature", 400

    # Make user a paid subscriber
    data = json.loads(payload)
    if data['type'] == 'checkout.session.completed':
        data_object = data['data']['object']
        user = User.query.filter_by(email=data_object['customer_email']).first()

        if user != None:
            user.subscription_active = True
            user.subscription_id = data_object['subscription']
            user.customer_id = data_object['customer']
            db.session.commit()

    return "", 200

@stripe_api.route("/cancel_subscription", methods=["PUT"])
@login_required
def cancel_subscription():
    try:
        session = stripe.Subscription.modify(
            current_user.subscription_id,
            cancel_at_period_end=True
        )

        timestamp = session['cancel_at']
        subscription_ends = datetime.utcfromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M:%S')
        current_user.subscription_cancelled_at = int(timestamp)
        db.session.commit()

        variables = dict(message='Success. You unsubscribed and will not be billed anymore. Your subscription will last until' + subscription_ends)

        return json.dumps(variables), 200
    except Exception as ex:
        print(ex)
        return json.dumps({'message':'Something went wrong'}), 401

@stripe_api.route("/reactivate_subscription", methods=["PUT"])
@login_required
def reactivate_subscription():
    try:
        session = stripe.Subscription.modify(
            current_user.subscription_id,
            cancel_at_period_end=False
        )

        current_user.subscription_cancelled_at = None
        db.session.commit()

        variables = dict(message='Success. You will automatically be billed every month.')

        return json.dumps(variables), 200
    except Exception as ex:
        return json.dumps({'message':'Something went wrong'}), 401
    