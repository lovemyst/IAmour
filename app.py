from flask import Flask, request, jsonify
from flask_cors import CORS
import openai
import os
import time
import stripe

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}}, supports_credentials=True)

# Clés d’environnement
openai.api_key = os.getenv("OPENAI_API_KEY")
ASSISTANT_ID_FREE = os.getenv("ASSISTANT_ID_FREE")
ASSISTANT_ID_PREMIUM = os.getenv("ASSISTANT_ID_PREMIUM")

stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
webhook_secret = os.getenv("STRIPE_WEBHOOK_SECRET")

@app.route('/')
def home():
    return "Bienvenue sur l’API IAmour !"

@app.route('/ask', methods=['POST'])
def ask():
    try:
        data = request.json
        message = data.get('message')
        is_premium = data.get('premium', False)

        assistant_id = ASSISTANT_ID_PREMIUM if is_premium else ASSISTANT_ID_FREE

        thread = openai.beta.threads.create()

        openai.beta.threads.messages.create(
            thread_id=thread.id,
            role="user",
            content=message
        )

        run = openai.beta.threads.runs.create(
            thread_id=thread.id,
            assistant_id=assistant_id
        )

        while True:
            run = openai.beta.threads.runs.retrieve(thread_id=thread.id, run_id=run.id)
            if run.status == "completed":
                break
            elif run.status == "failed":
                return jsonify({"error": "L'assistant a échoué à répondre."}), 500
            time.sleep(1)

        messages = openai.beta.threads.messages.list(thread_id=thread.id)
        latest_message = messages.data[0].content[0].text.value

        return jsonify({"response": latest_message})

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/webhook", methods=["POST"])
def stripe_webhook():
    payload = request.data
    sig_header = request.headers.get("stripe-signature")

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, webhook_secret
        )
    except stripe.error.SignatureVerificationError:
        return "Signature invalide", 400
    except Exception as e:
        print("Erreur Webhook :", e)
        return "Erreur Webhook", 400

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        print("Paiement reçu pour :", session.get("customer"))

    return "OK", 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
