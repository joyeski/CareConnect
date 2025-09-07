import json
import requests
from flask import Flask, request, Response
from twilio.twiml.messaging_response import MessagingResponse
from langdetect import detect
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import time

app = Flask(__name__)

# 🔹 Load FAQs from JSON
with open("responses.json", "r", encoding="utf-8") as f:
    responses = json.load(f)

# 🔹 Prepare semantic search
questions_list = list(responses.keys())
vectorizer = TfidfVectorizer().fit(questions_list)
question_vectors = vectorizer.transform(questions_list)

# 🔹 User context dictionary (in-memory)
# Stores: {user_id: {"last_topic": "dengue", "last_update": timestamp}}
user_contexts = {}

# 🔹 Hard-prompted Ollama query
def query_ollama(user_input, context="", lang="en"):
    try:
        health_context = (
            "You are a rural health assistant in India. Your users are mostly non-technical and may speak Hindi or simple English. "
            "Always respond directly in the language the user writes in. "
            "Keep answers short, simple, and factual. "
            "Only respond to health-related queries: fever, malaria, dengue, minor injuries, waterborne diseases, nutrition, and general health advice. "
            "Do NOT give any general, unrelated, or unnecessary answers. "
            "Do NOT translate unnecessarily. If the user writes in Hindi, answer in Hindi directly. "
            "If a query is unrelated to health, reply politely: 'I am here to answer health-related questions only. Please ask about fever, malaria, dengue, or other health issues.' "
            "Use the following conversation context to answer follow-up questions: "
            f"{context}"
        )

        response = requests.post(
            "http://127.0.0.1:11434/api/generate",
            json={
                "model": "tinyllama",
                "prompt": f"{health_context}\n\nUser: {user_input}\nAssistant:",
            },
            stream=True
        )

        if response.status_code == 200:
            full_reply = ""
            for line in response.iter_lines():
                if line:
                    try:
                        data = json.loads(line.decode("utf-8"))
                        if "response" in data:
                            full_reply += data["response"]
                    except Exception as e:
                        print("JSON parse error:", e, line)
            return full_reply.strip() if full_reply else "माफ़ कीजिए, मुझे समझ नहीं आया।"
        else:
            return f"Ollama API error: {response.text}"
    except Exception as e:
        print("Ollama request failed:", e)
        return "Sorry, I couldn’t connect to the AI engine."

# 🔹 Semantic search
def get_semantic_match(user_input):
    input_vec = vectorizer.transform([user_input])
    similarities = cosine_similarity(input_vec, question_vectors).flatten()
    max_idx = similarities.argmax()
    if similarities[max_idx] > 0.6:  # threshold
        return questions_list[max_idx]
    return None

# 🔹 Flask webhook
@app.route("/webhook", methods=["POST"])
def webhook():
    incoming_msg = request.values.get("Body", "").strip()
    user_id = request.values.get("From", "default_user")  # use phone number as ID

    # 🔹 Detect language
    try:
        lang_detected = detect(incoming_msg)
        lang = "hi" if lang_detected.startswith("hi") else "en"
    except:
        lang = "en"

    resp = MessagingResponse()
    msg = resp.message()
    incoming_lower = incoming_msg.lower()

    # 🔹 Get previous context if exists (reset after 15 min)
    context = ""
    if user_id in user_contexts:
        last_time = user_contexts[user_id].get("last_update", 0)
        if time.time() - last_time < 900:  # 15 minutes
            context = f"Previous topic: {user_contexts[user_id].get('last_topic','')}"
        else:
            user_contexts.pop(user_id, None)

    found = False

    # 🔹 Exact match in JSON
    for question, answer in responses.items():
        if question.lower() == incoming_lower:
            msg.body(answer.get(lang, answer.get("en")))
            # Update context
            user_contexts[user_id] = {"last_topic": question, "last_update": time.time()}
            found = True
            break

    # 🔹 Semantic match
    if not found:
        match_question = get_semantic_match(incoming_lower)
        if match_question:
            msg.body(responses[match_question].get(lang, responses[match_question].get("en")))
            # Update context
            user_contexts[user_id] = {"last_topic": match_question, "last_update": time.time()}
            found = True

    # 🔹 Ollama fallback with context
    if not found:
        dynamic_answer = query_ollama(incoming_msg, context=context, lang=lang)
        msg.body(dynamic_answer)
        # Update context with last Ollama answer as topic
        user_contexts[user_id] = {"last_topic": dynamic_answer[:50], "last_update": time.time()}

    return Response(str(resp), mimetype="application/xml")

if __name__ == "__main__":
    app.run(port=5000, debug=True)
