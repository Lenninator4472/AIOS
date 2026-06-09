from kernel.llm import get_provider, extract_json
import time

def benchmark_llm():
    llm = get_provider(model="llama3.2:1b")
    system_prompt = "You are a helpful AI assistant."
    user_input = "Explain the concept of an operating system in one sentence."
    history = []
    
    start_time = time.time()
    response = llm.query(system_prompt, user_input, history)
    end_time = time.time()
    
    print(f"LLM Response Time: {end_time - start_time:.2f}s")
    print(f"Response: {response[:100]}...")

if __name__ == "__main__":
    benchmark_llm()
