from flask import Flask, request, jsonify
from flask_cors import CORS
import openai
import os
import time

app = Flask(__name__)
CORS(app)

# Config
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ASSISTANT_ID_FREE = os.getenv("ASSISTANT_ID_FREE")
ASSISTANT_ID_PREMIUM = os.getenv("ASSISTANT_ID_PREMIUM")
SYSTEM_PROMPT_PREMIUM = os.getenv("SYSTEM_PROMPT_PREMIUM")

client = openai.OpenAI(api_key=OPENAI_API_KEY)

# Threads simulés pour tests
user_threads = {}

@app.route('/chat', methods=['POST'])
def chat():
    data = request.get_json()
    user_message = data.get("message")
    user_id = data.get("user_id")

    if not user_id or not user_message:
        return jsonify({"error": "user_id and message are required"}), 400

    # ⚡ Forçage pour tests Lovable (ajuste cette liste si besoin)
    PREMIUM_USER_IDS = ["anonymous_user", "test_admin", "user_1747692922028"]
    is_premium = user_id in PREMIUM_USER_IDS

    assistant_id = ASSISTANT_ID_PREMIUM if is_premium else ASSISTANT_ID_FREE
    system_prompt = SYSTEM_PROMPT_PREMIUM

    print("👤 USER_ID reçu :", user_id)
    print("✨ Premium activé ?", is_premium)
    print("🧠 Assistant utilisé :", assistant_id)

    # Thread en mémoire
    if user_id in user_threads:
        thread_id = user_threads[user_id]
    else:
        thread = client.beta.threads.create()
        thread_id = thread.id
        user_threads[user_id] = thread_id

        # Prompt injecté au début
        client.beta.threads.messages.create(
            thread_id=thread_id,
            role="user",
            content=f"[STYLE IAmour ACTIVÉ]\n{system_prompt}"
        )

    client.beta.threads.messages.create(
        thread_id=thread_id,
        role="user",
        content=user_message
    )

    run = client.beta.threads.runs.create(
        thread_id=thread_id,
        assistant_id=assistant_id
    )

    max_attempts = 30
    attempts = 0
    while attempts < max_attempts:
        run_status = client.beta.threads.runs.retrieve(thread_id=thread_id, run_id=run.id)
        if run_status.status == "completed":
            break
        elif run_status.status == "failed":
            return jsonify({"error": "L'assistant a échoué."}), 500
        time.sleep(1)
        attempts += 1

    if attempts == max_attempts:
        return jsonify({"error": "Temps d’attente dépassé."}), 504

    messages = client.beta.threads.messages.list(thread_id=thread_id)
    last_message = messages.data[0].content[0].text.value

    print("💬 Réponse brute :", last_message)

    return jsonify({"response": last_message})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
