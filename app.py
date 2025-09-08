import json
import os
import time
from flask import Flask, request, Response
from twilio.twiml.messaging_response import MessagingResponse
from langdetect import detect
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from groq import Groq

app = Flask(__name__)

#FAQs from JSON
with open("responses.json", "r", encoding="utf-8") as f:
    responses = json.load(f)

questions_list = list(responses.keys())
vectorizer = TfidfVectorizer().fit(questions_list)
question_vectors = vectorizer.transform(questions_list)

user_contexts = {}

client = Groq(api_key=os.getenv("GROQ_API_KEY"))

def query_groq(user_input, context="", lang="en"):
    health_context = (
        "You are a rural health assistant in India. "
        "STRICTLY follow these rules:\n"
        "1. Only answer health-related questions: fever, malaria, dengue, minor injuries, nutrition, waterborne diseases, etc.\n"
        "2. If the question is unrelated, reply exactly: "
        "'I am here to answer health-related questions only. Please ask about fever, malaria, dengue, or other health issues.'\n"
        "3. Respond in the SAME language as the user (Hindi if Hindi, English if English).\n"
        "4. Keep answers short, factual, and to the point. No unnecessary details or chit-chat.\n"
        f"5. Use this conversation context for follow-ups: {context}"
    )

    completion = client.chat.completions.create(
        model="llama3-8b-8192", 
        messages=[
            {"role": "system", "content": health_context},
            {"role": "user", "content": user_input},
        ],
        temperature=0.2,
        max_tokens=200,
    )

    return completion.choices[0].message.content.strip()


def get_semantic_match(user_input):
    input_vec = vectorizer.transform([user_input])
    similarities = cosine_similarity(input_vec, question_vectors).flatten()
    max_idx = similarities.argmax()
    if similarities[max_idx] > 0.6:  
        return questions_list[max_idx]
    return None


# webhook
@app.route("/webhook", methods=["POST"])
def webhook():
    incoming_msg = request.values.get("Body", "").strip()
    user_id = request.values.get("From", "default_user")  # phone number as ID

    
    try:
        lang_detected = detect(incoming_msg)
        lang = "hi" if lang_detected.startswith("hi") else "en"
    except:
        lang = "en"

    resp = MessagingResponse()
    msg = resp.message()
    incoming_lower = incoming_msg.lower()

    # Get previous context if exists (reset after 15 min)
    context = ""
    if user_id in user_contexts:
        last_time = user_contexts[user_id].get("last_update", 0)
        if time.time() - last_time < 900:  # 15 minutes
            context = f"Previous topic: {user_contexts[user_id].get('last_topic','')}"
        else:
            user_contexts.pop(user_id, None)

    found = False
    
    for question, answer in responses.items():
        if question.lower() == incoming_lower:
            msg.body(answer.get(lang, answer.get("en")))
            user_contexts[user_id] = {"last_topic": question, "last_update": time.time()}
            found = True
            break

    #Semantic match
    if not found:
        match_question = get_semantic_match(incoming_lower)
        if match_question:
            msg.body(responses[match_question].get(lang, responses[match_question].get("en")))
            user_contexts[user_id] = {"last_topic": match_question, "last_update": time.time()}
            found = True

    #Groq fallback
    if not found:
        dynamic_answer = query_groq(incoming_msg, context=context, lang=lang)
        msg.body(dynamic_answer)
        user_contexts[user_id] = {"last_topic": incoming_msg, "last_update": time.time()}

    return Response(str(resp), mimetype="application/xml")


if __name__ == "__main__":
    app.run(port=5000, debug=True)
