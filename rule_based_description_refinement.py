import os
import re
from model import ChatModel
from utils import parse_code_block, extract_module_header, run_design

description_refinement_rules = """
As a hardware design expert working with PyRTL (a Python-based HDL),
you will be given a hardware module description.

Your task is to clarify ambiguities or contradictions in the user-provided
description, specifically addressing the following aspects:

1. Clarify overall circuit functionality if ambiguous.
2. Ensure all inputs and outputs are clearly described with bitwidth.
3. Explicitly specify which signals are sequential (require Register)
   and which are combinational.
4. If initialization behavior is required, specify that all Registers
   must use reset_value=0.

Present the final optimized module description enclosed within:
[refined description begin]: ... [end]

The final output must be a natural language design description (not code).
"""

programming_rules_suffix = """
Here are the PyRTL design rules you must follow:

- The design must be implemented as:

    def TopModule(...):

- All inputs must be passed as function arguments.
- All outputs must be explicitly returned.

- Use WireVector(bitwidth) for combinational signals.
- Use Register(bitwidth, reset_value=0) for sequential signals.
- Always use <<= for hardware connections.
- Do NOT use '=' to assign hardware values.
- All wires and registers must have explicit bitwidth.
- Do not mix Python integers directly with WireVectors without proper bitwidth handling.
- The function must build hardware and return output WireVector(s).
- Do not include testbench or simulation code.
- Do not call pyrtl.Simulation().
"""

def rule_based_description_refinement(llm: ChatModel, description: str, task_prompt: str):
    messages = [
        {"role": "system", "content": description_refinement_rules},
        {"role": "user", "content": description}
    ]
    
    response = llm.generate(messages)
    pattern = r'\[refined description begin\]:(.*?)\[end\]'
    match = re.search(pattern, response, re.DOTALL)
    refined_description = ""
    
    if match:
        refined_description = match.group(1).strip()
    else:
        refined_description = description
    
    module_header = extract_module_header(description)

    system_prompt = f"""
    As a PyRTL (Python Hardware Description Language) programming expert, you need to complete PyRTL code based on user's prompt.
    {task_prompt}
    
    When writing PyRTL designs, you need to adhere to the following rules:
    {programming_rules_suffix}
    """

    user_prompt = f"""
    {refined_description}
    {module_header}
    """
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt}
    ]
    
    response = llm.generate(messages)
    module_block = parse_code_block(response, "python")

    design = module_header + module_block

    return design, refined_description

if __name__ == "__main__":
    llm = ChatModel(model_name = "/public/Qwen2.5-Coder-32B-Instruct", temperature = 0.1, local = True)
    
    task_prompt = """
    You only complete chats with syntax correct PyRTL code. 
    The top-level function must be named TopModule.
    Do not include extra explanations.
    Only output Python code.
    """
    input_path = "./input"
    llm = ChatModel(model_name = "/public/Qwen2.5-Coder-32B-Instruct", temperature = 0.1, local = True)
    
    with open(f"{input_path}/description.txt", "r", encoding = 'utf-8', errors = 'ignore') as file: description = file.read()
    with open(f"{input_path}/ref.sv", "r", encoding = 'utf-8', errors = 'ignore') as file: ref = file.read()
    with open(f"{input_path}/testbench.sv", "r", encoding = 'utf-8', errors = 'ignore') as file: testbench = file.read()
    corrected_design, example_prompt = rag_based_knowledge_error_mitigation(llm, description)
    
    with open(f"{input_path}/design.sv", "w", encoding = 'utf-8', errors = 'ignore') as file: file.write(design)
    print(corrected_design)
    print(meta_format)
