from flask import Flask, request, jsonify
import os
import openai
import time

app = Flask(__name__)

openai.api_key = os.environ.get("OPENAI_API_KEY")

@app.route('/chat', methods=['POST'])
def chat():
    data = request.get_json()
    user_message = data.get("message")
    is_premium = data.get("isPremium", False)

    assistant_id = os.environ.get("ASSISTANT_ID_PREMIUM") if is_premium else os.environ.get("ASSISTANT_ID_FREE")

    try:
        # Crée un thread
        thread = openai.beta.threads.create()

        # Envoie le message de l'utilisateur
        openai.beta.threads.messages.create(
            thread_id=thread.id,
            role="user",
            content=user_message
        )

        # Lance l’assistant
        run = openai.beta.threads.runs.create(
            thread_id=thread.id,
            assistant_id=assistant_id
        )

        # Attend la fin de l’exécution
        while True:
            run_status = openai.beta.threads.runs.retrieve(thread_id=thread.id, run_id=run.id)
            if run_status.status == "completed":
                break
            time.sleep(1)

        # Récupère la réponse
        messages = openai.beta.threads.messages.list(thread_id=thread.id)
        reply = messages.data[0].content[0].text.value

        return jsonify({"reply": reply})

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/')
def index():
    return "IAmour est en ligne !"
