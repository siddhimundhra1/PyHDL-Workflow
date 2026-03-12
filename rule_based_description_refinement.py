# rule_based_description_refinement.py
import os
import re
from model import ChatModel
from utils import parse_code_block, extract_module_header, run_design

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
Here are some additional PyRTL rules and coding conventions.

- Use the correct PyRTL object for each role:
  pyrtl.Input for external inputs,
  pyrtl.Output for external outputs,
  pyrtl.WireVector for internal combinational signals,
  pyrtl.Register for sequential state,
  pyrtl.MemBlock / pyrtl.RomBlock for memories.

- Do not use Python '=' when you mean a hardware connection.
  Use '<<=' to drive an existing wire/output, and use 'reg.next <<=' to assign a register's next-state value.

- Never assign directly to a pyrtl.Input.
  Inputs are placeholders for externally provided values.

- Do not use a pyrtl.Output as a source operand in other logic.
  Compute with internal wires/registers first, then drive the Output from that result.

- For sequential logic, assign only to 'reg.next', not to the Register object itself.

- Use '|=' only inside 'with pyrtl.conditional_assignment:' blocks.
  Outside conditional_assignment, use '<<='.

- Inside conditional_assignment, remember that:
  * wires default to 0 if not assigned in some case,
  * registers default to holding their current value,
  * memories default to "no write" when not enabled.
  Make these defaults explicit in the design when clarity matters.

- Do not use Python control flow or Python boolean operators on hardware values.
  Comparisons such as 'a == b' return a 1-bit WireVector, not a Python bool.
  Do not use WireVectors in Python 'if', 'while', 'and', 'or', 'not', or 'in' tests.
  Use pyrtl.select(...) or pyrtl.conditional_assignment for hardware-dependent behavior.

- Be explicit about bitwidths for all top-level signals, registers, and memories.
  If bitwidth is omitted for a temporary WireVector, it may be inferred later, but do not rely on inference
  when the intended width matters.

- When operand widths differ, PyRTL commonly zero-extends the narrower operand to match the wider one.
  Do not rely on accidental width matching for signed behavior.

- PyRTL arithmetic and comparisons are unsigned by default.
  If signed behavior is intended, state it explicitly and use signed operations / sign extension as needed.

- When truncation or width adaptation is required, use explicit operations such as:
  .truncate(bitwidth),
  .zero_extended(bitwidth),
  .sign_extended(bitwidth),
  or match_bitwidth(...),
  rather than leaving width resolution ambiguous.

- When indexing or slicing a vector, remember:
  * bit 0 is the least significant bit,
  * bit -1 is the most significant bit,
  * slices follow Python [start:stop:step] semantics.
  Ensure all indices and slice bounds stay within the declared bitwidth.

- Register state resets to 0 by default unless reset_value is specified.
  If startup behavior matters, specify reset_value explicitly for every Register.

- MemBlocks are synchronous by default.
  For normal synthesizable synchronous memory usage, keep memory address/data/write-enable sources as
  Registers, Inputs, or Consts unless asynchronous=True is intentionally required.

- Reads and writes each create memory ports.
  Avoid generating unnecessary read/write ports.

- In simulation, MemBlocks are zero-initialized by default unless overridden.
  If the same address is read and written in the same cycle, the read returns the old stored value,
  not the newly written value.
  If a different behavior is desired, the design description must say so explicitly.

- Use unique, stable names for important signals and state when inspection, tracing, or debugging matters.
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