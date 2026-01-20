import pandas as pd
import json

# 1. Configuration
INPUT_CSV = "rag_eval_dataset.csv"
OUTPUT_JSONL = "rag_eval_data.jsonl"
SYSTEM_PROMPT = "You are a helpful financial assistant. Answer the user's question based on the provided documents."

def convert_csv_to_jsonl():
    # Load the CSV
    try:
        df = pd.read_csv(INPUT_CSV)
        print(f"✅ Loaded {len(df)} rows from {INPUT_CSV}")
    except FileNotFoundError:
        print(f"❌ Error: Could not find {INPUT_CSV}")
        return

    with open(OUTPUT_JSONL, 'w', encoding='utf-8') as f:
        for index, row in df.iterrows():
            question = row['Question']
            answer = row['Answer']

            # Skip empty rows
            if pd.isna(question) or pd.isna(answer):
                continue

            # Construct the JSON object (Standard OpenAI/Ollama Format)
            # This combines your "User" input and "Assistant" output into one conversation history
            data_object = {
                "messages": [
                    # Optional: Add a system prompt to guide behavior
                    {"role": "system", "content": SYSTEM_PROMPT},
                    
                    # Your CSV Question
                    {"role": "user", "content": str(question).strip()},
                    
                    # Your CSV Answer
                    {"role": "assistant", "content": str(answer).strip()}
                ]
            }

            # Write as a single line of JSON
            f.write(json.dumps(data_object, ensure_ascii=False) + "\n")

    print(f"🎉 Success! Converted data saved to: {OUTPUT_JSONL}")

if __name__ == "__main__":
    convert_csv_to_jsonl()