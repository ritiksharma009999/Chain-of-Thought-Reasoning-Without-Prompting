import torch
from transformers import AutoModelForCausalLM, AutoTokenizer
from typing import List, Tuple
from tqdm import tqdm
from huggingface_hub import login
import os  # Add this import

# Authentication
HF_TOKEN = os.getenv("HF_TOKEN")  # Use environment variable instead
login(token=HF_TOKEN)

def load_model_and_tokenizer():
    """Load an open source model"""
    model_name = "TinyLlama/TinyLlama-1.1B-Chat-v1.0"
    
    tokenizer = AutoTokenizer.from_pretrained(model_name, trust_remote_code=True)
    model = AutoModelForCausalLM.from_pretrained(
        model_name,
        device_map="cpu",
        torch_dtype=torch.float16,
        low_cpu_mem_usage=True
    )
    
    return model, tokenizer

def format_cot_prompt(prompt: str) -> str:
    """Format prompt to encourage step-by-step reasoning"""
    return f"""<s>[INST] Let's solve this step by step:

{prompt}

Please show your work by:
1. Identifying the key information
2. Breaking down the calculation steps
3. Computing the final answer
[/INST]"""

def score_response(model, tokenizer, response: str) -> float:
    """Calculate a simple likelihood score for the response"""
    with torch.no_grad():
        inputs = tokenizer(response, return_tensors="pt")
        outputs = model(**inputs)
        # Calculate mean log probability across all tokens
        mean_log_prob = outputs.logits.mean().item()
        return mean_log_prob

def generate_branching_responses(
    model,
    tokenizer,
    prompt: str,
    num_branches: int = 5,
    max_length: int = 512,  # Increased for step-by-step reasoning
    temperature: float = 0.8,  # Slightly increased for more diverse responses
    top_k: int = 50,
    top_p: float = 0.9
) -> Tuple[List[str], List[float]]:
    """Generate multiple response paths using top-k sampling"""
    # Format prompt for chain of thought reasoning
    formatted_prompt = format_cot_prompt(prompt)
    
    # Tokenize input prompt
    inputs = tokenizer(formatted_prompt, return_tensors="pt")
    
    responses = []
    response_scores = []
    
    print("\nGenerating responses...")
    for i in tqdm(range(num_branches)):
        with torch.no_grad():
            outputs = model.generate(
                **inputs,
                max_length=max_length,
                do_sample=True,
                temperature=temperature,
                top_k=top_k,
                top_p=top_p,
                pad_token_id=tokenizer.eos_token_id,
                return_dict_in_generate=True
            )
            
            # Decode response
            response = tokenizer.batch_decode(outputs.sequences, skip_special_tokens=False)[0]
            
            # Score response
            score = score_response(model, tokenizer, response)
            
            responses.append(response)
            response_scores.append(score)
            
            # Clean up memory
            torch.cuda.empty_cache()
    
    return responses, response_scores

prompts = [
    "A restaurant needs to prepare meals for a large group. They need to cook 45 servings of pasta, and each serving requires 125 grams of pasta. How many kilograms of pasta do they need in total?",
    "If a car travels at 60 kilometers per hour for 2.5 hours, then increases its speed to 75 kilometers per hour for the next 1.5 hours, what is the total distance traveled?",
    "A store is offering a 15 percent discount on a laptop that originally costs $800. If the sales tax is 8%, what is the final price after both the discount and tax are applied?"
]

try:
    print("Loading model and tokenizer...")
    model, tokenizer = load_model_and_tokenizer()
    
    for i, prompt in enumerate(prompts, 1):
        print(f"\nProcessing prompt {i}/{len(prompts)}: {prompt[:50]}...")
        responses, scores = generate_branching_responses(model, tokenizer, prompt)
        
        print(f'\nResults for prompt {i}:')
        print('Prompt:', prompt, '\n')
        
        # Sort responses by score and show only the top 3
        sorted_responses = sorted(zip(responses, scores), key=lambda x: x[1], reverse=True)[:3]
        
        for k, (response, score) in enumerate(sorted_responses, 1):
            print(f'Top Response {k}:\n')
            # Extract only the model's response part
            response_text = response.split('[/INST]')[1].strip()
            # Clean up any trailing tokens
            response_text = response_text.split('</s>')[0].strip()
            print(response_text)
            print(f'\nConfidence Score: {score:.4f}\n')
            print("-" * 40 + "\n")
        
        print("=" * 80)
        
except Exception as e:
    print(f"An error occurred: {str(e)}")
    import traceback
    traceback.print_exc()
    
finally:
    if 'model' in locals():
        del model
    if 'tokenizer' in locals():
        del tokenizer
    torch.cuda.empty_cache()