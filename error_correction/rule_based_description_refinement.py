# rule_based_description_refinement.py
import os
import re
from model import ChatModel
from utils import parse_code_block, run_design

description_refinement_rules = """
As a PyRTL hardware-design understanding expert, you will be given a natural language module description.
Your task is to clarify ambiguities, missing assumptions, or contradictions in the user-provided description
so it can be implemented correctly in PyRTL.

Focus on the following:

1. Clarify the module's overall behavior.
   - Check whether the design is combinational, sequential, or memory-backed.
   - If the description mixes current-cycle and next-cycle behavior, rewrite it clearly using PyRTL semantics:
     combinational values are built from WireVectors, while sequential state must be modeled with Registers
     whose next values are assigned through reg.next.
   - If the behavior is still underspecified, explicitly note what is missing and state the most reasonable assumption.

2. Clarify all interfaces in PyRTL terms.
   - Identify which signals should be pyrtl.Input, pyrtl.Output, internal pyrtl.WireVector values,
     pyrtl.Register state, and pyrtl.MemBlock / pyrtl.RomBlock objects when memories are implied.
   - For each input and output, infer and supplement:
       * purpose
       * bitwidth
       * whether it is data, control, address, enable, or status
       * whether it is used combinationally or sampled across cycles
   - Include simple input/output examples when useful.

3. Clarify timing and state-update behavior.
   - If the module contains state, explicitly describe:
       * what state is stored
       * when it updates
       * what value is visible in the current cycle
       * what value is written for the next cycle
   - If reset or startup behavior is missing, add it explicitly for all Register-based state.

4. Clarify initialization and default behavior in PyRTL form.
   - Do not refer to Verilog-style "output reg" initialization.
   - Instead, specify initialization for all Registers using reset_value semantics.
   - If memories are present, describe their intended initial contents and any assumptions about read/write behavior.
   - If conditional behavior is described incompletely, state the intended default/fallthrough behavior explicitly.

5. Clarify width, signedness, and indexing assumptions.
   - If bitwidths are missing, infer the smallest sensible widths and state them explicitly.
   - If signed arithmetic or signed comparison is intended, say so explicitly instead of assuming default arithmetic.
   - If bit extraction or slicing is mentioned, restate the exact bit positions and direction clearly.

6. Clarify conditional logic in PyRTL form.
   - If the description implies hardware conditions, rewrite them as hardware predicates suitable for
     pyrtl.conditional_assignment or pyrtl.select, not Python control flow.
   - Make all mutually exclusive and fallthrough cases explicit.

Note: present the final optimized module description enclosed within
[refined description begin]:
[end]

Note: the final output must be a natural language design description for PyRTL, not code.
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
- Do NOT explicitly define clock signals, they are implicit.
- Do not use "don't care" terms like z and x.

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

    interface_note = """
    PyRTL interface requirements:
    - The top-level function must be named TopModule.
    - The function arguments must match the described input ports.
    - The returned values must match the described output ports.
    """

    system_prompt = f"""
    As a PyRTL programming expert, you need to complete PyRTL code based on user's prompt.
    {task_prompt}

    When writing PyRTL designs, you need to adhere to the following rules:
    {programming_rules_suffix}
    """

    user_prompt = f"""
    {refined_description}
    {interface_note}
    """

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt}
    ]

    response = llm.generate(messages)
    module_block = parse_code_block(response, "python")

    design = module_block.strip()

    return design, refined_description


if __name__ == "__main__":
    llm = ChatModel(model_name="gemini-3-flash-preview", temperature=0.1, local=False)

    task_prompt = """
    You only complete chats with syntax correct PyRTL code. 
    The top-level function must be named TopModule. 
    Do not include input and output definitions.
    """

    input_path = "./input"

    llm = ChatModel(model_name="gemini-3-flash-preview", temperature=0.1, local=False)

    with open(f"{input_path}/description.txt", "r", encoding='utf-8', errors='ignore') as file:
        description = file.read()

    with open(f"{input_path}/ref.py", "r", encoding='utf-8', errors='ignore') as file:
        ref = file.read()

    with open(f"{input_path}/testbench.py", "r", encoding='utf-8', errors='ignore') as file:
        testbench = file.read()

    design, refined_description = rule_based_description_refinement(
        llm, description, task_prompt
    )

    with open(f"{input_path}/design.py", "w", encoding='utf-8', errors='ignore') as file:
        file.write(design)

    print(design)
    print(refined_description)
    #print(corrected_design)
    #print(meta_format)
