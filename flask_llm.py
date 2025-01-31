from flask import Flask, request, jsonify
from werkzeug.exceptions import BadRequest
from transformers import AutoTokenizer, AutoModelForCausalLM, pipeline, GenerationConfig
import torch
from langchain import HuggingFacePipeline

import warnings
warnings.filterwarnings("ignore")

app = Flask(__name__)
print(torch.cuda.is_available())
# MODEL_NAME = "TheBloke/Llama-2-13b-Chat-GPTQ"
MODEL_NAME = "meta-llama/Llama-2-7b-chat-hf"
with open(".llm-token") as f:
    AUTH_TOKEN = f.read()

try:
    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME, use_fast=True, token=AUTH_TOKEN)
    model = AutoModelForCausalLM.from_pretrained(
        MODEL_NAME,
        torch_dtype=torch.float16,
        trust_remote_code=True,
        device_map="auto",
        token=AUTH_TOKEN
    )
    generation_config = GenerationConfig.from_pretrained(MODEL_NAME)
    generation_config.max_new_tokens = 1024
    generation_config.temperature = 0.0001
    generation_config.top_p = 0.95
    generation_config.do_sample = True
    generation_config.repetition_penalty = 1.15

    text_pipeline = pipeline(
        "text-generation",
        model=model,
        tokenizer=tokenizer,
        return_full_text=True,
        generation_config=generation_config,
    )
    llm = HuggingFacePipeline(pipeline=text_pipeline, model_kwargs={"temperature": 0})
except Exception as e:
    print(f"Error loading model: {e}")
    llm = None

def process_prompt(data):
    if not data:
        return {"error": "No data provided."}

    table_header = "event_time,event_type,product_id,category_id,category_code,brand,price,user_id,user_session\n"
    table_rows = ""
    for event in data:
        row = "{event_time},{event_type},{product_id},{category_id},{category_code},{brand},{price},{user_id},<user_session_placeholder>\n".format(
            event_time=event.get("event_time", ""),
            event_type=event.get("event_type", ""),
            product_id=event.get("product_id", ""),
            category_id=event.get("category_id", ""),
            category_code=event.get("category_code", ""),
            brand=event.get("brand", ""),
            price=event.get("price", ""),
            user_id=event.get("user_id", ""),
        )
        table_rows += row

    prompt = (
        "Consider the following table of user events:\n\n"
        f"{table_header}{table_rows}\n"
        "Based on this data, suggest one product per user_id that they should probably buy, based on what other users are looking at, maybe using the brand or categories of items. Return response in following format for each user_id: \n"
        "For user_id {user_id}, I recommend going for this product: {product_id} from brand: {brand}. Replace the things in {} with the actual values."
        )

    try:
        result = llm(prompt)
        return {"suggestion": result}
    except Exception as e:
        return {"error": f"Error processing prompt: {e}"}

@app.route('/',methods = ["POST"])
def process_events():
    if llm is None:
        return jsonify({"error": "LLM is not initialized."}), 500

    try:
        jsondata = request.get_json(force=True)
        
        if not isinstance(jsondata, list):
            raise BadRequest("JSON data must be a list of event objects.")
        result = process_prompt(jsondata)
    
        if "error" in result:
            return jsonify(result), 400
        print(jsonify(result).get_json())
        return jsonify(result), 200

    except BadRequest as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": "An unexpected error occurred.", "details": str(e)}), 500


if __name__ == "__main__":
    app.run()