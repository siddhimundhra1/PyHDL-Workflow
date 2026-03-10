# rule_based_description_refinement.py
import os
import re
from model import ChatModel
from utils import parse_code_block, extract_module_header, run_design

description_refinement_rules = """
As a natural language understanding expert, you will be given a PyRTL Module Description. 
Your task is to clarify ambiguities or contradictions in the user-provided description, specifically addressing the following aspects:

1. Check for unclear or contradictory functionality in the overall module description.
   If issues exist, clarify the module's overall function. Remind the user to provide additional information when necessary.
2. Examine whether input/output signals are clearly described. 
   If unclear, infer and supplement their basic functionality along with relevant input/output examples.
3. Verify if initialization information is missing. 
   If missing, you should add information about all register-type variables (pyrtl.Register) that must be explicitly initialized to 0.

Note present the final optimized module description enclosed within [refined descritption begin]: [end].
Note the final output must be a natural language design description (not code).
"""


programming_rules_suffix = """
Here are the PyRTL design rules you must follow:
- The design must be implemented as: def TopModule(...):
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
    As a PyRTL programming expert, you need to complete PyRTL code based on user's prompt.
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
    llm = ChatModel(model_name="Qwen/Qwen2.5-Coder-32B-Instruct", temperature=0.1, local=False)

    task_prompt = """
    You only complete chats with syntax correct PyRTL code. 
    The top-level function must be named TopModule. 
    Do not include input and output definitions.
    """

    input_path = "./input"

    llm = ChatModel(model_name="Qwen/Qwen2.5-Coder-32B-Instruct", temperature=0.1, local=False)

    with open(f"{input_path}/description.txt", "r", encoding='utf-8', errors='ignore') as file:
        description = file.read()

    with open(f"{input_path}/ref.sv", "r", encoding='utf-8', errors='ignore') as file:
        ref = file.read()

    with open(f"{input_path}/testbench.sv", "r", encoding='utf-8', errors='ignore') as file:
        testbench = file.read()

    #corrected_design, example_prompt = rule_based_description_refinement(llm, description)

    #with open(f"{input_path}/design.sv", "w", encoding='utf-8', errors='ignore') as file:
     #   file.write(design)
    design, refined_description =  rule_based_description_refinement(llm, description, task_prompt)

    print(design)
    print(refined_description)
    #print(corrected_design)
    #print(meta_format)